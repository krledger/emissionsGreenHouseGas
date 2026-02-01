"""
projections.py
Build annual projections with Budget Prime (phase-adjusted budget)
Last updated: 2026-02-02 01:15 AEST

Takes unified data from data_loader.py
Creates Budget Prime by applying phase adjustments to raw budget
Combines actuals + Budget Prime
Aggregates to annual and calculates safeguard metrics
"""

import pandas as pd
import numpy as np
from config import (
    calculate_fy, NGER_FY_START_MONTH, CREDIT_START_FY, FSEI_ROM, FSEI_ELEC,
    PHASE_MINING, PHASE_MINING_POST_GRID, PHASE_PROCESSING, PHASE_REHABILITATION,
    get_phase_profile, DECLINE_RATE, DECLINE_FROM, DECLINE_TO
)
from nga_loader import NGAFactorsByYear
from emissions_calc import (
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
                     end_mining_fy=2035,
                     end_processing_fy=2038,
                     end_rehabilitation_fy=2045,
                     grid_connected_fy=2030,
                     fsei_rom=FSEI_ROM,
                     fsei_elec=FSEI_ELEC,
                     credit_start_fy=CREDIT_START_FY,
                     start_fy=2023,
                     end_fy=2045):
    """Build annual projection with Budget Prime

    Args:
        df: Unified DataFrame from load_all_data()
        dataset: 'Base' or 'NPI-NGERS'
        end_mining_fy: Last year of mining operations
        end_processing_fy: Last year of processing operations
        end_rehabilitation_fy: Last year of rehabilitation
        grid_connected_fy: Year grid connection occurs
        fsei_rom: Facility specific emission intensity for ROM (tCO2-e/t)
        fsei_elec: Facility specific emission intensity for electricity (tCO2-e/MWh)
        credit_start_fy: First year credits can be earned
        start_fy: First projection year
        end_fy: Last projection year

    Returns:
        Annual projection DataFrame with columns:
        FY, Phase, ROM_Mt, Scope1, Scope2, Scope3, Total,
        Emission_Intensity, Baseline_Intensity, SMC_Annual, SMC_Cumulative, etc.
    """

    print(f"\n{'='*80}")
    print(f"BUILDING PROJECTION: {dataset}")
    print(f"{'='*80}")

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

    # 4. Apply phase adjustments to budget → Budget Prime
    print(f"\nApplying phase adjustments to budget...")
    print(f"  End Mining FY:        {end_mining_fy}")
    print(f"  End Processing FY:    {end_processing_fy}")
    print(f"  End Rehabilitation FY: {end_rehabilitation_fy}")
    print(f"  Grid Connected FY:    {grid_connected_fy}")

    # STEP 1: Handle grid connection transfer (before phase adjustments)
    budget_prime = apply_grid_connection_transfer(budget_future.copy(), grid_connected_fy)

    # STEP 2: Apply phase adjustments
    budget_prime = apply_phase_multipliers(
        budget_prime,
        end_mining_fy,
        end_processing_fy,
        end_rehabilitation_fy,
        grid_connected_fy
    )

    print(f"✅ Budget Prime created: {len(budget_prime)} records")

    # 5. Recalculate emissions for Budget Prime
    print(f"\nRecalculating emissions for Budget Prime...")

    # Get NGA factors
    nga_folder = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(nga_folder):
        nga_folder = '/mnt/project'
    nga_by_year = NGAFactorsByYear(nga_folder)

    budget_prime = recalculate_emissions(budget_prime, nga_by_year)
    print(f"✅ Emissions recalculated")

    # 6. Combine actuals + Budget Prime
    combined = pd.concat([actuals, budget_prime], ignore_index=True)
    print(f"\n✅ Combined: {len(actuals)} actuals + {len(budget_prime)} budget prime = {len(combined)} total")

    # 7. Aggregate to annual
    print(f"\nAggregating to annual...")
    annual = aggregate_to_annual(combined, start_fy, end_fy)
    print(f"✅ Annual projection: {len(annual)} years (FY{start_fy}-FY{end_fy})")

    # 8. Calculate safeguard metrics
    print(f"\nCalculating safeguard metrics...")
    annual = calculate_safeguard_metrics(
        annual,
        fsei_rom,
        fsei_elec,
        credit_start_fy,
        end_mining_fy,
        end_processing_fy,
        end_rehabilitation_fy,
        grid_connected_fy
    )
    print(f"✅ Safeguard metrics calculated")

    print(f"\n{'='*80}")
    print(f"PROJECTION COMPLETE")
    print(f"{'='*80}\n")

    return annual


