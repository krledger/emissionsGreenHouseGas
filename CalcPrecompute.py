"""
CalcPrecompute.py
Pre-compute ALL derived data once at startup.

ARCHITECTURE:
    Called once by App.py after load_all_data().
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

from Projections import build_projection
from CalcSafeguard import (
    apply_smc_transactions, smc_credit_value_analysis
)
from LoaderData import load_smc_transactions
from LoaderNga import NGAFactorsByYear
from CalcNga import build_year_factor_map
from CalcSafeguard import (
    build_safeguard_source_table, build_safeguard_production_table
)
from CalcCalendar import date_to_fy, aggregate_by_year_type, detect_year_type
from CalcGhg import build_ghg_frame
from CalcGhgCategories import build_scope3, add_other_categories_to_annual
from CalcUnits import TONNES_PER_MEGATONNE, KWH_PER_MWH


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

    # --- GHG Protocol frame (NGER + GHG-only items like explosives) ---
    # Tab 1 (GHG) uses these; Safeguard/NGER tabs use the NGER fields above.
    ghg_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    ghg_annual_fy: pd.DataFrame = field(default_factory=pd.DataFrame)
    ghg_annual_cy: pd.DataFrame = field(default_factory=pd.DataFrame)

    # --- Scope 3, all fifteen categories (Scope3Result from CalcGhgCategories) ---
    # Every GHG Protocol category except 3, which is already on the frames
    # above.  Deliberately separate: Scope 3 sits outside the Safeguard
    # baseline and the NGER position, so no tab reading those fields sees it.
    scope3: Any = None

    # Why Scope 3 is absent, where it is.  Carried so the tab can say what
    # went wrong instead of guessing at the cause.
    scope3_error: str = ''


def precompute_all(df, fsei_rom, fsei_elec,
                   start_date, end_date,
                   end_mining_date, end_processing_date, end_rehabilitation_date,
                   credit_start_date, decline_rate_phase2,
                   passphrase=None) -> PrecomputedData:
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
    # NGAFactorsByYear reads NgaFactors.csv from ./Data/ next to its module.
    nga_by_year = NGAFactorsByYear()

    unique_fy = sorted(df['FY'].unique()) if 'FY' in df.columns else []
    year_factor_map = build_year_factor_map(nga_by_year, unique_fy, state='QLD') if unique_fy else {}

    # ── 4. Safeguard source & production tables ──────────────────────
    safeguard_source = build_safeguard_source_table(df, year_factor_map) if year_factor_map else pd.DataFrame()
    prod_tables = build_safeguard_production_table(df)
    safeguard_ore = prod_tables['ore']
    safeguard_electricity = prod_tables['electricity']

    # ── 5. SMC transactions ──────────────────────────────────────────
    smc_transactions = load_smc_transactions(passphrase=passphrase)

    # ── 6. GHG Protocol frame (NGER + GHG-only items) ─────────────
    # Overlay GHG-only emissions (e.g. explosives Scope 1) onto the
    # NGER frame.  Runs a separate projection so GHG items flow through
    # to Tab 1 annual totals without affecting Safeguard / Carbon Tax.
    ghg_df = build_ghg_frame(df)
    ghg_monthly = build_projection(
        ghg_df,
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
    ghg_annual_fy = _aggregate_annual(ghg_monthly, 'FY')
    ghg_annual_cy = _aggregate_annual(ghg_monthly, 'CY')

    # ── 7. Scope 3, all fifteen categories ───────────
    # Runs on the same frame and the same horizon as the projection, so the
    # Scope 3 years line up with the Scope 1 and 2 years.  A failure here is
    # reported and does not stop the model: every other tab is independent
    # of it.
    scope3_error = ''
    try:
        scope3 = build_scope3(df, end_date=end_date)
        print(f'Scope 3: {len(scope3.detail):,} rows, '
              f'{len(scope3.outstanding)} open items')
    except Exception as exc:
        import traceback
        scope3_error = f'{type(exc).__name__}: {exc}'
        print(f'Scope 3 not computed: {scope3_error}')
        traceback.print_exc()
        scope3 = None

    # The GHG view reports the whole inventory, so the categories other than 3
    # go onto the GHG frames.  The Safeguard and NGER frames above are left
    # alone: their Scope3 column is the Category 3 figure the baseline and the
    # reported position are built on.
    ghg_annual_fy = add_other_categories_to_annual(ghg_annual_fy, scope3)
    ghg_annual_cy = add_other_categories_to_annual(ghg_annual_cy, scope3)

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
        ghg_df=ghg_df,
        ghg_annual_fy=ghg_annual_fy,
        ghg_annual_cy=ghg_annual_cy,
        scope3=scope3,
        scope3_error=scope3_error,
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

    # Gold ounces sold — denominator for the gold intensity series.
    # Guarded so older cached monthly frames without the column still work.
    if 'Gold_oz' in monthly.columns:
        agg_dict['Gold_oz'] = 'sum'

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
    annual['ROM_Mt'] = annual['ROM_t'] / TONNES_PER_MEGATONNE
    if 'Gold_oz' not in annual.columns:
        annual['Gold_oz'] = 0.0

    # Grid electricity in MWh (for carbon tax)
    if 'Grid_Electricity_kWh' in annual.columns:
        annual['Grid_Electricity_MWh'] = annual['Grid_Electricity_kWh'] / KWH_PER_MWH
    else:
        annual['Grid_Electricity_MWh'] = 0.0

    # Emission intensity columns - explicit by scope
    annual['Scope1_Intensity'] = 0.0
    annual['Total_Intensity'] = 0.0
    mask = annual['ROM_Mt'] > 0
    annual.loc[mask, 'Scope1_Intensity'] = (
        annual.loc[mask, 'Scope1'] / (annual.loc[mask, 'ROM_Mt'] * TONNES_PER_MEGATONNE)
    )
    annual.loc[mask, 'Total_Intensity'] = (
        annual.loc[mask, 'Total'] / (annual.loc[mask, 'ROM_Mt'] * TONNES_PER_MEGATONNE)
    )

    # Gold intensity: total (Scope 1+2+3) emissions per ounce of gold sold.
    # Uses the same 'Total' numerator as Total_Intensity so both series are
    # inclusive of every scope, not just the mining-phase sources.
    annual['Gold_Intensity'] = 0.0
    gold_mask = annual['Gold_oz'] > 0
    annual.loc[gold_mask, 'Gold_Intensity'] = (
        annual.loc[gold_mask, 'Total'] / annual.loc[gold_mask, 'Gold_oz']
    )
    # Legacy alias (consumers should migrate to explicit names)
    annual['Emission_Intensity'] = annual['Scope1_Intensity']

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


def get_annual(precomputed, year_type=None, start_date=None):
    """Return the correct annual DataFrame.

    Accepts either year_type ('FY'/'CY') for backward compatibility
    or start_date (datetime) which auto-detects from July=FY, Jan=CY.

    Returns a COPY so tabs can modify without affecting cached data.
    """
    if start_date is not None:
        detected = detect_year_type(start_date)
        year_type = detected if detected != 'custom' else 'CY'
    if year_type == 'FY':
        return precomputed.annual_fy.copy()
    else:
        return precomputed.annual_cy.copy()


def get_ghg_annual(precomputed, year_type=None, start_date=None):
    """Return the GHG Protocol annual DataFrame (NGER + GHG-only items).

    Same interface as get_annual() but returns the GHG frame which
    includes emissions not reportable under NGER (e.g. explosives).
    Used by Tab 1 (GHG).
    """
    if start_date is not None:
        detected = detect_year_type(start_date)
        year_type = detected if detected != 'custom' else 'CY'
    if year_type == 'FY':
        return precomputed.ghg_annual_fy.copy()
    else:
        return precomputed.ghg_annual_cy.copy()