"""
data_loader.py
Enhanced data loading with detailed fuel breakdown for NGERS compliance
Last updated: 2026-01-22 10:30 AEST

Loads Energy.xlsx with detailed fuel type tracking:
- Diesel by purpose (electricity, transport, stationary, explosives)
- LPG
- Petroleum oils and greases
- Gaseous fossil fuels
- Grid and site electricity

Loads ROM data from PhysicalsActual.xlsx:
- Extracts "Ore Mined t - Total" metric from all year sheets
- Combines data from 2022, 2023, 2024, 2025 sheets

Uses year-specific NGA emission factors (2021-2025)
"""

import pandas as pd
from pathlib import Path
from config import calculate_fy, NGER_PURPOSE_MAP
from nga_loader import NGAFactorsByYear
import sys
from datetime import datetime


# Log file path
LOG_FILE = 'data_loading.log'

def log_to_file(message):
    """Append message to log file with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")

def log_error(error_type, message, details=None):
    """Log data loading errors to file"""
    log_msg = f"ERROR [{error_type}]: {message}"
    if details:
        log_msg += f" | Details: {details}"
    log_to_file(log_msg)
    print(f"Ã¢ÂÅ’ {log_msg}", file=sys.stderr)

def log_success(message):
    """Log successful operation"""
    log_to_file(f"SUCCESS: {message}")
    print(f"Ã¢Å“â€œ {message}")

def start_loading_session():
    """Start a new loading session in log"""
    log_to_file("=" * 80)
    log_to_file("NEW DATA LOADING SESSION - ENHANCED WITH FUEL BREAKDOWN")
    log_to_file("=" * 80)


def classify_diesel_purpose(row, site_power_threshold=100000):
    """
    Classify diesel usage by purpose based on cost centre and context

    Returns: 'electricity', 'transport', 'stationary', or 'explosives'
    """
    cc = row['Costcentre']

    # Electricity generation - sites with significant onsite power generation
    if cc in ['Milling', 'Operations Administration'] and row.get('SitePower', 0) > site_power_threshold:
        return 'electricity'

    # Transport - mobile equipment
    if cc in ['Hauling', 'Light Vehicles', 'Loading', 'Rehandling', 'Mobile Equipment',
              'Supplementary Load and Haul']:
        return 'transport'

    # Explosives - blasting and drilling with ANFO
    if cc in ['Blasting', 'Drilling - Production']:
        return 'explosives'

    # Stationary - everything else
    return 'stationary'


def load_energy_data(filepath, nga_by_year, fy_start_month=1):
    """Load and process Energy.xlsx with detailed fuel type breakdown

    Energy.xlsx has a flat file structure in the 'data' sheet.
    This function aggregates by fuel type and purpose for NGERS compliance.

    Args:
        filepath: Path to Energy.xlsx
        nga_by_year: NGAFactorsByYear instance with factors for all years
        fy_start_month: Fiscal year start month (1=Jan, 7=Jul, etc.)

    Returns:
        DataFrame with detailed fuel breakdown and emissions by type
    """
    try:
        # Load both sheets
        data_df = pd.read_excel(filepath, sheet_name='data')
        ref_df = pd.read_excel(filepath, sheet_name='InventoryRef')
        log_success(f"Loaded Energy.xlsx: {len(data_df)} rows from 'data' sheet")
    except FileNotFoundError:
        log_error('FILE_NOT_FOUND', f'Energy.xlsx not found at {filepath}')
        raise
    except Exception as e:
        log_error('FILE_READ_ERROR', f'Error reading Energy.xlsx: {str(e)}')
        raise

    try:
        # Rename columns for consistency
        data_df = data_df.rename(columns={'Cost Centre': 'Costcentre'})

        # Merge with InventoryRef to get NGERS categories
        merged = data_df.merge(
            ref_df[['Inventory Item', 'NGERS Category', 'UOM']],
            left_on='Inventory Code',
            right_on='Inventory Item',
            how='left'
        )

        log_success(f"Merged with InventoryRef: {len(merged)} records")

        # =====================================================================
        # STEP 1: SEPARATE EACH FUEL TYPE
        # =====================================================================

        # Diesel (will be split by purpose later)
        diesel_all = merged[merged['NGERS Category'] == 'Diesel oil'].copy()

        # LPG
        lpg = merged[merged['NGERS Category'] == 'Liquefied petroleum gas'].copy()

        # Petroleum oils
        oils = merged[merged['NGERS Category'] == 'Petroleum based oils'].copy()

        # Petroleum greases
        greases = merged[merged['NGERS Category'] == 'Petroleum based greases'].copy()

        # Gaseous fossil fuels (acetylene, etc.)
        gases = merged[merged['NGERS Category'] == 'Other gaseous fossil fuels'].copy()

        # Grid and Site Power
        grid = merged[merged['Inventory Code'] == 'Grid Power'].copy()
        site = merged[merged['Inventory Code'] == 'Site Power'].copy()

        log_success(f"Separated fuel types: Diesel={len(diesel_all)}, LPG={len(lpg)}, " +
                   f"Oils={len(oils)}, Greases={len(greases)}, Gases={len(gases)}")

        # =====================================================================
        # STEP 2: AGGREGATE DIESEL BY PURPOSE
        # =====================================================================

        # First need to aggregate diesel by Date/Costcentre to classify purpose
        diesel_agg = diesel_all.groupby(['Date', 'Costcentre']).agg({
            'Quantity': 'sum'
        }).reset_index()

        # Get site power for each Date/Costcentre to help classify
        site_power_map = site.groupby(['Date', 'Costcentre'])['Quantity'].sum().to_dict()
        diesel_agg['SitePower'] = diesel_agg.apply(
            lambda r: site_power_map.get((r['Date'], r['Costcentre']), 0), axis=1
        )

        # Classify each diesel record by purpose
        diesel_agg['Purpose'] = diesel_agg.apply(classify_diesel_purpose, axis=1)

        # Split into separate dataframes by purpose
        diesel_electricity = diesel_agg[diesel_agg['Purpose'] == 'electricity'][['Date', 'Costcentre', 'Quantity']].copy()
        diesel_electricity = diesel_electricity.rename(columns={'Quantity': 'Diesel_Electricity_L'})

        diesel_transport = diesel_agg[diesel_agg['Purpose'] == 'transport'][['Date', 'Costcentre', 'Quantity']].copy()
        diesel_transport = diesel_transport.rename(columns={'Quantity': 'Diesel_Transport_L'})

        diesel_stationary = diesel_agg[diesel_agg['Purpose'] == 'stationary'][['Date', 'Costcentre', 'Quantity']].copy()
        diesel_stationary = diesel_stationary.rename(columns={'Quantity': 'Diesel_Stationary_L'})

        diesel_explosives = diesel_agg[diesel_agg['Purpose'] == 'explosives'][['Date', 'Costcentre', 'Quantity']].copy()
        diesel_explosives = diesel_explosives.rename(columns={'Quantity': 'Diesel_Explosives_L'})

        log_success(f"Split diesel by purpose: Electricity={len(diesel_electricity)}, " +
                   f"Transport={len(diesel_transport)}, Stationary={len(diesel_stationary)}, " +
                   f"Explosives={len(diesel_explosives)}")

        # =====================================================================
        # STEP 3: AGGREGATE OTHER FUEL TYPES
        # =====================================================================

        lpg_agg = lpg.groupby(['Date', 'Costcentre'])['Quantity'].sum().reset_index()
        lpg_agg = lpg_agg.rename(columns={'Quantity': 'LPG_kg'})

        oils_agg = oils.groupby(['Date', 'Costcentre'])['Quantity'].sum().reset_index()
        oils_agg = oils_agg.rename(columns={'Quantity': 'Petroleum_Oils_L'})

        greases_agg = greases.groupby(['Date', 'Costcentre'])['Quantity'].sum().reset_index()
        greases_agg = greases_agg.rename(columns={'Quantity': 'Petroleum_Greases_kg'})

        gases_agg = gases.groupby(['Date', 'Costcentre'])['Quantity'].sum().reset_index()
        gases_agg = gases_agg.rename(columns={'Quantity': 'Acetylene_m3'})

        grid_agg = grid.groupby(['Date', 'Costcentre'])['Quantity'].sum().reset_index()
        grid_agg = grid_agg.rename(columns={'Quantity': 'GridPower_kWh'})

        site_agg = site.groupby(['Date', 'Costcentre'])['Quantity'].sum().reset_index()
        site_agg = site_agg.rename(columns={'Quantity': 'SitePower_kWh'})

        # =====================================================================
        # STEP 4: MERGE ALL FUEL TYPES
        # =====================================================================

        # Start with all unique Date/Costcentre combinations
        all_dates_cc = pd.concat([
            diesel_electricity[['Date', 'Costcentre']],
            diesel_transport[['Date', 'Costcentre']],
            diesel_stationary[['Date', 'Costcentre']],
            diesel_explosives[['Date', 'Costcentre']],
            lpg_agg[['Date', 'Costcentre']],
            oils_agg[['Date', 'Costcentre']],
            greases_agg[['Date', 'Costcentre']],
            gases_agg[['Date', 'Costcentre']],
            grid_agg[['Date', 'Costcentre']],
            site_agg[['Date', 'Costcentre']]
        ]).drop_duplicates()

        # Merge all fuel types
        df = all_dates_cc
        df = df.merge(diesel_electricity, on=['Date', 'Costcentre'], how='left')
        df = df.merge(diesel_transport, on=['Date', 'Costcentre'], how='left')
        df = df.merge(diesel_stationary, on=['Date', 'Costcentre'], how='left')
        df = df.merge(diesel_explosives, on=['Date', 'Costcentre'], how='left')
        df = df.merge(lpg_agg, on=['Date', 'Costcentre'], how='left')
        df = df.merge(oils_agg, on=['Date', 'Costcentre'], how='left')
        df = df.merge(greases_agg, on=['Date', 'Costcentre'], how='left')
        df = df.merge(gases_agg, on=['Date', 'Costcentre'], how='left')
        df = df.merge(grid_agg, on=['Date', 'Costcentre'], how='left')
        df = df.merge(site_agg, on=['Date', 'Costcentre'], how='left')

        # Fill NaNs with 0
        fuel_columns = ['Diesel_Electricity_L', 'Diesel_Transport_L', 'Diesel_Stationary_L',
                       'Diesel_Explosives_L', 'LPG_kg', 'Petroleum_Oils_L', 'Petroleum_Greases_kg',
                       'Acetylene_m3', 'GridPower_kWh', 'SitePower_kWh']
        df[fuel_columns] = df[fuel_columns].fillna(0)

        log_success(f"Merged all fuel types: {len(df)} Date/Costcentre combinations")

        # =====================================================================
        # STEP 5: ADD DATE/FY COLUMNS
        # =====================================================================

        df['Year'] = df['Date'].dt.year
        df['Month'] = df['Date'].dt.month
        df['FY'] = df.apply(lambda r: calculate_fy(r['Year'], r['Month'], fy_start_month), axis=1)

        # Get purpose mapping for cost centres
        df['Purpose'] = df['Costcentre'].map(NGER_PURPOSE_MAP)

        # Check for unmapped cost centres
        unmapped = df[df['Purpose'].isna()]['Costcentre'].unique()
        if len(unmapped) > 0:
            log_error('UNMAPPED_COSTCENTRES', f'Found {len(unmapped)} unmapped cost centres',
                      f'Cost centres: {list(unmapped)}')

        # =====================================================================
        # STEP 6: APPLY EMISSION FACTORS AND CALCULATE EMISSIONS
        # =====================================================================

        def apply_year_factors(row):
            """Get emission factors for the row's year"""
            factors = nga_by_year.get_factors_for_year(row['FY'], 'QLD')
            if factors is None:
                log_error('MISSING_NGA_FACTORS', f'No NGA factors for FY{row["FY"]}')
                # Use defaults
                return pd.Series({
                    'EF_Diesel_Electricity_S1': 70.8,
                    'EF_Diesel_Transport_S1': 69.7,
                    'EF_Diesel_Stationary_S1': 69.9,
                    'EF_Diesel_Explosives_S1': 69.9,
                    'EF_Diesel_S3': 17.3,
                    'EF_LPG_S1': 60.6,
                    'EF_LPG_S3': 20.2,
                    'EF_Oil_S3': 18.0,
                    'EF_Grease_S3': 18.0,
                    'EF_Acetylene_S1': 51.53,
                    'EF_Grid_S2': 0.73,
                    'EF_Grid_S3': 0.09
                })

            # Get diesel factors by purpose
            purpose_factors = factors['diesel_by_purpose']

            return pd.Series({
                'EF_Diesel_Electricity_S1': purpose_factors.get('Electricity generation', {}).get('scope1', 70.8),
                'EF_Diesel_Transport_S1': purpose_factors.get('Transport', {}).get('scope1', 69.7),
                'EF_Diesel_Stationary_S1': purpose_factors.get('Stationary', {}).get('scope1', 69.9),
                'EF_Diesel_Explosives_S1': purpose_factors.get('Explosives', {}).get('scope1', 69.9),
                'EF_Diesel_S3': 17.3,  # Scope 3 same for all diesel
                'EF_LPG_S1': 60.6,      # kg CO2-e/GJ
                'EF_LPG_S3': 20.2,
                'EF_Oil_S3': 18.0,      # Only Scope 3 - not combusted
                'EF_Grease_S3': 18.0,   # Only Scope 3 - not combusted
                'EF_Acetylene_S1': 51.53,
                'EF_Grid_S2': factors['scope2'],
                'EF_Grid_S3': factors['scope3']
            })

        # Apply emission factors
        try:
            emission_factors = df.apply(apply_year_factors, axis=1)
            df = pd.concat([df, emission_factors], axis=1)
            log_success("Applied year-specific emission factors")
        except Exception as e:
            log_error('EMISSION_FACTOR_ERROR', f'Error applying emission factors: {str(e)}')
            raise

        # Calculate emissions for each fuel type
        # Energy content factors (GJ/unit)
        DIESEL_GJ_PER_KL = 38.6
        LPG_GJ_PER_KL = 25.7
        LPG_DENSITY = 0.51  # kg/L
        OIL_GJ_PER_KL = 38.8
        GREASE_GJ_PER_KL = 38.8
        GREASE_DENSITY = 0.9  # kg/L (approx)
        ACETYLENE_GJ_PER_M3 = 0.0393

        # Diesel - each purpose separately
        df['Diesel_Electricity_kL'] = df['Diesel_Electricity_L'] / 1000
        df['Diesel_Electricity_GJ'] = df['Diesel_Electricity_kL'] * DIESEL_GJ_PER_KL
        df['Diesel_Electricity_tCO2e_S1'] = df['Diesel_Electricity_GJ'] * df['EF_Diesel_Electricity_S1'] / 1000

        df['Diesel_Transport_kL'] = df['Diesel_Transport_L'] / 1000
        df['Diesel_Transport_GJ'] = df['Diesel_Transport_kL'] * DIESEL_GJ_PER_KL
        df['Diesel_Transport_tCO2e_S1'] = df['Diesel_Transport_GJ'] * df['EF_Diesel_Transport_S1'] / 1000

        df['Diesel_Stationary_kL'] = df['Diesel_Stationary_L'] / 1000
        df['Diesel_Stationary_GJ'] = df['Diesel_Stationary_kL'] * DIESEL_GJ_PER_KL
        df['Diesel_Stationary_tCO2e_S1'] = df['Diesel_Stationary_GJ'] * df['EF_Diesel_Stationary_S1'] / 1000

        df['Diesel_Explosives_kL'] = df['Diesel_Explosives_L'] / 1000
        df['Diesel_Explosives_GJ'] = df['Diesel_Explosives_kL'] * DIESEL_GJ_PER_KL
        df['Diesel_Explosives_tCO2e_S1'] = df['Diesel_Explosives_GJ'] * df['EF_Diesel_Explosives_S1'] / 1000

        # Diesel Scope 3 (combined - same factor for all)
        df['Diesel_Total_kL'] = (df['Diesel_Electricity_kL'] + df['Diesel_Transport_kL'] +
                                 df['Diesel_Stationary_kL'] + df['Diesel_Explosives_kL'])
        df['Diesel_Total_GJ'] = df['Diesel_Total_kL'] * DIESEL_GJ_PER_KL
        df['Diesel_Total_tCO2e_S3'] = df['Diesel_Total_GJ'] * df['EF_Diesel_S3'] / 1000

        # LPG
        df['LPG_kL'] = df['LPG_kg'] / (LPG_DENSITY * 1000)  # Convert kg to kL
        df['LPG_GJ'] = df['LPG_kL'] * LPG_GJ_PER_KL
        df['LPG_tCO2e_S1'] = df['LPG_GJ'] * df['EF_LPG_S1'] / 1000
        df['LPG_tCO2e_S3'] = df['LPG_GJ'] * df['EF_LPG_S3'] / 1000

        # Petroleum oils (Scope 3 only - not combusted)
        df['Petroleum_Oils_kL'] = df['Petroleum_Oils_L'] / 1000
        df['Petroleum_Oils_GJ'] = df['Petroleum_Oils_kL'] * OIL_GJ_PER_KL
        df['Petroleum_Oils_tCO2e_S3'] = df['Petroleum_Oils_GJ'] * df['EF_Oil_S3'] / 1000

        # Petroleum greases (Scope 3 only - not combusted)
        df['Petroleum_Greases_kL'] = df['Petroleum_Greases_kg'] / (GREASE_DENSITY * 1000)
        df['Petroleum_Greases_GJ'] = df['Petroleum_Greases_kL'] * GREASE_GJ_PER_KL
        df['Petroleum_Greases_tCO2e_S3'] = df['Petroleum_Greases_GJ'] * df['EF_Grease_S3'] / 1000

        # Acetylene
        df['Acetylene_GJ'] = df['Acetylene_m3'] * ACETYLENE_GJ_PER_M3
        df['Acetylene_tCO2e_S1'] = df['Acetylene_GJ'] * df['EF_Acetylene_S1'] / 1000

        # Grid electricity
        df['GridPower_MWh'] = df['GridPower_kWh'] / 1000
        df['GridPower_tCO2e_S2'] = df['GridPower_MWh'] * df['EF_Grid_S2']
        df['GridPower_tCO2e_S3'] = df['GridPower_MWh'] * df['EF_Grid_S3']

        # Site electricity (generation emissions already in diesel)
        df['SitePower_MWh'] = df['SitePower_kWh'] / 1000

        # Calculate totals by scope
        df['Total_Scope1_tCO2e'] = (
            df['Diesel_Electricity_tCO2e_S1'] +
            df['Diesel_Transport_tCO2e_S1'] +
            df['Diesel_Stationary_tCO2e_S1'] +
            df['Diesel_Explosives_tCO2e_S1'] +
            df['LPG_tCO2e_S1'] +
            df['Acetylene_tCO2e_S1']
        )

        df['Total_Scope2_tCO2e'] = df['GridPower_tCO2e_S2']

        df['Total_Scope3_tCO2e'] = (
            df['Diesel_Total_tCO2e_S3'] +
            df['LPG_tCO2e_S3'] +
            df['Petroleum_Oils_tCO2e_S3'] +
            df['Petroleum_Greases_tCO2e_S3'] +
            df['GridPower_tCO2e_S3']
        )

        log_success("Calculated emissions for all fuel types")

        # Log summary
        log_success(f"Energy.xlsx processed: FY{df['FY'].min()}-{df['FY'].max()}, {df['FY'].nunique()} years")
        log_success(f"Total Scope 1: {df['Total_Scope1_tCO2e'].sum():.0f} tCOÃ¢â€šâ€š-e")
        log_success(f"Total Scope 2: {df['Total_Scope2_tCO2e'].sum():.0f} tCOÃ¢â€šâ€š-e")
        log_success(f"Total Scope 3: {df['Total_Scope3_tCO2e'].sum():.0f} tCOÃ¢â€šâ€š-e")

        return df

    except Exception as e:
        log_error('DATA_PROCESSING_ERROR', f'Error processing Energy.xlsx: {str(e)}')
        raise


