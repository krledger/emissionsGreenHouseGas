"""
nga_to_csv.py
Utility to convert NGA Excel workbooks into a single flat CSV.

PURPOSE:
    Reads National Greenhouse Account (NGA) factor Excel files and produces
    a single nga_factors.csv containing every emission factor needed for
    NGER reporting and Safeguard Mechanism calculations.

    The CSV gives:
      - Full traceability (source table, scope, units)
      - One-time parse of slow Excel files
      - A single, version-controllable data artifact

USAGE:
    python nga_to_csv.py                              # default: current dir, all states
    python nga_to_csv.py --folder /path/to/nga        # custom folder
    python nga_to_csv.py --years 2023 2024 2025       # specific years only
    python nga_to_csv.py --states QLD NSW              # electricity for these states only

OUTPUT:
    nga_factors.csv with columns:
        NGA_Year         - Publication year of the NGA workbook (int)
        Fuel_Type        - Broad category: Liquid fuels, Gaseous fuels, Electricity
        Fuel_Name        - NGA fuel description (verbatim from Excel)
        Scope            - Emission scope: 1, 2, or 3
        EF_kgCO2e_per_GJ - Emission factor per GJ (combined gases).  Blank for electricity.
        Energy_Content   - Energy content value (e.g. 38.6).  Blank for electricity.
        Energy_Unit      - Energy content unit (e.g. GJ/kL).  Blank for electricity.
        EF_kgCO2e_per_unit - Pre-computed factor per native unit (kgCO2-e/kL, kgCO2-e/m3 etc.)
        EF_Unit          - Unit of the pre-computed factor (e.g. kg CO2-e/kL)
        State            - State/territory (electricity only, e.g. QLD).  Blank for fuels.
        Source_Table     - NGA sheet or table the factor was extracted from

DATA SOURCES BY NGA YEAR:
    Table numbering shifted between 2023 and 2024.  This utility auto-detects
    the correct tables by matching on sheet title keywords.

    Liquid fuels (stationary):
        2023: Table 7   |  2024-2025: Table 8
    Gaseous fuels:
        2023: Table 4   |  2024-2025: Table 5
    Transport fuels:
        2023: Table 8   |  2024-2025: Table 9
    Electricity (location-based Scope 2 & 3):
        All years: Table 1
    Pre-computed summaries:
        All years: 'Energy - Scope 1 ' and 'Energy - Scope 3' sheets

EXTRACTION METHOD:
    This utility reads the 'Energy - Scope 1' and 'Energy - Scope 3' summary
    sheets.  These are pre-computed by DCCEEW and contain final kgCO2-e/unit
    values for every fuel type.  Using the summary sheets avoids re-deriving
    factors and guarantees alignment with the published workbook.

    Electricity factors come from Table 1 (location-based) which has
    state-by-state kgCO2-e/kWh values.

VALIDATION:
    After extraction the utility prints a summary and cross-checks
    key factors against known NGA 2025 values.
"""

import pandas as pd
import os
import sys
import argparse
from datetime import datetime


# ============================================================================
# EXTRACTION: ENERGY SUMMARY SHEETS
# ============================================================================

def _extract_scope1(xl, year):
    """Extract all Scope 1 factors from 'Energy - Scope 1' summary sheet.

    Sheet layout (consistent across 2023-2025):
        Row 0-2: Headers
        Row 3:   Column labels
        Row 4+:  Data rows

    Columns:
        0: Fuel Type (Solid/Liquid/Gaseous)
        1: Fuel Combusted (name)
        2: CO2 (kgCO2-e/GJ)
        3: CH4 (kgCO2-e/GJ)
        4: N2O (kgCO2-e/GJ)
        5: Combined kgCO2-e/GJ
        6: Energy content value
        7: Energy content unit (GJ/kL, GJ/t, GJ/m3)
        8: kgCO2-e per native unit (pre-computed)
        9: Per-unit label (e.g. kgCO2-e/kL)
        10: Scope (always '1')
        11: Source table reference
    """
    sheet_name = 'Energy - Scope 1 '  # Note trailing space in NGA files
    if sheet_name not in xl.sheet_names:
        sheet_name = 'Energy - Scope 1'
    if sheet_name not in xl.sheet_names:
        print(f"  WARNING: No 'Energy - Scope 1' sheet in {year}")
        return []

    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    rows = []

    for i in range(4, len(df)):
        fuel_type = str(df.iloc[i, 0]).strip() if pd.notna(df.iloc[i, 0]) else ''
        fuel_name = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ''

        if not fuel_name or fuel_name == 'nan':
            continue

        # Parse numeric fields (some have asterisks for footnotes)
        def _num(val):
            if pd.isna(val):
                return None
            s = str(val).replace('*', '').strip()
            try:
                return float(s)
            except ValueError:
                return None

        combined_gj = _num(df.iloc[i, 5])
        energy_val  = _num(df.iloc[i, 6])
        energy_unit = str(df.iloc[i, 7]).strip() if pd.notna(df.iloc[i, 7]) else ''
        ef_per_unit = _num(df.iloc[i, 8])
        ef_unit     = str(df.iloc[i, 9]).strip() if pd.notna(df.iloc[i, 9]) else ''
        source      = str(df.iloc[i, 11]).strip() if pd.notna(df.iloc[i, 11]) else ''

        if ef_per_unit is None:
            continue

        rows.append({
            'NGA_Year': year,
            'Fuel_Type': fuel_type,
            'Fuel_Name': fuel_name,
            'Scope': 1,
            'EF_kgCO2e_per_GJ': combined_gj,
            'Energy_Content': energy_val,
            'Energy_Unit': energy_unit,
            'EF_kgCO2e_per_unit': ef_per_unit,
            'EF_Unit': ef_unit,
            'State': '',
            'Source_Table': source[:80] if source else sheet_name.strip(),
        })

    return rows


