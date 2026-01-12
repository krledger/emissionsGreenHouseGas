"""
data_loader.py
Data loading functions for Ravenswood Gold emissions model
Last updated: 2026-01-08 09:30 AEST

Loads Energy.csv (consolidated fuel and electricity) and ROM.csv
Uses year-specific NGA emission factors (2021-2025)
Includes persistent file logging for debugging
"""

import pandas as pd
from pathlib import Path
from config import calculate_fy
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
    print(f"âŒ {log_msg}", file=sys.stderr)

def log_success(message):
    """Log successful operation"""
    log_to_file(f"SUCCESS: {message}")
    print(f"âœ“ {message}")

def start_loading_session():
    """Start a new loading session in log"""
    log_to_file("=" * 80)
    log_to_file("NEW DATA LOADING SESSION")
    log_to_file("=" * 80)


def load_energy_data(filepath, nga_by_year, fy_start_month=1):
    """Load and process Energy.csv with fuel and electricity data

    Uses year-specific emission factors from NGAFactorsByYear

    Args:
        filepath: Path to Energy.csv
        nga_by_year: NGAFactorsByYear instance with factors for all years
        fy_start_month: Fiscal year start month (1=Jan, 7=Jul, etc.)

    Returns:
        DataFrame with Date, Year, Month, FY, Costcentre, Fuel (L),
        GridPower (kWh), SitePower (kWh), and calculated emissions
    """
    try:
        # Load file
        df = pd.read_csv(filepath, encoding='utf-8-sig')
        log_success(f"Loaded Energy.csv: {len(df)} rows")
    except FileNotFoundError:
        log_error('FILE_NOT_FOUND', f'Energy.csv not found at {filepath}')
        raise
    except Exception as e:
        log_error('FILE_READ_ERROR', f'Error reading Energy.csv: {str(e)}')
        raise

    try:
        # Parse dates - Energy.csv uses DD/MM/YYYY format
        df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', dayfirst=True)
        df['Year'] = df['Date'].dt.year
        df['Month'] = df['Date'].dt.month
        log_success("Parsed dates in Energy.csv")
    except Exception as e:
        log_error('DATE_PARSE_ERROR', f'Error parsing dates in Energy.csv: {str(e)}',
                  f'Sample dates: {df["Date"].head().tolist()}')
        raise

    # Calculate FY (uses configurable fiscal year)
    df['FY'] = df.apply(lambda r: calculate_fy(r['Year'], r['Month'], fy_start_month), axis=1)

    # Get emission factors by purpose
    from config import NGER_PURPOSE_MAP

    df['Purpose'] = df['Costcentre'].map(NGER_PURPOSE_MAP)

    # Check for unmapped cost centres
    unmapped = df[df['Purpose'].isna()]['Costcentre'].unique()
    if len(unmapped) > 0:
        log_error('UNMAPPED_COSTCENTRES', f'Found {len(unmapped)} unmapped cost centres',
                  f'Cost centres: {list(unmapped)}')

    # Fuel emissions (Scope 1 and Scope 3) - USE YEAR-SPECIFIC FACTORS
    df['Fuel_kL'] = df['Fuel'] / 1000

    # Apply year-specific emission factors to each row
    def apply_year_factors(row):
        """Get factors for the row's year"""
        factors = nga_by_year.get_factors_for_year(row['FY'], 'QLD')
        if factors is None:
            log_error('MISSING_NGA_FACTORS', f'No NGA factors for FY{row["FY"]}')
            # Fallback to defaults
            return pd.Series({
                'EF_S1': 2.708,
                'EF_S3': 0.669,
                'EF_Grid_S2': 0.67,
                'EF_Grid_S3': 0.09
            })

        # Get purpose-specific diesel factor
        purpose_factors = factors['diesel_by_purpose']
        ef_s1 = purpose_factors.get(row['Purpose'], {}).get('scope1', 2.708)
        ef_s3 = purpose_factors.get(row['Purpose'], {}).get('scope3', 0.669)

        return pd.Series({
            'EF_S1': ef_s1,
            'EF_S3': ef_s3,
            'EF_Grid_S2': factors['scope2'],
            'EF_Grid_S3': factors['scope3']
        })

    try:
        # Apply factors (this adds columns: EF_S1, EF_S3, EF_Grid_S2, EF_Grid_S3)
        emission_factors = df.apply(apply_year_factors, axis=1)
        df = pd.concat([df, emission_factors], axis=1)
        log_success("Applied year-specific emission factors")
    except Exception as e:
        log_error('EMISSION_FACTOR_ERROR', f'Error applying emission factors: {str(e)}')
        raise

    # Calculate emissions using year-specific factors
    df['Fuel_tCO2e_S1'] = df['Fuel_kL'] * df['EF_S1']
    df['Fuel_tCO2e_S3'] = df['Fuel_kL'] * df['EF_S3']

    # Grid electricity emissions (Scope 2 and Scope 3)
    df['GridPower_MWh'] = df['GridPower'] / 1000
    df['Grid_tCO2e_S2'] = df['GridPower_MWh'] * df['EF_Grid_S2']
    df['Grid_tCO2e_S3'] = df['GridPower_MWh'] * df['EF_Grid_S3']

    # Site Power is self-generated (fuel combustion already counted in Fuel column)
    # No additional emissions - just track the generation
    df['SitePower_MWh'] = df['SitePower'] / 1000

    # Log data summary
    log_success(f"Energy.csv processed: FY{df['FY'].min()}-{df['FY'].max()}, {df['FY'].nunique()} years")

    return df


