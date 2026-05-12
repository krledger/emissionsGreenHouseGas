"""
loader_data.py
Unified data loader — ONE DataFrame output
Last updated: 2026-03-26

PRINCIPLES:
- Load operations_metrics_actual.csv and operations_metrics_budget.csv
- Tag each with DataSet column (Actual / Budget)
- Enrich with NGAFuel/CommonName/RowType via lookup_identifiers.py
- Construct MatchKey from SubActivity for cross-dataset merging
- Aggregate to monthly level by Description/Department/CostCentre
- Calculate emissions using calc_emissions.py
- Return ONE enriched DataFrame
- STRICT VALIDATION: bad dates, non-numeric quantities raise errors
  The source file must be correct — loader does not silently fix data

New CSV schema (2026-03 restructure):
    Activity, SubActivity, Description, Identifier columns replace
    the old embedded NGAFuel/CommonName/RowType columns.
    lookup_identifiers.py maps (Activity, SubActivity) back to the
    derived columns needed by calc_emissions and GRI export.

Identifier field:
    Budget CSV:  Budget|SubActivity|CostCentre  (structured composite key)
    Actuals CSV: Invoice/source number          (metadata only)
    The budget Identifier is keyed on SubActivity — the same dimension
    used by projections.py to merge actuals over budget.

MatchKey field (constructed by loader):
    SubActivity value, used as the merge dimension in projections.py.
    When actuals exist for a (Date, MatchKey) pair, all budget rows
    for that pair are excluded.  This prevents double-counting in the
    overlap period where both datasets have data.

Output columns:
    Year, Month, FY, DataSet, Activity, SubActivity, Description,
    Department, CostCentre, State, UOM, Quantity, Identifier, MatchKey,
    NGAFuel, CommonName, RowType, Scope1_tCO2e, Scope2_tCO2e,
    Scope3_tCO2e, Energy_GJ, Source
"""

import io
import pandas as pd
import os
from pathlib import Path
from calc_calendar import date_to_fy
from config import NGER_FY_START_MONTH, DIESEL_TRANSPORT_COSTCENTRES, DIESEL_TRANSPORT_NGAFUEL
from lookup_identifiers import enrich_with_lookup
from loader_nga import NGAFactorsByYear
from calc_emissions import (
    build_year_factor_map,
    apply_emissions_to_df
)


# Data files live in ./data/ alongside this module.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data')


def _read_csv_or_enc(csv_path, passphrase=None, **read_csv_kwargs):
    """Read a CSV file, decrypting from .enc if available.

    Priority:
        1. If <csv_path>.enc exists AND a passphrase is provided, decrypt and load.
        2. Otherwise fall back to plain <csv_path>.

    This lets the app work in both distributed (encrypted) and local-dev
    (plain CSV) scenarios without code changes.
    """
    enc_path = csv_path + '.enc'
    if os.path.exists(enc_path) and passphrase:
        from crypto_utils import decrypt_file
        plaintext = decrypt_file(enc_path, passphrase)
        print(f'Decrypted: {enc_path}')
        return pd.read_csv(io.BytesIO(plaintext), **read_csv_kwargs)

    return pd.read_csv(csv_path, **read_csv_kwargs)



