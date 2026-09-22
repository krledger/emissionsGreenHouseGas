"""The GHG transaction frame, and the factors that price it.

The GHG Protocol counts every direct emission.  Most of them are fuels, and
fuels are priced from the National Greenhouse Accounts factors.  Some sources
are not fuels and carry no factor there: detonation of explosives is the one
at this operation.  Such a source is not a special case.  Its quantity is in
the activity data like any other line, its factor is a row in the factor
register (Reference/Factors.csv) like any other factor, and it is priced by
the same function, with the same unit conversion and the same unit check, as
diesel is.

What is declared, and where:

    the quantity     ActivityActual.csv and ActivityForecast.csv, from PrepData
    the factor       Reference/Factors.csv, one row, editable nowhere else
    which factor     Config.GHG_SOURCE_FACTORS: emission source -> factor key
    the pricing      CalcNga.apply_emissions_to_df, shared with every fuel

These sources are outside NGER and the Safeguard Mechanism, because those
schemes reach only what the Measurement Determination measures.  The
regulatory pipeline never sees this module: it prices its own frame against
the National Greenhouse Accounts factors alone, so a GHG source cannot enter
a regulatory figure.  The flags on the published table state, per row, which
framework a figure counts towards.
"""

import logging

import pandas as pd

import LoaderFactorTable
from CalcNga import (UNIT_GAP_COLUMN, apply_emissions_to_df,
                     build_year_factor_map)
from CalcUnits import KG_PER_TONNE_CO2E
from Config import GHG_SOURCE_FACTORS

logger = logging.getLogger(__name__)

__all__ = ['build_ghg_frame', 'build_ghg_factor_map', 'ghg_source_records']


def _per_unit(unit_text, value):
    """(kg CO2-e per unit, unit) from a register unit and value.

    The register states a factor as 't CO2-e per t' or 'kg CO2-e/kL'.  The
    pricing function works in kilograms per unit, as the National Greenhouse
    Accounts publish, so a factor stated in tonnes is carried to kilograms.
    """
    text = str(unit_text).strip()
    if ' per ' in text:
        numerator, denominator = text.split(' per ', 1)
    elif '/' in text:
        numerator, denominator = text.split('/', 1)
    else:
        raise ValueError(f"Factor unit '{text}' names no denominator.")
    scale = KG_PER_TONNE_CO2E if numerator.strip().lower().startswith('t ') \
        else 1.0
    return float(value) * scale, denominator.strip()


def ghg_source_records(years, register=None):
    """{year: {source: factor record}} for the sources NGA does not price.

    Read from the factor register.  A source named in GHG_SOURCE_FACTORS
    whose factor is missing from the register stops the build: a source that
    silently prices at nothing understates Scope 1, and nobody would see it.
    """
    register = LoaderFactorTable.load() if register is None else register
    records = {}
    for year in years:
        records[int(year)] = {}
        for source, key in GHG_SOURCE_FACTORS.items():
            row = LoaderFactorTable.resolve(register, key, int(year))
            value = LoaderFactorTable.value_for(row, 'Scope1')
            if row is None or value is None:
                raise ValueError(
                    f"No Scope 1 factor for '{source}' in Reference/"
                    f"Factors.csv under the key '{key}'.")
            per_unit, unit = _per_unit(row['Unit'], value)
            release = row.get('Release')
            release = '' if pd.isna(release) else str(int(float(release)))
            records[int(year)][source] = {
                's1': per_unit, 's2': 0, 's3': 0, 'energy': 0,
                'expected_uom': unit,
                # Where the figure came from, for the published table.
                'factor_source': ' '.join(
                    part for part in (str(row['Source']), release) if part)
                    + ', ' + str(row['Name']),
                'factor_year': release,
            }
    return records


def build_ghg_factor_map(nga_by_year, years, state='QLD', register=None):
    """The factor map of the GHG inventory: NGA fuels and electricity, plus
    the sources the GHG Protocol counts and NGA does not price."""
    years = [int(y) for y in years]
    factor_map = build_year_factor_map(nga_by_year, years, state=state)
    for year, sources in ghg_source_records(years, register).items():
        factor_map[year].update(sources)
    return factor_map


def build_ghg_frame(df, factor_map):
    """The GHG transaction frame: every line priced in the normal course.

    Takes the priced activity frame and prices, by the shared function, the
    lines whose emission source is declared in GHG_SOURCE_FACTORS.  The input
    is not modified.  A line in a unit that cannot be carried to the unit of
    its factor is marked as a unit gap, exactly as a fuel line would be, and
    blocks publishing until it is fixed at source.
    """
    ghg_df = df.copy()
    for column in ('NGAFuel',):
        if hasattr(ghg_df[column], 'cat'):
            ghg_df[column] = ghg_df[column].astype(object)

    common = ghg_df['CommonName'].astype(str)
    mask = common.isin(list(GHG_SOURCE_FACTORS)) \
        & (ghg_df['Quantity'].abs() > 0)
    if mask.any():
        lines = ghg_df.loc[mask].copy()
        lines['NGAFuel'] = lines['CommonName'].astype(str)
        lines = apply_emissions_to_df(lines, factor_map, fy_col='FY')

        for column in ('Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e',
                       'Energy_GJ'):
            ghg_df[column] = ghg_df[column].astype('float64')
            ghg_df.loc[mask, column] = lines[column]
        ghg_df.loc[mask, 'NGAFuel'] = lines['NGAFuel']
        if UNIT_GAP_COLUMN not in ghg_df.columns:
            ghg_df[UNIT_GAP_COLUMN] = False
        ghg_df.loc[mask, UNIT_GAP_COLUMN] = lines[UNIT_GAP_COLUMN]

    ghg_df['NGAFuel'] = ghg_df['NGAFuel'].astype('category')
    return ghg_df