def _extract_scope3(xl, year):
    """Extract all Scope 3 factors from 'Energy - Scope 3' summary sheet.

    Columns:
        0: Fuel Type
        1: Fuel Combusted
        2: kgCO2-e/GJ
        3: Energy content value
        4: Energy content unit
        5: kgCO2-e per native unit
        6: Per-unit label
        7: Scope (always '3')
        8: Source table reference
    """
    sheet_name = 'Energy - Scope 3'
    if sheet_name not in xl.sheet_names:
        print(f"  WARNING: No 'Energy - Scope 3' sheet in {year}")
        return []

    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    rows = []

    for i in range(4, len(df)):
        fuel_type = str(df.iloc[i, 0]).strip() if pd.notna(df.iloc[i, 0]) else ''
        fuel_name = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ''

        if not fuel_name or fuel_name == 'nan':
            continue

        def _num(val):
            if pd.isna(val):
                return None
            s = str(val).replace('*', '').strip()
            try:
                return float(s)
            except ValueError:
                return None

        ef_per_gj  = _num(df.iloc[i, 2])
        energy_val = _num(df.iloc[i, 3])
        energy_unit = str(df.iloc[i, 4]).strip() if pd.notna(df.iloc[i, 4]) else ''
        ef_per_unit = _num(df.iloc[i, 5])
        ef_unit     = str(df.iloc[i, 6]).strip() if pd.notna(df.iloc[i, 6]) else ''
        source      = str(df.iloc[i, 8]).strip() if pd.notna(df.iloc[i, 8]) else ''

        if ef_per_unit is None:
            continue

        rows.append({
            'NGA_Year': year,
            'Fuel_Type': fuel_type,
            'Fuel_Name': fuel_name,
            'Scope': 3,
            'EF_kgCO2e_per_GJ': ef_per_gj,
            'Energy_Content': energy_val,
            'Energy_Unit': energy_unit,
            'EF_kgCO2e_per_unit': ef_per_unit,
            'EF_Unit': ef_unit,
            'State': '',
            'Source_Table': source[:80] if source else sheet_name,
        })

    return rows


# ============================================================================
# EXTRACTION: ELECTRICITY (TABLE 1)
# ============================================================================