def load_all_data(actual_path=None,
                  budget_path=None,
                  nga_folder=None,
                  fy_start_month=NGER_FY_START_MONTH,
                  passphrase=None):
    """Load and process operational metrics from separate actual/budget files.

    Reads two CSVs with Activity/SubActivity/Description/Identifier schema,
    tags each with DataSet = Actual or Budget, enriches with NGAFuel/CommonName/
    RowType via lookup_identifiers, concatenates, aggregates and calculates emissions.

    Args:
        actual_path: Path to operations_metrics_actual.csv
        budget_path: Path to operations_metrics_budget.csv
        nga_folder: Folder containing NGA factor files (auto-detected if None)
        fy_start_month: Fiscal year start month (default: 7 for July)

    Returns:
        Single DataFrame with both datasets, aggregated monthly, emissions calculated
    """

    # Default to files in DATA_DIR.  Explicit paths override.
    if actual_path is None:
        actual_path = os.path.join(DATA_DIR, 'operations_metrics_actual.csv')
    if budget_path is None:
        budget_path = os.path.join(DATA_DIR, 'operations_metrics_budget.csv')

    print('=' * 80)
    print('LOADING EMISSIONS DATA')
    print('=' * 80)

    # 1. LOAD CSVs AND TAG WITH DATASET
    # Source files have no DataSet column — we synthesise it from the file origin.
    # Uses _read_csv_or_enc to transparently decrypt .enc files when distributed.
    frames = []
    for path, label in [(actual_path, 'Actual'), (budget_path, 'Budget')]:
        try:
            part = _read_csv_or_enc(path, passphrase=passphrase)
            part['DataSet'] = label
            frames.append(part)
            print(f'Loaded {label}: {len(part):,} records from {path}')
        except FileNotFoundError:
            print(f'File not found: {path}')
            raise

    df = pd.concat(frames, ignore_index=True)
    print(f'Combined: {len(df):,} records')

    # 2. PARSE DATES AND ADD TIME COLUMNS
    # Source files use DD/MM/YYYY format, all dates are 1st of month.
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')

    # Validate dates — no silent NaT allowed
    failed_dates = df['Date'].isna().sum()
    if failed_dates > 0:
        # Re-read raw to show bad rows
        raw_a = _read_csv_or_enc(actual_path, passphrase=passphrase)
        raw_a['DataSet'] = 'Actual'
        raw_b = _read_csv_or_enc(budget_path, passphrase=passphrase)
        raw_b['DataSet'] = 'Budget'
        raw_df = pd.concat([raw_a, raw_b], ignore_index=True)
        bad_mask = pd.to_datetime(raw_df['Date'], dayfirst=True, errors='coerce').isna()
        bad_rows = raw_df[bad_mask][['Date', 'DataSet', 'Description', 'Quantity']].head(5).to_string(index=False)
        raise ValueError(
            f' {failed_dates} dates failed to parse in source CSV. '
            f'Fix the source file.\n\nFirst bad rows:\n{bad_rows}'
        )

    df['Year'] = df['Date'].dt.year
    df['Month'] = df['Date'].dt.month
    # Calculate FY from Date (July start = FY, not CY)
    df['FY'] = df['Date'].apply(date_to_fy)

    print(f"Date range: {df['Date'].min():%Y-%m} to {df['Date'].max():%Y-%m}")

    # 2b. VALIDATE QUANTITY COLUMN
    # Quantity must be numeric in the source file — do not silently coerce
    if not pd.api.types.is_numeric_dtype(df['Quantity']):
        # Try conversion but treat failures as hard errors
        try:
            df['Quantity'] = pd.to_numeric(df['Quantity'])
        except (ValueError, TypeError) as e:
            bad_rows = df[pd.to_numeric(df['Quantity'], errors='coerce').isna()]
            sample = bad_rows[['Date', 'DataSet', 'Description', 'Quantity']].head(5).to_string(index=False)
            raise ValueError(
                f' Quantity column contains non-numeric values. '
                f'Fix the source CSV.\n\nFirst bad rows:\n{sample}'
            ) from e

    # 3. ENRICH WITH LOOKUP (Activity/SubActivity → NGAFuel/CommonName/RowType)
    # This replaces the old embedded NGA/GRI columns that were removed from
    # the source CSVs.  Must happen before aggregation so the derived columns
    # are available as groupby keys.
    print('Enriching with identifier lookup...')
    df = enrich_with_lookup(df)

    # 3b. CONSTRUCT MATCHKEY
    # MatchKey = SubActivity.  This is the merge dimension used by projections.py
    # to determine which budget rows are superseded by actuals.
    # SubActivity is consistent across both datasets (e.g. "Diesel" in both actuals
    # and budget) whereas Description differs ("Diesel fuel bulk" vs "Diesel - Stationary").
    # The budget Identifier field (Budget|SubActivity|CostCentre) is structured around
    # SubActivity as the primary matching dimension.
    df['MatchKey'] = df['SubActivity'].astype(str)

    # 3c. VALIDATE DATASETS
    datasets = sorted(df['DataSet'].unique())
    print(f'Datasets found: {datasets}')

    # 4. AGGREGATE TO MONTHLY LEVEL
    # Group by: Year, Month, FY, DataSet, Activity, SubActivity, Description,
    #           Department, CostCentre, UOM, NGAFuel, CommonName, RowType
    print(f'\nAggregating to monthly level...')

    agg_df = df.groupby([
        'Year', 'Month', 'FY', 'DataSet',
        'Activity', 'SubActivity', 'Description',
        'Department', 'CostCentre', 'State', 'UOM',
        'NGAFuel', 'CommonName', 'RowType', 'MatchKey'
    ], dropna=False).agg({
        'Quantity': 'sum',
        'Source': 'first',     # Keep first source as metadata
        'Identifier': 'first'  # Budget: Budget|SubActivity|CostCentre; Actuals: invoice number
    }).reset_index()

    print(f'Aggregated: {len(df):,} → {len(agg_df):,} records')

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
        print(f'Diesel transport: {n_transport} rows reclassified (CCs: {DIESEL_TRANSPORT_COSTCENTRES})')

    # 5. LOAD NGA FACTORS
    if nga_folder is None:
        # Auto-detect NGA folder from actual file location
        nga_folder = Path(actual_path).parent

    try:
        nga_by_year = NGAFactorsByYear(str(nga_folder))
        years_loaded = nga_by_year.available_years
        print(f'NGA factors loaded: {years_loaded}')
    except Exception as e:
        print(f'Error loading NGA factors: {e}')
        raise

    # 6. CALCULATE EMISSIONS
    # Uses shared factor builder and emission applicator from calc_emissions.py
    # This ensures loader_data (actuals) and projections (budget/forecast) use identical logic.
    print(f'\nCalculating emissions...')

    # Build year-specific NGA factor lookup
    unique_years = agg_df['FY'].unique()
    year_factor_map = build_year_factor_map(nga_by_year, unique_years, state='QLD')

    # Apply emissions to all rows based on NGAFuel and FY
    agg_df = apply_emissions_to_df(agg_df, year_factor_map, fy_col='FY')

    print(f'Emissions calculated')
    print(f"Total Scope 1: {agg_df['Scope1_tCO2e'].sum():,.0f} tCO\u2082-e")
    print(f"Total Scope 2: {agg_df['Scope2_tCO2e'].sum():,.0f} tCO\u2082-e")
    print(f"Total Scope 3: {agg_df['Scope3_tCO2e'].sum():,.0f} tCO\u2082-e")

    # 7. OPTIMIZE MEMORY (categorical dtypes)
    print(f'\nOptimizing memory...')

    agg_df['DataSet'] = agg_df['DataSet'].astype('category')
    agg_df['Activity'] = agg_df['Activity'].astype('category')
    agg_df['SubActivity'] = agg_df['SubActivity'].astype('category')
    agg_df['Description'] = agg_df['Description'].astype('category')
    agg_df['Department'] = agg_df['Department'].astype('category')
    agg_df['CostCentre'] = agg_df['CostCentre'].astype('category')
    agg_df['UOM'] = agg_df['UOM'].astype('category')
    agg_df['State'] = agg_df['State'].astype('category')
    agg_df['NGAFuel'] = agg_df['NGAFuel'].astype('category')
    agg_df['CommonName'] = agg_df['CommonName'].astype('category')
    agg_df['RowType'] = agg_df['RowType'].astype('category')
    agg_df['MatchKey'] = agg_df['MatchKey'].astype('category')
    agg_df['Year'] = agg_df['Year'].astype('int16')
    agg_df['Month'] = agg_df['Month'].astype('int8')
    agg_df['FY'] = agg_df['FY'].astype('int16')
    agg_df['Quantity'] = agg_df['Quantity'].astype('float32')
    agg_df['Scope1_tCO2e'] = agg_df['Scope1_tCO2e'].astype('float32')
    agg_df['Scope2_tCO2e'] = agg_df['Scope2_tCO2e'].astype('float32')
    agg_df['Scope3_tCO2e'] = agg_df['Scope3_tCO2e'].astype('float32')
    agg_df['Energy_GJ'] = agg_df['Energy_GJ'].astype('float32')

    memory_mb = agg_df.memory_usage(deep=True).sum() / 1024**2
    print(f'Memory optimized: {memory_mb:.2f} MB')

    # 8. RECREATE DATE COLUMN (for convenience, set to 1st of each month)
    agg_df['Date'] = pd.to_datetime(
        agg_df['Year'].astype(str) + '-' + agg_df['Month'].astype(str).str.zfill(2) + '-01'
    )

    # 9. SORT AND FINALIZE
    agg_df = agg_df.sort_values(['DataSet', 'Year', 'Month', 'Description']).reset_index(drop=True)

    print(f'\n' + '=' * 80)
    print(f'DATA LOADING COMPLETE')
    print(f'Records: {len(agg_df):,}')
    print(f"Datasets: {list(agg_df['DataSet'].cat.categories)}")
    print(f"Date range: FY{agg_df['FY'].min()}-{agg_df['FY'].max()}")
    print('=' * 80 + '\n')

    return agg_df


