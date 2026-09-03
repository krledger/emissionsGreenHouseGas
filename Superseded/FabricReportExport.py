"""
FabricReportExport.py
Produce reporting tables for Power BI via Fabric Lakehouse.
Last updated: 2026-04-24

PURPOSE:
    Bridge between the existing calculation core and Power BI reports.
    Takes raw data + PrecomputedData and produces flat DataFrames:

        1. GHG Emissions summary    (Calendar Year, site-level)
        2. GHG Detail               (Calendar Year, by Department & CostCentre)
        3. GHG Fuel detail           (Calendar Year, by fuel activity)
        4. NGERS Submission          (Financial Year)
        5. GRI 14 Disclosures        (Calendar Year, from existing ExportGri14)
        6. Safeguard Mechanism       (Financial Year, wide format)

    These DataFrames are designed to be:
    - Written to a Fabric Lakehouse as Delta tables, or
    - Exported to CSV/Parquet for Power BI import, or
    - Passed directly to Power BI via DirectQuery semantic model.

    All tables use long/tidy format so Power BI can filter/slice
    without complex DAX.  No multi-level headers, no merged cells.

LABEL CONVENTION (2026-04-24):
    Metric strings are short and display-ready for chart legends.
    Audit-grade detail (full disclosure name, methodology) lives in
    the Reference column or in the Category column, not in Metric.

USAGE:
    from LoaderData import load_all_data
    from CalcPrecompute import precompute_all
    from FabricReportExport import produce_all_reports

    df = load_all_data()
    precomputed = precompute_all(df, ...)

    reports = produce_all_reports(df, precomputed)
    reports['ghg'].to_csv('Out/ghg.csv', index=False)
    reports['ghg_detail'].to_csv('Out/ghg_detail.csv', index=False)
    reports['ngers'].to_csv('Out/ngers.csv', index=False)
    reports['gri14'].to_csv('Out/gri14.csv', index=False)

DESIGN PRINCIPLES:
    - Actuals-only by default (DataSet == 'Actual')
    - Numeric values stay numeric - no string formatting
    - One row per (Year, Metric) or (Year, Department, CostCentre) - tidy format
    - Consistent column names across summary tables:
        Year_Type      'FY' or 'CY'
        Year_Label     'FY2024' or 'CY2024' (string, human-readable)
        Year_Numeric   2024 (int, for sorting and joins)
        Report         'GHG' | 'NGERS' | 'GRI_14'
    - Each report has a 'Metric' column (short display name) and a
      'Value' column, plus 'Unit', 'Category', 'Reference'.
"""

import pandas as pd
from datetime import datetime

from ExportGri14 import build_gri14_export
from CalcCalendar import period_filter, year_to_date_range


# =====================================================================
# GHG EMISSIONS SUMMARY (CALENDAR YEAR)
# =====================================================================
# Site-level annual totals for GHG disclosure.  Scope 1, 2, 3,
# intensity metrics, energy consumption.  CY basis.

