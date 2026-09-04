"""
Projections.py
Build monthly projections from consolidated emissions data
Last updated: 2026-03-26

ARCHITECTURE:
    - Consolidated CSV contains all adjustments pre-baked (ROM ratios, processing
      ratios, grid connection transfer, phase multipliers)
    - No runtime adjustments to quantities — data file is the single source of truth
    - Baseline calculated per Section 11 hybrid formula with LINEAR ERC decline
    - Monthly granularity throughout; FY/CY aggregation happens at display time in tabs

Data flow:
    1. Separate actuals and budget from consolidated CSV
    2. Merge: actuals take precedence per (Date, MatchKey)
       MatchKey = SubActivity, constructed by LoaderData.py
       Budget Identifier (Budget|SubActivity|CostCentre) is keyed on same dimension
    3. Calculate emissions from quantities as-is
    4. Aggregate to monthly summary
    5. Calculate safeguard metrics (Section 11 baseline, SMC, exit/opt-in)
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

from Config import (
    NGER_FY_START_MONTH,
    CREDIT_START_DATE, SAFEGUARD_START_DATE,
    FSEI_ROM, FSEI_ELEC, SITE_GENERATION_RATIO,
    DEFAULT_INDUSTRY_EI_ROM, DEFAULT_INDUSTRY_EI_ELEC,
    SAFEGUARD_MINIMUM_BASELINE, SAFEGUARD_THRESHOLD, SAFEGUARD_FINAL_FY,
    GRID_SITE_ELEC_DESCRIPTION, GRID_GRID_ELEC_DESCRIPTION,
    DIESEL_TRANSPORT_COSTCENTRES, DIESEL_TRANSPORT_NGAFUEL,
    ROM_SUBACTIVITY, GOLD_SUBACTIVITY, SITE_ELEC_COMMONNAME, GRID_ELEC_COMMONNAME,
    DECLINE_RATE_PHASE1, DECLINE_RATE_PHASE2,
    DECLINE_PHASE1_START, DECLINE_PHASE1_END, DECLINE_PHASE2_START, DECLINE_PHASE2_END,
    DEFAULT_GRID_CONNECTION_DATE, DEFAULT_START_DATE,
    DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE, DEFAULT_END_REHABILITATION_DATE,
    get_transition_proportion, get_phase_name_for_date,
    S58B_EARLIEST_FY, S58B_LOOKBACK, S58B_MIN_COVERED,
)
from CalcCalendar import date_to_fy, series_to_fy, fy_to_date_range
from LoaderNga import NGAFactorsByYear
from CalcNga import (build_year_factor_map, apply_emissions_to_df,
                           merge_key_column, superseded_by_actual)
from CalcUnits import KWH_PER_MWH
from CalcSafeguard import calculate_safeguard_metrics


# =============================================================================
# MAIN PROJECTION BUILDER
# =============================================================================


def build_projection(df, dataset='Actual',
                     end_mining_date=DEFAULT_END_MINING_DATE,
                     end_processing_date=DEFAULT_END_PROCESSING_DATE,
                     end_rehabilitation_date=DEFAULT_END_REHABILITATION_DATE,
                     fsei_rom=FSEI_ROM,
                     fsei_elec=FSEI_ELEC,
                     credit_start_date=CREDIT_START_DATE,
                     start_date=DEFAULT_START_DATE,
                     end_date=DEFAULT_END_REHABILITATION_DATE,
                     decline_rate_phase2=None):
    """Build monthly projection combining actuals with budget data.

    All quantity adjustments (ROM ratios, processing ratios, grid connection
    transfer) are pre-baked into the consolidated CSV.  This function reads
    quantities as-is, calculates emissions, and builds safeguard metrics.

    Returns:
        Monthly DataFrame with columns: Date, Scope1_tCO2e, Scope2_tCO2e,
        Scope3_tCO2e, ROM_t, Site_Electricity_kWh, Grid_Electricity_kWh,
        Phase, Baseline, SMC_Monthly, SMC_Cumulative, etc.
    """

    print(f"\n{'='*80}")
    print(f"BUILDING PROJECTION: {dataset}")
    print(f"{'='*80}")

    # ---- Step 1: Separate actuals and budget ----
    actuals = df[df['DataSet'] == dataset].copy()
    budget = df[df['DataSet'] == 'Budget'].copy()

    if len(actuals) == 0:
        print(f"No actuals found for dataset: {dataset}")
        return pd.DataFrame()
    if len(budget) == 0:
        print(f"No budget data found")
        return pd.DataFrame()

    print(f"Actuals: {len(actuals)} records")
    print(f"Budget: {len(budget)} records")

    # ---- Step 2: Merge -- actuals take precedence per (Date, MatchKey) ----
    # MatchKey (= SubActivity) is the merge dimension constructed by LoaderData.py.
    # It is the same field that the budget Identifier is structured around:
    #   Budget Identifier = Budget|SubActivity|CostCentre
    # When actuals exist for a (Date, MatchKey) pair, ALL budget rows for that
    # pair are excluded — preventing double-counting in the overlap period.
    merge_col = merge_key_column(actuals)
    budget_fill = budget[
        ~superseded_by_actual(budget, actuals, merge_col)
    ].copy()

    # Log Identifier coverage for traceability
    if 'Identifier' in budget_fill.columns:
        budget_ids = budget_fill['Identifier'].nunique()
        print(f"Budget Identifiers in projection: {budget_ids} unique keys")

    last_actual_date = actuals['Date'].max()
    print(f"Last actual data: {last_actual_date.strftime('%Y-%m')}")
    print(f"Budget fill rows: {len(budget_fill)} (gaps + future)")

    # ---- Step 3: Calculate emissions for budget rows ----
    print(f"Calculating emissions for budget data...")
    nga_by_year = NGAFactorsByYear()
    budget_prime = recalculate_emissions(budget_fill, nga_by_year)

    # ---- Step 4: Combine actuals + budget ----
    monthly = pd.concat([actuals, budget_prime], ignore_index=True)
    print(f"Combined: {len(actuals)} actuals + {len(budget_prime)} budget = {len(monthly)} total")

    # ---- Step 5: Aggregate to monthly summary (one row per month) ----
    monthly_summary = aggregate_to_monthly(monthly)
    print(f"Monthly summary: {len(monthly_summary)} months")
    print(f"ROM range: {monthly_summary['ROM_t'].min():.0f} to {monthly_summary['ROM_t'].max():.0f} t/month")

    # ---- Step 6: Calculate safeguard metrics ----
    print(f"Calculating safeguard metrics (Section 11 hybrid baseline)...")
    monthly_summary = calculate_safeguard_metrics(
        monthly_summary, fsei_rom, fsei_elec, credit_start_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        decline_rate_phase2
    )

    print(f"\n{'='*80}")
    print(f"PROJECTION COMPLETE: {len(monthly_summary)} months")
    print(f"Date range: {monthly_summary['Date'].min().strftime('%Y-%m')} to {monthly_summary['Date'].max().strftime('%Y-%m')}")
    print(f"{'='*80}\n")

    return monthly_summary

# =============================================================================
# EMISSIONS RECALCULATION
# =============================================================================


def recalculate_emissions(data, nga_by_year):
    """Recalculate emissions from adjusted quantities.

    Uses shared build_year_factor_map + apply_emissions_to_df from CalcNga.py
    to ensure identical calculation logic between actuals and budget.
    """
    result = data.copy()
    result['FY_temp'] = series_to_fy(result['Date']).astype('int64')
    unique_years = result['FY_temp'].unique()
    year_factor_map = build_year_factor_map(nga_by_year, unique_years, state='QLD')
    result = apply_emissions_to_df(result, year_factor_map, fy_col='FY_temp')
    result = result.drop(columns=['FY_temp'])
    return result


# =============================================================================
# MONTHLY AGGREGATION
# =============================================================================


def aggregate_to_monthly(monthly):
    """Aggregate detailed rows to one row per month.

    Extracts ROM tonnes, gold ounces, site/grid electricity, and sums
    scope emissions.
    """
    # ROM tonnes: SubActivity == 'Ore ROM' (2026-03 CSV restructure)
    # Previously matched CostCentre == 'ROM' but actuals now use CostCentre == 'Hauling'
    # while budget retains CostCentre == 'ROM'.  SubActivity is the reliable key.
    rom_mask = (monthly['SubActivity'].astype(str) == ROM_SUBACTIVITY)
    rom_data = monthly[rom_mask].groupby('Date')['Quantity'].sum().reset_index()
    rom_data.columns = ['Date', 'ROM_t']

    # Gold ounces: SubActivity == 'Gold Sold' (UOM = oz in both CSVs).
    # Extracted here, from the SAME de-duplicated actual+budget frame that
    # produces the emissions totals, so the intensity numerator and
    # denominator always cover an identical set of months.  Deriving gold
    # separately from the raw df applied a different de-duplication rule and
    # silently dropped every budget year.
    gold_mask = (monthly['SubActivity'].astype(str) == GOLD_SUBACTIVITY)
    gold_data = monthly[gold_mask].groupby('Date')['Quantity'].sum().reset_index()
    gold_data.columns = ['Date', 'Gold_oz']

    # Site and grid electricity via CommonName (set by LookupIdentifiers.py)
    # CommonName == 'Site electricity' captures all site generation entries
    # CommonName == 'Grid electricity' captures Grid Power + Residential + Warehouse + Water Delivery
    site_elec = monthly[monthly['CommonName'].astype(str) == SITE_ELEC_COMMONNAME].groupby('Date')['Quantity'].sum().reset_index()
    site_elec.columns = ['Date', 'Site_Electricity_kWh']

    grid_elec = monthly[monthly['CommonName'].astype(str) == GRID_ELEC_COMMONNAME].groupby('Date')['Quantity'].sum().reset_index()
    grid_elec.columns = ['Date', 'Grid_Electricity_kWh']

    # Scope emissions
    emissions = monthly.groupby('Date').agg({
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum'
    }).reset_index()

    # Merge all
    result = emissions.merge(rom_data, on='Date', how='left')
    result = result.merge(gold_data, on='Date', how='left')
    result = result.merge(site_elec, on='Date', how='left')
    result = result.merge(grid_elec, on='Date', how='left')

    # Fill NaN
    result['ROM_t'] = result['ROM_t'].fillna(0)
    result['Gold_oz'] = result['Gold_oz'].fillna(0)
    result['Site_Electricity_kWh'] = result['Site_Electricity_kWh'].fillna(0)
    result['Grid_Electricity_kWh'] = result['Grid_Electricity_kWh'].fillna(0)

    return result


# =============================================================================
# SECTION 11 BASELINE CALCULATION
# =============================================================================
# Baseline = ERC \u00d7 \u03a3p [(h \u00d7 EI_p + (1\u2212h) \u00d7 EIF_p) \u00d7 Q_p]
#
# Calculated on FY boundaries:
#   - ERC and hybrid EI are constant within an FY (per legislation)
#   - Monthly values are summed to FY totals for baseline, then distributed
#     back to months for SMC tracking
#
# Minimum baseline floor: 100,000 tCO2-e per CER rule (annual)
# =============================================================================


# =============================================================================
# SAFEGUARD METRICS
# =============================================================================


# =============================================================================
# SUPPORT FUNCTIONS
# =============================================================================


# =============================================================================
# FINANCIAL ANALYSIS FUNCTIONS
# =============================================================================


