"""
projections.py
Build monthly projections with Budget Prime (phase-adjusted budget)
Last updated: 2026-02-05 17:30 AEST

ARCHITECTURE: Date-based processing
- Keeps monthly granularity with dates throughout
- No FY aggregation (happens at display time in tabs)
- Calculates Safeguard metrics on monthly data
- Returns monthly DataFrame with dates

Takes unified data from loader_data.py
Creates Budget Prime by applying phase adjustments to raw budget
Combines actuals + Budget Prime
Calculates safeguard metrics on monthly data
"""

import pandas as pd
import numpy as np
from datetime import datetime
from config import (
    NGER_FY_START_MONTH,
    CREDIT_START_DATE, SAFEGUARD_START_DATE, SMC_EXIT_PERIOD_YEARS,
    FSEI_ROM, FSEI_ELEC,
    PHASE_MINING, PHASE_MINING_POST_GRID, PHASE_PROCESSING, PHASE_REHABILITATION,
    get_phase_profile, DECLINE_RATE_PHASE1, DECLINE_RATE_PHASE2,
    DECLINE_PHASE1_START, DECLINE_PHASE1_END, DECLINE_PHASE2_START, DECLINE_PHASE2_END,
    DEFAULT_GRID_CONNECTION_DATE, DEFAULT_START_DATE,
    DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE, DEFAULT_END_REHABILITATION_DATE
)
from calc_calendar import date_to_fy, add_years
from loader_nga import NGAFactorsByYear
from calc_emissions import (
    calculate_scope1_diesel,
    calculate_scope1_lpg,
    calculate_scope1_oils,
    calculate_scope1_greases,
    calculate_scope1_acetylene,
    calculate_scope2_grid_electricity,
    calculate_scope3_diesel,
    calculate_scope3_grid_electricity,
    convert_kwh_to_mwh
)
import os


