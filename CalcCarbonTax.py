"""The carbon price scenario.

A price per tonne, a year it starts, and an escalation.  Scope 1 always;
Scope 2 only where the scenario asks for it, and then at a grid factor that
declines as the grid decarbonises.

This is a scenario and not a liability.  Nothing here is legislated, and the
figures it produces are what the price would cost at the emissions the model
projects, which is a different question from what the facility will owe.
"""

import numpy as np
import pandas as pd

from CalcCalendar import date_to_fy
from CalcUnits import KWH_PER_MWH
from Config import (NGER_FY_START_MONTH, DEFAULT_TAX_RATE,
                    DEFAULT_TAX_ESCALATION, DEFAULT_EF2_DECLINE_RATE)

def carbon_tax_analysis(projection, tax_start_fy, tax_rate_initial, tax_escalation_rate,
                        nga_by_year=None, state='QLD', ef2_decline_rate=0.05):
    """Calculate carbon tax liability per year — Scope 1 + Scope 2.

    Scope 1: Direct tax on facility emissions
        S1_Tax = Scope1_tCO2e × Tax_Rate

    Scope 2: Carbon cost pass-through on grid electricity
        S2_Tax = Grid_MWh × Tax_Rate × NGA_EF2 (tCO2e/MWh)

    The NGA Scope 2 emission factor is the published state-level grid
    intensity from NGA Factors Table 1.  It converts the per-tonne carbon
    rate into a per-MWh electricity cost — this is the pass-through
    mechanism by which a carbon tax on generators flows to consumers.

    The tax stacks on top of existing Safeguard Mechanism pass-through
    already embedded in electricity prices.  This calculates the additional
    carbon tax component only.

    Args:
        projection: Annual DataFrame from prepare_annual_for_tax()
                    Must contain: Year, Scope1
                    Optional: Grid_Electricity_kWh or Grid_Electricity_MWh
        tax_start_fy: First FY the tax applies (int, e.g. 2031)
        tax_rate_initial: Starting tax rate ($/tCO2-e)
        tax_escalation_rate: Annual escalation as decimal (e.g. 0.05 = 5%)
        nga_by_year: NGAFactorsByYear instance for Scope 2 EF lookup.
                     If None, Scope 2 tax columns are zero (backwards compat).
        state: NEM state for electricity emission factor (default 'QLD')
        ef2_decline_rate: Annual decline in grid emission factor for years
                          beyond last published NGA value (default 0.05 = 5%)

    Returns:
        DataFrame with columns:
            Tax_Rate, Tax_S1_Annual, Tax_S2_Annual, Tax_Annual,
            Tax_S1_Cumulative, Tax_S2_Cumulative, Tax_Cumulative,
            Grid_MWh, NGA_EF2, S2_Cost_per_MWh
    """
    result = projection.copy()
    result['FY_num'] = result['Year'].str.extract(r'(\d+)')[0].astype(int)

    # --- Tax rate schedule ---
    result['Tax_Rate'] = 0.0
    mask = result['FY_num'] >= tax_start_fy
    years = result.loc[mask, 'FY_num'] - tax_start_fy
    result.loc[mask, 'Tax_Rate'] = tax_rate_initial * ((1 + tax_escalation_rate) ** years)

    # --- Grid electricity in MWh ---
    if 'Grid_Electricity_MWh' in result.columns:
        result['Grid_MWh'] = result['Grid_Electricity_MWh']
    elif 'Grid_Electricity_kWh' in result.columns:
        result['Grid_MWh'] = result['Grid_Electricity_kWh'] / KWH_PER_MWH
    else:
        result['Grid_MWh'] = 0.0

    # --- NGA Scope 2 emission factor per year ---
    # kgCO2-e/kWh is numerically equal to tCO2-e/MWh
    # For years beyond last published NGA factor, apply annual decline rate
    # to reflect grid decarbonisation (renewables displacing fossil generation)
    result['NGA_EF2'] = 0.0
    if nga_by_year is not None:
        last_nga_year = max(nga_by_year.available_years)
        base_ef2 = nga_by_year.get_electricity_factor(last_nga_year, state, 2)
        for idx, row in result.iterrows():
            fy = int(row['FY_num'])
            ef2 = nga_by_year.get_electricity_factor(fy, state, 2)
            if ef2 is not None and fy <= last_nga_year:
                # Use published NGA factor
                result.at[idx, 'NGA_EF2'] = ef2
            elif base_ef2 is not None and fy > last_nga_year:
                # Decline from last published value
                years_beyond = fy - last_nga_year
                result.at[idx, 'NGA_EF2'] = base_ef2 * ((1 - ef2_decline_rate) ** years_beyond)

    # --- Scope 2 cost per MWh (rate × emission factor) ---
    result['S2_Cost_per_MWh'] = result['Tax_Rate'] * result['NGA_EF2']

    # --- Scope 1 tax ---
    result['Tax_S1_Annual'] = 0.0
    result.loc[mask, 'Tax_S1_Annual'] = result.loc[mask, 'Scope1'] * result.loc[mask, 'Tax_Rate']

    # --- Scope 2 tax (electricity pass-through) ---
    result['Tax_S2_Annual'] = 0.0
    result.loc[mask, 'Tax_S2_Annual'] = (
        result.loc[mask, 'Grid_MWh'] * result.loc[mask, 'S2_Cost_per_MWh']
    )

    # --- Combined annual ---
    result['Tax_Annual'] = result['Tax_S1_Annual'] + result['Tax_S2_Annual']

    # --- Cumulative ---
    result['Tax_S1_Cumulative'] = 0.0
    result['Tax_S2_Cumulative'] = 0.0
    result['Tax_Cumulative'] = 0.0
    result.loc[mask, 'Tax_S1_Cumulative'] = result.loc[mask, 'Tax_S1_Annual'].cumsum()
    result.loc[mask, 'Tax_S2_Cumulative'] = result.loc[mask, 'Tax_S2_Annual'].cumsum()
    result.loc[mask, 'Tax_Cumulative'] = result.loc[mask, 'Tax_Annual'].cumsum()

    return result

def build_carbon_tax_projection(annual, precomputed,
                                tax_start_fy=None, tax_rate=None, tax_escalation=None,
                                include_scope2=False, state='QLD',
                                ef2_decline_rate=0.05):
    """Build carbon tax analysis from annual data frame.

    Fast — no raw data processing.  Scope 2 EF lookup uses the
    pre-loaded NGAFactorsByYear instance.

    Args:
        annual: Annual projection DataFrame (selected by caller)
        precomputed: PrecomputedData (for NGA factor lookup)
        tax_start_fy: First FY tax applies
        tax_rate: Initial rate $/tCO2-e
        tax_escalation: Annual escalation (decimal)
        include_scope2: Include electricity pass-through (sensitivity)
        state: NEM state for EF2 lookup
        ef2_decline_rate: Annual grid decarbonisation rate

    Returns:
        Annual DataFrame with tax columns
    """
    from Projections import carbon_tax_analysis

    annual = annual.copy()

    return carbon_tax_analysis(
        annual, tax_start_fy, tax_rate, tax_escalation,
        nga_by_year=precomputed.nga_by_year if include_scope2 else None,
        state=state,
        ef2_decline_rate=ef2_decline_rate
    )
