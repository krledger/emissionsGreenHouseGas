"""
projections.py
Build monthly projections from consolidated emissions data
Last updated: 2026-03-09

ARCHITECTURE:
    - Consolidated CSV contains all adjustments pre-baked (ROM ratios, processing
      ratios, grid connection transfer, phase multipliers)
    - No runtime adjustments to quantities — data file is the single source of truth
    - Baseline calculated per Section 11 hybrid formula with LINEAR ERC decline
    - Monthly granularity throughout; FY/CY aggregation happens at display time in tabs

Data flow:
    1. Separate actuals and budget from consolidated CSV
    2. Merge: actuals take precedence per (Date, Description)
    3. Calculate emissions from quantities as-is
    4. Aggregate to monthly summary
    5. Calculate safeguard metrics (Section 11 baseline, SMC, exit/opt-in)
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os

from config import (
    NGER_FY_START_MONTH,
    CREDIT_START_DATE, SAFEGUARD_START_DATE,
    FSEI_ROM, FSEI_ELEC, SITE_GENERATION_RATIO,
    DEFAULT_INDUSTRY_EI_ROM, DEFAULT_INDUSTRY_EI_ELEC,
    SAFEGUARD_MINIMUM_BASELINE, SAFEGUARD_THRESHOLD,
    GRID_SITE_ELEC_DESCRIPTION, GRID_GRID_ELEC_DESCRIPTION,
    DIESEL_TRANSPORT_COSTCENTRES, DIESEL_TRANSPORT_NGAFUEL,
    DECLINE_RATE_PHASE1, DECLINE_RATE_PHASE2,
    DECLINE_PHASE1_START, DECLINE_PHASE1_END, DECLINE_PHASE2_START, DECLINE_PHASE2_END,
    DEFAULT_GRID_CONNECTION_DATE, DEFAULT_START_DATE,
    DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE, DEFAULT_END_REHABILITATION_DATE,
    get_transition_proportion, get_phase_name_for_date,
    S58B_EARLIEST_FY, S58B_LOOKBACK, S58B_MIN_COVERED,
)
from calc_calendar import date_to_fy, fy_to_date_range
from loader_nga import NGAFactorsByYear
from calc_emissions import build_year_factor_map, apply_emissions_to_df


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

    # ---- Step 2: Merge -- actuals take precedence per (Date, Description) ----
    actual_keys = set(zip(actuals['Date'], actuals['Description']))
    budget_fill = budget[
        ~budget.apply(lambda r: (r['Date'], r['Description']) in actual_keys, axis=1)
    ].copy()

    last_actual_date = actuals['Date'].max()
    print(f"Last actual data: {last_actual_date.strftime('%Y-%m')}")
    print(f"Budget fill rows: {len(budget_fill)} (gaps + future)")

    # ---- Step 3: Calculate emissions for budget rows ----
    print(f"Calculating emissions for budget data...")
    nga_folder = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(nga_folder):
        nga_folder = '/mnt/project'
    nga_by_year = NGAFactorsByYear(nga_folder)
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

    Uses shared build_year_factor_map + apply_emissions_to_df from calc_emissions.py
    to ensure identical calculation logic between actuals and budget.
    """
    result = data.copy()
    result['FY_temp'] = result['Date'].apply(date_to_fy)
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

    Extracts ROM tonnes, site/grid electricity, and sums scope emissions.
    """
    # ROM tonnes: CostCentre == 'ROM' with ore grade descriptions
    rom_mask = (
        (monthly['CostCentre'] == 'ROM') &
        (monthly['Description'].str.contains('Ore', case=False, na=False))
    )
    rom_data = monthly[rom_mask].groupby('Date')['Quantity'].sum().reset_index()
    rom_data.columns = ['Date', 'ROM_t']

    # Site and grid electricity
    site_elec = monthly[monthly['Description'] == GRID_SITE_ELEC_DESCRIPTION].groupby('Date')['Quantity'].sum().reset_index()
    site_elec.columns = ['Date', 'Site_Electricity_kWh']

    grid_elec = monthly[monthly['Description'] == GRID_GRID_ELEC_DESCRIPTION].groupby('Date')['Quantity'].sum().reset_index()
    grid_elec.columns = ['Date', 'Grid_Electricity_kWh']

    # Scope emissions
    emissions = monthly.groupby('Date').agg({
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum'
    }).reset_index()

    # Merge all
    result = emissions.merge(rom_data, on='Date', how='left')
    result = result.merge(site_elec, on='Date', how='left')
    result = result.merge(grid_elec, on='Date', how='left')

    # Fill NaN
    result['ROM_t'] = result['ROM_t'].fillna(0)
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


def calculate_erc_for_fy(fy, decline_rate_phase2=None):
    """Calculate Emissions Reduction Contribution (ERC) for a financial year.

    LINEAR decline per DCCEEW: "ERC is 0.951 in 2023-24, 0.902 in 2024-25"
    ERC = 1 - (n x decline_rate)  where n = FY - 2023

    Phase 1 (FY2024-FY2030): 4.9% p.a., linear
    Phase 2 (FY2031-FY2050): continues linearly from Phase 1 end ERC

    Key values:
        FY2024 (n=1): 0.951
        FY2025 (n=2): 0.902
        FY2030 (n=7): 0.657
        FY2031: 0.657 - 0.03285 = 0.62415
    """
    if fy < DECLINE_PHASE1_START:
        return 1.0

    # Phase 1: linear at 4.9%
    if fy <= DECLINE_PHASE1_END:
        n = fy - (DECLINE_PHASE1_START - 1)  # n=1 for FY2024
        return max(1.0 - (n * DECLINE_RATE_PHASE1), 0.0)

    # ERC at end of Phase 1
    phase1_years = DECLINE_PHASE1_END - (DECLINE_PHASE1_START - 1)  # 7
    erc_end_phase1 = 1.0 - (phase1_years * DECLINE_RATE_PHASE1)    # 0.657

    rate_p2 = decline_rate_phase2 if decline_rate_phase2 is not None else DECLINE_RATE_PHASE2

    # Phase 2: linear continuation from Phase 1 end
    if fy <= DECLINE_PHASE2_END:
        phase2_years = fy - DECLINE_PHASE1_END
        return max(erc_end_phase1 - (phase2_years * rate_p2), 0.0)

    # After FY2050: frozen at Phase 2 end value
    phase2_total = DECLINE_PHASE2_END - DECLINE_PHASE1_END  # 20
    return max(erc_end_phase1 - (phase2_total * rate_p2), 0.0)


def calculate_hybrid_ei(fy, fsei_rom, fsei_elec,
                        default_ei_rom=DEFAULT_INDUSTRY_EI_ROM,
                        default_ei_elec=DEFAULT_INDUSTRY_EI_ELEC):
    """Calculate hybrid emissions intensity for each production variable.

    Per Section 11: Hybrid_EI = h \u00d7 Default_EI + (1-h) \u00d7 FSEI
    Where h = transition proportion from get_transition_proportion()

    Returns:
        tuple: (hybrid_ei_rom, hybrid_ei_elec)
    """
    h = get_transition_proportion(fy)
    hybrid_rom = (h * default_ei_rom) + ((1 - h) * fsei_rom)
    hybrid_elec = (h * default_ei_elec) + ((1 - h) * fsei_elec)
    return hybrid_rom, hybrid_elec


def calculate_annual_baseline(fy, rom_t, site_mwh, fsei_rom, fsei_elec,
                              decline_rate_phase2=None):
    """Calculate Section 11 baseline for a financial year.

    Returns both the raw (unfloored) baseline and the floored baseline:
      - Floored: subject to s10(1) minimum of 100,000 tCO2-e
      - Unfloored: per s56(4), SMC uses baseline "as if s10(1) not enacted"

    Returns:
        tuple: (floored_baseline, unfloored_baseline) in tCO2-e
    """
    erc = calculate_erc_for_fy(fy, decline_rate_phase2)
    hybrid_rom, hybrid_elec = calculate_hybrid_ei(fy, fsei_rom, fsei_elec)

    # Section 11 formula (unfloored)
    unfloored = erc * ((hybrid_rom * rom_t) + (hybrid_elec * site_mwh))

    # s10(1) minimum baseline floor (for compliance only)
    floored = max(unfloored, SAFEGUARD_MINIMUM_BASELINE)

    return floored, unfloored


# =============================================================================
# SAFEGUARD METRICS
# =============================================================================


def calculate_safeguard_metrics(monthly, fsei_rom, fsei_elec, credit_start_date,
                                end_mining_date, end_processing_date,
                                end_rehabilitation_date,
                                decline_rate_phase2=None):
    """Calculate safeguard mechanism metrics on monthly data.

    Baseline is calculated per FY using Section 11 hybrid formula, then
    distributed to months proportionally by ROM and electricity.
    SMC credits/surrenders use three-phase model (safeguard/opt-in/exited).
    """
    result = monthly.copy()

    # Filter to Safeguard Mechanism start onwards
    result = result[result['Date'] >= SAFEGUARD_START_DATE].copy()
    if len(result) == 0:
        for col in ['Phase', 'Emission_Intensity', 'Baseline_Intensity',
                    'Baseline', 'SMC_Monthly', 'SMC_Cumulative', 'In_Safeguard']:
            result[col] = []
        return result

    # --- Phase labels ---
    result['Phase'] = result['Date'].apply(lambda d: get_phase_name_for_date(
        d, end_mining_date, end_processing_date, end_rehabilitation_date, DEFAULT_GRID_CONNECTION_DATE
    ))

    # --- Actual emission intensity (Scope 1 / ROM) ---
    result['Emission_Intensity'] = 0.0
    mask_rom = result['ROM_t'] > 0
    result.loc[mask_rom, 'Emission_Intensity'] = (
        result.loc[mask_rom, 'Scope1_tCO2e'] / result.loc[mask_rom, 'ROM_t']
    )

    # --- Section 11 baseline (calculated per FY, distributed to months) ---
    result['_fy'] = result['Date'].apply(date_to_fy)

    # Annual totals for production variables
    fy_rom = result.groupby('_fy')['ROM_t'].sum()
    fy_site_mwh = result.groupby('_fy')['Site_Electricity_kWh'].sum() / 1000  # kWh to MWh

    # Calculate annual baseline per FY (both floored and unfloored per s56(4))
    fy_baselines = {}
    fy_baselines_unfloored = {}
    for fy in sorted(result['_fy'].unique()):
        rom_annual = fy_rom.get(fy, 0)
        site_mwh_annual = fy_site_mwh.get(fy, 0)
        floored, unfloored = calculate_annual_baseline(
            fy, rom_annual, site_mwh_annual, fsei_rom, fsei_elec, decline_rate_phase2
        )
        fy_baselines[fy] = floored
        fy_baselines_unfloored[fy] = unfloored

    # Distribute annual baseline to months proportionally
    # Weight = month's (ROM contribution + electricity contribution) / FY total
    # This ensures months with more production get more baseline allocation
    result['Baseline'] = 0.0

    for fy, annual_baseline in fy_baselines.items():
        fy_mask = result['_fy'] == fy
        fy_rows = result[fy_mask]

        if len(fy_rows) == 0:
            continue

        # Monthly weights based on production share
        hybrid_rom, hybrid_elec = calculate_hybrid_ei(fy, fsei_rom, fsei_elec)
        month_rom_contrib = fy_rows['ROM_t'] * hybrid_rom
        month_elec_contrib = (fy_rows['Site_Electricity_kWh'] / 1000) * hybrid_elec
        month_total = month_rom_contrib + month_elec_contrib

        total_weight = month_total.sum()
        if total_weight > 0:
            # Distribute proportionally
            result.loc[fy_mask, 'Baseline'] = (month_total / total_weight) * annual_baseline
        else:
            # No production â€” distribute evenly across months
            n_months = len(fy_rows)
            result.loc[fy_mask, 'Baseline'] = annual_baseline / n_months

    # Distribute unfloored baseline to months (for SMC calculation per s56(4))
    result['Baseline_Unfloored'] = 0.0
    for fy, annual_baseline_uf in fy_baselines_unfloored.items():
        fy_mask = result['_fy'] == fy
        fy_rows = result[fy_mask]
        if len(fy_rows) == 0:
            continue
        hybrid_rom, hybrid_elec = calculate_hybrid_ei(fy, fsei_rom, fsei_elec)
        month_rom_contrib = fy_rows['ROM_t'] * hybrid_rom
        month_elec_contrib = (fy_rows['Site_Electricity_kWh'] / 1000) * hybrid_elec
        month_total = month_rom_contrib + month_elec_contrib
        total_weight = month_total.sum()
        if total_weight > 0:
            result.loc[fy_mask, 'Baseline_Unfloored'] = (month_total / total_weight) * annual_baseline_uf
        else:
            n_months = len(fy_rows)
            result.loc[fy_mask, 'Baseline_Unfloored'] = annual_baseline_uf / n_months

    # Baseline intensity (baseline / ROM_t, for chart display)
    result['Baseline_Intensity'] = 0.0
    mask_rom2 = result['ROM_t'] > 0
    result.loc[mask_rom2, 'Baseline_Intensity'] = (
        result.loc[mask_rom2, 'Baseline'] / result.loc[mask_rom2, 'ROM_t']
    )

    # Intensity excess (positive = above baseline)
    result['Intensity_Excess'] = result['Emission_Intensity'] - result['Baseline_Intensity']

    # --- SMC calculation (three-phase model) ---
    # Phase 1 - SAFEGUARD (Scope 1 >= 100k): credits and surrenders
    # Phase 2 - OPT-IN (below threshold, s58B rolling lookback): credits only
    # Phase 3 - EXITED: no credits or surrenders

    # Annual Safeguard status
    result['In_Safeguard'] = result.groupby('_fy')['Scope1_tCO2e'].transform('sum') >= SAFEGUARD_THRESHOLD

    # Raw SMC per s56(4): uses unfloored baseline
    # "BEN is the baseline emissions number ... as if subsection 10(1) had not been enacted"
    result['SMC_Monthly'] = 0.0
    credit_mask = result['Date'] >= credit_start_date
    result.loc[credit_mask, 'SMC_Monthly'] = (
        result.loc[credit_mask, 'Baseline_Unfloored'] - result.loc[credit_mask, 'Scope1_tCO2e']
    )

    # =========================================================================
    # SMC PHASE ASSIGNMENT
    # Four phases per legislation:
    #   Safeguard: Above 100k, credits and surrenders active
    #   Gap:       Below 100k, not yet eligible for s58B opt-in (no credits)
    #   Opt-In:    Below 100k, s58B eligible (credits only, floor at zero)
    #   Exited:    s58B lookback fails (no credits, can still trade banked)
    #
    # Phase is assigned per-FY then mapped to months.
    # Re-entry: if emissions bounce back above 100k, reverts to Safeguard.
    # =========================================================================

    # Build per-FY annual Scope 1 totals
    fy_scope1 = result.groupby('_fy')['Scope1_tCO2e'].sum()

    # Track which FYs are "covered" (above threshold) for s58B lookback
    covered_fys = set()
    for fy, s1 in fy_scope1.items():
        if s1 >= SAFEGUARD_THRESHOLD:
            covered_fys.add(fy)

    # Determine phase for each FY
    fy_phase = {}
    for fy in sorted(fy_scope1.index):
        fy_start = fy_to_date_range(fy)[0]

        if fy_start < credit_start_date:
            fy_phase[fy] = 'Pre-Safeguard'
        elif fy_scope1[fy] >= SAFEGUARD_THRESHOLD:
            # Above 100k = covered by Safeguard
            fy_phase[fy] = 'Safeguard'
        else:
            # Below 100k - check s58B eligibility
            # Condition 1: FY must be >= S58B_EARLIEST_FY (FY2029)
            # Condition 2: at least S58B_MIN_COVERED of previous S58B_LOOKBACK FYs covered
            lookback_fys = range(fy - S58B_LOOKBACK, fy)
            covered_count = sum(1 for y in lookback_fys if y in covered_fys)

            if fy >= S58B_EARLIEST_FY and covered_count >= S58B_MIN_COVERED:
                fy_phase[fy] = 'Opt-In'
            else:
                # Check if we ever were in Safeguard but lookback now fails
                any_prior_coverage = any(y in covered_fys for y in range(2024, fy))
                if any_prior_coverage and fy >= S58B_EARLIEST_FY and covered_count < S58B_MIN_COVERED:
                    fy_phase[fy] = 'Exited'
                else:
                    fy_phase[fy] = 'Gap'

    # Map FY phases to monthly rows
    result['SMC_Phase'] = result['_fy'].map(fy_phase).fillna('Pre-Safeguard')

    # Apply phase-specific SMC rules
    # Safeguard: full credits and surrenders (already calculated as Baseline - Scope1)
    # Gap: no credits, no surrenders
    gap_mask = result['SMC_Phase'] == 'Gap'
    result.loc[gap_mask, 'SMC_Monthly'] = 0.0

    # Opt-In: credits only (floor at zero, no surrenders)
    optin_mask = result['SMC_Phase'] == 'Opt-In'
    result.loc[optin_mask & (result['SMC_Monthly'] < 0), 'SMC_Monthly'] = 0.0

    # Exited: no credits, no surrenders
    exited_mask = result['SMC_Phase'] == 'Exited'
    result.loc[exited_mask, 'SMC_Monthly'] = 0.0

    # Find exit date for reporting
    exit_date = find_exit_date(result, SAFEGUARD_START_DATE)
    result['Exit_FY'] = date_to_fy(exit_date) if exit_date else None

    result['SMC_Cumulative'] = result['SMC_Monthly'].cumsum()

    # Clean up temp column
    result = result.drop(columns=['_fy'])

    return result


# =============================================================================
# SUPPORT FUNCTIONS
# =============================================================================


def find_exit_date(monthly, safeguard_start_date):
    """Find first date when annual Scope 1 drops below 100,000 tCO2-e.

    Handles re-entry: if emissions bounce back above threshold, exit resets.
    """
    monthly['_fy_exit'] = monthly['Date'].apply(date_to_fy)
    annual_scope1 = monthly.groupby('_fy_exit')['Scope1_tCO2e'].sum()

    exit_fy = None
    for fy in sorted(annual_scope1.index):
        if fy < date_to_fy(safeguard_start_date):
            continue
        if annual_scope1[fy] < SAFEGUARD_THRESHOLD:
            if exit_fy is None:
                exit_fy = fy
        else:
            exit_fy = None  # Re-entry

    monthly.drop(columns=['_fy_exit'], inplace=True)

    if exit_fy:
        exit_date, _ = fy_to_date_range(exit_fy)
        return exit_date
    return None


# =============================================================================
# FINANCIAL ANALYSIS FUNCTIONS
# =============================================================================


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
        result['Grid_MWh'] = result['Grid_Electricity_kWh'] / 1000.0
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


def apply_smc_transactions(projection, transactions):
    """Reconcile model SMC against CER registry transactions (smc_transactions.csv).

    Issuances use Applies_To_FY (the reporting year, not the transaction date)
    to override the model calc — CER issues FY2024 credits in Feb 2025.
    Sales/surrenders/corrections use Applies_To_FY to adjust the bank.
    Projection years with no issuance row keep the model value.

    Adds SMC_Issuance and SMC_Sold columns for chart breakdown.
    """
    result = projection.copy()
    result['SMC_Issuance'] = 0.0
    result['SMC_Sold'] = 0.0

    if transactions is None or transactions.empty:
        return result

    if 'FY_num' not in result.columns:
        result['FY_num'] = result['FY'].str.replace(r'^[A-Z]+', '', regex=True).astype(int)

    # Issuances replace model-calculated SMC_Annual using reporting FY
    for fy, qty in transactions[transactions['Type'] == 'Issuance'].groupby('Applies_To_FY')['Quantity'].sum().items():
        mask = result['FY_num'] == fy
        if mask.any():
            result.loc[mask, 'SMC_Annual'] = qty
            result.loc[mask, 'SMC_Issuance'] = qty

    # Sales, surrenders, corrections adjust using reporting FY
    for fy, qty in transactions[transactions['Type'] != 'Issuance'].groupby('Applies_To_FY')['Quantity'].sum().items():
        mask = result['FY_num'] == fy
        if mask.any():
            result.loc[mask, 'SMC_Annual'] += qty
            result.loc[mask, 'SMC_Sold'] = qty  # negative value

    result['SMC_Cumulative'] = result['SMC_Annual'].cumsum()
    return result


def smc_credit_value_analysis(projection, credit_start_fy, credit_price_initial,
                               credit_escalation_rate):
    """Calculate SMC credit value with price escalation.

    Two measures:
        Annual: credits earned that year valued at that year's price
        Cumulative: mark-to-market â€” entire credit bank at current price
    """
    result = projection.copy()
    if 'FY_num' not in result.columns:
        result['FY_num'] = result['FY'].str.replace(r'^[A-Z]+', '', regex=True).astype(int)

    result['Credit_Price'] = 0.0
    mask = result['FY_num'] >= credit_start_fy
    years = result.loc[mask, 'FY_num'] - credit_start_fy
    result.loc[mask, 'Credit_Price'] = credit_price_initial * ((1 + credit_escalation_rate) ** years)

    result['Credit_Value_Annual'] = result['SMC_Annual'] * result['Credit_Price']

    result['Credit_Value_Cumulative'] = 0.0
    result.loc[mask, 'Credit_Value_Cumulative'] = (
        result.loc[mask, 'SMC_Cumulative'] * result.loc[mask, 'Credit_Price']
    )

    return result