def apply_phase_multipliers(data, end_mining_fy, end_processing_fy,
                           end_rehabilitation_fy, grid_connected_fy):
    """Apply Cost Centre-based phase multipliers to quantities

    Creates Budget Prime by adjusting raw budget quantities based on phase.
    Does NOT handle grid connection transfer - that's done separately first.

    IMPORTANT: Only items with explicit multipliers in PHASE_ dicts get adjusted.
    Items without multipliers continue at 100% (no default adjustments).
    This makes missing config entries obvious and prevents hidden errors.
    """
    result = data.copy()

    # Process each FY
    for fy in result['FY'].unique():

        # Get phase profile for this FY
        phase_name, phase_profile, is_active = get_phase_profile(
            fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy, grid_connected_fy
        )

        fy_mask = result['FY'] == fy

        if not is_active:
            # Facility closed - zero everything
            result.loc[fy_mask, 'Quantity'] = 0
            continue

        # Apply Cost Centre multipliers ONLY to items in phase_profile
        # Items not in phase_profile continue at 100% (no default adjustment)
        for cost_centre, multiplier in phase_profile.items():
            mask = fy_mask & (result['CostCentre'] == cost_centre)
            if mask.any():
                result.loc[mask, 'Quantity'] *= multiplier

        # NO FALLBACK LOGIC
        # If a Cost Centre is not in the phase profile dictionary,
        # it continues at its budget value (100%).
        # This makes missing entries visible rather than hiding them with defaults.

    return result


