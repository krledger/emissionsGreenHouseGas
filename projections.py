"""
projections.py
Scenario projections and safeguard mechanism modeling
Last updated: 2026-01-29 14:30 AEST

Now uses detailed fuel breakdown: Total_Scope1_tCO2e, Total_Scope2_tCO2e, Total_Scope3_tCO2e
Credits only accrue from CREDIT_START_FY onwards
"""

import pandas as pd
from emissions_calc import calc_baseline, summarise_energy
from config import POST_GRID_MWH, BASE_MWH, CATEGORY_MAP, CREDIT_START_FY


def build_projection(fuel_summary, elec_summary, rom_annual, start_fy, end_fy,
                     grid_fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy, elec_factors):
    """Build emissions projection scenario

    Args:
        fuel_summary: Output from summarise_fuel()
        elec_summary: Output from summarise_electricity()
        rom_annual: ROM production by FY
        start_fy: First projection year
        end_fy: Last projection year
        grid_fy: Year grid connection occurs
        end_mining_fy: Year mining operations end
        end_processing_fy: Year processing operations end
        end_rehabilitation_fy: Year rehabilitation activities end
        elec_factors: Electricity emission factors dict

    Returns:
        DataFrame with projection by FY

    Note:
        For detailed cost centre-level phase profiles, see PHASE_PROFILES in config.py
        Phase 1 (Mining): All operations at 100%
        Phase 2 (Processing): Mining ceased, processing continues with rehabilitation
        Phase 3 (Rehabilitation): Only rehabilitation and minimal support operations
    """
    results = []

    # Extract baseline patterns
    emissions_by_phase = fuel_summary['emissions_by_phase']
    elec_by_fy = elec_summary['by_fy']
    seasonal = elec_summary['seasonal']

    # Historical data
    rom_by_fy = dict(zip(rom_annual['FY'], rom_annual['Total_ROM']))
    rom_months = dict(zip(rom_annual['FY'], rom_annual['Months']))

    # Average patterns for projection
    mature_rom = rom_annual[rom_annual['FY'] >= 2023]
    avg_rom = mature_rom['Total_ROM'].mean() if len(mature_rom) > 0 else 0

    mature_elec = {k: v for k, v in elec_by_fy.items() if k >= 2023}
    avg_grid_mwh = sum(v['grid_mwh'] for v in mature_elec.values()) / len(mature_elec) if mature_elec else 0
    avg_total_mwh = sum(v['total_mwh'] for v in mature_elec.values()) / len(mature_elec) if mature_elec else 0

    cumulative_smcs = 0

    for fy in range(start_fy, end_fy + 1):
        # Phase status
        mining_active = fy <= end_mining_fy
        processing_active = fy <= end_processing_fy
        rehabilitation_active = fy <= end_rehabilitation_fy
        has_grid = fy >= grid_fy

        # Determine operational phase
        if mining_active:
            phase = 'mining'
        elif processing_active:
            phase = 'processing'
        elif rehabilitation_active:
            phase = 'rehabilitation'
        else:
            phase = 'closed'

        # Fuel emissions by phase
        fy_scope1 = 0
        fy_scope3_fuel = 0

        # Apply phase-specific adjustments based on operational profiles
        # See config.py PHASE_PROFILES for detailed cost centre breakdowns
        for cat in ['Power', 'Mining', 'Processing', 'Fixed']:
            cat_s1 = emissions_by_phase[cat]['scope1']
            cat_s3 = emissions_by_phase[cat]['scope3']

            # Apply phase adjustments
            if phase == 'closed':
                # All operations ceased
                cat_s1 = 0
                cat_s3 = 0
            elif phase == 'rehabilitation':
                # Rehabilitation phase: minimal operations
                if cat == 'Power':
                    cat_s1 = 0  # No power generation
                    cat_s3 = 0
                elif cat == 'Mining':
                    cat_s1 = 0  # No mining
                    cat_s3 = 0
                elif cat == 'Processing':
                    cat_s1 = 0  # No processing
                    cat_s3 = 0
                elif cat == 'Fixed':
                    cat_s1 *= 0.15  # Minimal support (rehab, environment, light admin)
                    cat_s3 *= 0.15
            elif phase == 'processing':
                # Processing phase: mining ceased, processing continues
                if cat == 'Power':
                    if has_grid:
                        cat_s1 *= (POST_GRID_MWH / BASE_MWH)
                        cat_s3 *= (POST_GRID_MWH / BASE_MWH)
                    # else keep full power generation
                elif cat == 'Mining':
                    cat_s1 = 0  # Mining operations ceased
                    cat_s3 = 0
                elif cat == 'Processing':
                    pass  # Continue processing stockpiles
                elif cat == 'Fixed':
                    cat_s1 *= 0.75  # Reduced fixed operations
                    cat_s3 *= 0.75
            else:  # phase == 'mining'
                # Active mining phase: all operations
                if cat == 'Power' and has_grid:
                    cat_s1 *= (POST_GRID_MWH / BASE_MWH)
                    cat_s3 *= (POST_GRID_MWH / BASE_MWH)
                # All other categories operate at 100%

            fy_scope1 += cat_s1
            fy_scope3_fuel += cat_s3

        # ROM production
        if mining_active:
            if fy in rom_by_fy:
                rom_tonnes = rom_by_fy[fy]
                months = rom_months.get(fy, 12)
                if months < 12:
                    rom_tonnes = rom_tonnes * 12 / months
            else:
                rom_tonnes = avg_rom
        else:
            rom_tonnes = 0

        # Baseline
        baseline_mwh = POST_GRID_MWH if has_grid else BASE_MWH
        baseline = calc_baseline(rom_tonnes, baseline_mwh, fy, apply_decline=True)

        # Grid electricity (Scope 2)
        if fy in elec_by_fy:
            if has_grid:
                grid_mwh = max(elec_by_fy[fy]['total_mwh'] - POST_GRID_MWH, elec_by_fy[fy]['grid_mwh'])
            else:
                grid_mwh = elec_by_fy[fy]['grid_mwh']
        else:
            grid_mwh = (avg_total_mwh - POST_GRID_MWH) if has_grid else avg_grid_mwh

        # Phase adjustments for electricity
        if phase == 'closed':
            grid_mwh = 0  # Facility closed
        elif phase == 'rehabilitation':
            grid_mwh *= 0.05  # Minimal grid power (5%)
        elif phase == 'processing':
            grid_mwh *= 0.70  # Reduced operations (70%)
        # else: mining phase keeps full electricity

        scope2 = grid_mwh * elec_factors['scope2']
        scope3_elec = grid_mwh * elec_factors['scope3']
        scope3 = fy_scope3_fuel + scope3_elec

        total_ghg = fy_scope1 + scope2 + scope3

        # Only calculate credits from CREDIT_START_FY onwards
        if fy >= CREDIT_START_FY:
            annual_smc = baseline - fy_scope1
            cumulative_smcs += annual_smc
        else:
            annual_smc = 0

        # Data source label
        if fy in rom_by_fy and fy in elec_by_fy:
            source = 'Actual'
        elif fy > max(rom_by_fy.keys() if rom_by_fy else [0]):
            source = 'Projected'
        else:
            source = 'Mixed'

        # Check if in Safeguard Mechanism (threshold: 100,000 tCO2-e)
        in_safeguard = fy_scope1 >= 100000

        results.append({
            'FY': f"FY{fy}",
            'Source': source,
            'Phase': phase.title(),
            'Mining': '✓' if mining_active else '',
            'Processing': '✓' if processing_active else '',
            'Rehabilitation': '✓' if rehabilitation_active and not processing_active else '',
            'Grid': '✓' if has_grid else '',
            'ROM_Mt': rom_tonnes / 1e6,
            'ROM_Source': 'Actual' if fy in rom_by_fy else 'Projected',
            'Site_MWh': baseline_mwh,
            'Grid_MWh': grid_mwh,
            'Baseline': baseline,
            'Scope1': fy_scope1,
            'Scope2': scope2,
            'Scope3': scope3,
            'Total_GHG': total_ghg,
            'SMC_Annual': annual_smc,
            'SMC_Cumulative': cumulative_smcs,
            'InSafeguard': in_safeguard
        })

    return pd.DataFrame(results)