def build_projection(df, dataset='Base',
                     end_mining_date=DEFAULT_END_MINING_DATE,
                     end_processing_date=DEFAULT_END_PROCESSING_DATE,
                     end_rehabilitation_date=DEFAULT_END_REHABILITATION_DATE,
                     grid_connected_date=DEFAULT_GRID_CONNECTION_DATE,
                     fsei_rom=FSEI_ROM,
                     fsei_elec=FSEI_ELEC,
                     credit_start_date=CREDIT_START_DATE,
                     start_date=DEFAULT_START_DATE,
                     end_date=DEFAULT_END_REHABILITATION_DATE,
                     decline_rate_phase2=None):
    """Build monthly projection with Budget Prime (date-based)

    Args:
        df: Unified DataFrame from load_all_data()
        dataset: 'Base' or 'NPI-NGERS'
        end_mining_date: Date mining operations end
        end_processing_date: Date processing operations end
        end_rehabilitation_date: Date rehabilitation ends
        grid_connected_date: Date grid connection occurs
        fsei_rom: Facility specific emission intensity for ROM (tCO2-e/t)
        fsei_elec: Facility specific emission intensity for electricity (tCO2-e/MWh)
        credit_start_date: First date credits can be earned
        start_date: First projection date
        end_date: Last projection date
        decline_rate_phase2: Optional override for Phase 2 decline rate

    Returns:
        Monthly projection DataFrame with columns:
        Date, Scope1, Scope2, Scope3, Total, ROM_t, etc.
        (Display layer aggregates to FY/CY as needed)
    """

    print(f"\n{'='*80}")
    print(f"BUILDING PROJECTION: {dataset}")
    print(f"{'='*80}")

    # Convert dates to FY for display (not for logic)
    start_fy = date_to_fy(start_date)
    end_fy = date_to_fy(end_date)
    grid_connected_fy = date_to_fy(grid_connected_date)
    end_mining_fy = date_to_fy(end_mining_date)
    end_processing_fy = date_to_fy(end_processing_date)
    end_rehabilitation_fy = date_to_fy(end_rehabilitation_date)

    # 1. Separate actuals and budget
    actuals = df[df['DataSet'] == dataset].copy()
    budget = df[df['DataSet'] == 'Budget'].copy()

    if len(actuals) == 0:
        print(f"❌ No actuals found for dataset: {dataset}")
        return pd.DataFrame()

    if len(budget) == 0:
        print(f"⚠️  No budget data found")
        return pd.DataFrame()

    print(f"Actuals: {len(actuals)} records")
    print(f"Budget (raw): {len(budget)} records")

    # 2. Find last actual date
    last_actual_date = actuals['Date'].max()
    last_actual_year = last_actual_date.year
    last_actual_month = last_actual_date.month
    print(f"Last actual data: {last_actual_date.strftime('%Y-%m')}")

    # 3. Get budget for future only
    budget_future = budget[budget['Date'] > last_actual_date].copy()

    if len(budget_future) > 0:
        print(f"Budget future: {len(budget_future)} records (from {budget_future['Date'].min().strftime('%Y-%m')})")
    else:
        print(f"Budget future: 0 records")

    # 4. Apply phase adjustments to budget Ã¢â€ â€™ Budget Prime
    print(f"\nApplying phase adjustments to budget...")
    print(f"  End Mining FY:        {end_mining_fy} ({end_mining_date.strftime('%Y-%m-%d')})")
    print(f"  End Processing FY:    {end_processing_fy} ({end_processing_date.strftime('%Y-%m-%d')})")
    print(f"  End Rehabilitation FY: {end_rehabilitation_fy} ({end_rehabilitation_date.strftime('%Y-%m-%d')})")
    print(f"  Grid Connected FY:    {grid_connected_fy} ({grid_connected_date.strftime('%Y-%m-%d')})")

    # STEP 1: Handle grid connection transfer (before phase adjustments)
    budget_prime = apply_grid_connection_transfer(budget_future.copy(), grid_connected_date)

    # STEP 2: Apply phase adjustments
    budget_prime = apply_phase_multipliers(
        budget_prime,
        end_mining_date,
        end_processing_date,
        end_rehabilitation_date,
        grid_connected_date
    )

    print(f"ï¿½â€¦ Budget Prime created: {len(budget_prime)} records")

    # 5. Recalculate emissions for Budget Prime
    print(f"\nRecalculating emissions for Budget Prime...")

    # Get NGA factors
    nga_folder = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(nga_folder):
        nga_folder = '/mnt/project'
    nga_by_year = NGAFactorsByYear(nga_folder)

    budget_prime = recalculate_emissions(budget_prime, nga_by_year)
    print(f"ï¿½â€¦ Emissions recalculated")

    # 6. Combine actuals + Budget Prime Ã¢â€ â€™ Monthly data
    monthly = pd.concat([actuals, budget_prime], ignore_index=True)
    print(f"\nï¿½â€¦ Combined: {len(actuals)} actuals + {len(budget_prime)} budget prime = {len(monthly)} total monthly records")

    # 6a. Aggregate to monthly summary (one row per month)
    print(f"\nAggregating to monthly summary (one row per month)...")

    # Extract ROM quantities (Ore Mined)
    rom_data = monthly[monthly['Description'] == 'Ore Mined t'].groupby('Date')['Quantity'].sum().reset_index()
    rom_data.columns = ['Date', 'ROM_t']

    # Extract Site Electricity (kWh)
    site_elec_data = monthly[monthly['Description'] == 'Site electricity'].groupby('Date')['Quantity'].sum().reset_index()
    site_elec_data.columns = ['Date', 'Site_Electricity_kWh']

    # Extract Grid Electricity (kWh)
    grid_elec_data = monthly[monthly['Description'] == 'Grid electricity'].groupby('Date')['Quantity'].sum().reset_index()
    grid_elec_data.columns = ['Date', 'Grid_Electricity_kWh']

    # Aggregate emissions by Date
    emissions_agg = monthly.groupby('Date').agg({
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum'
    }).reset_index()

    # Merge all components
    monthly_summary = emissions_agg.merge(rom_data, on='Date', how='left')
    monthly_summary = monthly_summary.merge(site_elec_data, on='Date', how='left')
    monthly_summary = monthly_summary.merge(grid_elec_data, on='Date', how='left')

    # Fill NaN values with 0
    monthly_summary['ROM_t'] = monthly_summary['ROM_t'].fillna(0)
    monthly_summary['Site_Electricity_kWh'] = monthly_summary['Site_Electricity_kWh'].fillna(0)
    monthly_summary['Grid_Electricity_kWh'] = monthly_summary['Grid_Electricity_kWh'].fillna(0)

    print(f"ï¿½â€¦ Aggregated to {len(monthly_summary)} monthly records")
    print(f"   ROM range: {monthly_summary['ROM_t'].min():.0f} to {monthly_summary['ROM_t'].max():.0f} tonnes/month")
    print(f"   Site Electricity range: {monthly_summary['Site_Electricity_kWh'].min():.0f} to {monthly_summary['Site_Electricity_kWh'].max():.0f} kWh/month")

    # 7. Calculate safeguard metrics on monthly data
    print(f"\nCalculating safeguard metrics on monthly data...")
    monthly_summary = calculate_safeguard_metrics_monthly(
        monthly_summary,
        fsei_rom,
        fsei_elec,
        credit_start_date,
        end_mining_date,
        end_processing_date,
        end_rehabilitation_date,
        grid_connected_date,
        decline_rate_phase2
    )
    print(f"ï¿½â€¦ Safeguard metrics calculated")

    print(f"\n{'='*80}")
    print(f"PROJECTION COMPLETE")
    print(f"  Monthly records: {len(monthly_summary)}")
    print(f"  Date range: {monthly_summary['Date'].min().strftime('%Y-%m-%d')} to {monthly_summary['Date'].max().strftime('%Y-%m-%d')}")
    print(f"  Aggregate to FY/CY at display time")
    print(f"{'='*80}\n")

    return monthly_summary


