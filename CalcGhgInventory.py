"""The GHG inventory: Scopes 1, 2 and 3 on the GHG Protocol, calendar year.

This is the basis of the financial disclosure under AASB S2.  It is a
separate pipeline from the regulatory one (NGER and the Safeguard Mechanism,
CalcSafeguard and Projections) and shares nothing with it except the pricing
of a line against a published factor, which lives in CalcNga.

Kept apart on purpose, even where the two do the same arithmetic today:

    GHG inventory                      Regulatory filing
    -------------                      -----------------
    calendar year                      financial year
    from GHG_START_DATE                from SAFEGUARD_START_DATE
    Scope 1 includes explosives        Scope 1 as NGER measures it
    Scopes 1, 2 and 3                  Scope 1 and Scope 2
    no baseline, credit or status      Section 11 baseline, credits, s58B

A change to one must not move the other.  Nothing in this module imports
CalcSafeguard or Projections, and no frame it returns carries a baseline, a
credit or a Safeguard status, so a GHG view cannot show one by accident.

Calculation:
    1. A recorded month replaces the forecast for the same month and line
       (the rule in CalcNga, applied once).
    2. Forecast lines are priced with the same function and the same
       factors as recorded lines (CalcNga.apply_emissions_to_df, on the GHG
       factor map from CalcGhg, which prices explosives like any other line).
    3. Lines are summed to months, with the physical denominators (ore,
       gold sold, site and grid electricity) taken from the same rows.
    4. Months are summed to years.  Intensity is the year's emissions over
       the year's denominator, never a mean of monthly ratios.
"""

import pandas as pd

from CalcCalendar import aggregate_by_year_type, series_to_fy
from CalcNga import (apply_emissions_to_df, merge_key_column,
                     superseded_by_actual)
from CalcUnits import KWH_PER_MWH, TONNES_PER_MEGATONNE
from Config import (
    GHG_START_DATE,
    DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE,
    DEFAULT_END_REHABILITATION_DATE, DEFAULT_GRID_CONNECTION_DATE,
    ROM_SUBACTIVITY, GOLD_SUBACTIVITY,
    SITE_ELEC_COMMONNAME, GRID_ELEC_COMMONNAME,
    get_phase_name_for_date,
)

__all__ = ['build_ghg_monthly', 'aggregate_ghg_annual', 'GHG_MONTHLY_COLUMNS']

# What a GHG monthly row carries.  Stated so a Safeguard column arriving here
# is visibly out of place.
GHG_MONTHLY_COLUMNS = [
    'Date', 'Phase',
    'Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e',
    'ROM_t', 'Gold_oz', 'Site_Electricity_kWh', 'Grid_Electricity_kWh',
]


def _price_forecast(rows, factor_map):
    """Forecast lines priced against the GHG factor map (CalcGhg).

    The factor is the one published for the financial year the month falls
    in, because that is how the factors are published.  A year past the last
    edition takes the last edition, held flat.
    """
    priced = rows.copy()
    priced['_factor_year'] = series_to_fy(priced['Date']).astype('int64')
    priced = apply_emissions_to_df(priced, factor_map, fy_col='_factor_year')
    return priced.drop(columns=['_factor_year'])


def _sum_by_month(rows, mask, name):
    picked = rows[mask].groupby('Date')['Quantity'].sum().reset_index()
    picked.columns = ['Date', name]
    return picked