def build_ghg_report(precomputed, reporting_cys=None):
    """Build GHG emissions summary table (CY basis, site-level).

    Args:
        precomputed: PrecomputedData instance from CalcPrecompute
        reporting_cys: Optional list of CY integers to include.
                       Default: all CYs with Scope 1 > 0.

    Returns:
        DataFrame (long format) with columns:
            Report, Year_Type, Year_Label, Year_Numeric,
            Category, Metric, Value, Unit, Reference
    """
    annual = precomputed.annual_cy.copy()

    # Extract numeric CY from 'CY2024' label
    annual['_cy_numeric'] = annual['Year'].astype(str).str.replace('CY', '').astype(int)

    if reporting_cys is None:
        mask = annual['Scope1'] > 0
        reporting_cys = sorted(annual.loc[mask, '_cy_numeric'].unique().tolist())

    rows = []
    for cy in reporting_cys:
        row = annual[annual['_cy_numeric'] == cy]
        if row.empty:
            continue
        r = row.iloc[0]

        year_label = f'CY{cy}'

        # Absolute emissions by scope
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Absolute emissions', 'Scope 1',
                            float(r['Scope1']), 'tCO2-e',
                            'AASB S2 paragraph 29(a)(i)'))
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Absolute emissions', 'Scope 2',
                            float(r['Scope2']), 'tCO2-e',
                            'AASB S2 paragraph 29(a)(ii) - location-based'))
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Absolute emissions', 'Scope 3',
                            float(r['Scope3']), 'tCO2-e',
                            'AASB S2 paragraph 29(a)(iii)'))
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Absolute emissions', 'Total',
                            float(r['Total']), 'tCO2-e',
                            'AASB S2 paragraph 29(a)'))

        # Emissions intensity
        rom_t = float(r.get('ROM_t', 0))
        if rom_t > 0:
            intensity_s1 = float(r['Scope1']) / rom_t
            intensity_total = float(r['Total']) / rom_t
            rows.append(_mk_row('GHG', 'CY', year_label, cy,
                                'Emissions intensity', 'Scope 1 intensity',
                                intensity_s1, 'tCO2-e/t ROM',
                                'AASB S2 paragraph 29(b)'))
            rows.append(_mk_row('GHG', 'CY', year_label, cy,
                                'Emissions intensity', 'Total intensity',
                                intensity_total, 'tCO2-e/t ROM',
                                'AASB S2 paragraph 29(b)'))

        # Production denominator
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Production metrics', 'ROM ore',
                            rom_t, 't', 'AASB S2 paragraph 29(b)'))

        # Energy-related
        grid_kwh = float(r.get('Grid_Electricity_kWh', 0))
        site_kwh = float(r.get('Site_Electricity_kWh', 0))
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Energy', 'Grid electricity',
                            grid_kwh, 'kWh', 'AASB S2 paragraph 29 (energy)'))
        rows.append(_mk_row('GHG', 'CY', year_label, cy,
                            'Energy', 'Site electricity',
                            site_kwh, 'kWh', 'AASB S2 paragraph 29 (energy)'))

    return pd.DataFrame(rows)


# =====================================================================
# GHG DETAIL (CALENDAR YEAR, BY DEPARTMENT & COSTCENTRE)
# =====================================================================
# Department and CostCentre level breakdown for pie charts and
# drill-down analysis.  Actuals only.

def build_ghg_detail(df, reporting_cys=None):
    """Build GHG detail table with Department and CostCentre breakdown.

    Groups raw actual data by CY, Department, CostCentre.
    Produces Scope 1, 2, 3 and Total for each group.

    Args:
        df: Raw DataFrame from load_all_data()
        reporting_cys: Optional list of CY integers.
                       Default: all CYs with actual data.

    Returns:
        DataFrame with columns:
            Year_Label, Year_Numeric, Department, CostCentre,
            Scope1, Scope2, Scope3, Total
    """
    # Actuals only
    actuals = df[df['DataSet'] == 'Actual'].copy()

    if actuals.empty:
        return pd.DataFrame(columns=[
            'Year_Label', 'Year_Numeric', 'Department', 'CostCentre',
            'Scope1', 'Scope2', 'Scope3', 'Total'
        ])

    # CY = calendar year from the Year column (already in df from loader)
    actuals['CY'] = actuals['Year'].astype(int)

    if reporting_cys is not None:
        actuals = actuals[actuals['CY'].isin(reporting_cys)]

    # Group by CY, Department, CostCentre
    grouped = actuals.groupby(
        ['CY', 'Department', 'CostCentre'], observed=True, dropna=False
    ).agg(
        Scope1=('Scope1_tCO2e', 'sum'),
        Scope2=('Scope2_tCO2e', 'sum'),
        Scope3=('Scope3_tCO2e', 'sum'),
    ).reset_index()

    grouped['Total'] = grouped['Scope1'] + grouped['Scope2'] + grouped['Scope3']

    # Drop zero rows (no emissions at all)
    grouped = grouped[grouped['Total'].abs() > 0.01]

    # Add labelling columns
    grouped['Year_Label'] = grouped['CY'].apply(lambda y: f'CY{y}')
    grouped['Year_Numeric'] = grouped['CY'].astype(int)

    # Convert category dtypes to string for Delta/Parquet compatibility
    grouped['Department'] = grouped['Department'].astype(str)
    grouped['CostCentre'] = grouped['CostCentre'].astype(str)

    # Final column order
    result = grouped[[
        'Year_Label', 'Year_Numeric', 'Department', 'CostCentre',
        'Scope1', 'Scope2', 'Scope3', 'Total'
    ]].sort_values(['Year_Numeric', 'Department', 'CostCentre']).reset_index(drop=True)

    return result


