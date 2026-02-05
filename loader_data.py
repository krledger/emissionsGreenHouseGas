"""
loader_data.py
Simplified unified data loader - ONE DataFrame output
Last updated: 2026-02-01 23:55 AEST

SIMPLE PRINCIPLES:
- Load consolidated_emissions_data.csv ONCE
- Process ALL datasets (dynamic - no hardcoded names)
- Aggregate to monthly level by Description/Department/CostCentre
- Calculate emissions using emissions_calc.py
- Return ONE enriched DataFrame

Output columns:
    Year, Month, FY, DataSet, Description, Department, CostCentre, UOM,
    Quantity, Scope1_tCO2e, Scope2_tCO2e, Scope3_tCO2e, Source
"""

import pandas as pd
from pathlib import Path
from calc_calendar import date_to_fy
from config import NGER_FY_START_MONTH
from loader_nga import NGAFactorsByYear
from calc_emissions import (
    convert_litres_to_kilolitres,
    convert_kwh_to_mwh,
    calculate_scope1_diesel,
    calculate_scope1_lpg,
    calculate_scope1_oils,
    calculate_scope1_greases,
    calculate_scope1_acetylene,
    calculate_scope2_grid_electricity,
    calculate_scope3_diesel,
    calculate_scope3_grid_electricity
)