def carbon_tax_analysis(projection_df, tax_start_fy, tax_rate, annual_increase):
    """Analyze carbon tax liability

    Args:
        projection_df: Output from build_projection()
        tax_start_fy: First year of carbon tax
        tax_rate: Initial tax rate ($/tCO2-e)
        annual_increase: Annual escalation rate (decimal)

    Returns:
        Dict with carbon tax summary
    """
    results = []

    for idx, row in projection_df.iterrows():
        fy = int(row['FY'].replace('FY', ''))

        if fy >= tax_start_fy:
            years_since_start = fy - tax_start_fy
            current_rate = tax_rate * ((1 + annual_increase) ** years_since_start)

            # Tax on Scope 1 only
            annual_tax = row['Scope1'] * current_rate

            results.append({
                'FY': row['FY'],
                'Tax_Rate': current_rate,
                'Scope1': row['Scope1'],
                'Annual_Tax': annual_tax
            })

    if results:
        df = pd.DataFrame(results)
        total_tax = df['Annual_Tax'].sum()
        npv_10pct = (df['Annual_Tax'] / (1.1 ** df.index)).sum()

        return {
            'df': df,
            'total_tax': total_tax,
            'npv_10pct': npv_10pct
        }

    return None


def build_projection_simple(start_fy, end_fy, rom_df, energy_df, nga_factors,
                            fsei_rom, fsei_elec, grid_connected_fy,
                            end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                            credit_start_fy=None):
    """Build emissions projection from raw dataframes (wrapper for tabs)

    Args:
        start_fy: First projection year
        end_fy: Last projection year
        rom_df: ROM DataFrame from load_rom_data()
        energy_df: Energy DataFrame from load_energy_data()
        nga_factors: NGA factors dict
        fsei_rom: Facility Specific Emission Intensity for ROM (tCO2-e/t)
        fsei_elec: Facility Specific Emission Intensity for electricity (tCO2-e/MWh)
        grid_connected_fy: Year grid connection occurs (diesel generation stops)
        end_mining_fy: Year mining operations end
        end_processing_fy: Year processing operations end
        end_rehabilitation_fy: Year rehabilitation activities end
        credit_start_fy: First FY when credits can be earned (default: use CREDIT_START_FY from config)

    Returns:
        DataFrame with annual projections

    Notes:
        - Baseline uses FY2024-2025 average (post-expansion period)
        - Supplemental Power values only accurate from 2024 onwards
        - Pre-2024 site generation was minimal and not representative
        - Annual projections do not account for seasonality
        - Future monthly/quarterly reporting may need seasonal adjustments
    """
    # Use default from config if not specified
    if credit_start_fy is None:
        credit_start_fy = CREDIT_START_FY
    # Get historical emissions by year from energy_df
    actual_emissions_by_year = {}
    for fy in energy_df['FY'].unique():
        fy_data = energy_df[energy_df['FY'] == fy]
        actual_emissions_by_year[fy] = {
            'scope1': fy_data['Total_Scope1_tCO2e'].sum(),
            'scope2': fy_data['Total_Scope2_tCO2e'].sum(),
            'scope3': fy_data['Total_Scope3_tCO2e'].sum(),
            'site_mwh': fy_data['SitePower_MWh'].sum()
        }

    # Get baseline patterns for future projections
    # Use FY2024-2025 average as baseline (post-expansion period)
    # Note: Supplemental Power values only accurate from 2024 onwards after plant expansion
    baseline_years = [2024, 2025]

    # Calculate average baseline from post-expansion years
    baseline_data = energy_df[energy_df['FY'].isin(baseline_years)].copy()

    # Group by cost centre and average across baseline years
    from config import CATEGORY_MAP

    baseline_data['Category'] = baseline_data['Costcentre'].map(CATEGORY_MAP)

    by_cc = baseline_data.groupby('Costcentre').agg({
        'Diesel_Electricity_L': 'sum',
        'Diesel_Transport_L': 'sum',
        'Diesel_Stationary_L': 'sum',
        'Diesel_Explosives_L': 'sum',
        'Diesel_Total_kL': 'sum',
        'GridPower_kWh': 'sum',
        'GridPower_MWh': 'sum',
        'SitePower_kWh': 'sum',
        'SitePower_MWh': 'sum',
        'Total_Scope1_tCO2e': 'sum',
        'Total_Scope2_tCO2e': 'sum',
        'Total_Scope3_tCO2e': 'sum'
    }).reset_index()

    # Create simplified columns for display
    by_cc['Fuel'] = (by_cc['Diesel_Electricity_L'] + by_cc['Diesel_Transport_L'] +
                     by_cc['Diesel_Stationary_L'] + by_cc['Diesel_Explosives_L'])
    by_cc['Fuel_kL'] = by_cc['Diesel_Total_kL']
    by_cc['GridPower'] = by_cc['GridPower_kWh']
    by_cc['SitePower'] = by_cc['SitePower_kWh']

    # Average across the baseline years (2 years)
    num_years = len(baseline_years)
    for col in by_cc.columns:
        if col not in ['Costcentre']:
            by_cc[col] = by_cc[col] / num_years

    # Add category mapping
    by_cc['Category'] = by_cc['Costcentre'].map(CATEGORY_MAP)

    print(f"Using FY{baseline_years[0]}-{baseline_years[-1]} average as baseline (post-expansion)")

    # Sum by category
    power_baseline = by_cc[by_cc['Category'] == 'Power']['Total_Scope1_tCO2e'].sum()
    mining_baseline = by_cc[by_cc['Category'] == 'Mining']['Total_Scope1_tCO2e'].sum()
    processing_baseline = by_cc[by_cc['Category'] == 'Processing']['Total_Scope1_tCO2e'].sum()
    fixed_baseline = by_cc[by_cc['Category'] == 'Fixed']['Total_Scope1_tCO2e'].sum()

    print(f"Baseline averages (FY{baseline_years[0]}-{baseline_years[-1]}):")
    print(f"  Power: {power_baseline:,.0f} tCO2e")
    print(f"  Mining: {mining_baseline:,.0f} tCO2e")
    print(f"  Processing: {processing_baseline:,.0f} tCO2e")
    print(f"  Fixed: {fixed_baseline:,.0f} tCO2e")
    print(f"  Total Scope 1: {power_baseline + mining_baseline + processing_baseline + fixed_baseline:,.0f} tCO2e")

    # Electricity baselines - BOTH grid and site
    grid_baseline_mwh = by_cc['GridPower_MWh'].sum()  # Existing grid electricity
    site_baseline_mwh = by_cc['SitePower_MWh'].sum()  # Diesel-generated electricity

    print(f"  Grid Power (existing): {grid_baseline_mwh:,.0f} MWh")
    print(f"  Site Power (diesel): {site_baseline_mwh:,.0f} MWh")
    print(f"  Total Electricity: {grid_baseline_mwh + site_baseline_mwh:,.0f} MWh")

    # Get actual ROM by year from ROM.csv
    rom_by_year = rom_df.groupby('FY')['ROM'].sum().to_dict()

    # Calculate ROM projection using BEST YEAR approach with randomness
    # Rationale: Use proven capacity from best full year, not average that includes anomalies
    import numpy as np
    from config import NGER_FY_START_MONTH

    # Get annual ROM totals for full years only (12 months of data)
    annual_rom = rom_df.groupby('FY').agg({
        'ROM': 'sum',
        'Date': 'count'  # Count months
    }).reset_index()
    annual_rom.columns = ['FY', 'ROM', 'Months']

    # Create month count dictionary for checking partial years
    rom_months = dict(zip(annual_rom['FY'], annual_rom['Months']))

    # Filter to full years only (12 months) to avoid partial year anomalies
    full_years = annual_rom[annual_rom['Months'] >= 12]

    if len(full_years) > 0:
        # Use BEST full year as baseline capacity (proven achievable)
        best_rom = full_years['ROM'].max()
        best_year = full_years.loc[full_years['ROM'].idxmax(), 'FY']
        print(f"ROM projection: Using best full year FY{best_year} = {best_rom/1e6:.2f} Mt as baseline")
    else:
        # Fallback to average if no full years available
        best_rom = annual_rom['ROM'].mean() if len(annual_rom) > 0 else 9.5e6
        print(f"ROM projection: No full years available, using average = {best_rom/1e6:.2f} Mt")

    # Calculate FY2024 monthly average for projecting partial years
    # FY2024 is the most reliable baseline (post-expansion, pre-slowdown)
    # This represents PROVEN CAPABILITY when operations are running well
    fy2024_data = annual_rom[annual_rom['FY'] == 2024]
    if len(fy2024_data) > 0 and fy2024_data.iloc[0]['Months'] == 12:
        fy2024_monthly_avg = fy2024_data.iloc[0]['ROM'] / 12.0
        print(f"FY2024 baseline: {fy2024_data.iloc[0]['ROM']/1e6:.2f} Mt total, {fy2024_monthly_avg/1e3:.1f}k tonnes/month")
        print(f"  Using FY2024 average for projections (proven capability)")
    else:
        # Fallback to best year monthly average
        fy2024_monthly_avg = best_rom / 12.0
        print(f"FY2024 not available, using best year monthly average: {fy2024_monthly_avg/1e3:.1f}k tonnes/month")

    # 10 Mtpa cap (regulatory/operational limit)
    MTPA_CAP = 10.0e6  # 10 million tonnes per year
    MONTHLY_CAP = MTPA_CAP / 12.0  # 833,333 tonnes per month

    # Create monthly lookup for actual ROM data
    # This allows us to distinguish between:
    # - Months with data showing zero mining (use actual zero)
    # - Months with no data yet (project using FY2024 baseline)
    rom_df['Year'] = rom_df['Date'].dt.year
    rom_df['Month'] = rom_df['Date'].dt.month

    # Create lookup: (Year, Month) -> ROM tonnes
    rom_monthly_lookup = {}
    for _, row in rom_df.iterrows():
        rom_monthly_lookup[(row['Year'], row['Month'])] = row['ROM']

    # Set random seed based on start_fy for reproducible but varied projections
    np.random.seed(start_fy * 100)

    results = []
    cumulative_smc = 0

    for fy in range(start_fy, end_fy + 1):
        fy_str = f'FY{fy}'

        # Determine phase
        if fy <= end_mining_fy:
            phase = 'Mining'
            phase_factor = 1.0
        elif fy <= end_processing_fy:
            phase = 'Processing'
            phase_factor = 0.5
        elif fy <= end_rehabilitation_fy:
            phase = 'Rehabilitation'
            phase_factor = 0.1
        else:
            phase = 'Closed'
            phase_factor = 0.0

        # ROM production - DYNAMIC PROJECTION with monthly granularity
        rom_is_actual = False
        if phase == 'Mining':
            # Build ROM month-by-month for this FY
            # Safeguard FY runs July-June, so FY2026 = Jul 2025 - Jun 2026

            # Determine which calendar year/months belong to this FY
            # For NGER FY (July-June): FY2026 spans Jul 2025 (year=2025, month=7) to Jun 2026 (year=2026, month=6)
            fy_months = []
            for month_offset in range(12):
                if NGER_FY_START_MONTH == 7:  # July-June FY
                    # First 6 months are in year (fy-1), last 6 months are in year (fy)
                    if month_offset < 6:
                        # Jul-Dec of previous calendar year
                        cal_year = fy - 1
                        cal_month = NGER_FY_START_MONTH + month_offset
                    else:
                        # Jan-Jun of current calendar year
                        cal_year = fy
                        cal_month = month_offset - 6 + 1
                else:  # January-December FY
                    cal_year = fy
                    cal_month = month_offset + 1

                fy_months.append((cal_year, cal_month))

            # Check which months have actual data vs need projection
            actual_rom_total = 0
            projected_rom_total = 0
            months_with_actual = 0
            months_needing_projection = 0
            monthly_breakdown = []

            for cal_year, cal_month in fy_months:
                if (cal_year, cal_month) in rom_monthly_lookup:
                    # We have actual data for this month (even if zero)
                    month_rom = rom_monthly_lookup[(cal_year, cal_month)]
                    actual_rom_total += month_rom
                    months_with_actual += 1
                    monthly_breakdown.append(f"{cal_year}-{cal_month:02d}: {month_rom/1e3:.0f}k (actual)")
                else:
                    # No data for this month - project using FY2024 baseline
                    month_rom = min(fy2024_monthly_avg, MONTHLY_CAP)  # Apply cap
                    projected_rom_total += month_rom
                    months_needing_projection += 1
                    monthly_breakdown.append(f"{cal_year}-{cal_month:02d}: {month_rom/1e3:.0f}k (projected)")

            rom_tonnes = actual_rom_total + projected_rom_total

            # Determine if this is fully actual or partially projected
            if months_needing_projection == 0:
                rom_is_actual = True
            else:
                rom_is_actual = False
                print(f"\n  FY{fy} ROM Breakdown:")
                print(f"    {months_with_actual} months actual: {actual_rom_total/1e6:.2f} Mt")
                print(f"    {months_needing_projection} months projected (FY2024 baseline): {projected_rom_total/1e6:.2f} Mt")
                print(f"    Total FY{fy}: {rom_tonnes/1e6:.2f} Mt")
                if months_needing_projection <= 3:  # Show details for near-complete years
                    print(f"    Missing months:")
                    for breakdown in monthly_breakdown:
                        if 'projected' in breakdown:
                            print(f"      {breakdown}")
        else:
            rom_tonnes = 0
            rom_is_actual = False  # No ROM in processing/rehab

        rom_mt = rom_tonnes / 1e6

        # Check if we have actual historical emissions data for this year
        emissions_is_actual = fy in actual_emissions_by_year

        # Overall actual flag: both ROM and emissions must be actual
        is_actual_data = rom_is_actual and emissions_is_actual

        if is_actual_data:
            # Use actual historical data
            actual_data = actual_emissions_by_year[fy]
            scope1_total = actual_data['scope1']
            scope2_total = actual_data['scope2']
            scope3_total = actual_data['scope3']
            site_generation_mwh = actual_data['site_mwh']

            # Calculate grid MWh from scope2 if using grid
            if scope2_total > 0 and nga_factors['scope2'] > 0:
                grid_mwh = scope2_total / nga_factors['scope2']
            else:
                grid_mwh = 0

            # Determine if grid connected (based on actual data)
            grid_connected = (grid_mwh > 1000)  # Threshold: >1 GWh means grid connected

        else:
            # PROJECTION - no actual data available
            # Use baseline patterns for future projection
            if fy < grid_connected_fy:
                # Pre-grid: ALL power from onsite diesel generation
                power_s1 = power_baseline * phase_factor
                grid_connected = False
            else:
                # Post-grid: diesel generation mostly STOPS but keep some portable generation
                if phase == 'Mining':
                    # Mining: keep 10% supplemental power for portable generators
                    power_s1 = power_baseline * 0.10 * phase_factor
                elif phase == 'Processing':
                    # Processing: keep 5% supplemental power
                    power_s1 = power_baseline * 0.05 * phase_factor
                else:
                    # Rehabilitation/Closed: no supplemental power
                    power_s1 = 0
                grid_connected = True

            mining_s1 = mining_baseline * phase_factor if phase == 'Mining' else 0
            processing_s1 = processing_baseline * phase_factor if phase in ['Mining', 'Processing'] else 0
            fixed_s1 = fixed_baseline * phase_factor

            scope1_total = power_s1 + mining_s1 + processing_s1 + fixed_s1

            # Grid electricity emissions (Scope 2)
            if grid_connected:
                # Post-grid: Existing grid PLUS replacement of diesel generation
                if phase == 'Mining':
                    # Existing grid continues
                    existing_grid = grid_baseline_mwh * phase_factor
                    # Replace 90% of site generation with grid
                    replacement_grid = site_baseline_mwh * 0.90 * phase_factor
                    # Total grid
                    grid_mwh = existing_grid + replacement_grid
                    # Remaining 10% still diesel-generated
                    site_generation_mwh = site_baseline_mwh * 0.10 * phase_factor

                elif phase == 'Processing':
                    # Existing grid continues
                    existing_grid = grid_baseline_mwh * phase_factor
                    # Replace 95% of site generation with grid
                    replacement_grid = site_baseline_mwh * 0.95 * phase_factor
                    # Total grid
                    grid_mwh = existing_grid + replacement_grid
                    # Remaining 5% still diesel-generated
                    site_generation_mwh = site_baseline_mwh * 0.05 * phase_factor

                else:
                    # Rehabilitation: all electricity from grid
                    grid_mwh = (grid_baseline_mwh + site_baseline_mwh) * phase_factor
                    site_generation_mwh = 0

                scope2_total = grid_mwh * nga_factors['scope2']

            else:
                # Pre-grid: only existing grid electricity
                grid_mwh = grid_baseline_mwh * phase_factor
                scope2_total = grid_mwh * nga_factors['scope2']
                # All site power from diesel
                site_generation_mwh = site_baseline_mwh * phase_factor

            # Scope 3
            fuel_kl = scope1_total / 2.71  # Approximate diesel consumption from emissions
            scope3_fuel = fuel_kl * nga_factors['diesel']['scope3_t_co2e_per_kl']
            scope3_grid = grid_mwh * nga_factors['scope3']
            scope3_total = scope3_fuel + scope3_grid

        total_emissions = scope1_total + scope2_total + scope3_total

        # Baseline calculation with BOTH ROM and Electricity components
        # Baseline calculation - FIXED baseline with production adjustment
        # Baseline should NOT track actual performance
        if rom_tonnes > 0:
            # Import decline parameters (FSEI values come from function parameters)
            from config import DECLINE_RATE, DECLINE_FROM, DECLINE_TO

            # FIXED baseline intensity calculation using sidebar FSEI values
            # Uses baseline year's electricity generation, not actual
            baseline_rom_component = fsei_rom
            baseline_elec_component = (site_baseline_mwh * fsei_elec) / best_rom

            # Total baseline intensity (before decline)
            baseline_intensity_raw = baseline_rom_component + baseline_elec_component

            # Apply baseline decline (4.9% p.a. from FY2024 to FY2030)
            # CRITICAL: After FY2030, baseline STAYS at final declined value (doesn't revert)
            if fy < DECLINE_FROM:
                # Before decline period - use raw baseline
                baseline_intensity_value = baseline_intensity_raw
            elif fy <= DECLINE_TO:
                # During decline period - apply cumulative decline
                years_since = fy - DECLINE_FROM
                decline_factor = (1 - DECLINE_RATE) ** years_since
                baseline_intensity_value = baseline_intensity_raw * decline_factor
            else:
                # After decline period - STAY at final declined value
                years_total = DECLINE_TO - DECLINE_FROM
                final_decline_factor = (1 - DECLINE_RATE) ** years_total
                baseline_intensity_value = baseline_intensity_raw * final_decline_factor

            # Production-adjusted baseline: baseline intensity × actual ROM
            baseline_emissions = baseline_intensity_value * rom_tonnes

            # Actual emission intensity
            emission_intensity = scope1_total / rom_tonnes
        else:
            emission_intensity = 0
            baseline_emissions = 0
            baseline_intensity_value = 0

        # Only calculate credits from credit_start_fy onwards
        if fy >= credit_start_fy:
            smc_annual = baseline_emissions - scope1_total
            cumulative_smc += smc_annual
        else:
            smc_annual = 0

        # Check if in safeguard
        in_safeguard = scope1_total >= 100000

        # For actual data, component breakdown not available from raw data
        # Estimate using baseline patterns
        if not is_actual_data:
            power_component = power_s1 if 'power_s1' in locals() else 0
            mining_component = mining_s1 if 'mining_s1' in locals() else 0
            processing_component = processing_s1 if 'processing_s1' in locals() else 0
            fixed_component = fixed_s1 if 'fixed_s1' in locals() else 0
        else:
            # Actual data - estimate breakdown using baseline proportions
            total_baseline = power_baseline + mining_baseline + processing_baseline + fixed_baseline
            if total_baseline > 0:
                power_component = scope1_total * (power_baseline / total_baseline)
                mining_component = scope1_total * (mining_baseline / total_baseline)
                processing_component = scope1_total * (processing_baseline / total_baseline)
                fixed_component = scope1_total * (fixed_baseline / total_baseline)
            else:
                power_component = 0
                mining_component = 0
                processing_component = 0
                fixed_component = 0

        results.append({
            'FY': fy_str,
            'Phase': phase,
            'ROM_Mt': rom_mt,
            'Scope1': scope1_total,
            'Scope2': scope2_total,
            'Scope3': scope3_total,
            'Total': total_emissions,
            'Power': power_component,
            'Mining': mining_component,
            'Processing': processing_component,
            'Fixed': fixed_component,
            'Baseline': baseline_emissions,
            'Emission_Intensity': emission_intensity,
            'Baseline_Intensity': baseline_intensity_value,
            'SMC_Annual': smc_annual,
            'SMC_Cumulative': cumulative_smc,
            'In_Safeguard': in_safeguard,
            'Grid_MWh': grid_mwh,
            'Site_Generation_MWh': site_generation_mwh,
            'Is_Actual': is_actual_data,  # Both ROM and emissions actual
            'ROM_Is_Actual': rom_is_actual,  # ROM data is actual
            'Emissions_Is_Actual': emissions_is_actual  # Emissions data is actual
        })

    return pd.DataFrame(results)