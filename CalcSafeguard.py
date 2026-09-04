"""The Safeguard Mechanism.

Everything the mechanism asks of this facility, in one place: the emissions
reduction contribution that declines each year, the hybrid intensity that
shifts weight from the facility figure to the industry default, the Section
11 baseline the two produce, the source and production tables the baseline is
built from, the exit test, and the credit ledger.

Baseline, Section 11:

    Baseline = ERC x SUM over p [ (h x EI_p + (1 - h) x EIF_p) x Q_p ] + BA

        ERC   emissions reduction contribution, declining linearly
        h     transition proportion, rising each year to one
        EI_p  default industry intensity for production variable p
        EIF_p facility specific intensity for p
        Q_p   quantity of p
        BA    borrowing adjustment, nil here

Every rate and threshold below is read from Data/Assumptions.yaml through
Config.  Nothing in this module decides what a number should be; it decides
what the mechanism does with it.
"""

import numpy as np
import pandas as pd

from CalcCalendar import date_to_fy, series_to_fy, fy_to_date_range
from CalcNga import build_year_factor_map
from CalcUnits import KWH_PER_MWH, UnitError, factor as uom_factor
from Config import (
    NGER_FY_START_MONTH,
    CREDIT_START_DATE, SAFEGUARD_START_DATE,
    FSEI_ROM, FSEI_ELEC, SITE_GENERATION_RATIO,
    DEFAULT_INDUSTRY_EI_ROM, DEFAULT_INDUSTRY_EI_ELEC,
    SAFEGUARD_MINIMUM_BASELINE, SAFEGUARD_THRESHOLD, SAFEGUARD_FINAL_FY,
    GRID_SITE_ELEC_DESCRIPTION, GRID_GRID_ELEC_DESCRIPTION,
    DIESEL_TRANSPORT_COSTCENTRES, DIESEL_TRANSPORT_NGAFUEL,
    ROM_SUBACTIVITY, GOLD_SUBACTIVITY,
    SITE_ELEC_COMMONNAME, GRID_ELEC_COMMONNAME,
    DECLINE_RATE_PHASE1, DECLINE_RATE_PHASE2,
    DECLINE_PHASE1_START, DECLINE_PHASE1_END,
    DECLINE_PHASE2_START, DECLINE_PHASE2_END,
    DEFAULT_GRID_CONNECTION_DATE, DEFAULT_START_DATE,
    DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE,
    DEFAULT_END_REHABILITATION_DATE,
    get_transition_proportion, get_phase_name_for_date,
    S58B_EARLIEST_FY, S58B_LOOKBACK, S58B_MIN_COVERED,
)

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
                              decline_rate_phase2=None,
                              borrowing_adjustment=0.0):
    """Calculate the Section 11 baseline for a financial year.

    Section 11 in full, summed over each production variable p, is

        Baseline = ERC x SUM[ (h x EI + (1 - h) x EI_F) x Q + EI_B x Q_B ] + BA

    where Q is the quantity only where an emissions intensity determination
    specifies a facility-specific intensity for that variable, and Q_B is the
    mirror: the quantity only where one does not, charged at the best practice
    intensity with no transition proportion at all.

    This facility holds a determination for both production variables, so Q_B
    is zero for both and the best practice branch does not arise.  What is
    computed below is therefore the Q branch alone.  If a determination lapses
    or a new production variable is declared without one, this function
    ceases to be the right calculation and must be extended before it is
    relied on.

    Returns both the floored and the unfloored baseline, because the two
    provisions require different numbers:
      - Floored: subject to the s10(1) minimum of 100,000 tCO2-e.  Compliance.
      - Unfloored: per s56(4), credits use the baseline that would be
        ascertained "if subsection 10(1) had not been enacted".

    Args:
        borrowing_adjustment: the BA term of s11, from s47.  Zero unless a
            borrowing adjustment has been granted.  Carried explicitly rather
            than omitted, so the code matches the provision it implements.

    Returns:
        tuple: (floored_baseline, unfloored_baseline) in tCO2-e
    """
    erc = calculate_erc_for_fy(fy, decline_rate_phase2)
    hybrid_rom, hybrid_elec = calculate_hybrid_ei(fy, fsei_rom, fsei_elec)

    # s10(3): the baseline is zero for a financial year beginning after
    # 30 June 2049.  FY2050 begins on 1 July 2049, so FY2050 is the first
    # year that qualifies, not FY2051.  The model horizon reaches it, so the
    # rule is applied rather than left to produce a baseline, and a floor,
    # for a year that cannot have one.
    if fy >= SAFEGUARD_FINAL_FY:
        return 0.0, 0.0

    # Section 11, the Q branch, plus the borrowing adjustment.
    unfloored = (erc * ((hybrid_rom * rom_t) + (hybrid_elec * site_mwh))
                 + borrowing_adjustment)

    # s10(1) minimum baseline floor, for compliance only.
    floored = max(unfloored, SAFEGUARD_MINIMUM_BASELINE)

    return floored, unfloored

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
    fy_site_mwh = result.groupby('_fy')['Site_Electricity_kWh'].sum() / KWH_PER_MWH

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
        month_elec_contrib = (fy_rows['Site_Electricity_kWh'] / KWH_PER_MWH) * hybrid_elec
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
        month_elec_contrib = (fy_rows['Site_Electricity_kWh'] / KWH_PER_MWH) * hybrid_elec
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