def apply_grid_connection_transfer(data, grid_connected_fy):
    """Handle grid connection electricity transfer

    Grid connection occurs July 1st (Month 7) of grid_connected_fy.
    Runs BEFORE phase adjustments, so quantities are clean baselines.

    Changes:
    - Before grid: 100% diesel → site electricity (Scope 1)
    - Grid year Jul-Dec: 2% diesel → 2% site electricity + 98% grid (Scope 2)
    - After grid: 2% diesel → 2% site electricity + 98% grid (Scope 2)

    Adjustments made:
    1. Site electricity (kWh) → 2% of original
    2. Grid electricity (kWh) → +98% of site electricity
    3. Diesel oil - Site power generation (L) → 2% of original

    Args:
        data: DataFrame with monthly data (Budget, BEFORE phase adjustments)
        grid_connected_fy: Year grid connection occurs

    Returns:
        DataFrame with grid connection transfers applied
    """
    result = data.copy()

    # Track changes for logging
    diesel_before = 0
    diesel_after = 0
    site_elec_before = 0
    site_elec_after = 0
    grid_elec_before = 0
    grid_elec_after = 0

    # Process each month
    for fy in sorted(result['FY'].unique()):
        if fy < grid_connected_fy:
            continue  # Pre-grid: no changes needed

        for month in range(1, 13):
            # Determine if grid is active this month
            if fy > grid_connected_fy:
                grid_active = True  # Always on grid after connection year
            elif fy == grid_connected_fy and month >= 7:
                grid_active = True  # July onwards in connection year
            else:
                grid_active = False  # Pre-grid

            if not grid_active:
                continue  # No transfer needed

            # === 1. REDUCE DIESEL FUEL (Site power generation) ===
            diesel_mask = (result['FY'] == fy) & \
                         (result['Month'] == month) & \
                         (result['Description'] == 'Diesel oil - Site power generation')

            for idx in result[diesel_mask].index:
                original_qty = result.loc[idx, 'Quantity']
                diesel_before += original_qty

                # Reduce diesel to 2% (98% no longer needed)
                result.loc[idx, 'Quantity'] = original_qty * 0.02
                diesel_after += original_qty * 0.02

            # === 2. TRANSFER SITE ELECTRICITY TO GRID ===
            site_mask = (result['FY'] == fy) & \
                       (result['Month'] == month) & \
                       (result['Description'] == 'Site electricity')

            if not site_mask.any():
                continue  # No site electricity this month

            # Process each site electricity entry (by Cost Centre)
            for idx in result[site_mask].index:
                original_qty = result.loc[idx, 'Quantity']
                cost_centre = result.loc[idx, 'CostCentre']
                department = result.loc[idx, 'Department']

                site_elec_before += original_qty

                # Reduce site to 2%
                result.loc[idx, 'Quantity'] = original_qty * 0.02
                site_elec_after += original_qty * 0.02

                # Transfer 98% to grid
                transfer_qty = original_qty * 0.98

                # Find existing grid electricity for same cost centre/month
                grid_mask = (result['FY'] == fy) & \
                           (result['Month'] == month) & \
                           (result['Description'] == 'Grid electricity') & \
                           (result['CostCentre'] == cost_centre)

                if grid_mask.any():
                    # Add to existing grid entry
                    grid_idx = grid_mask.idxmax()
                    grid_elec_before += result.loc[grid_idx, 'Quantity']
                    result.loc[grid_idx, 'Quantity'] += transfer_qty
                    grid_elec_after += result.loc[grid_idx, 'Quantity']
                else:
                    # Create new grid electricity entry
                    new_row = result.loc[idx].copy()
                    new_row['Description'] = 'Grid electricity'
                    new_row['Quantity'] = transfer_qty
                    new_row['Source'] = 'Grid connection (from site)'
                    result = pd.concat([result, pd.DataFrame([new_row])], ignore_index=True)
                    grid_elec_after += transfer_qty

    # Summary logging
    print(f"✅ Grid connection transfer (active from FY{grid_connected_fy} July onwards):")
    print(f"   Diesel fuel:      {diesel_before:,.0f} → {diesel_after:,.0f} L ({diesel_before-diesel_after:,.0f} L reduced)")
    print(f"   Site electricity: {site_elec_before:,.0f} → {site_elec_after:,.0f} kWh ({site_elec_before-site_elec_after:,.0f} kWh reduced)")
    print(f"   Grid electricity: {grid_elec_before:,.0f} → {grid_elec_after:,.0f} kWh (+{grid_elec_after-grid_elec_before:,.0f} kWh added)")

    return result