def load_rom_data(filepath, fy_start_month=1):
    """Load and process ROM production data

    Args:
        filepath: Path to ROM.csv
        fy_start_month: Fiscal year start month (1=Jan, 7=Jul, etc.)

    Returns:
        DataFrame with Date, Year, Month, FY, ROM (tonnes)
    """
    try:
        df = pd.read_csv(filepath, encoding='utf-8-sig')
        log_success(f"Loaded ROM.csv: {len(df)} rows")
    except FileNotFoundError:
        log_error('FILE_NOT_FOUND', f'ROM.csv not found at {filepath}')
        raise
    except Exception as e:
        log_error('FILE_READ_ERROR', f'Error reading ROM.csv: {str(e)}')
        raise

    df.columns = df.columns.str.strip()

    try:
        # Parse dates - ROM.csv uses D/M/YYYY format (Australian - day first)
        # e.g., 1/1/2021 = 1st January, 1/2/2021 = 1st February
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
        df['Year'] = df['Date'].dt.year
        df['Month'] = df['Date'].dt.month
        log_success("Parsed dates in ROM.csv")
    except Exception as e:
        log_error('DATE_PARSE_ERROR', f'Error parsing dates in ROM.csv: {str(e)}',
                  f'Sample dates: {df["Date"].head().tolist()}')
        raise

    # Calculate FY (uses configurable fiscal year)
    df['FY'] = df.apply(lambda r: calculate_fy(r['Year'], r['Month'], fy_start_month), axis=1)

    # Clean ROM column - remove commas and whitespace before converting
    try:
        rom_col = [c for c in df.columns if 'ROM' in c.upper()][0]
        df['ROM'] = df[rom_col].str.replace(',', '').str.strip()
        df['ROM'] = pd.to_numeric(df['ROM'], errors='coerce')

        # Check for missing/invalid values
        missing = df['ROM'].isna().sum()
        if missing > 0:
            log_error('MISSING_ROM_VALUES', f'Found {missing} missing/invalid ROM values',
                      f'Total rows: {len(df)}')
        else:
            log_success("All ROM values valid")
    except Exception as e:
        log_error('ROM_PARSE_ERROR', f'Error parsing ROM values: {str(e)}')
        raise

    # Log data summary
    log_success(f"ROM.csv processed: FY{df['FY'].min()}-{df['FY'].max()}, {df['FY'].nunique()} years")

    return df[['Date', 'Year', 'Month', 'FY', 'ROM']]


def load_all_data(paths_dict, fy_start_month=1):
    """Load all data files for the application

    Args:
        paths_dict: Dictionary with keys 'nga', 'rom', 'energy' pointing to file paths
        fy_start_month: Fiscal year start month (1=Jan, 7=Jul, etc.)

    Returns:
        tuple: (rom_df, energy_df, nga_factors)

        nga_factors is a dict with year-specific factors for display purposes:
        - Uses factors from the 'nga' file specified in paths_dict
        - energy_df already has year-specific factors applied per row
    """
    # Start new loading session
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

    # Load Energy data with year-specific factors
    try:
        energy_df = load_energy_data(paths_dict['energy'], nga_by_year, fy_start_month)
    except Exception as e:
        log_error('ENERGY_LOAD_FAILED', f'Failed to load Energy data: {str(e)}')
        error_count += 1
        raise

    # For backward compatibility, return factors from the specified year
    # (used for projections and display)
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