# =====================================================================
# NGERS SUBMISSION (FINANCIAL YEAR)
# =====================================================================
# NGERS (National Greenhouse and Energy Reporting Scheme) requires annual
# submission of Scope 1 and Scope 2 emissions by facility, plus energy
# consumption and production.  Submitted via EERS by 31 October each year
# for the preceding FY.

def build_ngers_report(df, precomputed, reporting_fys=None):
    """Build NGERS annual submission table (FY basis).

    Args:
        df: Raw DataFrame from load_all_data() - needed for fuel breakdown
        precomputed: PrecomputedData instance
        reporting_fys: Optional list of FY integers.  Default: all with actuals.

    Returns:
        DataFrame (long format) with the unified schema.
    """
    annual = precomputed.annual_fy.copy()

    # Extract numeric FY from 'FY2024' label
    annual['_fy_numeric'] = annual['Year'].astype(str).str.replace('FY', '').astype(int)

    if reporting_fys is None:
        mask = annual['Scope1'] > 0
        reporting_fys = sorted(annual.loc[mask, '_fy_numeric'].unique().tolist())

    rows = []
    for fy in reporting_fys:
        row = annual[annual['_fy_numeric'] == fy]
        if row.empty:
            continue
        r = row.iloc[0]

        year_label = f'FY{fy}'

        # Section 1: Facility totals (EERS requires these explicitly)
        rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                            'Facility totals', 'Scope 1',
                            float(r['Scope1']), 'tCO2-e',
                            'NGER Act s19 / EERS facility report'))
        rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                            'Facility totals', 'Scope 2',
                            float(r['Scope2']), 'tCO2-e',
                            'NGER Act s19 / EERS facility report'))

        # Section 2: Energy
        grid_kwh = float(r.get('Grid_Electricity_kWh', 0))
        site_kwh = float(r.get('Site_Electricity_kWh', 0))
        grid_gj = grid_kwh * 0.0036  # 1 kWh = 0.0036 GJ
        site_gj = site_kwh * 0.0036

        rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                            'Energy consumption', 'Grid electricity',
                            grid_gj, 'GJ',
                            'NGER Regulations - energy consumption'))
        rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                            'Energy consumption', 'Site electricity',
                            site_gj, 'GJ',
                            'NGER Regulations - energy production'))

        # Section 3: Fuel breakdown by NGA fuel type (for EERS fuel rows)
        fuel_breakdown = _ngers_fuel_breakdown(df, fy)
        for _, fr in fuel_breakdown.iterrows():
            fuel = fr['NGAFuel']
            rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                                'Fuel consumption', fuel,
                                float(fr['Quantity']), fr['UOM'],
                                'NGER Regulations - fuel activity data'))
            rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                                'Fuel emissions', f'{fuel} (Scope 1)',
                                float(fr['Scope1_tCO2e']), 'tCO2-e',
                                'NGER Regulations - fuel Scope 1'))
            rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                                'Fuel emissions', f'{fuel} (Scope 3)',
                                float(fr['Scope3_tCO2e']), 'tCO2-e',
                                'NGER Regulations - fuel Scope 3'))

        # Section 4: Production (for Safeguard Mechanism cross-check)
        rom_t = float(r.get('ROM_t', 0))
        rows.append(_mk_row('NGERS', 'FY', year_label, fy,
                            'Production', 'ROM ore',
                            rom_t, 't',
                            'Safeguard Mechanism baseline'))

    return pd.DataFrame(rows)


