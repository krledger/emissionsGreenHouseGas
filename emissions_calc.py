"""
emissions_calc.py
Emissions calculation functions for Ravenswood Gold
Last updated: 2025-12-23

Calculates emissions from Energy.csv and ROM.csv
"""

import pandas as pd
from config import CATEGORY_MAP, MATURITY_CUTOFF


def summarise_energy(energy_df, baseline_fy=None, annualize_partial=True):
    """Summarise energy consumption and emissions by cost centre

    Args:
        energy_df: DataFrame from load_energy_data()
        baseline_fy: Financial year to use as baseline
        annualize_partial: If True, scale partial years to 12 months (default True)

    Returns:
        Dict with energy summaries by FY and cost centre
    """
    if baseline_fy is None:
        baseline_fy = energy_df['FY'].max()

    # =======================
    # FY TOTALS WITH OPTIONAL ANNUALIZATION
    # =======================

    by_fy = {}
    for fy in energy_df['FY'].unique():
        fy_data = energy_df[energy_df['FY'] == fy]
        months = fy_data['Month'].nunique()

        # Calculate actual values
        fuel_litres_actual = fy_data['Fuel'].sum()
        fuel_kL_actual = fy_data['Fuel_kL'].sum()
        grid_kwh_actual = fy_data['GridPower'].sum()
        grid_mwh_actual = fy_data['GridPower_MWh'].sum()
        site_kwh_actual = fy_data['SitePower'].sum()
        site_mwh_actual = fy_data['SitePower_MWh'].sum()
        scope1_actual = fy_data['Fuel_tCO2e_S1'].sum()
        scope2_actual = fy_data['Grid_tCO2e_S2'].sum()
        scope3_fuel_actual = fy_data['Fuel_tCO2e_S3'].sum()
        scope3_grid_actual = fy_data['Grid_tCO2e_S3'].sum()

        # Apply annualization if requested and partial year
        if annualize_partial and months < 12 and months > 0:
            scale_factor = 12.0 / months
            by_fy[fy] = {
                'fuel_litres': fuel_litres_actual * scale_factor,
                'fuel_kL': fuel_kL_actual * scale_factor,
                'grid_kwh': grid_kwh_actual * scale_factor,
                'grid_mwh': grid_mwh_actual * scale_factor,
                'site_kwh': site_kwh_actual * scale_factor,
                'site_mwh': site_mwh_actual * scale_factor,
                'scope1_fuel': scope1_actual * scale_factor,
                'scope2_grid': scope2_actual * scale_factor,
                'scope3_fuel': scope3_fuel_actual * scale_factor,
                'scope3_grid': scope3_grid_actual * scale_factor,
                'months_actual': months,
                'is_complete': False,
                'is_annualized': True,
                'scale_factor': scale_factor
            }
        else:
            by_fy[fy] = {
                'fuel_litres': fuel_litres_actual,
                'fuel_kL': fuel_kL_actual,
                'grid_kwh': grid_kwh_actual,
                'grid_mwh': grid_mwh_actual,
                'site_kwh': site_kwh_actual,
                'site_mwh': site_mwh_actual,
                'scope1_fuel': scope1_actual,
                'scope2_grid': scope2_actual,
                'scope3_fuel': scope3_fuel_actual,
                'scope3_grid': scope3_grid_actual,
                'months_actual': months,
                'is_complete': months == 12,
                'is_annualized': False,
                'scale_factor': 1.0
            }

    # =======================
    # BASELINE YEAR BY COST CENTRE WITH OPTIONAL ANNUALIZATION
    # =======================

    fy_data = energy_df[energy_df['FY'] == baseline_fy]
    months = fy_data['Month'].nunique()

    # Apply scaling factor if annualizing partial year
    if annualize_partial and months < 12 and months > 0:
        scale_factor = 12.0 / months
    else:
        scale_factor = 1.0

    by_cc = fy_data.groupby('Costcentre').agg({
        'Fuel': 'sum',
        'Fuel_kL': 'sum',
        'Fuel_tCO2e_S1': 'sum',
        'Fuel_tCO2e_S3': 'sum',
        'GridPower': 'sum',
        'GridPower_MWh': 'sum',
        'Grid_tCO2e_S2': 'sum',
        'Grid_tCO2e_S3': 'sum',
        'SitePower': 'sum',
        'SitePower_MWh': 'sum'
    }).reset_index()

    # Apply scale factor to all numeric columns
    numeric_cols = by_cc.select_dtypes(include=['number']).columns
    by_cc[numeric_cols] = by_cc[numeric_cols] * scale_factor

    # Add metadata
    by_cc['Months_Actual'] = months
    by_cc['Is_Annualized'] = (scale_factor != 1.0)

    # Add category
    by_cc['Category'] = by_cc['Costcentre'].map(CATEGORY_MAP).fillna('Fixed')

    # Calculate totals
    by_cc['Total_tCO2e_S1'] = by_cc['Fuel_tCO2e_S1']
    by_cc['Total_tCO2e_S2'] = by_cc['Grid_tCO2e_S2']
    by_cc['Total_tCO2e_S3'] = by_cc['Fuel_tCO2e_S3'] + by_cc['Grid_tCO2e_S3']
    by_cc['Total_tCO2e'] = by_cc['Total_tCO2e_S1'] + by_cc['Total_tCO2e_S2'] + by_cc['Total_tCO2e_S3']

    # Percentages
    total_fuel = by_cc['Fuel'].sum()
    total_grid = by_cc['GridPower'].sum()

    by_cc['Fuel_Pct'] = (by_cc['Fuel'] / total_fuel * 100) if total_fuel > 0 else 0
    by_cc['Grid_Pct'] = (by_cc['GridPower'] / total_grid * 100) if total_grid > 0 else 0

    # Sort by total emissions
    by_cc = by_cc.sort_values('Total_tCO2e', ascending=False)

    # =======================
    # SEASONAL PATTERNS
    # =======================

    mature = energy_df[energy_df['Date'] >= MATURITY_CUTOFF]
    seasonal_fuel = mature.groupby('Month')['Fuel_kL'].mean().to_dict()
    seasonal_grid = mature.groupby('Month')['GridPower_MWh'].mean().to_dict()
    seasonal_site = mature.groupby('Month')['SitePower_MWh'].mean().to_dict()

    # =======================
    # RETURN SUMMARY
    # =======================

    return {
        'by_fy': by_fy,
        'by_costcentre': by_cc,
        'baseline_fy': baseline_fy,
        'baseline_data': by_fy.get(baseline_fy, {}),
        'seasonal_fuel': seasonal_fuel,
        'seasonal_grid': seasonal_grid,
        'seasonal_site': seasonal_site,
        'total_scope1': by_cc['Total_tCO2e_S1'].sum(),
        'total_scope2': by_cc['Total_tCO2e_S2'].sum(),
        'total_scope3': by_cc['Total_tCO2e_S3'].sum(),
    }