def apply_phase_multipliers(data, end_mining_date, end_processing_date,
                           end_rehabilitation_date, grid_connected_date):
    """Apply Cost Centre-based phase multipliers based on dates

    Adjusts raw budget quantities based on operational phase at each date.
    Does NOT handle grid connection transfer - that's done separately first.

    Args:
        data: DataFrame with monthly budget data
        end_mining_date: Date when mining ends
        end_processing_date: Date when processing ends
        end_rehabilitation_date: Date when rehabilitation ends
        grid_connected_date: Date when grid connection occurs

    Returns:
        DataFrame with phase multipliers applied
    """
    result = data.copy()

    # Process each unique date
    for date in result['Date'].unique():
        # Get phase profile for this date
        phase_name, phase_profile, is_active = get_phase_profile(
            date, end_mining_date, end_processing_date, end_rehabilitation_date, grid_connected_date
        )

        date_mask = result['Date'] == date

        if not is_active:
            # Facility closed - zero everything
            result.loc[date_mask, 'Quantity'] = 0
            continue

        # Apply Cost Centre multipliers only to items in phase_profile
        for cost_centre, multiplier in phase_profile.items():
            mask = date_mask & (result['CostCentre'] == cost_centre)
            if mask.any():
                result.loc[mask, 'Quantity'] *= multiplier

    return result


def apply_grid_connection_transfer(data, grid_connected_date):
    """Apply grid connection transfer based on date (not FY)

    Diesel generation and site electricity reduce to 2% after grid connection.
    The 98% reduction in site electricity transfers to grid electricity.

    Args:
        data: DataFrame with monthly budget data
        grid_connected_date: datetime when grid connection occurs

    Returns:
        DataFrame with grid connection transfers applied
    """
    result = data.copy()

    # Filter to records on or after grid connection date
    post_grid = result['Date'] >= grid_connected_date

    if not post_grid.any():
        return result  # No records after grid connection

    # Track totals for logging
    diesel_reduced = 0
    site_reduced = 0
    grid_increased = 0

    # === 1. REDUCE DIESEL FUEL (Site power generation) ===
    diesel_mask = post_grid & (result['Description'] == 'Diesel oil - Site power generation')

    if diesel_mask.any():
        original_diesel = result.loc[diesel_mask, 'Quantity'].sum()
        result.loc[diesel_mask, 'Quantity'] *= 0.02
        new_diesel = result.loc[diesel_mask, 'Quantity'].sum()
        diesel_reduced = original_diesel - new_diesel

    # === 2. REDUCE SITE ELECTRICITY and TRANSFER TO GRID ===
    site_mask = post_grid & (result['Description'] == 'Site electricity')

    if site_mask.any():
        # Process each site electricity record
        for idx in result[site_mask].index:
            original_qty = result.loc[idx, 'Quantity']
            date = result.loc[idx, 'Date']
            cost_centre = result.loc[idx, 'CostCentre']
            department = result.loc[idx, 'Department']

            site_reduced += original_qty * 0.98

            # Reduce site to 2%
            result.loc[idx, 'Quantity'] = original_qty * 0.02

            # Transfer 98% to grid
            transfer_qty = original_qty * 0.98
            grid_increased += transfer_qty

            # Find existing grid electricity for same cost centre and date
            grid_mask = (result['Date'] == date) & \
                       (result['Description'] == 'Grid electricity') & \
                       (result['CostCentre'] == cost_centre)

            if grid_mask.any():
                # Add to existing grid record
                result.loc[grid_mask, 'Quantity'] += transfer_qty
            else:
                # Create new grid electricity record
                new_row = result.loc[idx].copy()
                new_row['Description'] = 'Grid electricity'
                new_row['Quantity'] = transfer_qty
                result = pd.concat([result, pd.DataFrame([new_row])], ignore_index=True)

    # Log the transfer
    print(f"ï¿½â€¦ Grid connection transfer (active from {grid_connected_date.strftime('%Y-%m-%d')} onwards):")
    print(f"   Diesel fuel:      {diesel_reduced:,.0f} L reduced")
    print(f"   Site electricity: {site_reduced:,.0f} kWh reduced")
    print(f"   Grid electricity: {grid_increased:,.0f} kWh added")

    return result