def _extract_electricity(xl, year, states=None):
    """Extract state-by-state electricity Scope 2 and 3 factors from Table 1.

    Table 1 structure (consistent across all years):
        Row 0: Title
        Row 1: Column headers (Scope 2, Scope 3)
        Row 2: Units (kgCO2-e/kWh, possibly also kgCO2-e/GJ for 2022-2023)
        Row 3+: Data rows

    2022-2023 have 5 columns: State, S2/kWh, S2/GJ, S3/kWh, S3/GJ
    2024-2025 have 3 columns: State, S2/kWh, S3/kWh

    Args:
        xl: pandas ExcelFile
        year: NGA publication year
        states: List of state codes to include (e.g. ['QLD', 'NSW']).
                None means include all states.
    """
    df = pd.read_excel(xl, sheet_name='Table 1', header=None)

    # Detect column layout by checking for GJ in units row
    units_row = df.iloc[2] if len(df) > 2 else None
    has_gj = False
    if units_row is not None:
        units_text = ' '.join([str(u) for u in units_row if pd.notna(u)])
        has_gj = 'GJ' in units_text

    if has_gj:
        # 2022-2023: State(0), S2_kWh(1), S2_GJ(2), S3_kWh(3), S3_GJ(4)
        s2_col, s3_col = 1, 3
    else:
        # 2024-2025: State(0), S2_kWh(1), S3_kWh(2)
        s2_col, s3_col = 1, 2

    # State name to code mapping
    state_map = {
        'New South Wales and Australian Capital Territory': 'NSW',
        'Victoria': 'VIC',
        'Queensland': 'QLD',
        'South Australia': 'SA',
        'Tasmania': 'TAS',
        'National': 'National',
    }

    rows = []

    for i in range(3, len(df)):
        state_name = str(df.iloc[i, 0]).strip() if pd.notna(df.iloc[i, 0]) else ''

        # Map state name
        state_code = state_map.get(state_name, '')

        # Handle WA and NT special cases
        if 'Western Australia' in state_name and 'SWIS' in state_name:
            state_code = 'WA'
        elif 'NWIS' in state_name:
            state_code = 'NWIS'
        elif 'Northern territory' in state_name.lower() or 'DKIS' in state_name:
            state_code = 'NT'

        if not state_code:
            continue

        # Filter by requested states (if specified)
        if states is not None and state_code not in states:
            continue

        def _num(val):
            if pd.isna(val):
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        s2 = _num(df.iloc[i, s2_col])
        s3 = _num(df.iloc[i, s3_col])

        if s2 is not None:
            rows.append({
                'NGA_Year': year,
                'Fuel_Type': 'Electricity',
                'Fuel_Name': 'Grid electricity',
                'Scope': 2,
                'EF_kgCO2e_per_GJ': None,
                'Energy_Content': None,
                'Energy_Unit': '',
                'EF_kgCO2e_per_unit': s2,
                'EF_Unit': 'kg CO2-e/kWh',
                'State': state_code,
                'Source_Table': 'Table 1',
            })

        if s3 is not None:
            rows.append({
                'NGA_Year': year,
                'Fuel_Type': 'Electricity',
                'Fuel_Name': 'Grid electricity',
                'Scope': 3,
                'EF_kgCO2e_per_GJ': None,
                'Energy_Content': None,
                'Energy_Unit': '',
                'EF_kgCO2e_per_unit': s3,
                'EF_Unit': 'kg CO2-e/kWh',
                'State': state_code,
                'Source_Table': 'Table 1',
            })

    return rows


# ============================================================================
# MAIN CONVERSION
# ============================================================================

def convert_nga_to_csv(folder_path='.', years=None, output_file=None, states=None):
    """Read all NGA Excel files and produce a single flat CSV.

    Args:
        folder_path: Directory containing NGA Excel files
        years: List of years to process (default: 2021-2025)
        output_file: Output CSV path (default: nga_factors.csv in folder_path)
        states: List of state codes for electricity (default: all states)

    Returns:
        DataFrame of all factors
    """
    if years is None:
        years = list(range(2021, 2026))

    if output_file is None:
        output_file = os.path.join(folder_path, 'nga_factors.csv')

    all_rows = []

    for year in years:
        # Try filename patterns
        filepath = os.path.join(folder_path, f'nationalgreenhouseaccountfactors{year}.xlsx')
        if not os.path.exists(filepath):
            filepath = os.path.join(folder_path, f'national-greenhouse-account-factors-{year}.xlsx')
        if not os.path.exists(filepath):
            print(f"  SKIP: No NGA file for {year}")
            continue

        print(f"  Reading {os.path.basename(filepath)}...")
        xl = pd.ExcelFile(filepath)

        # Extract fuel factors from Energy summary sheets
        s1_rows = _extract_scope1(xl, year)
        s3_rows = _extract_scope3(xl, year)
        elec_rows = _extract_electricity(xl, year, states=states)

        state_note = f" (states: {', '.join(states)})" if states else ""
        print(f"    Scope 1: {len(s1_rows)} factors")
        print(f"    Scope 3: {len(s3_rows)} factors")
        print(f"    Electricity: {len(elec_rows)} factors{state_note}")

        all_rows.extend(s1_rows)
        all_rows.extend(s3_rows)
        all_rows.extend(elec_rows)

    if not all_rows:
        print("ERROR: No factors extracted")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Sort for readability
    df = df.sort_values(
        ['NGA_Year', 'Fuel_Type', 'Fuel_Name', 'Scope', 'State']
    ).reset_index(drop=True)

    # Write CSV
    df.to_csv(output_file, index=False)
    print(f"\n  Wrote {len(df)} rows to {output_file}")

    return df


# ============================================================================
# VALIDATION
# ============================================================================

