"""
calc_precompute.py
Pre-compute ALL derived data once at startup.

ARCHITECTURE:
    Called once by app.py after load_all_data().
    Builds every DataFrame that any tab needs:
      - monthly projection (build_projection)
      - NGA year_factor_map (for source tables)
      - annual projections in FY and CY variants
      - safeguard source/production tables
      - carbon tax analysis (deferred — depends on sidebar inputs)
      - SMC ledger data (forecast and combined)

    Tabs receive a PrecomputedData object and only filter/render.
    No tab should import build_projection, NGAFactorsByYear, or
    build_year_factor_map directly.

    Carbon tax and SMC valuation depend on sidebar inputs (prices,
    escalation rates) so they are computed in lightweight functions
    that operate on the pre-built annual projection — not on raw data.

Last updated: 2026-03-10
"""

import os
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from projections import (
    build_projection, apply_smc_transactions, smc_credit_value_analysis
)
from loader_data import load_smc_transactions
from loader_nga import NGAFactorsByYear
from calc_emissions import (
    build_year_factor_map, build_safeguard_source_table,
    build_safeguard_production_table
)
from calc_calendar import date_to_fy, aggregate_by_year_type


@dataclass
class PrecomputedData:
    """Container for all pre-computed data passed to tabs.

    Tabs should treat this as read-only.  Filter with .copy() before
    modifying any DataFrame for display formatting.
    """

    # --- Core monthly projection (one row per month, full timeline) ---
    monthly: pd.DataFrame

    # --- Annual projections (one row per FY or CY) ---
    annual_fy: pd.DataFrame     # Aggregated by Financial Year
    annual_cy: pd.DataFrame     # Aggregated by Calendar Year

    # --- NGA factor map (for source/audit tables) ---
    year_factor_map: Dict[int, Any]

    # --- Safeguard source & production tables ---
    safeguard_source: pd.DataFrame      # Fuel source detail (Scope 1)
    safeguard_ore: pd.DataFrame         # ROM ore tonnes by grade
    safeguard_electricity: pd.DataFrame  # Electricity kWh by cost centre

    # --- SMC transactions from CSV ---
    smc_transactions: pd.DataFrame

    # --- NGA factor loader (for carbon tax Scope 2 lookup) ---
    nga_by_year: Any  # NGAFactorsByYear instance


def precompute_all(df, fsei_rom, fsei_elec,
                   start_date, end_date,
                   end_mining_date, end_processing_date, end_rehabilitation_date,
                   credit_start_date, decline_rate_phase2) -> PrecomputedData:
    """Run all heavy computation once.

    Args:
        df: Raw DataFrame from load_all_data() (monthly aggregated actuals with emissions)
        All other args: config/sidebar constants that don't change within a session

    Returns:
        PrecomputedData with everything tabs need
    """

    # ── 1. Build monthly projection (the expensive bit) ──────────────
    monthly = build_projection(
        df,
        end_mining_date=end_mining_date,
        end_processing_date=end_processing_date,
        end_rehabilitation_date=end_rehabilitation_date,
        fsei_rom=fsei_rom,
        fsei_elec=fsei_elec,
        credit_start_date=credit_start_date,
        start_date=start_date,
        end_date=end_date,
        decline_rate_phase2=decline_rate_phase2
    )

    # ── 2. Annual aggregation (FY and CY) ────────────────────────────
    annual_fy = _aggregate_annual(monthly, 'FY')
    annual_cy = _aggregate_annual(monthly, 'CY')

    # ── 3. NGA factor map (for audit/source tables) ──────────────────
    nga_folder = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(nga_folder, 'nga_factors.csv')):
        nga_folder = '.'
    nga_by_year = NGAFactorsByYear(nga_folder)

    unique_fy = sorted(df['FY'].unique()) if 'FY' in df.columns else []
    year_factor_map = build_year_factor_map(nga_by_year, unique_fy, state='QLD') if unique_fy else {}

    # ── 4. Safeguard source & production tables ──────────────────────
    safeguard_source = build_safeguard_source_table(df, year_factor_map) if year_factor_map else pd.DataFrame()
    prod_tables = build_safeguard_production_table(df)
    safeguard_ore = prod_tables['ore']
    safeguard_electricity = prod_tables['electricity']

    # ── 5. SMC transactions ──────────────────────────────────────────
    smc_transactions = load_smc_transactions()

    return PrecomputedData(
        monthly=monthly,
        annual_fy=annual_fy,
        annual_cy=annual_cy,
        year_factor_map=year_factor_map,
        safeguard_source=safeguard_source,
        safeguard_ore=safeguard_ore,
        safeguard_electricity=safeguard_electricity,
        smc_transactions=smc_transactions,
        nga_by_year=nga_by_year,
    )


# ─────────────────────────────────────────────────────────────────────
# ANNUAL AGGREGATION (shared logic, replaces prepare_annual_for_*)
# ─────────────────────────────────────────────────────────────────────