# Backward compatibility — for code that expects old signature
def load_rom_data(*args, **kwargs):
    """Deprecated — use load_all_data() and filter SubActivity == 'Ore ROM'"""
    raise NotImplementedError('load_rom_data() deprecated — use load_all_data()')


def load_energy_data(*args, **kwargs):
    """Deprecated — use load_all_data()"""
    raise NotImplementedError('load_energy_data() deprecated — use load_all_data()')


def load_smc_transactions(filepath=None, passphrase=None):
    """Load SMC transaction log for reconciling model against registry actuals.

    Transaction types:
        Issuance   — CER issues credits (positive quantity)
        Sale       — credits sold / transferred out (negative quantity)
        Surrender  — credits used for compliance (negative quantity)
        Correction — manual adjustment, positive or negative

    Returns DataFrame with columns:
        Date, FY, Type, Quantity, Unit_Price, Total_Value, Reference, Notes

    Sales and surrenders should have negative Quantity.
    Adjustments to the SMC bank are summed by FY and applied to the model.
    """
    from calc_calendar import date_to_fy

    if filepath is None:
        filepath = os.path.join(DATA_DIR, 'smc_transactions.csv')

    path = Path(filepath)
    enc_path = Path(filepath + '.enc')
    if not path.exists() and not enc_path.exists():
        return pd.DataFrame(columns=['Date', 'FY', 'Type', 'Quantity',
                                      'Unit_Price', 'Total_Value',
                                      'Reference', 'Notes'])

    df = _read_csv_or_enc(filepath, passphrase=passphrase, parse_dates=['Date'])

    # Applies_To_FY is the reporting year the transaction relates to
    # (issuances lag — CER issues FY2024 credits in Feb 2025)
    df['Applies_To_FY'] = df['Applies_To_FY'].astype(int)

    return df