def load_all_data(filepath='consolidated_emissions_data.csv',
                  nga_folder=None,
                  fy_start_month=NGER_FY_START_MONTH):
    """Load and process consolidated emissions data

    Args:
        filepath: Path to consolidated_emissions_data.csv
        nga_folder: Folder containing NGA factor files (auto-detected if None)
        fy_start_month: Fiscal year start month (default: 7 for July)

    Returns:
        Single DataFrame with all datasets, aggregated monthly, emissions calculated
    """

    print("="*80)
    print("LOADING EMISSIONS DATA")
    print("="*80)

    # 1. LOAD CSV
    try:
        df = pd.read_csv(filepath)
        print(f"âœ… Loaded CSV: {len(df):,} records")
    except FileNotFoundError:
        print(f"âŒ File not found: {filepath}")
        raise

    # 2. PARSE DATES AND ADD TIME COLUMNS
    # Handle DD/MM/YY format with dayfirst=True
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')

    # Check for failed parsing
    failed_dates = df['Date'].isna().sum()
    if failed_dates > 0:
        print(f"⚠️  Warning: {failed_dates} dates failed to parse")

    df['Year'] = df['Date'].dt.year
    df['Month'] = df['Date'].dt.month
    # Calculate FY from Date (July start = FY, not CY)
    df['FY'] = df['Date'].apply(date_to_fy)

    print(f"✅ Date range: {df['Date'].min():%Y-%m} to {df['Date'].max():%Y-%m}")

    # 3. DISCOVER DATASETS (dynamic - don't hardcode)
    datasets = sorted(df['DataSet'].unique())
    print(f"âœ… Datasets found: {datasets}")

    # 4. AGGREGATE TO MONTHLY LEVEL
    # Group by: Year, Month, FY, DataSet, Description, Department, CostCentre, UOM
    print(f"\nðŸ“Š Aggregating to monthly level...")

    agg_df = df.groupby([
        'Year', 'Month', 'FY', 'DataSet',
        'Description', 'Department', 'CostCentre', 'UOM'
    ], dropna=False).agg({
        'Quantity': 'sum',
        'Source': 'first'  # Keep first source as metadata
    }).reset_index()

    print(f"âœ… Aggregated: {len(df):,} â†’ {len(agg_df):,} records")

    # 5. LOAD NGA FACTORS
    if nga_folder is None:
        # Auto-detect NGA folder
        nga_folder = Path(filepath).parent

    try:
        nga_by_year = NGAFactorsByYear(str(nga_folder))
        years_loaded = sorted(nga_by_year.factors_by_year.keys())
        print(f"âœ… NGA factors loaded: {years_loaded}")
    except Exception as e:
        print(f"âŒ Error loading NGA factors: {e}")
        raise

    # 6. CALCULATE EMISSIONS
    print(f"\n⚙️  Calculating emissions...")

    # Initialize emission columns
    agg_df['Scope1_tCO2e'] = 0.0
    agg_df['Scope2_tCO2e'] = 0.0
    agg_df['Scope3_tCO2e'] = 0.0

    # Get NGA factors for each FY (vectorized)
    unique_years = agg_df['FY'].unique()
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

    # Calculate emissions based on Description (fuel type)
    # This is vectorized - processes all rows at once

    # Diesel - Site power generation (electricity)
    mask = agg_df['Description'] == 'Diesel oil - Site power generation'
    if mask.any():
        agg_df.loc[mask, 'factor_s1'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_elec_s1'])
        agg_df.loc[mask, 'factor_s3'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_s3'])
        agg_df.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_diesel(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s1'])
        agg_df.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_diesel(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s3'])

    # Diesel - Mobile equipment (stationary)
    mask = agg_df['Description'] == 'Diesel oil - Mobile equipment'
    if mask.any():
        agg_df.loc[mask, 'factor_s1'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_stat_s1'])
        agg_df.loc[mask, 'factor_s3'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['diesel_s3'])
        agg_df.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_diesel(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s1'])
        agg_df.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_diesel(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s3'])

    # LPG
    mask = agg_df['Description'].str.contains('Liquefied petroleum gas', case=False, na=False)
    if mask.any():
        agg_df.loc[mask, 'factor_s1'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['lpg_s1'])
        agg_df.loc[mask, 'factor_s3'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['lpg_s3'])
        agg_df.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_lpg(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s1'])
        agg_df.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_lpg(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s3'])

    # Petroleum oils (Scope 3 only)
    mask = agg_df['Description'].str.contains('Petroleum based oils', case=False, na=False)
    if mask.any():
        agg_df.loc[mask, 'factor_s3'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['oil_s3'])
        agg_df.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_oils(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s3'])

    # Petroleum greases (Scope 3 only)
    mask = agg_df['Description'].str.contains('Petroleum based greases', case=False, na=False)
    if mask.any():
        agg_df.loc[mask, 'factor_s3'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['grease_s3'])
        agg_df.loc[mask, 'Scope3_tCO2e'] = calculate_scope1_greases(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s3'])

    # Acetylene
    mask = agg_df['Description'].str.contains('gaseous fossil fuels', case=False, na=False)
    if mask.any():
        agg_df.loc[mask, 'factor_s1'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['acetylene_s1'])
        agg_df.loc[mask, 'Scope1_tCO2e'] = calculate_scope1_acetylene(agg_df.loc[mask, 'Quantity'], agg_df.loc[mask, 'factor_s1'])

    # Grid electricity
    mask = agg_df['Description'] == 'Grid electricity'
    if mask.any():
        agg_df.loc[mask, 'factor_s2'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['grid_s2'])
        agg_df.loc[mask, 'factor_s3'] = agg_df.loc[mask, 'FY'].map(lambda y: year_factor_map[y]['grid_s3'])
        # Convert kWh to MWh
        mwh = convert_kwh_to_mwh(agg_df.loc[mask, 'Quantity'])
        agg_df.loc[mask, 'Scope2_tCO2e'] = calculate_scope2_grid_electricity(mwh, agg_df.loc[mask, 'factor_s2'])
        agg_df.loc[mask, 'Scope3_tCO2e'] = calculate_scope3_grid_electricity(mwh, agg_df.loc[mask, 'factor_s3'])

    # Site electricity (no emissions - already counted in diesel)
    # Just note it exists but don't double-count

    # Drop temporary factor columns
    factor_cols = [col for col in agg_df.columns if col.startswith('factor_')]
    agg_df = agg_df.drop(columns=factor_cols)

    print(f"âœ… Emissions calculated")
    print(f"   Total Scope 1: {agg_df['Scope1_tCO2e'].sum():,.0f} tCOâ‚‚-e")
    print(f"   Total Scope 2: {agg_df['Scope2_tCO2e'].sum():,.0f} tCOâ‚‚-e")
    print(f"   Total Scope 3: {agg_df['Scope3_tCO2e'].sum():,.0f} tCOâ‚‚-e")

    # 7. OPTIMIZE MEMORY (categorical dtypes)
    print(f"\nðŸ’¾ Optimizing memory...")

    agg_df['DataSet'] = agg_df['DataSet'].astype('category')
    agg_df['Description'] = agg_df['Description'].astype('category')
    agg_df['Department'] = agg_df['Department'].astype('category')
    agg_df['CostCentre'] = agg_df['CostCentre'].astype('category')
    agg_df['UOM'] = agg_df['UOM'].astype('category')
    agg_df['Year'] = agg_df['Year'].astype('int16')
    agg_df['Month'] = agg_df['Month'].astype('int8')
    agg_df['FY'] = agg_df['FY'].astype('int16')
    agg_df['Quantity'] = agg_df['Quantity'].astype('float32')
    agg_df['Scope1_tCO2e'] = agg_df['Scope1_tCO2e'].astype('float32')
    agg_df['Scope2_tCO2e'] = agg_df['Scope2_tCO2e'].astype('float32')
    agg_df['Scope3_tCO2e'] = agg_df['Scope3_tCO2e'].astype('float32')

    memory_mb = agg_df.memory_usage(deep=True).sum() / 1024**2
    print(f"âœ… Memory optimized: {memory_mb:.2f} MB")

    # 8. RECREATE DATE COLUMN (for convenience, set to 1st of each month)
    agg_df['Date'] = pd.to_datetime(
        agg_df['Year'].astype(str) + '-' + agg_df['Month'].astype(str).str.zfill(2) + '-01'
    )

    # 9. SORT AND FINALIZE
    agg_df = agg_df.sort_values(['DataSet', 'Year', 'Month', 'Description']).reset_index(drop=True)

    print(f"\n" + "="*80)
    print(f"âœ… DATA LOADING COMPLETE")
    print(f"   Records: {len(agg_df):,}")
    print(f"   Datasets: {list(agg_df['DataSet'].cat.categories)}")
    print(f"   Date range: FY{agg_df['FY'].min()}-{agg_df['FY'].max()}")
    print("="*80 + "\n")

    return agg_df


# Backward compatibility - for code that expects old signature
def load_rom_data(*args, **kwargs):
    """Deprecated - use load_all_data() and filter Description == 'Ore Mined t'"""
    raise NotImplementedError("load_rom_data() deprecated - use load_all_data()")


def load_energy_data(*args, **kwargs):
    """Deprecated - use load_all_data()"""
    raise NotImplementedError("load_energy_data() deprecated - use load_all_data()")