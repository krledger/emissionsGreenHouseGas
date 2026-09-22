"""The source frames behind the GRI 14 export.

The GRI 14 export is for the sustainability team.  It reports the calendar
year and aligns with the GHG inventory today, but it is given its own frames
so that a change to the GHG view, or to the Safeguard tables, cannot move a
GRI figure without somebody deciding that it should.

    gri_annual   one row per calendar year: scopes, ore, gold, electricity
    gri_source   one row per month per emission source, recorded only:
                 quantity, energy and Scope 1, which is what the energy
                 disclosures and the split of Scope 1 by gas are built from

Nothing here reads a Safeguard table.  The Safeguard source table is a
financial year table for the regulator and is the wrong period for GRI.
"""

import pandas as pd

__all__ = ['build_gri_annual', 'build_gri_source', 'GRI_SOURCE_COLUMNS']

GRI_SOURCE_COLUMNS = ['Date', 'CalendarYear', 'NGAFuel', 'UOM', 'Quantity',
                      'Energy_GJ', 'Scope1_tCO2e']


def build_gri_annual(ghg_annual_cy):
    """The calendar year totals the export reads.

    A copy of the GHG calendar year frame, taken after the Scope 3
    categories are added, so gross Scope 3 is gross.
    """
    if ghg_annual_cy is None or len(ghg_annual_cy) == 0:
        return pd.DataFrame()
    return ghg_annual_cy.copy()


def build_gri_source(ghg_df, start_date=None):
    """Recorded emission sources by month, for energy and the gas split.

    Recorded rows only: a GRI disclosure reports what happened.  Explosives
    are included, with no energy content, because their detonation is part
    of gross Scope 1.
    """
    if ghg_df is None or len(ghg_df) == 0:
        return pd.DataFrame(columns=GRI_SOURCE_COLUMNS)
    fuel = ghg_df['NGAFuel'].astype(str)
    rows = ghg_df[(ghg_df['DataSet'] == 'Actual')
                  & ghg_df['NGAFuel'].notna()
                  & (fuel != '') & (fuel != 'nan')
                  & (fuel != 'Grid electricity')]
    if start_date is not None:
        rows = rows[rows['Date'] >= pd.Timestamp(start_date)]
    if rows.empty:
        return pd.DataFrame(columns=GRI_SOURCE_COLUMNS)
    rows = rows.assign(NGAFuel=rows['NGAFuel'].astype(str),
                       UOM=rows['UOM'].astype(str))
    source = rows.groupby(['Date', 'NGAFuel', 'UOM'], observed=True).agg(
        Quantity=('Quantity', 'sum'),
        Energy_GJ=('Energy_GJ', 'sum'),
        Scope1_tCO2e=('Scope1_tCO2e', 'sum'),
    ).reset_index()
    source['CalendarYear'] = source['Date'].dt.year
    return source[GRI_SOURCE_COLUMNS]