def load_rom_data(filepath, fy_start_month=1):
    """Load and process ROM production data from PhysicalsActual.xlsx

    Args:
        filepath: Path to PhysicalsActual.xlsx
        fy_start_month: Fiscal year start month (1=Jan, 7=Jul, etc.)

    Returns:
        DataFrame with Date, Year, Month, FY, ROM (tonnes)
    """
    try:
        xl_file = pd.ExcelFile(filepath)
        log_success(f"Loaded PhysicalsActual.xlsx with sheets: {xl_file.sheet_names}")
    except FileNotFoundError:
        log_error('FILE_NOT_FOUND', f'PhysicalsActual.xlsx not found at {filepath}')
        raise
    except Exception as e:
        log_error('FILE_READ_ERROR', f'Error reading PhysicalsActual.xlsx: {str(e)}')
        raise

    try:
        all_data = []

        for sheet in xl_file.sheet_names:
            df_sheet = pd.read_excel(filepath, sheet_name=sheet)

            mined_data = df_sheet[df_sheet['Metric'] == 'Ore Mined t - Total'][['Date', 'Value']].copy()

            if not mined_data.empty:
                all_data.append(mined_data)
                log_success(f"Extracted {len(mined_data)} ROM records from sheet '{sheet}'")

        if not all_data:
            log_error('NO_ROM_DATA', 'No "Ore Mined t - Total" data found in any sheet')
            raise ValueError('No ROM data found in PhysicalsActual.xlsx')

        df = pd.concat(all_data, ignore_index=True)
        df = df.rename(columns={'Value': 'ROM'})

        log_success(f"Combined ROM data: {len(df)} total records")

    except Exception as e:
        log_error('ROM_EXTRACTION_ERROR', f'Error extracting ROM data: {str(e)}')
        raise

    try:
        # Convert Date to datetime BEFORE sorting to avoid mixed type comparison
        # Use errors='raise' to fail fast on invalid dates rather than silently converting to NaT
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='raise')
        
        # Check for any null dates after conversion
        null_dates = df['Date'].isna().sum()
        if null_dates > 0:
            invalid_rows = df[df['Date'].isna()]
            log_error('INVALID_DATES', f'Found {null_dates} rows with invalid dates',
                      f'Sample invalid dates: {invalid_rows["Date"].head().tolist()}')
            raise ValueError(f'Found {null_dates} rows with invalid/unparseable dates in ROM data')
        
        # Now safe to sort - all dates are guaranteed to be Timestamps
        df = df.sort_values('Date').reset_index(drop=True)
        
        df['Year'] = df['Date'].dt.year
        df['Month'] = df['Date'].dt.month
        log_success("Parsed dates in ROM data")
    except Exception as e:
        log_error('DATE_PARSE_ERROR', f'Error parsing dates in ROM data: {str(e)}',
                      f'Sample dates: {df["Date"].head().tolist()}')
        raise

    df['FY'] = df.apply(lambda r: calculate_fy(r['Year'], r['Month'], fy_start_month), axis=1)

    try:
        df['ROM'] = pd.to_numeric(df['ROM'], errors='coerce')

        missing = df['ROM'].isna().sum()
        if missing > 0:
            log_error('MISSING_ROM_VALUES', f'Found {missing} missing/invalid ROM values',
                      f'Total rows: {len(df)}')
        else:
            log_success("All ROM values valid")
    except Exception as e:
        log_error('ROM_PARSE_ERROR', f'Error parsing ROM values: {str(e)}')
        raise

    log_success(f"ROM data processed: FY{df['FY'].min()}-{df['FY'].max()}, {df['FY'].nunique()} years")

    return df[['Date', 'Year', 'Month', 'FY', 'ROM']]