def validate_output(df):
    """Cross-check key factors against known NGA 2025 values.

    These are manually verified reference values from the published
    NGA Factors 2025 workbook.
    """
    checks = [
        # (year, fuel_name, scope, state, expected, tolerance, description)
        (2025, 'Diesel oil', 1, '', 2709.72, 1.0,
         'Diesel S1 stationary kgCO2-e/kL'),
        (2025, 'Diesel oil', 3, '', 667.78, 1.0,
         'Diesel S3 stationary kgCO2-e/kL'),
        (2025, 'Grid electricity', 2, 'QLD', 0.67, 0.01,
         'QLD Scope 2 kgCO2-e/kWh'),
        (2025, 'Grid electricity', 3, 'QLD', 0.09, 0.01,
         'QLD Scope 3 kgCO2-e/kWh'),
        (2025, 'Liquefied petroleum gas (LPG)', 1, '', 1557.42, 1.0,
         'LPG S1 kgCO2-e/kL'),
        (2025, 'Petroleum based greases', 1, '', 135.80, 1.0,
         'Greases S1 kgCO2-e/kL'),
        (2025, 'Petroleum based greases', 3, '', 698.40, 1.0,
         'Greases S3 kgCO2-e/kL'),
    ]

    print("\n  Validation checks:")
    all_ok = True

    for year, fuel, scope, state, expected, tol, desc in checks:
        mask = (
            (df['NGA_Year'] == year)
            & (df['Fuel_Name'] == fuel)
            & (df['Scope'] == scope)
        )
        if state:
            mask = mask & (df['State'] == state)

        matches = df[mask]

        if len(matches) == 0:
            print(f"    FAIL: {desc} - not found")
            all_ok = False
            continue

        actual = matches.iloc[0]['EF_kgCO2e_per_unit']
        if abs(actual - expected) <= tol:
            print(f"    OK:   {desc} = {actual:.4f} (expected {expected:.4f})")
        else:
            print(f"    FAIL: {desc} = {actual:.4f} (expected {expected:.4f})")
            all_ok = False

    return all_ok


# ============================================================================
# SUMMARY
# ============================================================================

def print_summary(df):
    """Print a human-readable summary of extracted factors."""
    print("\n  Summary by year:")
    for year in sorted(df['NGA_Year'].unique()):
        ydf = df[df['NGA_Year'] == year]
        n_fuels = len(ydf[ydf['Fuel_Type'] != 'Electricity'])
        n_elec = len(ydf[ydf['Fuel_Type'] == 'Electricity'])
        states = sorted(ydf[ydf['Fuel_Type'] == 'Electricity']['State'].dropna().unique())
        print(f"    {year}: {n_fuels} fuel factors + {n_elec} electricity factors "
              f"({', '.join(states)})")

    # Show Ravenswood-relevant fuels for latest year
    latest = df['NGA_Year'].max()
    print(f"\n  Ravenswood-relevant factors ({latest}):")

    target_fuels = [
        'Diesel oil',
        'Liquefied petroleum gas (LPG)',
        'Petroleum based oils',
        'Petroleum based greases',
        'Gaseous fossil fuels other than',
    ]

    ldf = df[df['NGA_Year'] == latest]
    for target in target_fuels:
        matches = ldf[ldf['Fuel_Name'].str.startswith(target)]
        # Only stationary (exclude transport variants with hyphens)
        matches = matches[~matches['Fuel_Name'].str.contains('-', na=False)]
        for _, row in matches.iterrows():
            print(f"    S{row['Scope']}: {row['Fuel_Name'][:50]:50s} "
                  f"{row['EF_kgCO2e_per_unit']:>10.4f} {row['EF_Unit']}")

    # Electricity
    elec = ldf[(ldf['Fuel_Type'] == 'Electricity')]
    for _, row in elec.iterrows():
        print(f"    S{row['Scope']}: Grid electricity ({row['State']})"
              f"{'':22s} {row['EF_kgCO2e_per_unit']:>10.4f} {row['EF_Unit']}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Convert NGA Excel workbooks to a single flat CSV')
    parser.add_argument('--folder', default='.',
                        help='Folder containing NGA Excel files')
    parser.add_argument('--years', nargs='+', type=int, default=None,
                        help='Specific years to process (default: 2021-2025)')
    parser.add_argument('--states', nargs='+', default=None,
                        help='State codes for electricity (e.g. QLD NSW). '
                             'Default: all states')
    parser.add_argument('--output', default=None,
                        help='Output CSV path (default: nga_factors.csv)')
    args = parser.parse_args()

    print(f"NGA Factor Extraction Utility")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Folder: {os.path.abspath(args.folder)}")
    if args.states:
        print(f"States: {', '.join(args.states)}")
    print()

    df = convert_nga_to_csv(args.folder, args.years, args.output,
                            states=args.states)

    if len(df) > 0:
        print_summary(df)
        validate_output(df)
        print("\nDone.")