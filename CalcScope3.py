"""
CalcScope3.py
Scope 3 emissions across the fifteen GHG Protocol categories.

Last updated: 2026-09-02

Regulatory and method basis:
    GHG Protocol Corporate Value Chain (Scope 3) Accounting and Reporting
      Standard, and its Technical Guidance for Calculating Scope 3 Emissions
    Scope 3 Category Assessment Methods, Ravenswood Gold Pty Ltd
    National Greenhouse Account Factors, DCCEEW
    US EPA Supply Chain Greenhouse Gas Emission Factors v1.3 (NAICS, USD 2022)
    AusLCI V48, DCCEEW, May 2026

Boundary
--------
Category 3 is computed at transaction level in CalcEmissions.py and carried on
the Scope3_tCO2e column.  That column feeds the Safeguard baseline and the
NGER position, so nothing here writes to it.  Every other category is produced
on its own frame, and only the total GHG view adds the two together.

Calculation methods
-------------------
Spend based
    tCO2-e = Value_AUD x AUD/USD x factor_kgCO2e_per_USD / 1000
    The rate is the quarter's AUD/USD from ReferenceFx.csv, then the deflator
    stated in ConfigScope3.yaml.  PrepData distributes the rate and converts
    nothing, so the conversion happens once, here, and is visible on the row.

Physical unit
    tCO2-e = Quantity x factor
    Takes precedence over the spend factor for the same product group, per the
    method: the highest priority physical unit source wins.

Forward projection
    Expenditure is recorded on inventory transactions from January 2026, and
    the budget physicals carry no value.  A dollar per reporting unit rate is
    fitted per Activity, SubActivity and unit over the window in
    ConfigScope3.yaml and applied to budget quantities.  A line with no fitted
    rate projects nothing and is named.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List

from LoaderScope3 import load_scope3_reference
from CalcEmissions import dedupe_actual_over_budget

# ---------------------------------------------------------------------
# CATEGORY REGISTER
# ---------------------------------------------------------------------
# Names as published in the GHG Protocol standard.  Every category appears in
# the output, whether it carries a number, awaits data or is a documented
# exclusion, so completeness is visible rather than asserted.

CATEGORY_NAMES = {
    1: 'Purchased goods and services',
    2: 'Capital goods',
    3: 'Fuel and energy related activities',
    4: 'Upstream transport and distribution',
    5: 'Waste generated in operations',
    6: 'Business travel',
    7: 'Employee commuting',
    8: 'Upstream leased assets',
    9: 'Downstream transport and distribution',
    10: 'Processing of sold products',
    11: 'Use of sold products',
    12: 'End of life treatment of sold products',
    13: 'Downstream leased assets',
    14: 'Franchises',
    15: 'Investments',
}

UPSTREAM = (1, 2, 3, 4, 5, 6, 7, 8)
DOWNSTREAM = (9, 10, 11, 12, 13, 14, 15)

DETAIL_COLUMNS = [
    'Date', 'Year', 'FY', 'DataSet', 'Category', 'CategoryName',
    'Method', 'Basis', 'Group', 'GroupDescription',
    # Department and cost centre come from the line the emission was computed
    # from, so Scope 3 joins the same breakdown as Scope 1 and Scope 2 rather
    # than sitting outside it.  An estimate made at facility level says so.
    'Department', 'CostCentre',
    'Activity', 'SubActivity', 'Quantity', 'UOM',
    'Spend_AUD', 'Rate_AUDUSD', 'Spend_USD', 'Factor', 'FactorUnit',
    'FactorSource', 'tCO2e',
]

from CalcUnits import (TROY_OUNCE_KG, KG_PER_TONNE_CO2E,
                       TONNES_PER_MEGATONNE)

# Currency, not a unit of measure, so it is named here rather than in
# CalcUnits.  The capital goods factors are published per million dollars.
AUD_PER_MILLION = 1_000_000.0


@dataclass
class Scope3Result:
    """Everything the Scope 3 view and the exports need."""

    detail: pd.DataFrame                       # one row per month, category, group
    annual_fy: pd.DataFrame                    # year by category, financial year
    annual_cy: pd.DataFrame                    # year by category, calendar year
    rates: pd.DataFrame                        # fitted dollar per unit rates
    outstanding: List[Dict[str, Any]]          # parameters and data not yet supplied
    exclusions: pd.DataFrame                   # documented exclusions with rationale
    coverage: Dict[str, Any]                   # spend reconciliation and gaps
    notes: Dict[str, str] = field(default_factory=dict)
    reference: Any = None

    def category_total(self, category, year=None, year_type='FY'):
        """Total tCO2-e for one category, optionally for one year."""
        frame = self.detail
        if frame.empty:
            return 0.0
        mask = frame['Category'] == category
        if year is not None:
            column = 'FY' if year_type == 'FY' else 'Year'
            mask &= frame[column] == year
        return float(frame.loc[mask, 'tCO2e'].sum())


# ---------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------

def build_scope3(df, reference=None, end_date=None):
    """Build the Scope 3 frame from the operations physicals.

    Args:
        df:        the loaded operations frame from LoaderData.load_all_data(),
                   carrying both datasets with ProductGroup, Value and the
                   Category 3 Scope3_tCO2e column already populated
        reference: a Scope3Reference; read from disk when not supplied
        end_date:  horizon.  Rows beyond it are dropped so the Scope 3 frame
                   covers the same period as the emissions projection

    Returns:
        Scope3Result
    """
    reference = reference or load_scope3_reference()
    config = reference.config

    work = df.copy()
    if end_date is not None:
        work = work[work['Date'] <= pd.Timestamp(end_date)]

    # Actuals supersede budget on the same month and match key, exactly as
    # Projections.build_projection() does, so the Scope 3 total covers the same
    # months as the Scope 1 and 2 totals and the overlap is not counted twice.
    work = _dedupe_actual_over_budget(work)

    outstanding: List[Dict[str, Any]] = []
    parts: List[pd.DataFrame] = []

    rates = _fit_unit_rates(work, reference)

    for builder in (_category_1, _category_2, _category_4, _category_5,
                    _category_6, _category_7, _category_10):
        frame, gaps = builder(work, reference, rates)
        parts.append(frame)
        outstanding.extend(gaps)

    parts.append(_category_3(work, reference))

    frames = [p for p in parts if p is not None and not p.empty]
    detail = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=DETAIL_COLUMNS)
    detail = detail.reindex(columns=DETAIL_COLUMNS)

    return Scope3Result(
        detail=detail,
        annual_fy=_annual(detail, 'FY'),
        annual_cy=_annual(detail, 'Year'),
        rates=rates,
        outstanding=outstanding,
        exclusions=_exclusions(config),
        coverage=_coverage(work, detail, reference),
        notes={
            'currency': reference.currency_note(),
            'projection': _projection_note(config),
            'boundary': 'Category 3 is the Scope3_tCO2e column from the '
                        'emissions calculation and is not recomputed here.',
        },
        reference=reference,
    )


# ---------------------------------------------------------------------
# SHARED HELPERS
# ---------------------------------------------------------------------

def _dedupe_actual_over_budget(df):
    """Drop budget rows superseded by an actual on the same month and match key."""
    return dedupe_actual_over_budget(df)


def _blank_detail(rows):
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS)
    return frame.reindex(columns=DETAIL_COLUMNS)


def _rate_series(dates, reference):
    """AUD to factor-year USD, one rate per row.

    Takes a Series, an Index or a plain sequence.  Coerced to an Index first
    because pandas will not run unique() over a list.
    """
    index = pd.Index(dates)
    unique = index.unique()
    rates = np.array([reference.usd_rate(value) for value in unique],
                     dtype=float)
    # Map back by position rather than by a lookup per row.  A projection
    # carries hundreds of thousands of rows over a few hundred distinct
    # months, so the rate is resolved once per month and then taken.
    return rates[unique.get_indexer(index)]


def _window(config):
    projection = config.get('projection', {}) or {}
    return (pd.Timestamp(projection.get('rate_window_from')),
            pd.Timestamp(projection.get('rate_window_to')))


def _operating_years(df):
    """Years the site is operating, from the physicals themselves."""
    if 'Year' not in df.columns or df.empty:
        return []
    return sorted(int(y) for y in df['Year'].unique())


def _spread_rows(year, category, method, basis, group, quantity, uom,
                 factor, factor_unit, factor_source, tco2e, description=None):
    """An annual estimate spread evenly across the twelve months of the year.

    An estimate charged to a single date would fall wholly inside one
    financial year and nothing of it into the other, so the same estimate
    would read differently on a calendar and a financial year.  Spreading it
    monthly makes both correct and lets the estimate sit on the same monthly
    frame as the measured categories.
    """
    rows = []
    for month in range(1, 13):
        record = _annual_row(year, category, method, basis, group,
                             quantity / 12.0, uom, factor, factor_unit,
                             factor_source, tco2e / 12.0, description)
        record['Date'] = pd.Timestamp(year=year, month=month, day=1)
        record['FY'] = year + 1 if month >= 7 else year
        rows.append(record)
    return rows


def _annual_row(year, category, method, basis, group, quantity, uom,
                factor, factor_unit, factor_source, tco2e, description=None):
    """One estimate, dated to 1 July so it lands in one financial year.

    Used for a point event such as a capital acquisition.  A recurring annual
    estimate goes through _spread_rows() instead.
    """
    return {
        'Date': pd.Timestamp(year=year, month=7, day=1),
        'Year': year,
        'FY': year + 1,
        'DataSet': 'Estimate',
        'Category': category,
        'CategoryName': CATEGORY_NAMES[category],
        'Method': method,
        'Basis': basis,
        'Group': group,
        'GroupDescription': description or group,
        'Department': 'Site wide estimate',
        'CostCentre': '',
        'Activity': 'Estimate',
        'SubActivity': group,
        'Quantity': quantity,
        'UOM': uom,
        'Spend_AUD': 0.0,
        'Rate_AUDUSD': np.nan,
        'Spend_USD': np.nan,
        'Factor': factor,
        'FactorUnit': factor_unit,
        'FactorSource': factor_source,
        'tCO2e': tco2e,
    }


# ---------------------------------------------------------------------
# UNIT RATE FITTING
# ---------------------------------------------------------------------

def _fit_unit_rates(df, reference):
    """Dollars per reporting unit, per Activity, SubActivity and unit.

    Fitted over the window in ConfigScope3.yaml from valued actual rows only.
    Each key carries the product group holding the largest share of its value
    in the window, which is the group whose factor projected spend is charged
    at.  A key with nil quantity produces no rate, so a line that was valued
    but never measured does not project an infinite rate.
    """
    columns = ['Activity', 'SubActivity', 'UOM', 'ProductGroup',
               'Spend_AUD', 'Quantity', 'RateAudPerUnit', 'Months']
    if 'Value' not in df.columns:
        return pd.DataFrame(columns=columns)

    start, end = _window(reference.config)
    valued = df[
        (df['DataSet'] == 'Actual')
        & (df['Value'] != 0)
        & (df['Date'] >= start)
        & (df['Date'] <= end)
    ].copy()
    if valued.empty:
        return pd.DataFrame(columns=columns)

    for column in ('Activity', 'SubActivity', 'UOM', 'ProductGroup'):
        valued[column] = valued[column].astype(str)

    grouped = valued.groupby(['Activity', 'SubActivity', 'UOM'], observed=True).agg(
        Spend_AUD=('Value', 'sum'),
        Quantity=('Quantity', 'sum'),
        Months=('Date', 'nunique'),
    ).reset_index()

    shares = valued.groupby(
        ['Activity', 'SubActivity', 'UOM', 'ProductGroup'], observed=True
    )['Value'].sum().reset_index().sort_values('Value', ascending=False)
    dominant = shares.drop_duplicates(subset=['Activity', 'SubActivity', 'UOM'])[
        ['Activity', 'SubActivity', 'UOM', 'ProductGroup']]

    rates = grouped.merge(dominant, on=['Activity', 'SubActivity', 'UOM'], how='left')
    rates['RateAudPerUnit'] = np.where(
        rates['Quantity'] > 0, rates['Spend_AUD'] / rates['Quantity'], np.nan)
    return rates[columns]


# ---------------------------------------------------------------------
# CATEGORY 1 - PURCHASED GOODS AND SERVICES
# ---------------------------------------------------------------------

def _category_1(df, reference, rates):
    """Recorded and projected spend by product group, plus physical unit lines."""
    settings = reference.config.get('category_1', {}) or {}
    if not settings.get('applies', True):
        return _blank_detail([]), []

    factors = reference.category_1_factors()
    method = settings.get('method', 'Spend based')
    gaps: List[Dict[str, Any]] = []
    frames = []

    # -- physical unit lines ------------------------------------------
    # Charged before spend so a line carrying both is counted once, on the
    # physical factor, which is the higher priority source.
    # Read from the factor table where it is present, so the physical unit
    # factors sit beside every other factor rather than only in the parameter
    # file.  The parameter file still supplies the match key and the unit.
    physical = settings.get('physical_unit_factors', {}) or {}
    physical_names = set()
    for code, spec in physical.items():
        name = spec.get('match_common_name')
        if not name:
            continue
        if code in factors.index and str(factors.loc[code, 'Basis']) == 'physical':
            entry = factors.loc[code]
            spec = dict(spec)
            spec['factor'] = float(entry['Factor'])
            spec['unit'] = entry['FactorUnit'] or spec.get('unit')
            spec['quantity_uom'] = entry['QuantityUOM'] or spec.get('quantity_uom')
            spec['source'] = entry['FactorSource'] or spec.get('source')
            if pd.notna(entry.get('MatchKey')):
                name = entry['MatchKey']
        physical_names.add(name)
        rows = df[
            (df['CommonName'].astype(str) == name)
            & (df['UOM'].astype(str) == str(spec.get('quantity_uom')))
            & (df['Quantity'] > 0)
        ]
        if rows.empty:
            gaps.append({
                'Category': 1,
                'Item': f'{code} physical unit factor unused',
                'Detail': f"No line matched common name '{name}' in "
                          f"{spec.get('quantity_uom')}, so nothing is charged.",
            })
            continue
        factor = float(spec['factor'])
        frames.append(pd.DataFrame({
            'Date': rows['Date'].values,
            'Year': rows['Year'].values,
            'FY': rows['FY'].values,
            'DataSet': rows['DataSet'].astype(str).values,
            'Category': 1,
            'CategoryName': CATEGORY_NAMES[1],
            'Method': method,
            'Basis': 'Physical unit',
            'Group': code,
            'GroupDescription': (factors.loc[code, 'Description']
                                 if code in factors.index else code),
            'Department': rows['Department'].astype(str).values,
            'CostCentre': rows['CostCentre'].astype(str).values,
            'Activity': rows['Activity'].astype(str).values,
            'SubActivity': rows['SubActivity'].astype(str).values,
            'Quantity': rows['Quantity'].values,
            'UOM': rows['UOM'].astype(str).values,
            'Spend_AUD': 0.0,
            'Rate_AUDUSD': np.nan,
            'Spend_USD': np.nan,
            'Factor': factor,
            'FactorUnit': spec.get('unit'),
            'FactorSource': spec.get('source'),
            'tCO2e': rows['Quantity'].values * factor,
        }))

    spend_factors = factors[(factors['Basis'] == 'spend') & (~factors['Excluded'])]

    recorded, recorded_gaps = _spend_lines(
        df, reference, spend_factors, category=1, method=method,
        basis='Spend, recorded', exclude_common_names=physical_names,
        all_factors=factors)
    frames.append(recorded)
    gaps.extend(recorded_gaps)

    projected, projected_gaps = _projected_spend_lines(
        df, reference, rates, spend_factors, category=1, method=method,
        basis='Spend, projected on fitted unit rate',
        exclude_common_names=physical_names)
    frames.append(projected)
    gaps.extend(projected_gaps)

    frames = [f for f in frames if not f.empty]
    detail = pd.concat(frames, ignore_index=True) if frames else _blank_detail([])
    return detail, gaps


# ---------------------------------------------------------------------
# CATEGORY 4 - UPSTREAM TRANSPORT AND DISTRIBUTION
# ---------------------------------------------------------------------

def _category_4(df, reference, rates):
    """The margin component of the same factor set, on the same expenditure.

    Fuel inbound freight is excluded: it sits inside the Category 3 well to
    tank coefficient and would be counted twice here.
    """
    settings = reference.config.get('category_4', {}) or {}
    if not settings.get('applies', True):
        return _blank_detail([]), []

    factors = reference.category_4_factors()
    priceable = factors[(factors['Basis'] == 'spend') & (~factors['Excluded'])]
    method = settings.get('method', 'EPA supply chain margin factors')

    recorded, gaps = _spend_lines(
        df, reference, priceable, category=4, method=method,
        basis='Margin on recorded spend', exclude_common_names=set(),
        all_factors=factors)
    projected, projected_gaps = _projected_spend_lines(
        df, reference, rates, priceable, category=4, method=method,
        basis='Margin on projected spend')

    frames = [f for f in (recorded, projected) if not f.empty]
    detail = pd.concat(frames, ignore_index=True) if frames else _blank_detail([])
    return detail, gaps + projected_gaps


# ---------------------------------------------------------------------
# SPEND LINE BUILDERS (shared by categories 1 and 4)
# ---------------------------------------------------------------------

def _spend_lines(df, reference, factors, category, method, basis,
                 exclude_common_names, all_factors=None):
    """Charge recorded expenditure at the factor for its product group.

    factors carries the priceable groups only.  all_factors carries every
    group in the register including those charged elsewhere, so a group whose
    emissions are computed from NGA factors is reported as a deliberate
    exclusion rather than as a gap in the register.
    """
    gaps: List[Dict[str, Any]] = []
    if 'Value' not in df.columns or factors.empty:
        return _blank_detail([]), gaps
    if all_factors is None:
        all_factors = factors

    # Value nets: an inventory return carries a negative line cost against the
    # negative quantity it reverses, so both sides are charged and the result
    # is consumption, not issues.
    rows = df[df['Value'] != 0].copy()
    if exclude_common_names:
        rows = rows[~rows['CommonName'].astype(str).isin(exclude_common_names)]
    if rows.empty:
        return _blank_detail([]), gaps

    rows['ProductGroup'] = rows['ProductGroup'].astype(str).str.strip()
    known = rows[rows['ProductGroup'].isin(factors.index)]
    unpriced = rows[(~rows['ProductGroup'].isin(factors.index))
                    & (rows['ProductGroup'] != '')]

    if not unpriced.empty:
        by_group = unpriced.groupby('ProductGroup', observed=True)['Value'].sum()
        for code, value in by_group.sort_values(ascending=False).items():
            if code in all_factors.index and bool(all_factors.loc[code, 'Excluded']):
                # Charged elsewhere by design.  Not a gap.
                continue
            gaps.append({
                'Category': category,
                'Item': f'Product group {code} carries no factor',
                'Detail': f'${value:,.0f} of recorded expenditure has no factor '
                          f'for this category in the product group register.',
            })

    if known.empty:
        return _blank_detail([]), gaps

    known = known.reset_index(drop=True)
    rate = _rate_series(known['Date'], reference)
    factor = known['ProductGroup'].map(factors['Factor']).astype(float).values
    spend_usd = known['Value'].values * rate

    detail = pd.DataFrame({
        'Date': known['Date'].values,
        'Year': known['Year'].values,
        'FY': known['FY'].values,
        'DataSet': known['DataSet'].astype(str).values,
        'Category': category,
        'CategoryName': CATEGORY_NAMES[category],
        'Method': method,
        'Basis': basis,
        'Group': known['ProductGroup'].values,
        'GroupDescription': known['ProductGroup'].map(factors['Description']).values,
        'Department': known['Department'].astype(str).values,
        'CostCentre': known['CostCentre'].astype(str).values,
        'Activity': known['Activity'].astype(str).values,
        'SubActivity': known['SubActivity'].astype(str).values,
        'Quantity': known['Quantity'].values,
        'UOM': known['UOM'].astype(str).values,
        'Spend_AUD': known['Value'].values,
        'Rate_AUDUSD': rate,
        'Spend_USD': spend_usd,
        'Factor': factor,
        'FactorUnit': known['ProductGroup'].map(factors['FactorUnit']).values,
        'FactorSource': known['ProductGroup'].map(factors['FactorSource']).values,
        # kilograms per USD on USD of spend, to tonnes.
        'tCO2e': spend_usd * factor / KG_PER_TONNE_CO2E,
    })
    return detail, gaps


def _projected_spend_lines(df, reference, rates, factors, category, method,
                           basis, exclude_common_names=frozenset()):
    """Price budget quantities at the fitted dollar per unit rate for their line.

    A line already charged on a physical unit factor is excluded, so it is
    neither counted twice nor reported as a line that failed to project.
    """
    config = reference.config
    projection = config.get('projection', {}) or {}
    gaps: List[Dict[str, Any]] = []

    if projection.get('basis') == 'none':
        gaps.append({
            'Category': category,
            'Item': 'Forward projection is off',
            'Detail': 'ConfigScope3.yaml sets projection.basis to none, so the '
                      'forward years carry no spend based emissions.',
        })
        return _blank_detail([]), gaps

    if factors.empty:
        return _blank_detail([]), gaps
    if rates.empty and 'Value' not in df.columns:
        return _blank_detail([]), gaps

    _, window_end = _window(config)
    # Only lines that are a purchased input can carry spend.  Production,
    # revenue, headcount and electricity measures are drivers, not purchases,
    # so they are never priced and never reported as a gap.
    projectable = set(projection.get(
        'projectable_rowtypes', ['consumption', 'stores', 'fuel']))
    budget = df[
        (df['DataSet'] == 'Budget')
        & (df['Date'] > window_end)
        & (df['RowType'].astype(str).isin(projectable))
    ].copy()
    if exclude_common_names:
        budget = budget[~budget['CommonName'].astype(str).isin(exclude_common_names)]
    if budget.empty:
        return _blank_detail([]), gaps

    # A budget row carrying its own value needs no fitted rate.  The budget
    # physicals do not carry one today.  PrepData feeds several programs, so
    # this model does not ask it to change; the test costs nothing and means a
    # value column appearing upstream is used the day it arrives, in
    # preference to a rate fitted from seven months of history.
    recorded = pd.to_numeric(budget.get('Value'), errors='coerce') \
        if 'Value' in budget.columns else None
    has_recorded = recorded is not None and bool((recorded.fillna(0) != 0).any())

    for column in ('Activity', 'SubActivity', 'UOM'):
        budget[column] = budget[column].astype(str)

    if rates.empty:
        priced = budget.copy()
        priced['RateAudPerUnit'] = float('nan')
        priced['ProductGroup_rate'] = None
    else:
        priced = budget.merge(
            rates[['Activity', 'SubActivity', 'UOM', 'ProductGroup', 'RateAudPerUnit']],
            on=['Activity', 'SubActivity', 'UOM'], how='left', suffixes=('', '_rate'))

    group_column = 'ProductGroup_rate' if 'ProductGroup_rate' in priced.columns else 'ProductGroup'

    # The row's own product group beats the group the rate was fitted on: it is
    # the row's statement rather than an inference from a similar line.
    if 'ProductGroup' in priced.columns and group_column != 'ProductGroup':
        own = priced['ProductGroup'].astype(str).str.strip()
        priced[group_column] = priced[group_column].where(
            ~own.isin(factors.index), own)

    priced['_recorded'] = (pd.to_numeric(priced.get('Value'), errors='coerce').fillna(0.0)
                           if 'Value' in priced.columns else 0.0)
    priceable = priced['RateAudPerUnit'].notna() | (priced['_recorded'] != 0)

    matched = priced[
        priceable
        & priced[group_column].isin(factors.index)
        & (priced['Quantity'] > 0)
    ].copy()

    # Budget lines with a quantity but no fitted rate.  Named, not assumed nil.
    if category == 1:
        unmatched = priced[~priceable & (priced['Quantity'] > 0)]
        if not unmatched.empty:
            keys = unmatched.groupby(['Activity', 'SubActivity'], observed=True).size()
            for (activity, subactivity), count in keys.sort_values(ascending=False).items():
                gaps.append({
                    'Category': category,
                    'Item': f'No fitted rate: {activity} / {subactivity}',
                    'Detail': f'{count:,} budget months carry a quantity but no '
                              f'dollar per unit rate, so nothing is projected.',
                })

    if matched.empty:
        return _blank_detail([]), gaps

    escalation = float(projection.get('escalation_per_year', 0.0) or 0.0)
    years = (matched['Date'].dt.year - pd.Timestamp(window_end).year).clip(lower=0)
    escalator = (1.0 + escalation) ** years

    matched = matched.reset_index(drop=True)
    escalator = escalator.reset_index(drop=True)

    fitted = (matched['Quantity'].values
              * matched['RateAudPerUnit'].fillna(0.0).values
              * escalator.values)
    if has_recorded:
        # A recorded value stands as recorded, unescalated.
        recorded_value = matched['_recorded'].values
        spend_aud = np.where(recorded_value != 0, recorded_value, fitted)
        row_basis = np.where(recorded_value != 0,
                             f'{basis} (value recorded on the budget)', basis)
    else:
        spend_aud = fitted
        row_basis = basis
    rate = _rate_series(matched['Date'], reference)
    spend_usd = spend_aud * rate
    group = matched[group_column]
    factor = group.map(factors['Factor']).astype(float).values

    detail = pd.DataFrame({
        'Date': matched['Date'].values,
        'Year': matched['Year'].values,
        'FY': matched['FY'].values,
        'DataSet': 'Budget',
        'Category': category,
        'CategoryName': CATEGORY_NAMES[category],
        'Method': method,
        'Basis': row_basis,
        'Group': group.values,
        'GroupDescription': group.map(factors['Description']).values,
        'Department': matched['Department'].astype(str).values,
        'CostCentre': matched['CostCentre'].astype(str).values,
        'Activity': matched['Activity'].values,
        'SubActivity': matched['SubActivity'].values,
        'Quantity': matched['Quantity'].values,
        'UOM': matched['UOM'].values,
        'Spend_AUD': spend_aud,
        'Rate_AUDUSD': rate,
        'Spend_USD': spend_usd,
        'Factor': factor,
        'FactorUnit': group.map(factors['FactorUnit']).values,
        'FactorSource': group.map(factors['FactorSource']).values,
        'tCO2e': spend_usd * factor / KG_PER_TONNE_CO2E,
    })
    return detail, gaps


# ---------------------------------------------------------------------
# CATEGORY 2 - CAPITAL GOODS
# ---------------------------------------------------------------------

def _category_2(df, reference, rates):
    """Owned and finance leased acquisitions, priced on capitalised value.

    Recognised in full in the year of acquisition.  A rental is an expensed
    service and belongs in Category 1, so the register's tenure decides
    whether an asset produces a Category 2 event at all.
    """
    settings = reference.config.get('category_2', {}) or {}
    gaps: List[Dict[str, Any]] = []
    if not settings.get('applies', True):
        return _blank_detail([]), gaps

    register = reference.capital_register
    intensity = reference.capital_intensity()
    if register.empty or not intensity:
        gaps.append({
            'Category': 2,
            'Item': 'Asset register or capital factors absent',
            'Detail': 'Category 2 cannot be computed without both.',
        })
        return _blank_detail([]), gaps

    class_map = settings.get('asset_class_map', {}) or {}
    tenures = set(settings.get('include_tenure', ['Owned']))

    work = register.copy()
    work['Tenure'] = work['Tenure'].astype(str).str.strip()
    applies = work['Cat2_Applies'].astype(str).str.strip().str.lower().str.startswith('yes')
    work = work[applies & work['Tenure'].isin(tenures)]

    if work.empty:
        gaps.append({
            'Category': 2,
            'Item': 'No qualifying acquisition in the register',
            'Detail': 'Every reviewed asset is a rental, which is an expensed '
                      'service in Category 1.',
        })

    rows = []
    unmapped = set()
    for _, asset in work.iterrows():
        asset_category = str(asset.get('Category', '')).strip()
        asset_class = class_map.get(asset_category)
        if asset_class is None or asset_class not in intensity:
            unmapped.add(asset_category)
            continue
        value = float(asset.get('Market_Value_AUD') or 0.0)
        year = int(asset.get('Model_Year') or 0)
        if value <= 0 or year <= 0:
            continue
        factor = float(intensity[asset_class])
        record = _annual_row(
            year, category=2, method=settings.get('method', ''),
            basis='Capitalised value',
            group=str(asset.get('Unit', '')),
            quantity=1.0, uom='asset',
            factor=factor, factor_unit='t CO2-e per $1M AUD',
            factor_source=f'EPA SCEF, {asset_class}, banded to AUD',
            # The factor is per million dollars of capitalised value.
            tco2e=value / AUD_PER_MILLION * factor,
            description=f"{asset_category}, {asset.get('Make', '')} "
                        f"{asset.get('Model', '')}".strip(),
        )
        record.update({
            'Spend_AUD': value,
            'Department': str(asset.get('Department', '') or 'Capital'),
            'CostCentre': '',
            'Activity': 'Capital',
            'SubActivity': asset_category,
            'DataSet': 'Actual',
        })
        rows.append(record)

    for asset_category in sorted(unmapped):
        gaps.append({
            'Category': 2,
            'Item': f"Asset category '{asset_category}' is not mapped",
            'Detail': 'No entry in category_2.asset_class_map, so the asset is '
                      'not priced.',
        })

    # Approved capital projects carry no value in the screen, so they are
    # reported rather than estimated.
    projects = reference.capital_projects
    if not projects.empty and 'ApprovedValue_AUD' in projects.columns:
        missing = int(pd.to_numeric(projects['ApprovedValue_AUD'],
                                    errors='coerce').isna().sum())
        if missing:
            gaps.append({
                'Category': 2,
                'Item': f'{missing} approved capital projects carry no value',
                'Detail': 'Cat2ProjectScreen.csv records the NAICS class and the '
                          'intensity for each, but the approved value is not in '
                          'the tracker, so no emission is recognised for them.',
            })

    return _blank_detail(rows), gaps


# ---------------------------------------------------------------------
# CATEGORY 3 - FUEL AND ENERGY RELATED ACTIVITIES
# ---------------------------------------------------------------------

def _category_3(df, reference):
    """The NGA well to tank and grid loss result already on the frame.

    Read, never recomputed.  Aggregated to month and line so the Scope 3 view
    can show its composition without returning to the raw frame.
    """
    settings = reference.config.get('category_3', {}) or {}
    column = settings.get('source_column', 'Scope3_tCO2e')
    if column not in df.columns:
        return _blank_detail([])

    rows = df[df[column] != 0]
    if rows.empty:
        return _blank_detail([])

    grouped = rows.groupby(
        ['Date', 'Year', 'FY', 'DataSet', 'Department', 'CostCentre',
         'Activity', 'SubActivity', 'CommonName', 'UOM'],
        observed=True, dropna=False
    ).agg(Quantity=('Quantity', 'sum'), tCO2e=(column, 'sum')).reset_index()
    grouped = grouped[grouped['tCO2e'] != 0]

    return pd.DataFrame({
        'Date': grouped['Date'].values,
        'Year': grouped['Year'].values,
        'FY': grouped['FY'].values,
        'DataSet': grouped['DataSet'].astype(str).values,
        'Category': 3,
        'CategoryName': CATEGORY_NAMES[3],
        'Method': settings.get('method', 'NGA Scope 3 coefficients'),
        'Basis': 'NGA factor at transaction level',
        'Group': grouped['CommonName'].astype(str).values,
        'GroupDescription': grouped['CommonName'].astype(str).values,
        'Department': grouped['Department'].astype(str).values,
        'CostCentre': grouped['CostCentre'].astype(str).values,
        'Activity': grouped['Activity'].astype(str).values,
        'SubActivity': grouped['SubActivity'].astype(str).values,
        'Quantity': grouped['Quantity'].values,
        'UOM': grouped['UOM'].astype(str).values,
        'Spend_AUD': 0.0,
        'Rate_AUDUSD': np.nan,
        'Spend_USD': np.nan,
        'Factor': np.nan,
        'FactorUnit': None,
        'FactorSource': 'National Greenhouse Account Factors, Scope 3',
        'tCO2e': grouped['tCO2e'].values,
    }).reindex(columns=DETAIL_COLUMNS)


# ---------------------------------------------------------------------
# CATEGORY 5 - WASTE GENERATED IN OPERATIONS
# ---------------------------------------------------------------------

def _category_5(df, reference, rates):
    """Waste mass by stream times a treatment factor, over the operating years.

    Tailings and waste rock are process residues retained on site and are not
    a Category 5 stream; the exclusion is recorded in ConfigScope3.yaml.
    """
    settings = reference.config.get('category_5', {}) or {}
    gaps: List[Dict[str, Any]] = []
    if not settings.get('applies', True):
        return _blank_detail([]), gaps

    streams = settings.get('streams', []) or []
    supplied = [s for s in streams if s.get('tonnes_per_year') is not None]
    for stream in [s for s in streams if s.get('tonnes_per_year') is None]:
        gaps.append({
            'Category': 5,
            'Item': f"Waste stream '{stream.get('name')}' has no volume",
            'Detail': 'Volumes come from the waste contractor and are not held '
                      'in the model.  The stream is carried at nil until they '
                      'are supplied.',
        })
    if not supplied:
        return _blank_detail([]), gaps

    scale = _activity_scalar(df, settings.get('scale_to_subactivity'))

    rows = []
    for year in _operating_years(df):
        weight = scale.get(year, 1.0)
        if weight <= 0:
            continue
        for stream in supplied:
            tonnes = float(stream['tonnes_per_year']) * weight
            factor = float(reference.factor_for(
                5, stream.get('name'), stream.get('factor_tco2e_per_t', 0.0)))
            rows.extend(_spread_rows(
                year, category=5, method=settings.get('method', ''),
                basis='Volume estimate', group=stream.get('name'),
                quantity=tonnes, uom='t', factor=factor,
                factor_unit='t CO2-e per t',
                factor_source=stream.get('factor_source'),
                tco2e=tonnes * factor))
    return _blank_detail(rows), gaps


# ---------------------------------------------------------------------
# ACTIVITY SCALARS
# ---------------------------------------------------------------------

def _activity_scalar(df, subactivity, baseline_year=None):
    """Year to a multiple of a driver line's own baseline year.

    Used to carry an estimate that was measured in one year across the rest of
    the mine life on the physicals rather than flat.  A stated subactivity of
    None returns 1.0 for every year, which holds the estimate flat and says so
    by omission in the configuration.
    """
    if not subactivity:
        return {}

    rows = df[df['SubActivity'].astype(str) == str(subactivity)]
    if rows.empty:
        return {}

    annual = rows.groupby('Year', observed=True)['Quantity'].sum()
    annual = annual[annual > 0]
    if annual.empty:
        return {}

    if baseline_year is None or baseline_year not in annual.index:
        baseline_year = int(annual.index.min())
    base = float(annual.loc[baseline_year])
    if base <= 0:
        return {}

    # Every year in the horizon gets a weight.  A year the driver does not
    # reach is nil, not one: an estimate scaled on milled tonnes stops when
    # milling stops rather than running flat into rehabilitation.
    scalar = {int(year): float(value) / base for year, value in annual.items()}
    first, last = min(scalar), max(scalar)
    for year in range(int(df['Year'].min()), int(df['Year'].max()) + 1):
        if year not in scalar:
            scalar[year] = 1.0 if year < first else 0.0
    return scalar


def _headcount_by_year(df):
    """Average full time equivalents per calendar year, from the physicals."""
    headcount = df[df['RowType'].astype(str) == 'headcount']
    if headcount.empty:
        return {}
    monthly = headcount.groupby(['Year', 'Date'], observed=True)['Quantity'].sum()
    annual = monthly.groupby(level=0).mean()
    return {int(year): float(value) for year, value in annual.items()}


# ---------------------------------------------------------------------
# CATEGORY 6 - BUSINESS TRAVEL
# ---------------------------------------------------------------------

def _category_6(df, reference, rates):
    """Air and road legs on the stated travel pattern, off site portions only.

    On site vehicle fuel is Scope 1 already, so only the leg between the
    worker's origin and the site boundary belongs here.
    """
    settings = reference.config.get('category_6', {}) or {}
    gaps: List[Dict[str, Any]] = []
    if not settings.get('applies', True):
        return _blank_detail([]), gaps

    air_legs = settings.get('air_legs', []) or []
    road_legs = settings.get('road_legs', []) or []
    if not air_legs and not road_legs:
        gaps.append({
            'Category': 6,
            'Item': 'Travel pattern not supplied',
            'Detail': 'No air or road leg is defined in ConfigScope3.yaml, so '
                      'business travel carries nothing.',
        })
        return _blank_detail([]), gaps

    scale = _activity_scalar(df, settings.get('scale_to_subactivity'),
                             settings.get('baseline_year'))
    method = settings.get('method', '')
    rows = []

    for year in _operating_years(df):
        weight = scale.get(year, 1.0) if scale else 1.0
        if weight <= 0:
            continue

        for leg in air_legs:
            sectors = leg.get('sectors_per_year')
            if sectors is None and leg.get('sectors_per_week') is not None:
                sectors = float(leg['sectors_per_week']) * 52.0
            km = leg.get('km_per_sector')
            if sectors is None or km is None:
                gaps.append({
                    'Category': 6,
                    'Item': f"Air leg '{leg.get('name')}' is incomplete",
                    'Detail': 'Sectors per year and kilometres per sector are '
                              'both required.',
                })
                continue
            # A return trip is two sectors.
            multiplier = 2.0 if leg.get('return_trip', True) else 1.0
            pkm = float(sectors) * float(km) * multiplier * weight
            factor = float(reference.factor_for(
                6, leg.get('name'), leg.get('factor_kgco2e_per_pkm', 0.0)))
            rows.extend(_spread_rows(
                year, category=6, method=method, basis='Stated travel pattern',
                group=leg.get('name'), quantity=pkm, uom='passenger km',
                factor=factor, factor_unit='kg CO2-e per passenger km',
                factor_source=leg.get('factor_source'),
                tco2e=pkm * factor / KG_PER_TONNE_CO2E))

        for leg in road_legs:
            km_per_year = leg.get('km_per_year')
            if km_per_year is None:
                gaps.append({
                    'Category': 6,
                    'Item': f"Road leg '{leg.get('name')}' has no distance",
                    'Detail': 'Kilometres per year are required.',
                })
                continue
            km = float(km_per_year) * weight
            factor = float(reference.factor_for(
                6, leg.get('name'), leg.get('factor_kgco2e_per_km', 0.0)))
            rows.extend(_spread_rows(
                year, category=6, method=method, basis='Stated travel pattern',
                group=leg.get('name'), quantity=km, uom='km',
                factor=factor, factor_unit='kg CO2-e per km',
                factor_source=leg.get('factor_source'),
                tco2e=km * factor / KG_PER_TONNE_CO2E))

    return _blank_detail(rows), gaps


# ---------------------------------------------------------------------
# CATEGORY 7 - EMPLOYEE COMMUTING
# ---------------------------------------------------------------------

def _category_7(df, reference, rates):
    """Drive in drive out travel on the roster, off site portion only.

    Headcount is in the operations physicals in full time equivalents, so the
    workforce is scaled year by year against its baseline and the estimate
    follows the wind down rather than running flat to the horizon.
    """
    settings = reference.config.get('category_7', {}) or {}
    gaps: List[Dict[str, Any]] = []
    if not settings.get('applies', True):
        return _blank_detail([]), gaps

    roster = settings.get('roster', {}) or {}
    legs = roster.get('legs', []) or []
    workforce = roster.get('workforce_headcount')
    trips = roster.get('return_trips_per_person_per_year')

    if not legs or workforce is None or trips is None:
        gaps.append({
            'Category': 7,
            'Item': 'Roster pattern is incomplete',
            'Detail': 'Workforce headcount, return trips per person per year '
                      'and at least one leg are all required.',
        })
        return _blank_detail([]), gaps

    shares = sum(float(leg.get('share', 0.0)) for leg in legs)
    if abs(shares - 1.0) > 0.001:
        gaps.append({
            'Category': 7,
            'Item': 'Commuting leg shares do not sum to one',
            'Detail': f'The stated shares total {shares:.3f}.  The estimate is '
                      f'computed as stated and is understated or overstated by '
                      f'that difference.',
        })

    headcount = _headcount_by_year(df)
    baseline_year = roster.get('baseline_headcount_year')
    scale = {}
    if roster.get('scale_to_headcount', True) and headcount:
        if baseline_year not in headcount:
            baseline_year = min(headcount)
        base = headcount[baseline_year]
        if base > 0:
            scale = {year: value / base for year, value in headcount.items()}
    if not scale:
        gaps.append({
            'Category': 7,
            'Item': 'Commuting held flat',
            'Detail': 'No headcount series was available to scale the workforce, '
                      'so every year carries the stated headcount.',
        })

    factor = float(reference.factor_for(
        7, 'Commuting passenger vehicle', roster.get('factor_kgco2e_per_km', 0.0)))
    occupancy = float(roster.get('occupancy', 1.0) or 1.0)
    method = settings.get('method', '')

    rows = []
    for year in _operating_years(df):
        weight = scale.get(year, 1.0) if scale else 1.0
        if weight <= 0:
            continue
        people = float(workforce) * weight
        for leg in legs:
            share = float(leg.get('share', 0.0))
            one_way = leg.get('one_way_km')
            if one_way is None:
                gaps.append({
                    'Category': 7,
                    'Item': f"Commuting leg '{leg.get('name')}' has no distance",
                    'Detail': 'A one way distance is required.',
                })
                continue
            # Return trips, both directions, divided by vehicle occupancy.
            km = people * share * float(trips) * float(one_way) * 2.0 / occupancy
            rows.extend(_spread_rows(
                year, category=7, method=method,
                basis='Roster headcount and stated distance',
                group=leg.get('name'), quantity=km, uom='vehicle km',
                factor=factor, factor_unit='kg CO2-e per km',
                factor_source=roster.get('factor_source'),
                tco2e=km * factor / KG_PER_TONNE_CO2E))

    return _blank_detail(rows), gaps


# ---------------------------------------------------------------------
# CATEGORY 10 - PROCESSING OF SOLD PRODUCTS
# ---------------------------------------------------------------------

def _category_10(df, reference, rates):
    """Refining of dore, on gold sold and a published refining intensity."""
    settings = reference.config.get('category_10', {}) or {}
    gaps: List[Dict[str, Any]] = []
    if not settings.get('applies', True):
        return _blank_detail([]), gaps

    intensity = reference.factor_for(
        10, 'Gold refining', settings.get('refining_intensity_kgco2e_per_kg_au'))
    if intensity is None:
        gaps.append({
            'Category': 10,
            'Item': 'Refining intensity not supplied',
            'Detail': 'Gold mass is in the model; the refiner intensity per '
                      'kilogram is not, so nothing is charged.',
        })
        return _blank_detail([]), gaps

    subactivity = settings.get('gold_subactivity', 'Gold Sold')
    gold = df[df['SubActivity'].astype(str) == subactivity]
    if gold.empty:
        gaps.append({
            'Category': 10,
            'Item': f"No '{subactivity}' line in the physicals",
            'Detail': 'Category 10 cannot be scaled without the gold measure.',
        })
        return _blank_detail([]), gaps

    annual = gold.groupby('Year', observed=True)['Quantity'].sum()
    rows = []
    for year, ounces in annual.items():
        kilograms = float(ounces) * TROY_OUNCE_KG
        rows.extend(_spread_rows(
            int(year), category=10, method=settings.get('method', ''),
            basis='Gold mass times refining intensity', group='Gold refining',
            quantity=kilograms, uom='kg Au', factor=float(intensity),
            factor_unit='kg CO2-e per kg Au',
            factor_source=settings.get('factor_source'),
            tco2e=kilograms * float(intensity) / KG_PER_TONNE_CO2E))
    return _blank_detail(rows), gaps


# ---------------------------------------------------------------------
# AGGREGATION AND REPORTING
# ---------------------------------------------------------------------

def _annual(detail, year_column):
    """Year by category, with upstream, downstream and total columns."""
    if detail.empty:
        return pd.DataFrame()

    pivot = detail.pivot_table(index=year_column, columns='Category',
                               values='tCO2e', aggfunc='sum', fill_value=0.0)
    for category in CATEGORY_NAMES:
        if category not in pivot.columns:
            pivot[category] = 0.0
    pivot = pivot[sorted(pivot.columns)]
    pivot.columns = [f'Cat{c}' for c in pivot.columns]
    pivot['Upstream'] = pivot[[f'Cat{c}' for c in UPSTREAM]].sum(axis=1)
    pivot['Downstream'] = pivot[[f'Cat{c}' for c in DOWNSTREAM]].sum(axis=1)
    pivot['Total'] = pivot['Upstream'] + pivot['Downstream']
    return pivot.reset_index().rename(columns={year_column: 'Year'})


def _exclusions(config):
    """The documented exclusion register, as a frame."""
    excluded = config.get('exclusions', {}) or {}
    rows = [{
        'Category': int(category),
        'CategoryName': CATEGORY_NAMES.get(int(category), ''),
        'Rationale': ' '.join(str(rationale).split()),
    } for category, rationale in excluded.items()]
    if not rows:
        return pd.DataFrame(columns=['Category', 'CategoryName', 'Rationale'])
    return pd.DataFrame(rows).sort_values('Category').reset_index(drop=True)


def _coverage(df, detail, reference):
    """How much recorded expenditure reached a factor, and what did not."""
    coverage: Dict[str, Any] = {}

    if 'Value' in df.columns:
        actual = df[df['DataSet'] == 'Actual']
        recorded = float(actual['Value'].sum())
        priced = float(detail.loc[
            (detail['Category'] == 1)
            & (detail['Basis'] == 'Spend, recorded'), 'Spend_AUD'].sum())

        # Fuels are charged as Scope 1 combustion and Category 3 well to tank,
        # so their spend is deliberately outside the Category 1 base.  Naming
        # it separately keeps the coverage figure honest.
        register = reference.category_1_factors()
        excluded_codes = set(register.index[register['Excluded']])
        by_design = float(actual.loc[
            actual['ProductGroup'].astype(str).isin(excluded_codes), 'Value'].sum())

        coverage['recorded_spend_aud'] = recorded
        coverage['excluded_by_design_aud'] = by_design
        coverage['priced_spend_aud'] = priced
        coverage['unpriced_spend_aud'] = recorded - by_design - priced
        base = recorded - by_design
        coverage['priced_share_of_assessable'] = (priced / base) if base else 0.0
        coverage['priced_share_pct'] = coverage['priced_share_of_assessable'] * 100.0

    supplier = reference.supplier_spend
    if not supplier.empty and 'Spend_AUD' in supplier.columns:
        coverage['accounts_payable_aud'] = float(
            pd.to_numeric(supplier['Spend_AUD'], errors='coerce').fillna(0).sum())

    coverage['registers_missing'] = list(reference.errors)
    return coverage


def _projection_note(config):
    projection = config.get('projection', {}) or {}
    if projection.get('basis') == 'none':
        return ('Forward projection is off; the spend based categories cover '
                'the recorded period only.')
    return (f"Spend based categories are projected on a dollar per reporting "
            f"unit rate fitted over {projection.get('rate_window_from')} to "
            f"{projection.get('rate_window_to')} and applied to budget "
            f"quantities.  Rates are nominal.")


# ---------------------------------------------------------------------
# VIEW AGGREGATIONS
# ---------------------------------------------------------------------
# Every figure the Scope 3 tab shows is produced here.  The tab filters
# nothing, sums nothing and derives no share: it receives a frame and renders
# it.  Keeping the maths on this side means one place to test and one place an
# auditor has to read.

def year_column(year_type):
    """Column carrying the reporting year for the selected basis."""
    return 'FY' if year_type == 'FY' else 'Year'


def annual_frame(result, year_type):
    """The year by category frame for the selected basis."""
    return result.annual_fy if year_type == 'FY' else result.annual_cy


def present_categories(result):
    """Categories carrying a number, in category order."""
    if result.detail.empty:
        return []
    totals = result.detail.groupby('Category')['tCO2e'].sum()
    return [int(c) for c in sorted(totals.index) if abs(totals.loc[c]) > 0.05]


def period_detail(result, year_type, year):
    """Detail rows for one reporting year."""
    if result.detail.empty:
        return result.detail
    return result.detail[result.detail[year_column(year_type)] == year]


def headline(result, year_type, year):
    """Totals for one reporting year: upstream, downstream, total, Cat 3 share."""
    annual = annual_frame(result, year_type)
    if annual.empty:
        return None
    row = annual[annual['Year'] == year]
    if row.empty:
        return None
    row = row.iloc[0]

    total = float(row['Total'])
    cat3 = float(row.get('Cat3', 0.0))
    return {
        'upstream': float(row['Upstream']),
        'downstream': float(row['Downstream']),
        'total': total,
        'cat3': cat3,
        'cat3_share': (cat3 / total * 100.0) if total else 0.0,
    }


def category_totals(result, year_type, year):
    """One row per category carrying a number, with share and cumulative share.

    Sorted largest first.  This is the materiality screen: which categories
    carry the result and which are tail.
    """
    period = period_detail(result, year_type, year)
    columns = ['Category', 'CategoryName', 'tCO2e', 'Share', 'Cumulative']
    if period.empty:
        return pd.DataFrame(columns=columns)

    totals = period.groupby('Category')['tCO2e'].sum()
    totals = totals[totals.abs() > 0.05].sort_values(ascending=False)
    if totals.empty:
        return pd.DataFrame(columns=columns)

    grand = float(totals.sum())
    frame = pd.DataFrame({
        'Category': [int(c) for c in totals.index],
        'CategoryName': [CATEGORY_NAMES[int(c)] for c in totals.index],
        'tCO2e': totals.values,
    })
    frame['Share'] = frame['tCO2e'] / grand * 100.0 if grand else 0.0
    frame['Cumulative'] = frame['Share'].cumsum()
    return frame


def method_register(result, year_type, year):
    """Every category in the standard, with its status for the period.

    Status is one of: Assessed, Excluded, Awaiting data, or Nil for the
    period.  A category is never simply absent, so completeness is visible.
    """
    period = period_detail(result, year_type, year)

    excluded = {}
    if not result.exclusions.empty:
        excluded = dict(zip(result.exclusions['Category'],
                            result.exclusions['Rationale']))

    outstanding: Dict[int, List[str]] = {}
    for item in result.outstanding:
        outstanding.setdefault(int(item['Category']), []).append(str(item['Item']))

    rows = []
    for category in sorted(CATEGORY_NAMES):
        lines = period[period['Category'] == category] if not period.empty \
            else period
        value = float(lines['tCO2e'].sum()) if len(lines) else 0.0

        if category in excluded:
            status, detail, sources = 'Excluded', excluded[category], ''
        elif len(lines) and abs(value) > 0.05:
            status = 'Assessed'
            methods = lines['Method'].dropna().astype(str)
            detail = methods.iloc[0] if len(methods) else ''
            sources = '; '.join(sorted({
                str(s) for s in lines['FactorSource'].dropna().unique()}))
        elif category in outstanding:
            status = 'Awaiting data'
            detail = '; '.join(outstanding[category])
            sources = ''
        else:
            status, detail, sources = 'Nil for the period', '', ''

        rows.append({
            'Category': category,
            'CategoryName': CATEGORY_NAMES[category],
            'Status': status,
            'tCO2e': value,
            'Detail': detail,
            'FactorSource': sources,
        })
    return pd.DataFrame(rows)


def purchased_goods_table(result, year_type, year):
    """Category 1 by product group for one year, with share and cumulative."""
    period = period_detail(result, year_type, year)
    columns = ['Group', 'GroupDescription', 'Basis', 'Spend_AUD', 'Quantity',
               'Factor', 'FactorUnit', 'FactorSource', 'tCO2e', 'Share',
               'Cumulative']
    if period.empty:
        return pd.DataFrame(columns=columns)

    lines = period[period['Category'] == 1]
    if lines.empty:
        return pd.DataFrame(columns=columns)

    grouped = lines.groupby(['Group', 'GroupDescription', 'Basis'],
                            observed=True).agg(
        Spend_AUD=('Spend_AUD', 'sum'),
        Quantity=('Quantity', 'sum'),
        tCO2e=('tCO2e', 'sum'),
        Factor=('Factor', 'first'),
        FactorUnit=('FactorUnit', 'first'),
        FactorSource=('FactorSource', 'first'),
    ).reset_index().sort_values('tCO2e', ascending=False)

    grand = float(grouped['tCO2e'].sum())
    grouped['Share'] = grouped['tCO2e'] / grand * 100.0 if grand else 0.0
    grouped['Cumulative'] = grouped['Share'].cumsum()
    return grouped[columns]


def rate_table(result):
    """Fitted dollar per unit rates, largest expenditure first."""
    if result.rates is None or result.rates.empty:
        return pd.DataFrame()
    return result.rates.sort_values('Spend_AUD', ascending=False).reset_index(drop=True)


def outstanding_table(result):
    """Open items, ordered by category."""
    if not result.outstanding:
        return pd.DataFrame(columns=['Category', 'Item', 'Detail'])
    return pd.DataFrame(result.outstanding).sort_values(
        ['Category', 'Item']).reset_index(drop=True)


# ---------------------------------------------------------------------
# SPEND AGAINST PHYSICAL
# ---------------------------------------------------------------------
# A spend based factor is an economic average for a commodity class in the
# country the factor was published for.  The EPA set is United States
# production, and the method takes the position that manufacturing intensity
# per dollar is broadly comparable across countries for a traded commodity.
# That position holds better for some classes than others, and the way to test
# it is to divide the result by the physical quantity the same rows carry and
# compare the implied intensity against a published physical factor.
#
# This produces the comparison and states nothing about whether a given
# number is right.  A group whose implied intensity sits far from the physical
# literature is a candidate to move off dollars, which is a configuration
# change: add it to category_1.physical_unit_factors and rebuild the table.

PHYSICAL_UNITS = ('t', 'kg', 'kL', 'L', 'm3')


def implied_intensity_table(result, units=PHYSICAL_UNITS):
    """Implied tCO2-e per physical unit for every spend based group.

    Restricted to groups whose physicals carry a mass or volume unit, because
    a count of items cannot be compared with a factor per tonne without a mass
    per item.  Recorded expenditure only: a projected line inherits the same
    intensity by construction and would tell us nothing.

    Columns:
        Group, Description, UOM, Quantity, Spend_AUD, tCO2e,
        Implied_tCO2e_per_unit, AUD_per_unit, Basis, FactorSource
    """
    columns = ['Group', 'Description', 'UOM', 'Quantity', 'Spend_AUD', 'tCO2e',
               'Implied_tCO2e_per_unit', 'AUD_per_unit', 'Basis', 'FactorSource']
    detail = result.detail
    if detail.empty:
        return pd.DataFrame(columns=columns)

    lines = detail[
        (detail['Category'] == 1)
        & (detail['Basis'].astype(str).str.startswith('Spend, recorded'))
        & (detail['UOM'].astype(str).isin(units))
        & (detail['Quantity'] > 0)
    ]
    if lines.empty:
        return pd.DataFrame(columns=columns)

    grouped = lines.groupby(['Group', 'GroupDescription', 'UOM'],
                            observed=True).agg(
        Quantity=('Quantity', 'sum'),
        Spend_AUD=('Spend_AUD', 'sum'),
        tCO2e=('tCO2e', 'sum'),
        FactorSource=('FactorSource', 'first'),
    ).reset_index().rename(columns={'GroupDescription': 'Description'})

    grouped['Implied_tCO2e_per_unit'] = np.where(
        grouped['Quantity'] > 0, grouped['tCO2e'] / grouped['Quantity'], np.nan)
    grouped['AUD_per_unit'] = np.where(
        grouped['Quantity'] > 0, grouped['Spend_AUD'] / grouped['Quantity'], np.nan)
    grouped['Basis'] = 'Spend, EPA supply chain factor'

    return grouped[columns].sort_values('tCO2e', ascending=False).reset_index(drop=True)


def physical_factor_status(result):
    """Which groups are charged on a physical unit and which are still on spend.

    One row per product group carrying a factor, so the extent of the spend
    based estimate is visible rather than implied.
    """
    reference = result.reference
    if reference is None:
        return pd.DataFrame(columns=['Group', 'Description', 'Basis', 'FactorSource'])

    factors = reference.category_1_factors()
    if factors.empty:
        return pd.DataFrame(columns=['Group', 'Description', 'Basis', 'FactorSource'])

    charged = factors[~factors['Excluded']]
    return pd.DataFrame({
        'Group': charged.index,
        'Description': charged['Description'].values,
        'Basis': charged['Basis'].values,
        'FactorSource': charged['FactorSource'].values,
    }).sort_values(['Basis', 'Group']).reset_index(drop=True)


# ---------------------------------------------------------------------
# MERGE INTO THE GHG PROTOCOL VIEW
# ---------------------------------------------------------------------
# The total GHG position is Scope 1 plus Scope 2 plus the whole of Scope 3,
# not the fuel and energy related part of it alone.  This puts the remaining
# categories onto the annual frame the GHG view reads.
#
# Naming: the whole of Scope 3 is value chain emissions, which is the title of
# the standard itself, so that term cannot also name the part of Scope 3 that
# excludes Category 3.  The split here is Category 3 against the other
# categories, and it exists because the two halves have different standing,
# not because they are different kinds of emission.
#
# It is applied to the GHG frames only.  The Safeguard and NGER frames keep
# `Scope3` meaning Category 3, because that is the figure the baseline and the
# reported position are built on, and adding the rest to them would corrupt
# both.

OTHER_CATEGORIES = tuple(c for c in CATEGORY_NAMES if c != 3)


def _year_from_label(label):
    """2026 from 'FY2026' or 'CY2026', and from a bare 2026."""
    text = str(label)
    digits = ''.join(character for character in text if character.isdigit())
    return int(digits) if digits else None


def add_other_categories_to_annual(annual, result):
    """Add the Scope 3 categories other than 3 to an annual GHG frame.

    Reads the year label on the frame to decide whether the financial or the
    calendar year totals apply, so the two never cross.

    Columns added:
        Scope3_Cat3         fuel and energy related, unchanged
        Scope3_Other        categories 1, 2 and 4 to 15
        Scope3_Total        the whole of Scope 3
        Total_WithScope3    Scope 1 plus Scope 2 plus Scope3_Total

    `Scope3` and `Total` are left as they were, so anything reading them keeps
    the meaning it had.
    """
    if annual is None or annual.empty:
        return annual

    frame = annual.copy()
    label_column = 'FY' if 'FY' in frame.columns else 'Year'
    labels = frame[label_column].astype(str)
    year_type = 'FY' if labels.str.startswith('FY').any() else 'CY'

    frame['Scope3_Cat3'] = frame.get('Scope3', 0.0)
    frame['Scope3_Other'] = 0.0

    if result is not None:
        source = result.annual_fy if year_type == 'FY' else result.annual_cy
        if source is not None and not source.empty:
            columns = [f'Cat{c}' for c in OTHER_CATEGORIES
                       if f'Cat{c}' in source.columns]
            if columns:
                value_chain = source[['Year'] + columns].copy()
                value_chain['_year'] = value_chain['Year'].map(_year_from_label)
                value_chain['_value'] = value_chain[columns].sum(axis=1)
                lookup = dict(zip(value_chain['_year'], value_chain['_value']))
                frame['Scope3_Other'] = labels.map(_year_from_label).map(
                    lookup).fillna(0.0).values

    frame['Scope3_Total'] = frame['Scope3_Cat3'] + frame['Scope3_Other']
    frame['Total_WithScope3'] = (frame.get('Scope1', 0.0)
                                 + frame.get('Scope2', 0.0)
                                 + frame['Scope3_Total'])

    # Intensities restated on the inclusive total, so the GHG view's per tonne
    # and per ounce series cover the whole inventory rather than part of it.
    if 'ROM_Mt' in frame.columns:
        frame['Total_Intensity_WithScope3'] = 0.0
        mask = frame['ROM_Mt'] > 0
        frame.loc[mask, 'Total_Intensity_WithScope3'] = (
            frame.loc[mask, 'Total_WithScope3']
            / (frame.loc[mask, 'ROM_Mt'] * TONNES_PER_MEGATONNE))
    if 'Gold_oz' in frame.columns:
        frame['Gold_Intensity_WithScope3'] = 0.0
        mask = frame['Gold_oz'] > 0
        frame.loc[mask, 'Gold_Intensity_WithScope3'] = (
            frame.loc[mask, 'Total_WithScope3'] / frame.loc[mask, 'Gold_oz'])

    return frame