def apply_smc_transactions(projection, transactions):
    """Reconcile model SMC against CER registry transactions (SmcTransactions.csv).

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

def build_safeguard_source_table(df, year_factor_map):
    """Build a detailed source table for Safeguard Mechanism validation and NGER filing.

    Aggregates actuals data to annual level (FY), enriches each row with the
    NGA emission factors and energy content that produced the emissions, so a
    third party can independently verify every tCO2-e line item.

    Calculation shown in each row:
        Quantity_Factor_Basis = Quantity * UOM_Conversion
        tCO2-e    = Quantity_Factor_Basis * EF_kgCO2e_per_unit / 1000
        Energy_GJ = Quantity_Factor_Basis * Energy_GJ_per_unit

    Quantity stays in the unit the site reports it in.  UOM_Conversion is the
    exact definition that carries it to the unit the factor is published
    against, and is 1.0 where the two already agree.  Both are on the row so
    it reconciles without the reader knowing which units disagreed.

    Only rows that have an NGAFuel assignment are included (i.e. consumable
    energy items — not production or ROM data).

    Args:
        df:               Processed DataFrame from load_all_data()
                          Must contain: FY, Description, Department, CostCentre,
                          NGAFuel, UOM, Quantity, Scope1_tCO2e, Scope2_tCO2e,
                          Scope3_tCO2e, Energy_GJ
        year_factor_map:  Dict from build_year_factor_map() — provides the exact
                          NGA factor values used during emissions calculation.

    Returns:
        DataFrame with one row per FY / Description / NGAFuel combination,
        ready for CSV download.  Columns:
            FY, Description, Department, CostCentre, NGAFuel, NGA_Year,
            UOM, Quantity, Factor_UOM, UOM_Conversion, Quantity_Factor_Basis,
            EF_Scope1_kgCO2e_per_unit, Energy_GJ_per_unit,
            Scope1_tCO2e, Energy_GJ
    """
    # Filter to rows that carry an NGAFuel (energy / consumable lines only).
    # Exclude grid electricity: Scope 1 = 0 for purchased electricity, and the
    # kWh quantities are already provided in the electricity production table
    # (build_safeguard_production_table).  Including them here adds zero-emission
    # rows that clutter the audit trail without adding information.
    fuel_mask = (
        df['NGAFuel'].notna()
        & (df['NGAFuel'].astype(str) != '')
        & (df['NGAFuel'].astype(str) != 'Grid electricity')
    )
    source = df[fuel_mask].copy()

    if source.empty:
        return pd.DataFrame()

    # --- Annual aggregation ---
    # Group to FY / Description / Department / CostCentre / NGAFuel / UOM
    # UOM is included so split fuel types (kL vs m3) stay separate.
    agg = source.groupby(
        ['FY', 'DataSet', 'Description', 'Department', 'CostCentre', 'NGAFuel', 'UOM'],
        observed=True, dropna=False
    ).agg(
        Quantity=('Quantity', 'sum'),
        Scope1_tCO2e=('Scope1_tCO2e', 'sum'),
        Energy_GJ=('Energy_GJ', 'sum'),
    ).reset_index()

    # --- Attach NGA factor values ---
    # Resolve the factor key the same way apply_emissions_to_df() does so
    # the EF columns reflect exactly what was used in the calculation.
    ef_s1 = []
    ef_energy = []
    nga_years = []
    factor_uoms = []
    conversions = []

    for _, row in agg.iterrows():
        fy = int(row['FY'])
        nga_fuel = str(row['NGAFuel'])
        yf_all = year_factor_map.get(fy, {})

        # Resolve factor key: exact then longest prefix, then reverse prefix
        factor_key = None
        if nga_fuel in yf_all:
            factor_key = nga_fuel
        else:
            prefixes = [(k, len(k)) for k in yf_all if nga_fuel.startswith(k)]
            if prefixes:
                factor_key = max(prefixes, key=lambda x: x[1])[0]
            else:
                reverse = [k for k in yf_all if k.startswith(nga_fuel)]
                if reverse:
                    factor_key = reverse[0]

        if factor_key and factor_key in yf_all:
            yf = yf_all[factor_key]
            ef_s1.append(yf.get('s1', 0))
            ef_energy.append(yf.get('energy', 0))

            # The row keeps the quantity in the unit the site reports it in.
            # Where that differs from the unit the factor is published
            # against, the conversion is shown so the row reconciles:
            #     Quantity x UOM_Conversion x EF / 1000 = tCO2-e
            factor_uom = yf.get('expected_uom', '') or ''
            row_uom = str(row['UOM'])
            factor_uoms.append(factor_uom)
            if factor_uom:
                try:
                    conversions.append(uom_factor(row_uom, factor_uom))
                except UnitError:
                    conversions.append(None)
            else:
                conversions.append(1.0)
        else:
            ef_s1.append(None)
            ef_energy.append(None)
            factor_uoms.append(None)
            conversions.append(None)

        nga_years.append(yf_all.get('_nga_year', fy))

    agg['Factor_UOM'] = factor_uoms
    agg['UOM_Conversion'] = conversions
    agg['Quantity_Factor_Basis'] = agg['Quantity'] * agg['UOM_Conversion']
    agg['EF_Scope1_kgCO2e_per_unit'] = ef_s1
    agg['Energy_GJ_per_unit'] = ef_energy
    agg['NGA_Year'] = nga_years

    # --- Column order for auditor readability ---
    col_order = [
        'FY', 'DataSet', 'Description', 'Department', 'CostCentre', 'NGAFuel',
        'NGA_Year',
        'UOM', 'Quantity',
        'Factor_UOM', 'UOM_Conversion', 'Quantity_Factor_Basis',
        'EF_Scope1_kgCO2e_per_unit', 'Energy_GJ_per_unit',
        'Scope1_tCO2e', 'Energy_GJ',
    ]
    agg = agg[[c for c in col_order if c in agg.columns]]

    return agg.sort_values(['FY', 'DataSet', 'Description', 'NGAFuel']).reset_index(drop=True)

def build_safeguard_production_table(df):
    """Build annual physical quantities table for Safeguard FSEI target validation.

    The Safeguard baseline target is calculated using pre-defined FSEI constants:

        Baseline = ERC x ((FSEI_ROM x ROM_t) + (FSEI_Elec x Site_MWh))

    FSEI values are fixed — a third party only needs the physical quantities
    (tonnes and kWh) to independently verify the target.  No emissions columns
    are included here; those are in build_safeguard_source_table().

    Two physical quantity datasets:

    1. ROM Ore (SubActivity=='Ore ROM', UOM==t)
          All ore grades by beneficiation status (BRW/SARS, HG/MG/LG/VLG).
          Matches the ROM_t variable used in projections.aggregate_to_monthly().
          Subtotal row per FY/DataSet.

    2. Electricity — kWh (UOM==kWh, CommonName in ['Site electricity', 'Grid electricity'])
          Site electricity (CommonName=='Site electricity') feeds Site_MWh in the
          FSEI formula.  Grid electricity (CommonName=='Grid electricity') covers
          all cost centres including Residential, which is an attributed portion
          of the grid supply and must be included.
          Both are shown in one table for cross-reference.
          Subtotal rows per FY/DataSet/Description type.

    Args:
        df: Processed DataFrame from load_all_data()

    Returns:
        dict with keys 'ore' and 'electricity', each a DataFrame with columns:
            FY, DataSet, Description, CostCentre, UOM, Quantity
        Sorted by FY, DataSet, Description.
    """

    def _aggregate(subset):
        """Aggregate to FY/DataSet/Description/CostCentre/UOM — no totals rows."""
        if subset.empty:
            return pd.DataFrame()
        return subset.groupby(
            ['FY', 'DataSet', 'Description', 'CostCentre', 'UOM'],
            observed=True, dropna=False
        ).agg(Quantity=('Quantity', 'sum')).reset_index().sort_values(
            ['FY', 'DataSet', 'Description']
        ).reset_index(drop=True)

    # --- 1. ROM Ore --- matches Projections.py aggregate_to_monthly() ROM filter:
    #   SubActivity == 'Ore ROM' (2026-03 CSV restructure)
    #   Previously matched CostCentre == 'ROM' but actuals now use CostCentre == 'Hauling'
    #   while budget retains CostCentre == 'ROM'.  SubActivity is the reliable key.
    rom_mask = (df['SubActivity'].astype(str) == 'Ore ROM')
    ore_df = _aggregate(df[rom_mask].copy())

    # --- 2. Electricity kWh --- via CommonName (set by LookupIdentifiers.py)
    #   CommonName == 'Site electricity' captures all site generation
    #   CommonName == 'Grid electricity' captures Grid Power + Residential + Warehouse + Water Delivery
    #   All cost centres included — Residential is an attributed portion of grid supply
    elec_mask = (
        (df['UOM'].astype(str) == 'kWh') &
        (df['CommonName'].astype(str).isin(['Site electricity', 'Grid electricity']))
    )
    elec_df = _aggregate(df[elec_mask].copy())

    return {'ore': ore_df, 'electricity': elec_df}

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