def _ngers_fuel_breakdown(df, fy):
    """Aggregate actuals by NGA fuel type for a single FY.

    Uses date-range filtering via period_filter.
    """
    start, end = year_to_date_range(fy, 'FY')
    actuals = period_filter(df[df['DataSet'] == 'Actual'], start, end).copy()

    # Only rows with a fuel assigned
    has_fuel = actuals['NGAFuel'].notna() & (actuals['NGAFuel'].astype(str) != '')
    actuals = actuals[has_fuel]
    if actuals.empty:
        return pd.DataFrame(columns=['NGAFuel', 'UOM', 'Quantity',
                                      'Scope1_tCO2e', 'Scope3_tCO2e'])

    grouped = actuals.groupby(['NGAFuel', 'UOM'], observed=True, dropna=False).agg(
        Quantity=('Quantity', 'sum'),
        Scope1_tCO2e=('Scope1_tCO2e', 'sum'),
        Scope3_tCO2e=('Scope3_tCO2e', 'sum'),
    ).reset_index()

    # Drop zero rows
    grouped = grouped[grouped['Quantity'].abs() > 0]
    return grouped.sort_values('NGAFuel').reset_index(drop=True)


# =====================================================================
# GRI 14 DISCLOSURES (CALENDAR YEAR label, FY underlying - known limitation)
# =====================================================================
# Delegates to the existing ExportGri14 module.  Descriptions are kept
# verbatim for audit traceability - they map to published GRI disclosure
# language.  Short display labels can be added via a Power BI calculated
# column if needed.

def build_gri14_report(df, precomputed, reporting_cys=None):
    """Build GRI 14 disclosure table, normalised to the unified schema."""
    if reporting_cys is None:
        annual = precomputed.annual_cy.copy()
        annual['_cy_numeric'] = annual['Year'].astype(str).str.replace('CY', '').astype(int)
        mask = annual['Scope1'] > 0
        reporting_cys = sorted(annual.loc[mask, '_cy_numeric'].unique().tolist())

    # Convert CY integers to date-range periods
    reporting_periods = []
    for cy in reporting_cys:
        start, end = year_to_date_range(cy, 'CY')
        reporting_periods.append((start, end, f'CY{cy}'))

    # Delegate to existing GRI export with date-range periods
    gri_raw = build_gri14_export(precomputed, raw_df=df,
                                  reporting_periods=reporting_periods, year_type='CY')

    if gri_raw.empty:
        return pd.DataFrame(columns=['Report', 'Year_Type', 'Year_Label',
                                      'Year_Numeric', 'Category', 'Metric',
                                      'Value', 'Unit', 'Reference'])

    # Normalise column names to the unified schema
    out = pd.DataFrame({
        'Report': 'GRI_14',
        'Year_Type': 'CY',
        'Year_Label': gri_raw['FY'].apply(lambda y: f'CY{int(y)}'),
        'Year_Numeric': gri_raw['FY'].astype(int),
        'Category': gri_raw['Section'],
        'Metric': gri_raw['Description'],
        'Value': pd.to_numeric(gri_raw['Value'], errors='coerce'),
        'Unit': gri_raw['Unit'],
        'Reference': gri_raw['GRI_Reference'],
    })

    return out




# =====================================================================
# SAFEGUARD MECHANISM (FINANCIAL YEAR)
# =====================================================================
# Wide-format table: one row per FY with all safeguard columns.
# Power BI needs multiple measures on the same chart axis (Scope 1 bars
# + Baseline line + SMC values), so wide format is more natural here
# than long format.