def summarise_rom(rom_df, annualize_partial=True):
    """Summarise ROM production by financial year

    Args:
        rom_df: DataFrame from load_rom_data()
        annualize_partial: If True, scale partial years to 12 months (default True)

    Returns:
        Dict with ROM totals by FY
    """
    by_fy = {}
    for fy in rom_df['FY'].unique():
        fy_data = rom_df[rom_df['FY'] == fy]
        months = fy_data['Month'].nunique()

        rom_actual = fy_data['ROM'].sum()

        # Apply annualization if requested and partial year
        if annualize_partial and months < 12 and months > 0:
            scale_factor = 12.0 / months
            rom_annualized = rom_actual * scale_factor
            by_fy[fy] = {
                'rom_tonnes': rom_annualized,
                'rom_tonnes_actual': rom_actual,
                'months_actual': months,
                'is_complete': False,
                'is_annualized': True,
                'scale_factor': scale_factor
            }
        else:
            by_fy[fy] = {
                'rom_tonnes': rom_actual,
                'rom_tonnes_actual': rom_actual,
                'months_actual': months,
                'is_complete': months == 12,
                'is_annualized': False,
                'scale_factor': 1.0
            }

    return by_fy


def calc_baseline(rom_tonnes, site_mwh, baseline_fy, fsei_rom=0.0177, fsei_elec=0.9081, apply_decline=False):
    """Calculate Safeguard baseline using FSEI method

    Args:
        rom_tonnes: ROM production (tonnes)
        site_mwh: On-site electricity generation (MWh)
        baseline_fy: Baseline financial year
        fsei_rom: ROM emission intensity (tCO2-e/tonne)
        fsei_elec: Electricity emission intensity (tCO2-e/MWh)
        apply_decline: Apply baseline decline rate (default False)

    Returns:
        Baseline emissions (tCO2-e)
    """
    from config import DECLINE_RATE, DECLINE_FROM, DECLINE_TO

    baseline = (rom_tonnes * fsei_rom) + (site_mwh * fsei_elec)

    if apply_decline and baseline_fy >= DECLINE_FROM and baseline_fy <= DECLINE_TO:
        years_since = baseline_fy - DECLINE_FROM
        decline_factor = (1 - DECLINE_RATE) ** years_since
        baseline *= decline_factor

    return baseline