def recalculate_emissions(data, nga_by_year):
    """Recalculate emissions from adjusted quantities

    Uses same logic as data_loader.py but on Budget Prime quantities
    """
    result = data.copy()

    # Reset emissions
    result['Scope1_tCO2e'] = 0.0
    result['Scope2_tCO2e'] = 0.0
    result['Scope3_tCO2e'] = 0.0

    # Get NGA factors for each FY
    unique_years = result['FY'].unique()
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
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_elec_s1'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_s3'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Diesel - Mobile equipment
    mask = result['Description'] == 'Diesel oil - Mobile equipment'
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_stat_s1'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_s3'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_diesel(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # LPG
    mask = result['Description'].str.contains('Liquefied petroleum gas', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['lpg_s1'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['lpg_s3'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_lpg(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_lpg(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Petroleum oils (Scope 3 only)
    mask = result['Description'].str.contains('Petroleum based oils', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['oil_s3'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_oils(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Petroleum greases (Scope 3 only)
    mask = result['Description'].str.contains('Petroleum based greases', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['grease_s3'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_greases(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s3'])

    # Acetylene
    mask = result['Description'].str.contains('gaseous fossil fuels', case=False, na=False)
    if mask.any():
        result.loc[mask, 'factor_s1'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['acetylene_s1'])
        result.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_acetylene(result.loc[mask, 'Quantity'], result.loc[mask, 'factor_s1'])

    # Grid electricity
    mask = result['Description'] == 'Grid electricity'
    if mask.any():
        result.loc[mask, 'factor_s2'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['grid_s2'])
        result.loc[mask, 'factor_s3'] = result.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['grid_s3'])
        # Convert kWh to MWh
        mwh = convert_kwh_to_mwh(result.loc[mask, 'Quantity'])
        result.loc[mask, 'Scope2_tCO2e'] = calculate_scope2_grid_electricity(mwh, result.loc[mask, 'factor_s2'])
        result.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_grid_electricity(mwh, result.loc[mask, 'factor_s3'])

    # Drop temporary factor columns
    factor_cols = [col for col in result.columns if col.startswith('factor_')]
    result = result.drop(columns=factor_cols)

    return result


def aggregate_to_annual(data, start_fy, end_fy):
    """Aggregate monthly data to annual"""

    # Aggregate emissions
    emissions_annual = data.groupby('FY').agg({
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum'
    }).reset_index()

    # Aggregate ROM (use "Ore Mined t" only - Safeguard production variable)
    rom_data = data[data['Description'] == 'Ore Mined t']
    rom_annual = rom_data.groupby('FY')['Quantity'].sum().reset_index()
    rom_annual['ROM_Mt'] = rom_annual['Quantity'] / 1_000_000
    rom_annual = rom_annual[['FY', 'ROM_Mt']]

    # Aggregate electricity consumption
    site_elec_data = data[data['Description'] == 'Site electricity']
    site_elec_annual = site_elec_data.groupby('FY')['Quantity'].sum().reset_index()
    site_elec_annual.columns = ['FY', 'Site_Electricity_kWh']

    grid_elec_data = data[data['Description'] == 'Grid electricity']
    grid_elec_annual = grid_elec_data.groupby('FY')['Quantity'].sum().reset_index()
    grid_elec_annual.columns = ['FY', 'Grid_Electricity_kWh']

    # Merge
    annual = emissions_annual.merge(rom_annual, on='FY', how='left')
    annual = annual.merge(site_elec_annual, on='FY', how='left')
    annual = annual.merge(grid_elec_annual, on='FY', how='left')
    annual['ROM_Mt'] = annual['ROM_Mt'].fillna(0)
    annual['Site_Electricity_kWh'] = annual['Site_Electricity_kWh'].fillna(0)
    annual['Grid_Electricity_kWh'] = annual['Grid_Electricity_kWh'].fillna(0)

    # Ensure all years present
    all_fys = pd.DataFrame({'FY': range(start_fy, end_fy + 1)})
    annual = all_fys.merge(annual, on='FY', how='left')
    annual = annual.fillna(0)

    # Add total emissions
    annual['Total'] = annual['Scope1_tCO2e'] + annual['Scope2_tCO2e'] + annual['Scope3_tCO2e']

    # Add aliases for backward compatibility
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']

    return annual


def calculate_safeguard_metrics(annual, fsei_rom, fsei_elec, credit_start_fy,
                                end_mining_fy, end_processing_fy,
                                end_rehabilitation_fy, grid_connected_fy):
    """Calculate safeguard mechanism metrics with dual FSEI components"""

    # Add phase column
    annual['Phase'] = annual['FY'].apply(lambda fy: get_phase_name(
        fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy, grid_connected_fy
    ))

    # Emission intensity (actual Scope 1 / ROM)
    annual['Emission_Intensity'] = 0.0
    mask = annual['ROM_Mt'] > 0
    annual.loc[mask, 'Emission_Intensity'] = annual.loc[mask, 'Scope1'] / (annual.loc[mask, 'ROM_Mt'] * 1_000_000)

    # Baseline intensity with BOTH ROM and electricity components
    # Based on FY2023-24 operational data: 11.624 Mt ROM, 101,540 MWh site generation
    # Site generation ratio: 101,540 / 11,624,000 = 0.008735 MWh/t ROM
    SITE_GENERATION_RATIO = 0.008735  # MWh per tonne ROM

    # Baseline Intensity = FSEI_ROM + (Site_MWh / ROM) × FSEI_ELEC
    #                    = 0.0177 + (0.008735 × 0.9081)
    #                    = 0.0177 + 0.00793
    #                    = 0.02563 tCO2-e/t
    baseline_intensity_base = fsei_rom + (SITE_GENERATION_RATIO * fsei_elec)

    annual['Baseline_Intensity'] = baseline_intensity_base
    for idx, row in annual.iterrows():
        fy = row['FY']
        if DECLINE_FROM <= fy <= DECLINE_TO:
            years_declining = fy - DECLINE_FROM
            decline_factor = (1 - DECLINE_RATE) ** years_declining
            annual.at[idx, 'Baseline_Intensity'] = baseline_intensity_base * decline_factor
        elif fy > DECLINE_TO:
            years_declining = DECLINE_TO - DECLINE_FROM
            decline_factor = (1 - DECLINE_RATE) ** years_declining
            annual.at[idx, 'Baseline_Intensity'] = baseline_intensity_base * decline_factor

    # Baseline emissions
    annual['Baseline'] = annual['Baseline_Intensity'] * annual['ROM_Mt'] * 1_000_000

    # Intensity excess (for reporting - positive means above baseline)
    annual['Intensity_Excess'] = annual['Emission_Intensity'] - annual['Baseline_Intensity']

    # SMC Annual = Baseline - Actual Scope 1
    # Positive = Credits earned (actual below baseline - good performance)
    # Negative = Liability (actual above baseline - need to buy credits or pay tax)
    annual['SMC_Annual'] = 0.0
    mask = (annual['FY'] >= credit_start_fy) & (annual['ROM_Mt'] > 0)
    annual.loc[mask, 'SMC_Annual'] = annual.loc[mask, 'Baseline'] - annual.loc[mask, 'Scope1']

    # Apply 10-year exit rule: Credits stop 10 years after dropping below 100,000 tCO2-e
    # Per Safeguard Mechanism regulations
    exit_year = None
    for idx, row in annual.iterrows():
        fy_num = row['FY']
        scope1 = row['Scope1']

        # Find first year below 100,000 tCO2-e threshold
        if exit_year is None and scope1 < 100_000:
            exit_year = fy_num

        # Zero credits after 10 years past exit year
        if exit_year is not None and (fy_num - exit_year) >= 10:
            annual.at[idx, 'SMC_Annual'] = 0.0

    # SMC Cumulative
    annual['SMC_Cumulative'] = 0.0
    cumulative = 0.0
    for idx, row in annual.iterrows():
        if row['FY'] >= credit_start_fy:
            cumulative += row['SMC_Annual']
        annual.at[idx, 'SMC_Cumulative'] = cumulative

    # In Safeguard threshold (100,000 tCO2-e)
    annual['In_Safeguard'] = annual['Scope1'] >= 100_000

    # Store exit year for reference
    annual['Exit_Year'] = exit_year if exit_year is not None else None

    # Format FY column
    annual['FY'] = 'FY' + annual['FY'].astype(int).astype(str)

    return annual


def get_phase_name(fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy, grid_connected_fy):
    """Get phase name for display"""
    phase_name, _, is_active = get_phase_profile(
        fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy, grid_connected_fy
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

    # Extract FY number
    result['FY_num'] = result['FY'].str.replace('FY', '').astype(int)

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

    # Credit value (SMC credits × escalated price)
    result['Credit_Value_Annual'] = result['SMC_Annual'] * result['Credit_Price']
    result['Credit_Value_Cumulative'] = result['Credit_Value_Annual'].cumsum()

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