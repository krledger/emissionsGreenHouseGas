"""Canonical emissions table.

One granular monthly row per emission and per physical measure, carrying
enough provenance to trace any reported figure back to the quantity, the
factor and the source it came from.

    Scope 1 and Scope 2   from the aggregated physicals, charged against the
                          NGA factor the line resolves to
    Scope 3               from the Scope 3 build, all fifteen categories
    Physicals             production and metric lines that carry no factor:
                          ore, gold, drilling and the rest, which are the
                          denominators every intensity is read against

This module calculates nothing.  Every figure in the table has already been
computed by CalcNga or CalcGhgCategories; what happens here is a projection of
those results into one shape, so there is one emissions source of truth and
not one per view.  If a number in this table disagrees with the engine that
produced it, this module is wrong.

Actual and forecast are separated on every row rather than inferred from the
date, so a reader never has to know where the record stops to know whether a
figure is one.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import numpy as np
import pandas as pd

from CalcNga import dedupe_actual_over_budget, resolve_factor_key
from CalcUnits import KG_PER_TONNE_CO2E
from Config import (FACTOR_SET_NGA, canonical_factor_source,
                    factor_derivation, factor_is_regulated, factor_set)

__all__ = [
    'COLUMNS', 'build_emissions_table', 'build_id_for',
    'reconcile', 'monthly_pivot',
]


# ---------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------
# Ordered so a reader scans left to right from "when and what" through
# "how much" to "on what authority".

COLUMNS = [
    # When
    'Date', 'FinancialYear', 'CalendarYear',
    # What kind of row, and on what basis
    'Dataset', 'RowKind', 'IsForecast', 'IsEstimated',
    # Where it came from in the business
    'Activity', 'SubActivity', 'Department', 'CostCentre',
    'Identifier', 'Description',
    # The physical measure
    'Quantity', 'UOM', 'SpendAUD',
    # The emission
    'GHGScope', 'Scope3Category', 'Scope3CategoryName',
    'EmissionSource', 'EmissionFactor', 'FactorUOM', 'FactorSet',
    'FactorSource', 'FactorDerivation', 'FactorRegulated', 'FactorYear',
    'Emissions_tCO2e', 'Energy_GJ',
    # How it was arrived at
    'CalculationMethod', 'ActivityDataSource', 'DateBasis', 'DataQuality',
    # Which framework it counts towards
    'NGERApplicable', 'SafeguardApplicable', 'GRIApplicable',
    # Provenance of the build itself
    'BuildID', 'Notes',
]

# A physical line carries a measure and no factor.  It is in the table
# because every intensity needs a denominator and a denominator that lives
# somewhere else is a denominator that drifts.
# What a null looks like once something has cast it to text.
_NULL_WORDS = frozenset(['nan', 'NaN', 'NAN', 'none', 'None',
                         'NONE', '<NA>', '<na>', 'NaT', 'nat'])

PHYSICAL_ROW_TYPES = ('production', 'total', 'metric')

SCOPE3_NAMES = {
    1: 'Purchased goods and services',
    2: 'Capital goods',
    3: 'Fuel- and energy-related activities',
    4: 'Upstream transportation and distribution',
    5: 'Waste generated in operations',
    6: 'Business travel',
    7: 'Employee commuting',
    8: 'Upstream leased assets',
    9: 'Downstream transportation and distribution',
    10: 'Processing of sold products',
    11: 'Use of sold products',
    12: 'End-of-life treatment of sold products',
    13: 'Downstream leased assets',
    14: 'Franchises',
    15: 'Investments',
}


def _dataset_label(series, dates=None, actual_to=None):
    """Actual stays Actual; anything budgeted is a forecast and says so.

    Categories 6 and 7 are modelled across the whole plan rather than taken
    from transactions, so they arrive on neither the actual nor the budget
    dataset.  A modelled line falling in a month that has already happened
    belongs to the record: it is an estimate of what occurred, not a
    projection of what will.  Labelling it a forecast would leave an Actual
    filter reporting less than the period actually produced.
    """
    text = series.astype(str).str.lower()
    label = np.where(text == 'actual', 'Actual', 'Forecast')
    if dates is None or actual_to is None:
        return label
    modelled = ~text.isin(['actual', 'budget'])
    within = pd.to_datetime(dates) <= pd.Timestamp(actual_to)
    return np.where(modelled & within, 'Actual', label)


def build_id_for(*parts):
    """A short, stable identifier for one build.

    Derived from the inputs rather than from the clock, so the same inputs
    give the same identifier and a build can be shown to be a rebuild rather
    than a change.
    """
    digest = hashlib.sha256('|'.join(str(p) for p in parts).encode()).hexdigest()
    return digest[:12]


# ---------------------------------------------------------------------
# SCOPE 1 AND SCOPE 2, FROM THE PHYSICALS
# ---------------------------------------------------------------------

def _factor_lookup(agg_df, year_factor_map):
    """Factor, unit and NGA vintage for each (fuel, year) pair in the frame.

    Built once per distinct pair rather than per row, and resolved through
    the same matcher the emissions engine uses, so the table reports the
    factor that was actually applied and not one re-derived from the answer.
    """
    pairs = agg_df[['NGAFuel', 'FY']].drop_duplicates()
    out = {}
    for nga_fuel, fy in zip(pairs['NGAFuel'].astype(str), pairs['FY']):
        year_factors = year_factor_map.get(fy) or {}
        key = resolve_factor_key(nga_fuel, year_factors)
        record = year_factors.get(key) if key else None
        out[(nga_fuel, fy)] = {
            'key': key or '',
            's1': (record or {}).get('s1', 0.0),
            's2': (record or {}).get('s2', 0.0),
            'uom': (record or {}).get('expected_uom', ''),
            # A factor from outside the National Greenhouse Accounts names
            # its own publication and edition on its record.
            'source': (record or {}).get('factor_source', FACTOR_SET_NGA),
            'nga_year': (record or {}).get('factor_year',
                                           year_factors.get('_nga_year', '')),
        }
    return out


def _scope12_rows(agg_df, year_factor_map, build_id, actual_to=None):
    """One row per line per scope it actually produces.

    A fuel line produces Scope 1 and no Scope 2; an electricity line the
    reverse.  The physical quantity is carried on that one row, so summing
    Quantity over the table counts each measure once.
    """
    # Every line that produced an emission, whether or not it resolved to an
    # NGA factor.  Explosives are the case that matters: they carry no NGA
    # combustion factor, so they are outside NGER and outside the Safeguard
    # Mechanism, but they are a real Scope 1 source and the GHG inventory
    # reports them.  Excluding them here would make the table disagree with
    # the GHG view by the amount of the blast.  They are carried, and the
    # applicability flags say which frameworks they count towards.
    has_emission = ((agg_df['Scope1_tCO2e'].fillna(0.0) != 0.0)
                    | (agg_df['Scope2_tCO2e'].fillna(0.0) != 0.0))
    frame = agg_df[has_emission].copy()
    if frame.empty:
        return pd.DataFrame(columns=COLUMNS)

    lookup = _factor_lookup(frame, year_factor_map)
    keys = list(zip(frame['NGAFuel'].astype(str), frame['FY']))
    frame['_source'] = [lookup[k]['key'] for k in keys]
    frame['_f1'] = [lookup[k]['s1'] for k in keys]
    frame['_f2'] = [lookup[k]['s2'] for k in keys]
    frame['_funit'] = [lookup[k]['uom'] for k in keys]
    frame['_ngayear'] = [lookup[k]['nga_year'] for k in keys]
    frame['_fsource'] = [lookup[k]['source'] for k in keys]

    parts = []
    for scope, column, factor_col in (('Scope 1', 'Scope1_tCO2e', '_f1'),
                                      ('Scope 2', 'Scope2_tCO2e', '_f2')):
        rows = frame[frame[column].fillna(0.0) != 0.0]
        if rows.empty:
            continue
        parts.append(pd.DataFrame({
            'Date': rows['Date'].values,
            'Dataset': _dataset_label(rows['DataSet'], rows['Date'],
                                      actual_to),
            'RowKind': 'Emission',
            'Activity': rows['Activity'].astype(str).values,
            'SubActivity': rows['SubActivity'].astype(str).values,
            'Department': rows['Department'].astype(str).values,
            'CostCentre': rows['CostCentre'].astype(str).values,
            'Identifier': rows['Identifier'].astype(str).values,
            'Description': rows['Description'].astype(str).values,
            'Quantity': rows['Quantity'].values,
            'UOM': rows['UOM'].astype(str).values,
            'SpendAUD': rows['Value'].values,
            'GHGScope': scope,
            'Scope3Category': np.nan,
            # Every line is priced from the GHG factor map, so the factor,
            # its unit and its publication are read from the record that
            # priced it.  No source is a special case here.
            'EmissionSource': rows['_source'].astype(str).to_numpy(),
            'EmissionFactor': rows[factor_col].values,
            'FactorUOM': ('kg CO2-e/' + rows['_funit'].astype(str)).values,
            'FactorSource': rows['_fsource'].astype(str).to_numpy(),
            'FactorYear': rows['_ngayear'].values,
            'Emissions_tCO2e': rows[column].values,
            'Energy_GJ': rows['Energy_GJ'].values if 'Energy_GJ' in rows else np.nan,
            'CalculationMethod': 'Quantity x published factor / 1000',
            'ActivityDataSource': rows['Source'].astype(str).values,
            'DataQuality': 'Metered or inventory-derived',
        }))
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    return _finalise(pd.concat(parts, ignore_index=True), build_id)


def _physical_rows(agg_df, build_id, actual_to=None):
    """Production and metric lines: a measure, and no factor.

    These carry no emissions and are not double counting.  They are in the
    table because the denominators belong beside the numerators.
    """
    if 'RowType' not in agg_df.columns:
        return pd.DataFrame(columns=COLUMNS)
    rows = agg_df[agg_df['RowType'].astype(str).isin(PHYSICAL_ROW_TYPES)]
    rows = rows[rows['Quantity'].fillna(0.0) != 0.0]
    if rows.empty:
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.DataFrame({
        'Date': rows['Date'].values,
        'Dataset': _dataset_label(rows['DataSet'], rows['Date'],
                                  actual_to),
        'RowKind': 'Physical',
        'Activity': rows['Activity'].astype(str).values,
        'SubActivity': rows['SubActivity'].astype(str).values,
        'Department': rows['Department'].astype(str).values,
        'CostCentre': rows['CostCentre'].astype(str).values,
        'Identifier': rows['Identifier'].astype(str).values,
        'Description': rows['CommonName'].astype(str).values,
        'Quantity': rows['Quantity'].values,
        'UOM': rows['UOM'].astype(str).values,
        'SpendAUD': rows['Value'].values,
        'GHGScope': '',
        'Scope3Category': np.nan,
        'Emissions_tCO2e': 0.0,
        'CalculationMethod': 'Reported quantity, no factor applied',
        'ActivityDataSource': rows['Source'].astype(str).values,
        'DataQuality': 'Operationally reported',
        'Notes': 'Physical measure, denominator for intensity',
    })
    return _finalise(frame, build_id)


# ---------------------------------------------------------------------
# SCOPE 3, FROM THE SCOPE 3 BUILD
# ---------------------------------------------------------------------

def _scope3_rows(detail, build_id, actual_to=None):
    """Every Scope 3 line, all fifteen categories, as the build produced it.

    Category 3 is taken from here too rather than from the physicals, so
    Scope 3 has one source and cannot be counted twice by taking part of it
    from each.
    """
    if detail is None or detail.empty:
        return pd.DataFrame(columns=COLUMNS)
    rows = detail.copy()
    category = pd.to_numeric(rows['Category'], errors='coerce')
    frame = pd.DataFrame({
        'Date': rows['Date'].values,
        'Dataset': _dataset_label(rows['DataSet'], rows['Date'],
                                  actual_to),
        'RowKind': 'Emission',
        # A line the build produced from a stated assumption rather than from
        # a transaction says so, and says it on the row.
        'IsEstimated': (~rows['DataSet'].astype(str).str.lower()
                        .isin(['actual', 'budget'])).values,
        'Activity': rows['Activity'].astype(str).values,
        'SubActivity': rows['SubActivity'].astype(str).values,
        'Department': rows['Department'].astype(str).values,
        'CostCentre': rows['CostCentre'].astype(str).values,
        'Identifier': rows['Group'].astype(str).values,
        'Description': rows['GroupDescription'].astype(str).values,
        'Quantity': rows['Quantity'].values,
        'UOM': rows['UOM'].astype(str).values,
        'SpendAUD': rows['Spend_AUD'].values,
        'GHGScope': 'Scope 3',
        'Scope3Category': category.values,
        'Scope3CategoryName': category.map(SCOPE3_NAMES).fillna('').values,
        'EmissionSource': rows['Basis'].astype(str).values,
        'EmissionFactor': rows['Factor'].values,
        'FactorUOM': rows['FactorUnit'].astype(str).values,
        'FactorSource': rows['FactorSource'].astype(str).values,
        'Emissions_tCO2e': rows['tCO2e'].values,
        'CalculationMethod': rows['Method'].astype(str).values,
        'ActivityDataSource': rows['Basis'].astype(str).values,
    })
    # Provenance class, on the basis the line was computed on.  It is the
    # evidence question an assessor asks first.
    #
    # Tested with pandas string methods rather than numpy character
    # functions: the frames arrive with whichever string backend the
    # installed pandas uses, and only the pandas accessor works across all
    # of them.
    basis = rows['Basis'].astype(str).str.lower()
    quality = pd.Series('Inventory-derived', index=rows.index)
    quality = quality.mask(basis.str.contains('stated', na=False),
                           'Parameter estimate')
    quality = quality.mask(basis.str.contains('value', na=False),
                           'Purchase value')
    frame['DataQuality'] = quality.to_numpy()
    return _finalise(frame, build_id)


# ---------------------------------------------------------------------
# ASSEMBLY
# ---------------------------------------------------------------------

def _finalise(frame, build_id):
    """Fill the columns a part did not set, and put them in schema order."""
    frame = frame.copy()
    dates = pd.to_datetime(frame['Date'])
    frame['Date'] = dates
    frame['CalendarYear'] = dates.dt.year
    frame['FinancialYear'] = dates.dt.year + (dates.dt.month >= 7).astype(int)
    frame['IsForecast'] = (frame['Dataset'] == 'Forecast')
    if 'IsEstimated' not in frame.columns:
        frame['IsEstimated'] = False
    # One name per publication, and the scope taken out of it.  Done here so
    # every part of the table is written the same way whatever produced it.
    #
    # Resolved on the distinct sources rather than on the rows.  There are
    # about fifty source strings and eight hundred thousand rows, and the
    # four functions below are Python, do string work and call one another,
    # so mapping them row by row ran them three million times to answer fifty
    # questions.  That was two thirds of the time the whole build took.
    if 'FactorSource' in frame.columns:
        sources = frame['FactorSource'].fillna('').astype(str)
        canonical = {text: canonical_factor_source(text)
                     for text in sources.unique()}
        frame['FactorSource'] = sources.map(canonical)
        settled = frame['FactorSource']
        distinct = settled.unique()
        frame['FactorSet'] = settled.map(
            {text: factor_set(text) for text in distinct})
        frame['FactorDerivation'] = settled.map(
            {text: factor_derivation(text) for text in distinct})
        frame['FactorRegulated'] = settled.map(
            {text: factor_is_regulated(text) for text in distinct})

    scope = frame.get('GHGScope', pd.Series('', index=frame.index)).astype(str)
    # Which framework a row counts towards.  Stated per row so a view never
    # has to know the rule, and the rule is only written once.
    # NGER and the Safeguard Mechanism cover the sources the National
    # Greenhouse Account factors reach.  A GHG-only source such as explosives
    # is a real Scope 1 emission and is reported as one, but it is outside
    # both schemes, so the flags say so and no view has to know the rule.
    # Tested on the publication rather than on the file name.  The source
    # string is canonicalised a few lines above, so a test against a file
    # name silently stops matching and every row falls out of both schemes.
    nga_backed = frame.get('FactorSet',
                           pd.Series('', index=frame.index)).astype(str).eq(
        FACTOR_SET_NGA)
    frame['NGERApplicable'] = scope.isin(['Scope 1', 'Scope 2']) & nga_backed
    frame['SafeguardApplicable'] = scope.eq('Scope 1') & nga_backed
    frame['GRIApplicable'] = True
    frame['DateBasis'] = 'Month of consumption'
    frame['BuildID'] = build_id
    # Every column gets a settled type here, so the parts concatenate into
    # one frame without pandas having to guess from whichever part happened
    # to carry values.  A missing text field is blank, not null: a blank
    # reads as "nothing to say", a null reads as "not asked".
    numeric = ('Quantity', 'SpendAUD', 'Scope3Category', 'EmissionFactor',
               'Emissions_tCO2e', 'Energy_GJ', 'CalendarYear',
               'FinancialYear')
    boolean = ('IsForecast', 'IsEstimated', 'NGERApplicable',
               'SafeguardApplicable', 'GRIApplicable', 'FactorRegulated')
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan if column in numeric else (
                False if column in boolean else '')
    # float64 across every part, not whatever width the source frame used.
    # The physicals are stored float32 for memory and the Scope 3 detail is
    # float64; concatenating the two without settling this first lets the
    # result's precision depend on which part happened to be longer.
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column],
                                      errors='coerce').astype('float64')
    for column in boolean:
        frame[column] = frame[column].fillna(False).astype(bool)
    for column in COLUMNS:
        if column in numeric or column in boolean or column == 'Date':
            continue
        text = frame[column].fillna('').astype(str)
        # A part that cast a null column to text before it reached here
        # carries the literal string "nan", which then groups as a
        # department of its own.  A missing label is blank, not a word.
        frame[column] = text.mask(text.isin(_NULL_WORDS), '')
    return frame[COLUMNS]


def build_emissions_table(precomputed, agg_df, build_id=None):
    """The canonical table: every scope, every physical, monthly.

    Args:
        precomputed:  PrecomputedData, for the Scope 3 detail and the factor
                      map that was actually applied.
        agg_df:       the aggregated physicals from LoaderData.load_all_data.
        build_id:     identifier for this build; derived from the inputs
                      where not supplied.

    Returns:
        DataFrame in COLUMNS order, one row per line per scope, plus the
        physical measures.
    """
    detail = getattr(getattr(precomputed, 'scope3', None), 'detail', None)
    settle_id = build_id is None
    if build_id is None:
        build_id = build_id_for(
            len(agg_df), 0 if detail is None else len(detail),
            agg_df['Date'].max() if len(agg_df) else '',
            sorted((getattr(precomputed, 'ghg_factor_map', None)
                       or getattr(precomputed, 'year_factor_map', {}) or {})),
        )

    # Where the record stops, taken from the data rather than from a
    # constant, so the table cannot disagree with what was loaded.
    recorded = agg_df.loc[agg_df['DataSet'].astype(str).str.lower() == 'actual',
                          'Date']
    actual_to = recorded.max() if len(recorded) else None

    # A month can carry both an actual and a budget line for the same thing:
    # the record has run past the start of the forecast.  The engines keep
    # the actual and drop the budget line it supersedes, on the same month
    # and match key, and the table must do the same or it counts the month
    # twice.  Scope 3 detail arrives already superseded from CalcGhgCategories.
    agg_df = dedupe_actual_over_budget(agg_df)

    parts = [
        _scope12_rows(agg_df, (getattr(precomputed, 'ghg_factor_map', None)
                       or getattr(precomputed, 'year_factor_map', {}) or {}),
                      build_id, actual_to),
        _scope3_rows(detail, build_id, actual_to),
        _physical_rows(agg_df, build_id, actual_to),
    ]
    # Drop empty parts before concatenating: an all-blank frame contributes
    # no rows and pandas would otherwise let its dtypes decide the result's.
    filled = [p for p in parts if not p.empty]
    table = (pd.concat(filled, ignore_index=True) if filled
             else pd.DataFrame(columns=COLUMNS))
    table = table.sort_values(['Date', 'GHGScope', 'Scope3Category',
                               'Department', 'SubActivity'],
                              na_position='last').reset_index(drop=True)
    # The identifier is settled from the figures the build produced, not from
    # the shape of the inputs that produced them.  Read from the shape, a
    # forecast corrected and republished carried the identifier of the build
    # it replaced: three publications an hour apart, each a million tonnes
    # apart, all called eaa0713cccd9, and an archive a person could tell
    # apart only by its timestamp.  Same figures, same identifier still, so a
    # rebuild is still visibly a rebuild.
    if settle_id and not table.empty:
        emissions = table.loc[table['RowKind'] == 'Emission']
        by_year = (emissions.groupby(['CalendarYear', 'GHGScope'],
                                     observed=True)['Emissions_tCO2e']
                   .sum().round(3))
        table['BuildID'] = build_id_for(
            len(table), round(float(emissions['Emissions_tCO2e'].sum()), 3),
            *(f'{where}:{value}' for where, value in by_year.items()))
    # Text columns as categories.  Every one of them is a label from a short
    # list, and holding eight hundred thousand rows of Python strings costs
    # more memory than the whole of the rest of the model.  Done after the
    # concatenation, because concatenating categoricals with different
    # categories gives objects back.
    for column in table.columns:
        if table[column].dtype == object:
            table[column] = table[column].astype('category')
    return table


# ---------------------------------------------------------------------
# RECONCILIATION
# ---------------------------------------------------------------------

def reconcile(table, precomputed, basis='CY', tolerance=1.0):
    """Prove the table says what the engines say.

    The table is a projection of results the engines already produced, so
    any difference between the two is a fault in the projection and not a
    finding about emissions.  This is the gate a build passes before it is
    published, and the gate a reporting view passes before it is migrated on
    to the table.

    Args:
        table:       the canonical table.
        precomputed: PrecomputedData, carrying the annual frames.
        basis:       'CY' or 'FY'.
        tolerance:   tonnes.  A rounding difference, not a real one.

    Returns:
        DataFrame with one row per year per scope: table, engine, difference
        and whether it is within tolerance.
    """
    annual = (precomputed.ghg_annual_cy if basis == 'CY'
              else precomputed.ghg_annual_fy)
    if annual is None or annual.empty:
        return pd.DataFrame(columns=['Year', 'Scope', 'Table', 'Engine',
                                     'Difference', 'Within'])

    label_column = 'Year' if basis == 'CY' else 'FY'
    year_column = 'CalendarYear' if basis == 'CY' else 'FinancialYear'

    # Compare like with like.  The annual frames are built from the
    # projection, which starts at the Safeguard commencement, so a year the
    # projection only partly covers is not a difference in emissions and must
    # not be reported as one.
    #
    # Only the start is trimmed.  The engines' annual frames carry a modelled
    # annual estimate (Categories 6 and 7) for the whole of the last year
    # even where the physicals stop part way through it, so trimming the
    # table at the last month compared a full year against part of one and
    # failed on a difference that is not there.  A table year the engines do
    # not carry is never compared, so nothing past the end needs trimming.
    rows = table[table['RowKind'] == 'Emission']
    # The GHG inventory's own window.  The table is a GHG table, so it is
    # compared over the months the GHG pipeline covers and not over the
    # Safeguard projection's.
    window = getattr(precomputed, 'ghg_monthly', None)
    if window is not None and not window.empty:
        rows = rows[rows['Date'] >= window['Date'].min()]
        first_full = window['Date'].min()
        annual = annual[pd.to_datetime(annual['Date']) >= first_full] \
            if 'Date' in annual.columns else annual

    from_table = rows.groupby([year_column, 'GHGScope'],
                              observed=True)['Emissions_tCO2e'].sum()

    engine_columns = {'Scope 1': 'Scope1', 'Scope 2': 'Scope2',
                      'Scope 3': ('Scope3_Total' if 'Scope3_Total'
                                  in annual.columns else 'Scope3')}

    rows = []
    for _, record in annual.iterrows():
        label = str(record[label_column])
        year = int(''.join(ch for ch in label if ch.isdigit()) or 0)
        for scope, column in engine_columns.items():
            engine = float(record.get(column, 0.0) or 0.0)
            value = float(from_table.get((year, scope), 0.0))
            rows.append({
                'Year': label, 'Scope': scope,
                'Table': round(value, 2), 'Engine': round(engine, 2),
                'Difference': round(value - engine, 2),
                'Within': abs(value - engine) <= tolerance,
            })
    return pd.DataFrame(rows)


def monthly_pivot(table, value='Emissions_tCO2e', dataset=None):
    """Monthly buckets by scope, which is how the table is normally read."""
    rows = table[table['RowKind'] == 'Emission']
    if dataset:
        rows = rows[rows['Dataset'] == dataset]
    if rows.empty:
        return pd.DataFrame()
    return (rows.pivot_table(index='Date', columns='GHGScope', values=value,
                             aggfunc='sum', observed=True)
            .fillna(0.0).sort_index())