def recalculate_emissions(data, nga_by_year):
    """Recalculate emissions from adjusted quantities

    Uses same logic as loader_data.py but on Budget Prime quantities
    """
    result = data.copy()

    # Reset emissions
    result['Scope1_tCO2e'] = 0.0
    result['Scope2_tCO2e'] = 0.0
    result['Scope3_tCO2e'] = 0.0

    # Get NGA factors for each year (using FY from dates)
    result['FY_temp'] = result['Date'].apply(date_to_fy)
    unique_years = result['FY_temp'].unique()
    year_factor_map = {}

    for year in unique_years:
        factors = nga_by_year.get_factors_for_year(year, 'QLD')
        if factors is None:
            # Use defaults if factors not available
            year_factor_map[year] = {
                'diesel_elec_s1': 70.8 * 0.0386,
                'diesel_stat_s1': 69.9 * 0.0386,
                'diesel_s3': 17.3 * 0.0386,
                'lpg_s1': 60.6 * 0.051,
                'lpg_s3': 20.2 * 0.051,
                'oil_s3': 18.0 * 0.0388,
                'grease_s3': 18.0 * 0.0349,
                'acetylene_s1': 51.53 * 0.0393,
                'grid_s2': 0.73,
                'grid_s3': 0.09
            }
        else:
            purpose_factors = factors['diesel_by_purpose']
            year_factor_map[year] = {
                'diesel_elec_s1': purpose_factors.get('Electricity generation', {}).get('scope1', 70.8) * 0.0386,
                'diesel_stat_s1': purpose_factors.get('Stationary', {}).get('scope1', 69.9) * 0.0386,
                'diesel_s3': 17.3 * 0.0386,
                'lpg_s1': 60.6 * 0.051,
                'lpg_s3': 20.2 * 0.051,
                'oil_s3': 18.0 * 0.0388,
                'grease_s3': 18.0 * 0.0349,
                'acetylene_s1': 51.53 * 0.0393,
                'grid_s2': factors['electricity']['QLD']['scope2'],
                'grid_s3': factors['electricity']['QLD']['scope3']
            }

    # Calculate emissions by fuel type (vectorized)

    # Diesel - Site power
    mask = result['Description'] == 'Diesel oil - Site power generation'
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['diesel_elec_s1'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['diesel_s3'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Diesel - Mobile equipment
    mask = result['Description'] == 'Diesel oil - Mobile equipment'
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['diesel_stat_s1'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['diesel_s3'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # LPG
    mask = result['Description'].str.contains('Liquefied petroleum gas', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['lpg_s1'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['lpg_s3'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_lpg(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_lpg(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Petroleum oils (Scope 3 only)
    mask = result['Description'].str.contains('Petroleum based oils', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['oil_s3'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_oils(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Petroleum greases (Scope 3 only)
    mask = result['Description'].str.contains('Petroleum based greases', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['grease_s3'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_greases(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Acetylene
    mask = result['Description'].str.contains('gaseous fossil fuels', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['acetylene_s1'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_acetylene(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])

    # Grid electricity
    mask = result['Description'] == 'Grid electricity'
    if mask.any():
        result.loc[mask, 'factor_s2'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['grid_s2'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY_temp'].map(lambda y: year_factor_map[y]['grid_s3'])
        # Convert kWh to MWh
        mwh = convert_kwh_to_mwh(result.loc[mask, 'Quantity'])
        result.loc[mask, 'Scope2_tCO2e'] = calculate_scope2_grid_electricity(mwh, result.loc[mask, 'factor_s2'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_grid_electricity(mwh, result.loc[mask, 'factor_s3'])

    # Drop temporary factor columns
    factor_cols = [col for col in result.columns if col.startswith('factor_')]
    result = result.drop(columns=factor_cols)

    return result




def calculate_safeguard_metrics_monthly(monthly, fsei_rom, fsei_elec, credit_start_date,
                                        end_mining_date, end_processing_date,
                                        end_rehabilitation_date, grid_connected_date,
                                        decline_rate_phase2=None):
    """Calculate safeguard mechanism metrics on monthly data (date-based)

    Calculates baseline intensity, SMC credits and applies 10-year exit rule.
    Works on monthly data with dates (not annual FY data).

    Args:
        monthly: Monthly DataFrame with Date, Scope1, ROM_t columns
        fsei_rom: Facility specific emission intensity for ROM (tCO2-e/t)
        fsei_elec: Facility specific emission intensity for electricity (tCO2-e/MWh)
        credit_start_date: First date credits can be earned
        end_mining_date: Date when mining ends
        end_processing_date: Date when processing ends
        end_rehabilitation_date: Date when rehabilitation ends
        grid_connected_date: Date when grid connection occurs
        decline_rate_phase2: Optional override for Phase 2 decline rate

    Returns:
        Monthly DataFrame with added metrics columns
    """
    result = monthly.copy()

    # Filter to only include dates from Safeguard Mechanism start onwards
    result = result[result['Date'] >= SAFEGUARD_START_DATE].copy()

    if len(result) == 0:
        # Return empty DataFrame with expected columns if all data filtered out
        result['Phase'] = []
        result['Emission_Intensity'] = []
        result['Baseline_Intensity'] = []
        result['Baseline'] = []
        result['Intensity_Excess'] = []
        result['SMC_Monthly'] = []
        result['SMC_Cumulative'] = []
        result['In_Safeguard'] = []
        return result

    # Add phase column
    result['Phase'] = result['Date'].apply(lambda d: get_phase_name_by_date(
        d, end_mining_date, end_processing_date, end_rehabilitation_date, grid_connected_date
    ))

    # Emission intensity (actual Scope 1 / ROM tonnes)
    result['Emission_Intensity'] = 0.0
    mask = result['ROM_t'] > 0
    result.loc[mask, 'Emission_Intensity'] = result.loc[mask, 'Scope1_tCO2e'] / result.loc[mask, 'ROM_t']

    # Calculate baseline intensity for each month's date
    SITE_GENERATION_RATIO = 0.008735  # MWh per tonne ROM
    baseline_intensity_base = fsei_rom + (SITE_GENERATION_RATIO * fsei_elec)

    # NOTE: Baseline_Intensity is calculated AFTER the baseline (derived from
    # actual baseline / ROM_t).  The fixed-ratio version below is kept as
    # 'Baseline_Intensity_Fixed' for reference only (valid pre-grid, misleading post-grid).
    result['Baseline_Intensity_Fixed'] = result['Date'].apply(
        lambda d: calculate_baseline_intensity_for_date(
            d, baseline_intensity_base, decline_rate_phase2
        )
    )

    # Baseline emissions - separate ROM and electricity components with decline
    # Both components decline at the same rate as baseline_intensity

    # Calculate declining FSEI factors for this date
    result['FSEI_ROM_Declining'] = result['Date'].apply(
        lambda d: fsei_rom * (calculate_baseline_intensity_for_date(d, 1.0, decline_rate_phase2))
    )
    result['FSEI_ELEC_Declining'] = result['Date'].apply(
        lambda d: fsei_elec * (calculate_baseline_intensity_for_date(d, 1.0, decline_rate_phase2))
    )

    # Baseline per Safeguard Mechanism Rule 2015, Section 19:
    #   Baseline = Σ (Production_qty × FSEI × decline_factor)
    # Two production variables per approved EID (CER October 2024):
    #   1. ROM metal ore:          ROM_t × FSEI_ROM × decline
    #   2. Electricity generation: Site_MWh × FSEI_ELEC × decline
    # Ref: EID Basis of Preparation (Turner & Townsend, Feb 2024) Tables 13-14
    result['Baseline_ROM'] = result['FSEI_ROM_Declining'] * result['ROM_t']
    result['Baseline_Electricity'] = 0.0
    if 'Site_Electricity_kWh' in result.columns:
        result['Baseline_Electricity'] = result['FSEI_ELEC_Declining'] * (result['Site_Electricity_kWh'] / 1000)

    # Total baseline (sum of both production variable components)
    result['Baseline'] = result['Baseline_ROM'] + result['Baseline_Electricity']

    # Derive effective Baseline_Intensity from actual baseline for chart display
    # This reflects the TRUE baseline per tonne (including actual electricity component)
    # Pre-grid: ~0.0256 (matches combined formula)
    # Post-grid: drops to ~0.018 (electricity component shrinks with site generation)
    result['Baseline_Intensity'] = 0.0
    mask_rom = result['ROM_t'] > 0
    result.loc[mask_rom, 'Baseline_Intensity'] = (
        result.loc[mask_rom, 'Baseline'] / result.loc[mask_rom, 'ROM_t']
    )

    # Intensity excess (for reporting - positive means above baseline)
    result['Intensity_Excess'] = result['Emission_Intensity'] - result['Baseline_Intensity']

    # -------------------------------------------------------------------------
    # SMC CALCULATION - THREE-PHASE MODEL
    # Per Safeguard Mechanism Rule 2015 (Reformed 2023)
    #
    # Phase 1 - SAFEGUARD (Scope 1 >= 100,000 tCO2-e annually):
    #   Covered facility.  Credits (s22XB) and surrenders (s22XE) both apply.
    #   SMC = Baseline - Actual (positive = credit, negative = surrender)
    #
    # Phase 2 - OPT-IN (Scope 1 < 100,000 tCO2-e, up to 10 years, s58B):
    #   Facility drops below threshold, opts in to continue earning credits.
    #   Credits only - no surrender obligations.  Baseline keeps declining.
    #   Negatives clamped to zero.
    #
    # Phase 3 - EXITED (after 10-year opt-in expires):
    #   No credits, no surrenders.  Existing credits can still be traded.
    #   SMC = 0
    # -------------------------------------------------------------------------

    # Step 1: Determine annual Safeguard status (In/Out of threshold)
    result['In_Safeguard'] = result.groupby(result['Date'].dt.year)['Scope1_tCO2e'].transform('sum') >= 100_000

    # Step 2: Calculate raw SMC (before phase rules)
    result['SMC_Monthly'] = 0.0
    mask = (result['Date'] >= credit_start_date)
    result.loc[mask, 'SMC_Monthly'] = result.loc[mask, 'Baseline'] - result.loc[mask, 'Scope1_tCO2e']

    # Step 3: Find exit date (first FY below threshold)
    exit_date = find_exit_date(result, SAFEGUARD_START_DATE)

    # Step 4: Assign SMC_Phase and apply phase-specific rules
    result['SMC_Phase'] = 'Pre-Safeguard'
    result.loc[result['Date'] >= credit_start_date, 'SMC_Phase'] = 'Safeguard'

    if exit_date:
        from calc_calendar import date_to_fy
        result['Exit_FY'] = date_to_fy(exit_date)
        stop_date = add_years(exit_date, SMC_EXIT_PERIOD_YEARS)

        # Opt-in period: below threshold, within 10 years
        opt_in_mask = (result['Date'] >= exit_date) & (result['Date'] < stop_date)
        result.loc[opt_in_mask, 'SMC_Phase'] = 'Opt-In'

        # Opt-in: credits only, clamp negatives to zero (no surrender obligations)
        result.loc[opt_in_mask & (result['SMC_Monthly'] < 0), 'SMC_Monthly'] = 0.0

        # Exited: no credits, no surrenders
        exited_mask = (result['Date'] >= stop_date)
        result.loc[exited_mask, 'SMC_Phase'] = 'Exited'
        result.loc[exited_mask, 'SMC_Monthly'] = 0.0
    else:
        result['Exit_FY'] = None

    # SMC Cumulative
    result['SMC_Cumulative'] = result['SMC_Monthly'].cumsum()

    return result


def calculate_baseline_intensity_for_date(date, baseline_intensity_base, decline_rate_phase2=None):
    """Calculate declining baseline intensity for a specific date

    Two-phase decline per Safeguard Mechanism legislation:
    - Phase 1: 4.9% per year (FY2024-FY2030)
    - Phase 2: 3.285% per year (FY2031-FY2050)
    - Flat after FY2050

    Args:
        date: Date to calculate baseline for
        baseline_intensity_base: Base baseline intensity (tCO2-e/t)
        decline_rate_phase2: Optional override for Phase 2 decline rate

    Returns:
        float: Baseline intensity for the given date
    """
    from calc_calendar import date_to_fy

    fy = date_to_fy(date)

    # Phase 1: FY2024-FY2030 (4.9% decline)
    if DECLINE_PHASE1_START <= fy <= DECLINE_PHASE1_END:
        years_declining = fy - DECLINE_PHASE1_START
        decline_factor = (1 - DECLINE_RATE_PHASE1) ** years_declining
        return baseline_intensity_base * decline_factor

    # Phase 2: FY2031-FY2050 (3.285% decline)
    elif DECLINE_PHASE2_START <= fy <= DECLINE_PHASE2_END:
        # First apply Phase 1 decline (6 years from FY2025-FY2030)
        phase1_years = DECLINE_PHASE1_END - DECLINE_PHASE1_START
        phase1_factor = (1 - DECLINE_RATE_PHASE1) ** phase1_years
        baseline_after_phase1 = baseline_intensity_base * phase1_factor

        # Then apply Phase 2 decline
        rate_phase2 = decline_rate_phase2 if decline_rate_phase2 is not None else DECLINE_RATE_PHASE2
        phase2_years = fy - DECLINE_PHASE1_END
        phase2_factor = (1 - rate_phase2) ** phase2_years
        return baseline_after_phase1 * phase2_factor

    # After FY2050: Flat baseline
    elif fy > DECLINE_PHASE2_END:
        # Apply both phases
        phase1_years = DECLINE_PHASE1_END - DECLINE_PHASE1_START
        phase1_factor = (1 - DECLINE_RATE_PHASE1) ** phase1_years
        baseline_after_phase1 = baseline_intensity_base * phase1_factor

        rate_phase2 = decline_rate_phase2 if decline_rate_phase2 is not None else DECLINE_RATE_PHASE2
        phase2_years = DECLINE_PHASE2_END - DECLINE_PHASE1_END
        phase2_factor = (1 - rate_phase2) ** phase2_years
        return baseline_after_phase1 * phase2_factor

    # Before FY2024: No decline
    else:
        return baseline_intensity_base


def find_exit_date(monthly, safeguard_start_date):
    """Find first date when emissions drop below 100,000 tCO2-e threshold

    Only considers dates after Safeguard Mechanism started.
    Handles re-entry: If emissions go back above 100k, exit date resets.

    Args:
        monthly: Monthly DataFrame with Date and Scope1_tCO2e columns
        safeguard_start_date: Date when Safeguard Mechanism started

    Returns:
        datetime or None: First date emissions drop below 100k (after considering re-entry)
    """
    from calc_calendar import date_to_fy

    # Group by FY and sum emissions
    monthly['FY_temp'] = monthly['Date'].apply(date_to_fy)
    annual_scope1 = monthly.groupby('FY_temp')['Scope1_tCO2e'].sum()

    exit_fy = None
    for fy in sorted(annual_scope1.index):
        # Only consider years after Safeguard started
        if fy < date_to_fy(safeguard_start_date):
            continue

        scope1 = annual_scope1[fy]

        # Find first year below threshold
        if scope1 < 100_000:
            if exit_fy is None:
                exit_fy = fy
        else:
            # Re-entry: emissions back above threshold
            if exit_fy is not None:
                exit_fy = None

    # Convert exit FY to first date of that FY
    if exit_fy:
        from calc_calendar import fy_to_date_range
        exit_date, _ = fy_to_date_range(exit_fy)
        return exit_date

    return None


def get_phase_name_by_date(date, end_mining_date, end_processing_date,
                           end_rehabilitation_date, grid_connected_date):
    """Get phase name for display based on date"""
    phase_name, _, is_active = get_phase_profile(
        date, end_mining_date, end_processing_date, end_rehabilitation_date, grid_connected_date
    )

    if not is_active:
        return 'Closed'
    elif phase_name == 'mining':
        return 'Mining'
    elif phase_name == 'mining_post_grid':
        return 'Mining (Grid)'
    elif phase_name == 'processing':
        return 'Processing'
    elif phase_name == 'rehabilitation':
        return 'Rehabilitation'
    else:
        return 'Unknown'


def carbon_tax_analysis(projection, tax_start_fy, tax_rate_initial, tax_escalation_rate):
    """Calculate carbon tax liability

    Args:
        projection: Annual projection DataFrame
        tax_start_fy: First year of carbon tax (FY number, not string)
        tax_rate_initial: Initial tax rate ($/tCO2-e)
        tax_escalation_rate: Annual escalation rate (decimal, e.g., 0.025 = 2.5%)

    Returns:
        DataFrame with tax calculations

    Note: Tax is based on Scope 1 emissions only
    """
    result = projection.copy()

    # Extract year number (works for both FY2023 and CY2023 formats)
    result['FY_num'] = result['Year'].str.extract(r'(\d+)')[0].astype(int)

    # Calculate tax rate for each year (escalates annually)
    result['Tax_Rate'] = 0.0
    mask = result['FY_num'] >= tax_start_fy
    years_since_start = result.loc[mask, 'FY_num'] - tax_start_fy
    result.loc[mask, 'Tax_Rate'] = tax_rate_initial * ((1 + tax_escalation_rate) ** years_since_start)

    # Tax liability (based on Scope 1 emissions only)
    result['Tax_Annual'] = 0.0
    result.loc[mask, 'Tax_Annual'] = result.loc[mask, 'Scope1'] * result.loc[mask, 'Tax_Rate']

    # Cumulative tax (only accumulate from tax start year)
    result['Tax_Cumulative'] = 0.0
    result.loc[mask, 'Tax_Cumulative'] = result.loc[mask, 'Tax_Annual'].cumsum()

    return result


def smc_credit_value_analysis(projection, credit_start_fy, credit_price_initial, credit_escalation_rate):
    """Calculate SMC credit value with price escalation

    Args:
        projection: Annual projection DataFrame
        credit_start_fy: First year credits can be earned (FY number, not string)
        credit_price_initial: Initial credit price ($/tCO2-e)
        credit_escalation_rate: Annual price escalation rate (decimal, e.g., 0.03 = 3%)

    Returns:
        DataFrame with credit value calculations
    """
    result = projection.copy()

    # Extract FY number if needed
    if 'FY_num' not in result.columns:
        result['FY_num'] = result['FY'].str.replace('FY', '').astype(int)

    # Calculate credit price for each year with escalation
    result['Credit_Price'] = 0.0
    mask = result['FY_num'] >= credit_start_fy
    years_since_start = result.loc[mask, 'FY_num'] - credit_start_fy
    result.loc[mask, 'Credit_Price'] = credit_price_initial * ((1 + credit_escalation_rate) ** years_since_start)

    # Credit value - two measures:
    # 1. Annual: credits/surrenders earned that year valued at that year's price
    # 2. Cumulative: mark-to-market - entire credit bank valued at current year's price
    #    This reflects what the banked credits are WORTH now, not what they cost to earn
    #    Value keeps growing as price escalates even after credits stop being earned
    result['Credit_Value_Annual'] = result['SMC_Annual'] * result['Credit_Price']
    mask_cv = result['FY_num'] >= credit_start_fy
    result['Credit_Value_Cumulative'] = 0.0
    result.loc[mask_cv, 'Credit_Value_Cumulative'] = (
        result.loc[mask_cv, 'SMC_Cumulative'] * result.loc[mask_cv, 'Credit_Price']
    )

    return result


# Backward compatibility wrapper
def build_projection_simple(start_fy, end_fy, rom_df, energy_df, nga_factors,
                            fsei_rom, fsei_elec, grid_connected_fy,
                            end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                            credit_start_fy=None):
    """Backward compatibility wrapper - deprecated

    Old signature for tabs that haven't been updated yet
    """
    print("⚠️  WARNING: build_projection_simple() is deprecated")
    print("   Use build_projection(df, dataset=...) instead")

    # This won't work with new architecture - return empty
    return pd.DataFrame()