def build_ghg_monthly(ghg_df,
                      start_date=GHG_START_DATE,
                      end_date=DEFAULT_END_REHABILITATION_DATE,
                      end_mining_date=DEFAULT_END_MINING_DATE,
                      end_processing_date=DEFAULT_END_PROCESSING_DATE,
                      end_rehabilitation_date=DEFAULT_END_REHABILITATION_DATE,
                      grid_connection_date=DEFAULT_GRID_CONNECTION_DATE,
                      factor_map=None):
    """One row per month of the GHG inventory, recorded then forecast.

    Args:
        ghg_df: the GHG transaction frame from CalcGhg.build_ghg_frame.

    Returns:
        DataFrame in GHG_MONTHLY_COLUMNS order, from start_date to end_date.
        Scope3_tCO2e here is Category 3 only; the other categories are added
        to the annual frames from the Scope 3 build.
    """
    if ghg_df is None or len(ghg_df) == 0:
        return pd.DataFrame(columns=GHG_MONTHLY_COLUMNS)

    recorded = ghg_df[ghg_df['DataSet'] == 'Actual']
    forecast = ghg_df[ghg_df['DataSet'] == 'Budget']

    # 1. A recorded month replaces the forecast for the same line.
    if len(recorded) and len(forecast):
        key = merge_key_column(recorded)
        forecast = forecast[~superseded_by_actual(forecast, recorded, key)]

    # 2. Price the forecast exactly as the record was priced.
    if len(forecast):
        forecast = _price_forecast(forecast, factor_map)

    lines = pd.concat([recorded, forecast], ignore_index=True)
    lines = lines[(lines['Date'] >= pd.Timestamp(start_date))
                  & (lines['Date'] <= pd.Timestamp(end_date))]
    if lines.empty:
        return pd.DataFrame(columns=GHG_MONTHLY_COLUMNS)

    # 3. Lines to months.  Numerators and denominators from the same rows,
    #    so an intensity always covers one set of months.
    monthly = lines.groupby('Date').agg(
        Scope1_tCO2e=('Scope1_tCO2e', 'sum'),
        Scope2_tCO2e=('Scope2_tCO2e', 'sum'),
        Scope3_tCO2e=('Scope3_tCO2e', 'sum'),
    ).reset_index()

    sub = lines['SubActivity'].astype(str)
    common = lines['CommonName'].astype(str)
    for mask, name in (
            (sub == ROM_SUBACTIVITY, 'ROM_t'),
            (sub == GOLD_SUBACTIVITY, 'Gold_oz'),
            (common == SITE_ELEC_COMMONNAME, 'Site_Electricity_kWh'),
            (common == GRID_ELEC_COMMONNAME, 'Grid_Electricity_kWh')):
        monthly = monthly.merge(_sum_by_month(lines, mask, name),
                                on='Date', how='left')
        monthly[name] = monthly[name].fillna(0.0)

    monthly['Phase'] = monthly['Date'].apply(
        lambda d: get_phase_name_for_date(
            d, end_mining_date, end_processing_date,
            end_rehabilitation_date, grid_connection_date))

    return monthly[GHG_MONTHLY_COLUMNS].sort_values('Date') \
        .reset_index(drop=True)


def aggregate_ghg_annual(monthly, year_type='CY'):
    """Months to years.  Calendar year is the reporting basis.

    A financial year aggregate is also available, as a control total for
    reconciling the published table on both bases.  It is not reported.
    """
    if monthly is None or monthly.empty:
        return pd.DataFrame()

    annual = aggregate_by_year_type(monthly, year_type, agg_dict={
        'Scope1_tCO2e': 'sum', 'Scope2_tCO2e': 'sum', 'Scope3_tCO2e': 'sum',
        'ROM_t': 'sum', 'Gold_oz': 'sum',
        'Site_Electricity_kWh': 'sum', 'Grid_Electricity_kWh': 'sum',
        'Phase': 'last',
    })

    # Names the views read.  'FY' is the period label column the views were
    # built around; on this frame it holds a calendar year label.
    annual['FY'] = annual['Year']
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']
    annual['Total'] = annual['Scope1'] + annual['Scope2'] + annual['Scope3']
    annual['ROM_Mt'] = annual['ROM_t'] / TONNES_PER_MEGATONNE
    annual['Grid_Electricity_MWh'] = annual['Grid_Electricity_kWh'] / KWH_PER_MWH

    # Intensity: the year's emissions over the year's denominator.
    ore = annual['ROM_t'] > 0
    gold = annual['Gold_oz'] > 0
    annual['Scope1_Intensity'] = 0.0
    annual['Total_Intensity'] = 0.0
    annual['Gold_Intensity'] = 0.0
    annual.loc[ore, 'Scope1_Intensity'] = (annual.loc[ore, 'Scope1']
                                           / annual.loc[ore, 'ROM_t'])
    annual.loc[ore, 'Total_Intensity'] = (annual.loc[ore, 'Total']
                                          / annual.loc[ore, 'ROM_t'])
    annual.loc[gold, 'Gold_Intensity'] = (annual.loc[gold, 'Total']
                                          / annual.loc[gold, 'Gold_oz'])
    return annual
