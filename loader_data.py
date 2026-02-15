"""
loader_data.py
Unified data loader - ONE DataFrame output
Last updated: 2026-02-11 09:00 AEST

PRINCIPLES:
- Load consolidated_emissions_data.csv ONCE
- Process ALL datasets (dynamic - no hardcoded names)
- Aggregate to monthly level by Description/Department/CostCentre
- Calculate emissions using calc_emissions.py
- Return ONE enriched DataFrame
- STRICT VALIDATION: bad dates, non-numeric quantities raise errors
  The source file must be correct - loader does not silently fix data

Output columns:
    Year, Month, FY, DataSet, Description, Department, CostCentre, State,
    UOM, Quantity, NGAFuel, Scope1_tCO2e, Scope2_tCO2e, Scope3_tCO2e, Source
"""

import pandas as pd
from pathlib import Path
from calc_calendar import date_to_fy
from config import NGER_FY_START_MONTH, DIESEL_TRANSPORT_COSTCENTRES, DIESEL_TRANSPORT_NGAFUEL
from loader_nga import NGAFactorsByYear
from calc_emissions import (
    build_year_factor_map,
    apply_emissions_to_df
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
        print(f"Loaded CSV: {len(df):,} records")
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        raise

    # 2. PARSE DATES AND ADD TIME COLUMNS
    # Handle DD/MM/YY format with dayfirst=True
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')

    # Validate dates - no silent NaT allowed
    failed_dates = df['Date'].isna().sum()
    if failed_dates > 0:
        # Find the original bad rows before Date was parsed
        raw_df = pd.read_csv(filepath)
        bad_mask = pd.to_datetime(raw_df['Date'], dayfirst=True, errors='coerce').isna()
        bad_rows = raw_df[bad_mask][['Date', 'Description', 'Quantity']].head(5).to_string(index=False)
        raise ValueError(
            f" {failed_dates} dates failed to parse in source CSV. "
            f"Fix the source file.\n\nFirst bad rows:\n{bad_rows}"
        )

    # 2b. FIX DAY-AS-MONTH ENCODING
    # Consolidated CSV stores fuel consumption with day-as-month encoding:
    # Annual data split as 12 rows in January where day N = month N.
    # e.g. 2024-01-05 means May 2024 data.  Electricity has proper monthly dates.
    # Detection: group by (NGAFuel, year).  If ALL dates are in January with
    # days spanning 1-12, remap day -> month.
    import logging
    _log = logging.getLogger(__name__)

    day_as_month_mask = pd.Series(False, index=df.index)
    for (nga_fuel, year), grp in df.groupby([df['NGAFuel'], df['Date'].dt.year]):
        if pd.isna(nga_fuel) or nga_fuel == '':
            continue
        months_used = grp['Date'].dt.month.unique()
        days_used = sorted(grp['Date'].dt.day.unique())
        # Pattern: all in January, days are subset of 1-12
        if list(months_used) == [1] and len(days_used) >= 2 and max(days_used) <= 12:
            day_as_month_mask.loc[grp.index] = True

    n_remapped = day_as_month_mask.sum()
    if n_remapped > 0:
        # Remap: date(Y, 1, D) -> date(Y, D, 1)
        remap_idx = df.index[day_as_month_mask]
        df.loc[remap_idx, 'Date'] = df.loc[remap_idx, 'Date'].apply(
            lambda d: d.replace(month=d.day, day=1)
        )
        print(f"Day-as-month fix: {n_remapped:,} rows remapped (fuel data Jan day N -> month N)")
    else:
        print(f"Day-as-month fix: no remapping needed (dates already monthly)")

    df['Year'] = df['Date'].dt.year
    df['Month'] = df['Date'].dt.month
    # Calculate FY from Date (July start = FY, not CY)
    df['FY'] = df['Date'].apply(date_to_fy)

    print(f"Date range: {df['Date'].min():%Y-%m} to {df['Date'].max():%Y-%m}")

    # 2b. VALIDATE QUANTITY COLUMN
    # Quantity must be numeric in the source file - do not silently coerce
    if not pd.api.types.is_numeric_dtype(df['Quantity']):
        # Try conversion but treat failures as hard errors
        try:
            df['Quantity'] = pd.to_numeric(df['Quantity'])
        except (ValueError, TypeError) as e:
            bad_rows = df[pd.to_numeric(df['Quantity'], errors='coerce').isna()]
            sample = bad_rows[['Date', 'Description', 'Quantity']].head(5).to_string(index=False)
            raise ValueError(
                f" Quantity column contains non-numeric values. "
                f"Fix the source CSV.\n\nFirst bad rows:\n{sample}"
            ) from e

    # 3. VALIDATE DATASETS
    datasets = sorted(df['DataSet'].unique())
    print(f"Datasets found: {datasets}")

    # 4. AGGREGATE TO MONTHLY LEVEL
    # Group by: Year, Month, FY, DataSet, Description, Department, CostCentre, UOM
    print(f"\nAggregating to monthly level...")

    agg_df = df.groupby([
        'Year', 'Month', 'FY', 'DataSet',
        'Description', 'Department', 'CostCentre', 'State', 'UOM', 'NGAFuel'
    ], dropna=False).agg({
        'Quantity': 'sum',
        'Source': 'first'  # Keep first source as metadata
    }).reset_index()

    print(f"Aggregated: {len(df):,} â†’ {len(agg_df):,} records")

    # 4b. RECLASSIFY DIESEL TRANSPORT (NGER requirement)
    # Light vehicles use transport emission factor per NGER Measurement Determination
    # All other diesel uses stationary factor (mining equipment operates on-site)
    transport_mask = (
        (agg_df['NGAFuel'].astype(str).str.startswith('Diesel oil')) &
        (agg_df['CostCentre'].isin(DIESEL_TRANSPORT_COSTCENTRES))
    )
    n_transport = transport_mask.sum()
    if n_transport > 0:
        agg_df.loc[transport_mask, 'NGAFuel'] = DIESEL_TRANSPORT_NGAFUEL
        print(f"Diesel transport: {n_transport} rows reclassified (CCs: {DIESEL_TRANSPORT_COSTCENTRES})")

    # 5. LOAD NGA FACTORS
    if nga_folder is None:
        # Auto-detect NGA folder
        nga_folder = Path(filepath).parent

    try:
        nga_by_year = NGAFactorsByYear(str(nga_folder))
        years_loaded = nga_by_year.available_years
        print(f"NGA factors loaded: {years_loaded}")
    except Exception as e:
        print(f"Error loading NGA factors: {e}")
        raise

    # 6. CALCULATE EMISSIONS
    # Uses shared factor builder and emission applicator from calc_emissions.py
    # This ensures loader_data (actuals) and projections (budget/forecast) use identical logic.
    print(f"\nCalculating emissions...")

    # Build year-specific NGA factor lookup
    unique_years = agg_df['FY'].unique()
    year_factor_map = build_year_factor_map(nga_by_year, unique_years, state='QLD')

    # Apply emissions to all rows based on Description and FY
    agg_df = apply_emissions_to_df(agg_df, year_factor_map, fy_col='FY')

    print(f"Emissions calculated")
    print(f"Total Scope 1: {agg_df['Scope1_tCO2e'].sum():,.0f} tCOâ‚‚-e")
    print(f"Total Scope 2: {agg_df['Scope2_tCO2e'].sum():,.0f} tCOâ‚‚-e")
    print(f"Total Scope 3: {agg_df['Scope3_tCO2e'].sum():,.0f} tCOâ‚‚-e")

        # 7. OPTIMIZE MEMORY (categorical dtypes)
    print(f"\nOptimizing memory...")

    agg_df['DataSet'] = agg_df['DataSet'].astype('category')
    agg_df['Description'] = agg_df['Description'].astype('category')
    agg_df['Department'] = agg_df['Department'].astype('category')
    agg_df['CostCentre'] = agg_df['CostCentre'].astype('category')
    agg_df['UOM'] = agg_df['UOM'].astype('category')
    agg_df['State'] = agg_df['State'].astype('category')
    agg_df['NGAFuel'] = agg_df['NGAFuel'].astype('category')
    agg_df['Year'] = agg_df['Year'].astype('int16')
    agg_df['Month'] = agg_df['Month'].astype('int8')
    agg_df['FY'] = agg_df['FY'].astype('int16')
    agg_df['Quantity'] = agg_df['Quantity'].astype('float32')
    agg_df['Scope1_tCO2e'] = agg_df['Scope1_tCO2e'].astype('float32')
    agg_df['Scope2_tCO2e'] = agg_df['Scope2_tCO2e'].astype('float32')
    agg_df['Scope3_tCO2e'] = agg_df['Scope3_tCO2e'].astype('float32')
    agg_df['Energy_GJ'] = agg_df['Energy_GJ'].astype('float32')

    memory_mb = agg_df.memory_usage(deep=True).sum() / 1024**2
    print(f"Memory optimized: {memory_mb:.2f} MB")

    # 8. RECREATE DATE COLUMN (for convenience, set to 1st of each month)
    agg_df['Date'] = pd.to_datetime(
        agg_df['Year'].astype(str) + '-' + agg_df['Month'].astype(str).str.zfill(2) + '-01'
    )

    # 9. SORT AND FINALIZE
    agg_df = agg_df.sort_values(['DataSet', 'Year', 'Month', 'Description']).reset_index(drop=True)

    print(f"\n" + "="*80)
    print(f"DATA LOADING COMPLETE")
    print(f"Records: {len(agg_df):,}")
    print(f"Datasets: {list(agg_df['DataSet'].cat.categories)}")
    print(f"Date range: FY{agg_df['FY'].min()}-{agg_df['FY'].max()}")
    print("="*80 + "\n")

    return agg_df


# Backward compatibility - for code that expects old signature
def load_rom_data(*args, **kwargs):
    """Deprecated - use load_all_data() and filter CostCentre == 'ROM' with Description containing 'Ore'"""
    raise NotImplementedError("load_rom_data() deprecated - use load_all_data()")


def load_energy_data(*args, **kwargs):
    """Deprecated - use load_all_data()"""
    raise NotImplementedError("load_energy_data() deprecated - use load_all_data()")