def build_safeguard_report(precomputed):
    """Build safeguard projection table using config defaults.

    Uses DEFAULT_CARBON_CREDIT_PRICE and DEFAULT_CREDIT_ESCALATION
    from Config.py.  Interactive scenario modelling stays in Streamlit.

    Args:
        precomputed: PrecomputedData instance

    Returns:
        DataFrame (wide format) with columns:
            Year_Label, Year_Numeric, Phase, ROM_Mt,
            Scope1, Scope2, Scope3, Total,
            Baseline, SMC_Annual, SMC_Cumulative, SMC_Phase,
            In_Safeguard, Exit_FY,
            SMC_Issuance, SMC_Sold,
            Credit_Price, Credit_Value_Annual, Credit_Value_Cumulative,
            Site_Electricity_kWh, Grid_Electricity_kWh
    """
    from CalcPrecompute import build_safeguard_projection
    from Config import (
        DEFAULT_CARBON_CREDIT_PRICE, DEFAULT_CREDIT_ESCALATION,
        CREDIT_START_DATE,
    )
    from CalcCalendar import date_to_fy

    credit_start_fy = date_to_fy(CREDIT_START_DATE)

    projection = build_safeguard_projection(
        precomputed, year_type='FY',
        credit_start_fy=credit_start_fy,
        carbon_credit_price=DEFAULT_CARBON_CREDIT_PRICE,
        credit_escalation=DEFAULT_CREDIT_ESCALATION,
    )

    if projection.empty:
        return pd.DataFrame()

    # Select and rename columns for Power BI
    cols_wanted = [
        'FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total',
        'Baseline', 'SMC_Annual', 'SMC_Cumulative', 'SMC_Phase',
        'In_Safeguard', 'Exit_FY',
        'SMC_Issuance', 'SMC_Sold',
        'Credit_Price', 'Credit_Value_Annual', 'Credit_Value_Cumulative',
        'Site_Electricity_kWh', 'Grid_Electricity_kWh',
    ]
    # Only include columns that exist
    cols_present = [c for c in cols_wanted if c in projection.columns]
    result = projection[cols_present].copy()

    # Add year labelling
    result['Year_Label'] = result['FY']
    result['Year_Numeric'] = (
        result['FY'].astype(str).str.replace(r'^[A-Z]+', '', regex=True).astype(int)
    )

    return result


# =====================================================================
# GHG FUEL DETAIL (CALENDAR YEAR)
# =====================================================================
# Fuel consumption and emissions by Description (fuel activity).
# Powers the "Fuel Consumption" expander in Tab 1 and can serve as
# drill-down in Power BI.

def build_ghg_fuel(df, reporting_cys=None):
    """Build fuel consumption detail table (CY basis, all years).

    Groups raw actuals by CY + Description (fuel activity).
    Includes quantity, energy, and emissions by scope.

    Args:
        df: Raw DataFrame from load_all_data()
        reporting_cys: Optional list of CY integers.
                       Default: all CYs with actual fuel data.

    Returns:
        DataFrame with columns:
            Year_Label, Year_Numeric, Description, UOM,
            Quantity, Energy_GJ, Scope1, Scope2, Scope3, Total
    """
    actuals = df[df['DataSet'] == 'Actual'].copy()

    # Only rows with a fuel assigned
    has_fuel = actuals['NGAFuel'].notna() & (actuals['NGAFuel'].astype(str) != '')
    actuals = actuals[has_fuel]

    if actuals.empty:
        return pd.DataFrame(columns=[
            'Year_Label', 'Year_Numeric', 'Description', 'UOM',
            'Quantity', 'Energy_GJ', 'Scope1', 'Scope2', 'Scope3', 'Total'
        ])

    actuals['CY'] = actuals['Year'].astype(int)

    if reporting_cys is not None:
        actuals = actuals[actuals['CY'].isin(reporting_cys)]

    agg_cols = {
        'Quantity': 'sum',
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum',
        'UOM': 'first',
    }
    if 'Energy_GJ' in actuals.columns:
        agg_cols['Energy_GJ'] = 'sum'

    grouped = actuals.groupby(
        ['CY', 'Description'], observed=True, dropna=False
    ).agg(agg_cols).reset_index()

    grouped['Total'] = (
        grouped['Scope1_tCO2e'] + grouped['Scope2_tCO2e'] + grouped['Scope3_tCO2e']
    )

    # Drop zero rows
    grouped = grouped[grouped['Total'].abs() > 0.01]

    if grouped.empty:
        return pd.DataFrame(columns=[
            'Year_Label', 'Year_Numeric', 'Description', 'UOM',
            'Quantity', 'Energy_GJ', 'Scope1', 'Scope2', 'Scope3', 'Total'
        ])

    # Labelling
    grouped['Year_Label'] = grouped['CY'].apply(lambda y: f'CY{y}')
    grouped['Year_Numeric'] = grouped['CY'].astype(int)

    # Ensure Energy_GJ exists
    if 'Energy_GJ' not in grouped.columns:
        grouped['Energy_GJ'] = 0.0

    # Rename emission columns to short labels
    grouped = grouped.rename(columns={
        'Scope1_tCO2e': 'Scope1',
        'Scope2_tCO2e': 'Scope2',
        'Scope3_tCO2e': 'Scope3',
    })

    # Convert category dtypes for Delta compatibility
    grouped['Description'] = grouped['Description'].astype(str)
    grouped['UOM'] = grouped['UOM'].astype(str)

    result = grouped[[
        'Year_Label', 'Year_Numeric', 'Description', 'UOM',
        'Quantity', 'Energy_GJ', 'Scope1', 'Scope2', 'Scope3', 'Total'
    ]].sort_values(['Year_Numeric', 'Description']).reset_index(drop=True)

    return result