def calculate_emissions(energy_df, fy, rom_tonnes, nga_factors, annualize_partial=True):
    """Calculate emissions for a specific financial year

    Args:
        energy_df: DataFrame from load_energy_data()
        fy: Financial year - can be int (2024) or string ('FY2024')
        rom_tonnes: ROM production for the year (tonnes)
        nga_factors: Dict from load_nga_factors()
        annualize_partial: If True, scale partial years to 12 months (default True)

    Returns:
        Dict with scope1, scope2, scope3, total emissions
        Returns None if no data exists for this FY
    """
    # Convert FY to integer if it's a string like "FY2024"
    if isinstance(fy, str):
        fy_int = int(fy.replace('FY', ''))
    else:
        fy_int = fy

    # Filter to the specific FY
    fy_data = energy_df[energy_df['FY'] == fy_int]

    if len(fy_data) == 0:
        # No data for this FY - return None, not zeros
        return None

    # Count actual months
    months = fy_data['Month'].nunique()

    # Calculate actual values
    scope1_actual = fy_data['Fuel_tCO2e_S1'].sum()
    scope2_actual = fy_data['Grid_tCO2e_S2'].sum()
    scope3_fuel_actual = fy_data['Fuel_tCO2e_S3'].sum()
    scope3_grid_actual = fy_data['Grid_tCO2e_S3'].sum()
    scope3_actual = scope3_fuel_actual + scope3_grid_actual
    fuel_kl_actual = fy_data['Fuel_kL'].sum()
    grid_mwh_actual = fy_data['GridPower_MWh'].sum()
    site_mwh_actual = fy_data['SitePower_MWh'].sum()

    # Apply annualization if requested and partial year
    if annualize_partial and months < 12 and months > 0:
        scale_factor = 12.0 / months
        return {
            'scope1': scope1_actual * scale_factor,
            'scope2': scope2_actual * scale_factor,
            'scope3': scope3_actual * scale_factor,
            'total': (scope1_actual + scope2_actual + scope3_actual) * scale_factor,
            'fuel_kl': fuel_kl_actual * scale_factor,
            'grid_mwh': grid_mwh_actual * scale_factor,
            'site_mwh': site_mwh_actual * scale_factor,
            'rom_tonnes': rom_tonnes,
            'months_actual': months,
            'is_complete': False,
            'is_annualized': True,
            'scale_factor': scale_factor
        }
    else:
        return {
            'scope1': scope1_actual,
            'scope2': scope2_actual,
            'scope3': scope3_actual,
            'total': scope1_actual + scope2_actual + scope3_actual,
            'fuel_kl': fuel_kl_actual,
            'grid_mwh': grid_mwh_actual,
            'site_mwh': site_mwh_actual,
            'rom_tonnes': rom_tonnes,
            'months_actual': months,
            'is_complete': months == 12,
            'is_annualized': False,
            'scale_factor': 1.0
        }