def load_all_data(paths_dict, fy_start_month=1):
    """Load all data files for the application

    Args:
        paths_dict: Dictionary with keys 'nga', 'rom', 'energy' pointing to file paths
        fy_start_month: Fiscal year start month (1=Jan, 7=Jul, etc.)

    Returns:
        tuple: (rom_df, energy_df, nga_factors)
    """
    start_loading_session()

    error_count = 0

    # Load ALL years of NGA factors
    nga_folder = Path(paths_dict['nga']).parent
    try:
        nga_by_year = NGAFactorsByYear(str(nga_folder))
        years_loaded = sorted(nga_by_year.factors_by_year.keys())
        log_success(f"Loaded NGA factors for years: {years_loaded}")
        if len(years_loaded) == 0:
            log_error('NO_NGA_FACTORS', 'No NGA factor files could be loaded',
                      f'Folder: {nga_folder}')
            error_count += 1
    except Exception as e:
        log_error('NGA_LOAD_ERROR', f'Error loading NGA factors: {str(e)}')
        error_count += 1
        raise

    # Load ROM data
    try:
        rom_df = load_rom_data(paths_dict['rom'], fy_start_month)
    except Exception as e:
        log_error('ROM_LOAD_FAILED', f'Failed to load ROM data: {str(e)}')
        error_count += 1
        raise

    # Load Energy data with detailed fuel breakdown
    try:
        energy_df = load_energy_data(paths_dict['energy'], nga_by_year, fy_start_month)
    except Exception as e:
        log_error('ENERGY_LOAD_FAILED', f'Failed to load Energy data: {str(e)}')
        error_count += 1
        raise

    # For backward compatibility, return factors from the specified year
    from nga_loader import load_nga_factors
    try:
        nga_factors = load_nga_factors(paths_dict['nga'])
        log_success("Loaded display NGA factors")
    except Exception as e:
        log_error('NGA_FACTORS_LOAD_FAILED', f'Failed to load NGA factors: {str(e)}')
        error_count += 1
        raise

    # Log completion
    if error_count == 0:
        log_to_file("DATA LOADING COMPLETE - NO ERRORS")
    else:
        log_to_file(f"DATA LOADING COMPLETE - {error_count} ERROR(S) OCCURRED")

    return rom_df, energy_df, nga_factors