# =====================================================================
# WRAPPER - PRODUCE ALL REPORTS
# =====================================================================

def produce_all_reports(df, precomputed,
                        reporting_cys=None,
                        reporting_fys=None):
    """Produce all reporting tables in one call.

    Returns dict with keys:
        'ghg'        - site-level GHG summary (CY, long format)
        'ghg_detail' - department/cost centre breakdown (CY, wide format)
        'ghg_fuel'   - fuel consumption detail (CY, wide format)
        'ngers'      - NGERS submission (FY, long format)
        'gri14'      - GRI 14 disclosures (CY, long format)
        'safeguard'  - safeguard projection (FY, wide format)
        'combined'   - ghg + ngers + gri14 stacked (long format only)
    """
    ghg = build_ghg_report(precomputed, reporting_cys=reporting_cys)
    ghg_detail = build_ghg_detail(df, reporting_cys=reporting_cys)
    ghg_fuel = build_ghg_fuel(df, reporting_cys=reporting_cys)
    ngers = build_ngers_report(df, precomputed, reporting_fys=reporting_fys)
    gri14 = build_gri14_report(df, precomputed, reporting_cys=reporting_cys)
    safeguard = build_safeguard_report(precomputed)

    # Combined long table - ghg + ngers + gri14 (not detail/fuel/safeguard, different schema)
    combined = pd.concat([ghg, ngers, gri14], ignore_index=True)

    return {
        'ghg': ghg,
        'ghg_detail': ghg_detail,
        'ghg_fuel': ghg_fuel,
        'ngers': ngers,
        'gri14': gri14,
        'safeguard': safeguard,
        'combined': combined,
    }


# =====================================================================
# HELPERS
# =====================================================================

def _mk_row(report, year_type, year_label, year_numeric,
            category, metric, value, unit, reference):
    """Build one long-format row with the unified schema."""
    return {
        'Report': report,
        'Year_Type': year_type,
        'Year_Label': year_label,
        'Year_Numeric': int(year_numeric),
        'Category': category,
        'Metric': metric,
        'Value': float(value) if value is not None else None,
        'Unit': unit,
        'Reference': reference,
    }


# =====================================================================
# LOCAL TEST HARNESS
# =====================================================================

if __name__ == '__main__':
    from pathlib import Path
    from LoaderData import load_all_data
    from CalcPrecompute import precompute_all
    from Config import (
        FSEI_ROM, FSEI_ELEC,
        DEFAULT_START_DATE, DEFAULT_END_REHABILITATION_DATE,
        DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE,
        CREDIT_START_DATE, DECLINE_RATE_PHASE2,
    )

    print('Loading data...')
    df = load_all_data()

    print('Precomputing...')
    precomputed = precompute_all(
        df, FSEI_ROM, FSEI_ELEC,
        DEFAULT_START_DATE, DEFAULT_END_REHABILITATION_DATE,
        DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE,
        DEFAULT_END_REHABILITATION_DATE,
        CREDIT_START_DATE, DECLINE_RATE_PHASE2,
    )

    print('Producing reports...')
    reports = produce_all_reports(df, precomputed)

    out = Path('Out')
    out.mkdir(exist_ok=True)

    for name, tbl in reports.items():
        path = out / f'{name}.csv'
        tbl.to_csv(path, index=False)
        print(f'  {name:12s} {len(tbl):>5} rows -> {path}')

    print('\nDone.')