def _aggregate_annual(monthly, year_type='FY'):
    """Aggregate monthly projection to annual with all columns tabs need.

    Replaces prepare_annual_for_display, prepare_annual_for_safeguard,
    and prepare_annual_for_tax — they were 90% identical.

    Args:
        monthly: Monthly DataFrame from build_projection()
        year_type: 'FY' or 'CY'

    Returns:
        Annual DataFrame with standardised column names
    """
    agg_dict = {
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum',
        'ROM_t': 'sum',
    }

    # Optional columns — include if present
    optional_sum = ['Site_Electricity_kWh', 'Grid_Electricity_kWh',
                    'Baseline', 'SMC_Monthly', 'Baseline_Unfloored']
    optional_last = ['Phase', 'SMC_Cumulative', 'In_Safeguard',
                     'Exit_FY', 'SMC_Phase']
    optional_mean = ['Baseline_Intensity', 'Emission_Intensity']

    for col in optional_sum:
        if col in monthly.columns:
            agg_dict[col] = 'sum'
    for col in optional_last:
        if col in monthly.columns:
            agg_dict[col] = 'last'
    for col in optional_mean:
        if col in monthly.columns:
            agg_dict[col] = 'mean'

    annual = aggregate_by_year_type(monthly, year_type, agg_dict=agg_dict)

    # ── Compatibility columns (tabs expect these names) ──
    annual['FY'] = annual['Year']
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']
    annual['Total'] = annual['Scope1'] + annual['Scope2'] + annual['Scope3']
    annual['ROM_Mt'] = annual['ROM_t'] / 1_000_000

    # Grid electricity in MWh (for carbon tax)
    if 'Grid_Electricity_kWh' in annual.columns:
        annual['Grid_Electricity_MWh'] = annual['Grid_Electricity_kWh'] / 1000.0
    else:
        annual['Grid_Electricity_MWh'] = 0.0

    # Recalculate emission intensity from annual totals
    annual['Emission_Intensity'] = 0.0
    mask = annual['ROM_Mt'] > 0
    annual.loc[mask, 'Emission_Intensity'] = (
        annual.loc[mask, 'Scope1'] / (annual.loc[mask, 'ROM_Mt'] * 1_000_000)
    )

    # SMC annual from monthly sum
    if 'SMC_Monthly' in annual.columns:
        annual['SMC_Annual'] = annual['SMC_Monthly']
    elif 'SMC_Annual' not in annual.columns:
        annual['SMC_Annual'] = 0.0

    # Ensure electricity columns exist
    for col in ['Site_Electricity_kWh', 'Grid_Electricity_kWh']:
        if col not in annual.columns:
            annual[col] = 0

    if 'Phase' not in annual.columns:
        annual['Phase'] = 'Unknown'

    return annual


# ─────────────────────────────────────────────────────────────────────
# LIGHTWEIGHT POST-COMPUTATION (sidebar-dependent, runs fast)
# ─────────────────────────────────────────────────────────────────────

def build_safeguard_projection(precomputed, year_type,
                               credit_start_fy, carbon_credit_price,
                               credit_escalation):
    """Build the annual safeguard projection with SMC transactions and valuation.

    Fast — operates on pre-aggregated annual data, no raw data processing.

    Args:
        precomputed: PrecomputedData
        year_type: 'FY' or 'CY' (Safeguard always forces FY)
        credit_start_fy: First FY credits earned
        carbon_credit_price: Initial SMC price
        credit_escalation: Annual escalation rate (decimal)

    Returns:
        Annual projection DataFrame with SMC values applied
    """
    # Safeguard always uses FY
    annual = precomputed.annual_fy.copy()

    # Apply registry transactions (issuances, sales, surrenders)
    if not precomputed.smc_transactions.empty:
        annual = apply_smc_transactions(annual, precomputed.smc_transactions)

    # Apply credit value escalation
    annual = smc_credit_value_analysis(
        annual, credit_start_fy, carbon_credit_price, credit_escalation
    )

    return annual


def build_carbon_tax_projection(precomputed, year_type,
                                tax_start_fy, tax_rate, tax_escalation,
                                include_scope2=False, state='QLD',
                                ef2_decline_rate=0.05):
    """Build carbon tax analysis from pre-computed annual data.

    Fast — no raw data processing.  Scope 2 EF lookup uses the
    pre-loaded NGAFactorsByYear instance.

    Args:
        precomputed: PrecomputedData
        year_type: 'FY' or 'CY'
        tax_start_fy: First FY tax applies
        tax_rate: Initial rate $/tCO2-e
        tax_escalation: Annual escalation (decimal)
        include_scope2: Include electricity pass-through (sensitivity)
        state: NEM state for EF2 lookup
        ef2_decline_rate: Annual grid decarbonisation rate

    Returns:
        Annual DataFrame with tax columns
    """
    from projections import carbon_tax_analysis

    annual = precomputed.annual_fy.copy() if year_type == 'FY' else precomputed.annual_cy.copy()

    return carbon_tax_analysis(
        annual, tax_start_fy, tax_rate, tax_escalation,
        nga_by_year=precomputed.nga_by_year if include_scope2 else None,
        state=state,
        ef2_decline_rate=ef2_decline_rate
    )


def get_annual(precomputed, year_type):
    """Return the correct annual DataFrame for the given year_type.

    Returns a COPY so tabs can modify without affecting cached data.
    """
    if year_type == 'FY':
        return precomputed.annual_fy.copy()
    else:
        return precomputed.annual_cy.copy()
