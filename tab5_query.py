"""
tab5_query.py
Data Query tab — interactive filtering and SMC reporting
"""

import streamlit as st
import pandas as pd
from calc_emissions import build_year_factor_map
from loader_nga import NGAFactorsByYear
from loader_data import load_smc_transactions
from projections import (build_projection, apply_smc_transactions,
                         smc_credit_value_analysis)
from calc_calendar import date_to_fy
from config import DEFAULT_GRID_CONNECTION_DATE
import os


def render_query_tab(df, fsei_rom=None, fsei_elec=None,
                     start_date=None, end_date=None,
                     end_mining_date=None, end_processing_date=None,
                     end_rehabilitation_date=None,
                     carbon_credit_price=0, credit_escalation=0,
                     credit_start_date=None, decline_rate_phase2=None,
                     monthly=None):
    """Render the Data Query tab.

    Two sections:
        1. Emissions Data Query — multi-select filters over full dataset
        2. SMC Ledger — all years, forecast vs actual vs combined
    """

    # NGA factor map (shared by both sections)
    nga_folder = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(nga_folder, 'nga_factors.csv')):
        nga_folder = '/mnt/project'
    try:
        nga_by_year = NGAFactorsByYear(nga_folder)
    except FileNotFoundError:
        nga_by_year = None

    unique_fy = sorted(df['FY'].unique()) if df is not None else []
    year_factor_map = {}
    if nga_by_year and len(unique_fy) > 0:
        try:
            year_factor_map = build_year_factor_map(nga_by_year, unique_fy, state='QLD')
        except Exception as e:
            st.warning(f"Could not build NGA factor map: {e}")

    _render_emissions_query(df, year_factor_map)

    st.markdown("---")

    st.subheader("SMC Ledger")
    if st.button("Load SMC Ledger", key="btn_smc_ledger"):
        st.session_state['_smc_loaded'] = True

    if st.session_state.get('_smc_loaded', False):
        _render_smc_ledger(df, fsei_rom, fsei_elec, start_date, end_date,
                           end_mining_date, end_processing_date,
                           end_rehabilitation_date, carbon_credit_price,
                           credit_escalation, credit_start_date,
                           decline_rate_phase2, monthly=monthly)


# =====================================================================
# SECTION 1: EMISSIONS DATA QUERY
# =====================================================================

def _render_emissions_query(df, year_factor_map):
    """Emissions data with multi-select filters and NGA enrichment."""

    st.subheader("Emissions Data Query")
    st.caption("Filter and explore the full emissions dataset with NGA factors and calculated emissions.")

    if df is None or df.empty:
        st.warning("No data loaded.")
        return

    # --- Date range: year + month dropdowns ---
    all_years = sorted(df['Year'].unique())
    all_months = list(range(1, 13))
    month_names = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun',
                   7:'Jul', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}

    col_d1, col_d2, col_d3, col_d4 = st.columns(4)
    with col_d1:
        start_year = st.selectbox("Start Year", all_years, index=0, key="q_start_yr")
    with col_d2:
        start_month = st.selectbox("Start Month", all_months,
                                    format_func=lambda m: month_names[m],
                                    index=0, key="q_start_mo")
    with col_d3:
        end_year = st.selectbox("End Year", all_years,
                                 index=len(all_years) - 1, key="q_end_yr")
    with col_d4:
        end_month = st.selectbox("End Month", all_months,
                                  format_func=lambda m: month_names[m],
                                  index=11, key="q_end_mo")

    # --- Cascading multi-select filters ---
    # Each filter narrows the pool for subsequent filters.
    # Date range applied first, then filters cascade top-to-bottom.
    pool = df.copy()
    pool = pool[
        ((pool['Year'] > start_year) |
         ((pool['Year'] == start_year) & (pool['Month'] >= start_month))) &
        ((pool['Year'] < end_year) |
         ((pool['Year'] == end_year) & (pool['Month'] <= end_month)))
    ]

    # Dataset defaults to actuals-containing datasets
    all_datasets = sorted(pool['DataSet'].dropna().unique().tolist())
    actuals = [d for d in all_datasets if 'actual' in d.lower()]
    default_datasets = actuals if actuals else all_datasets

    col1, col2, col3 = st.columns(3)
    with col1:
        sel_datasets = st.multiselect("Dataset", all_datasets,
                                       default=default_datasets, key="q_dataset")
    if sel_datasets:
        pool = pool[pool['DataSet'].isin(sel_datasets)]

    with col2:
        sel_descriptions = st.multiselect("Description",
                                           sorted(pool['Description'].dropna().unique().tolist()),
                                           key="q_desc")
    if sel_descriptions:
        pool = pool[pool['Description'].isin(sel_descriptions)]

    with col3:
        sel_departments = st.multiselect("Department",
                                          sorted(pool['Department'].dropna().unique().tolist()),
                                          key="q_dept")
    if sel_departments:
        pool = pool[pool['Department'].isin(sel_departments)]

    col4, col5 = st.columns(2)
    with col4:
        sel_ccs = st.multiselect("Cost Centre",
                                  sorted(pool['CostCentre'].dropna().unique().tolist()),
                                  key="q_cc")
    if sel_ccs:
        pool = pool[pool['CostCentre'].isin(sel_ccs)]

    with col5:
        sel_fuels = st.multiselect("NGA Fuel",
                                    sorted(pool['NGAFuel'].dropna().unique().tolist()),
                                    key="q_fuel")
    if sel_fuels:
        pool = pool[pool['NGAFuel'].isin(sel_fuels)]

    # --- Apply all filters to get final filtered set ---
    filtered = pool

    if filtered.empty:
        st.info("No data matches the selected filters.")
        return

    # --- Aggregate to FY ---
    group_cols = ['FY', 'DataSet', 'Description', 'Department', 'CostCentre',
                  'NGAFuel', 'UOM', 'State']
    group_cols = [c for c in group_cols if c in filtered.columns]

    agg_dict = {
        'Quantity': ('Quantity', 'sum'),
        'Scope1_tCO2e': ('Scope1_tCO2e', 'sum'),
        'Scope2_tCO2e': ('Scope2_tCO2e', 'sum'),
        'Scope3_tCO2e': ('Scope3_tCO2e', 'sum'),
    }
    if 'Energy_GJ' in filtered.columns:
        agg_dict['Energy_GJ'] = ('Energy_GJ', 'sum')

    agg = filtered.groupby(group_cols, observed=True, dropna=False).agg(**agg_dict).reset_index()

    # --- Enrich with NGA factors ---
    ef_s1, ef_s2, ef_s3, ef_energy, nga_years = [], [], [], [], []

    for _, row in agg.iterrows():
        fy = int(row['FY']) if str(row['FY']).isdigit() else int(str(row['FY']).replace('FY', ''))
        nga_fuel = str(row.get('NGAFuel', ''))
        desc = str(row.get('Description', ''))
        yf_all = year_factor_map.get(fy, {})

        factor_key = None
        if nga_fuel in yf_all:
            factor_key = nga_fuel
        elif desc in yf_all:
            factor_key = desc
        else:
            prefixes = [(k, len(k)) for k in yf_all if k != '_nga_year' and nga_fuel.startswith(k)]
            if prefixes:
                factor_key = max(prefixes, key=lambda x: x[1])[0]
            else:
                reverse = [k for k in yf_all if k != '_nga_year' and k.startswith(nga_fuel)]
                if reverse:
                    factor_key = reverse[0]

        if factor_key and factor_key in yf_all:
            fac = yf_all[factor_key]
            ef_s1.append(fac.get('s1', 0))
            ef_s2.append(fac.get('s2', 0))
            ef_s3.append(fac.get('s3', 0))
            ef_energy.append(fac.get('energy', 0))
        else:
            ef_s1.append(0)
            ef_s2.append(0)
            ef_s3.append(0)
            ef_energy.append(0)

        nga_years.append(yf_all.get('_nga_year', ''))

    agg['NGA_Year'] = nga_years
    agg['EF_S1_kgCO2e'] = ef_s1
    agg['EF_S2_kgCO2e'] = ef_s2
    agg['EF_S3_kgCO2e'] = ef_s3
    agg['Energy_per_unit'] = ef_energy
    agg['Total_tCO2e'] = agg['Scope1_tCO2e'] + agg['Scope2_tCO2e'] + agg['Scope3_tCO2e']

    col_order = [
        'FY', 'DataSet', 'Description', 'Department', 'CostCentre',
        'NGAFuel', 'UOM', 'State', 'NGA_Year',
        'Quantity', 'EF_S1_kgCO2e', 'EF_S2_kgCO2e', 'EF_S3_kgCO2e', 'Energy_per_unit',
        'Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e', 'Total_tCO2e', 'Energy_GJ',
    ]
    col_order = [c for c in col_order if c in agg.columns]
    agg = agg[col_order].sort_values(['FY', 'DataSet', 'Description']).reset_index(drop=True)

    # Summary metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rows", f"{len(agg):,}")
    c2.metric("Scope 1", f"{agg['Scope1_tCO2e'].sum():,.0f} t")
    c3.metric("Scope 2", f"{agg['Scope2_tCO2e'].sum():,.0f} t")
    c4.metric("Scope 3", f"{agg['Scope3_tCO2e'].sum():,.0f} t")
    c5.metric("Total", f"{agg['Total_tCO2e'].sum():,.0f} t")

    # Format and display
    display = _format_emissions_table(agg)
    st.dataframe(display, hide_index=True, width='stretch', height=600)

    st.download_button(
        label="Download filtered data",
        data=display.to_csv(index=False),
        file_name="emissions_query_export.csv",
        mime="text/csv",
        key="dl_query_export",
    )


def _format_emissions_table(agg):
    """Round and rename columns for display. Values stay numeric for clean Excel import."""
    display = agg.copy()
    round_map = {
        'Quantity': 1, 'EF_S1_kgCO2e': 4, 'EF_S2_kgCO2e': 4,
        'EF_S3_kgCO2e': 4, 'Energy_per_unit': 4,
        'Scope1_tCO2e': 1, 'Scope2_tCO2e': 1, 'Scope3_tCO2e': 1,
        'Total_tCO2e': 1, 'Energy_GJ': 1,
    }
    for c, d in round_map.items():
        if c in display.columns:
            display[c] = display[c].round(d)

    return display.rename(columns={
        'DataSet': 'Dataset', 'CostCentre': 'Cost Centre',
        'NGAFuel': 'NGA Fuel', 'NGA_Year': 'NGA Year',
        'EF_S1_kgCO2e': 'EF S1 (kg/unit)', 'EF_S2_kgCO2e': 'EF S2 (kg/unit)',
        'EF_S3_kgCO2e': 'EF S3 (kg/unit)', 'Energy_per_unit': 'GJ/unit',
        'Scope1_tCO2e': 'Scope 1 tCO2-e', 'Scope2_tCO2e': 'Scope 2 tCO2-e',
        'Scope3_tCO2e': 'Scope 3 tCO2-e', 'Total_tCO2e': 'Total tCO2-e',
        'Energy_GJ': 'Energy GJ',
    })


# =====================================================================
# SECTION 2: SMC LEDGER
# =====================================================================

def _render_smc_ledger(df, fsei_rom, fsei_elec, start_date, end_date,
                       end_mining_date, end_processing_date,
                       end_rehabilitation_date, carbon_credit_price,
                       credit_escalation, credit_start_date,
                       decline_rate_phase2, monthly=None):
    """SMC ledger: forecast, actual transactions, and combined view."""

    st.caption("Safeguard Mechanism Credits \u2014 forecast, actual transactions and combined position.")

    if df is None or credit_start_date is None:
        st.info("Insufficient data for SMC ledger. Check sidebar parameters.")
        return

    credit_start_fy = date_to_fy(credit_start_date)

    view = st.radio("View", ["Combined", "Forecast Only", "Transactions Only"],
                     horizontal=True, key="smc_view")

    # --- Use pre-built monthly if available, otherwise build ---
    if monthly is None:
        monthly = build_projection(
            df,
            end_mining_date=end_mining_date,
            end_processing_date=end_processing_date,
            end_rehabilitation_date=end_rehabilitation_date,
            fsei_rom=fsei_rom, fsei_elec=fsei_elec,
            credit_start_date=credit_start_date,
            start_date=start_date, end_date=end_date,
            decline_rate_phase2=decline_rate_phase2
        )

    from tab2_safeguard import prepare_annual_for_safeguard
    forecast = prepare_annual_for_safeguard(monthly, year_type='FY')

    # Raw forecast (before transactions)
    forecast_raw = forecast.copy()
    if 'SMC_Monthly' in forecast_raw.columns:
        forecast_raw['SMC_Annual'] = forecast_raw['SMC_Monthly']
    forecast_raw['SMC_Cumulative'] = forecast_raw['SMC_Annual'].cumsum()
    forecast_raw = smc_credit_value_analysis(
        forecast_raw, credit_start_fy, carbon_credit_price, credit_escalation)

    # --- Load transactions ---
    smc_txns = load_smc_transactions()

    # --- Combined (forecast + transactions) ---
    combined = forecast.copy()
    if 'SMC_Monthly' in combined.columns:
        combined['SMC_Annual'] = combined['SMC_Monthly']
    if not smc_txns.empty:
        combined = apply_smc_transactions(combined, smc_txns)
    combined = smc_credit_value_analysis(
        combined, credit_start_fy, carbon_credit_price, credit_escalation)

    # Filter to credit period
    for frame in [forecast_raw, combined]:
        if 'FY_num' not in frame.columns:
            frame['FY_num'] = frame['FY'].str.replace(r'^[A-Z]+', '', regex=True).astype(int)

    forecast_credit = forecast_raw[forecast_raw['FY_num'] >= credit_start_fy].copy()
    combined_credit = combined[combined['FY_num'] >= credit_start_fy].copy()

    # === TRANSACTIONS TABLE ===
    if view in ["Transactions Only", "Combined"]:
        with st.expander("Transaction Log", expanded=(view == "Transactions Only")):
            if smc_txns.empty:
                st.info("No transactions found in smc_transactions.csv")
            else:
                txn_display = smc_txns.copy()
                txn_display['Date'] = txn_display['Date'].dt.strftime('%d %b %Y')
                for c in ['Unit_Price', 'Total_Value']:
                    if c in txn_display.columns:
                        txn_display[c] = txn_display[c].round(2)

                st.dataframe(txn_display, hide_index=True, width='stretch')
                st.download_button(
                    label="Download transactions",
                    data=smc_txns.to_csv(index=False),
                    file_name="smc_transactions_export.csv",
                    mime="text/csv",
                    key="dl_smc_txn",
                )

    # === FORECAST TABLE ===
    if view in ["Forecast Only", "Combined"]:
        with st.expander("Model Forecast (no transactions)", expanded=(view == "Forecast Only")):
            fc_cols = ['FY', 'Scope1', 'Baseline', 'SMC_Annual', 'SMC_Cumulative',
                       'Credit_Price', 'Credit_Value_Annual', 'Credit_Value_Cumulative']
            fc_cols = [c for c in fc_cols if c in forecast_credit.columns]
            fc_display = forecast_credit[fc_cols].copy()

            for c in ['Scope1', 'Baseline', 'SMC_Annual', 'SMC_Cumulative',
                       'Credit_Value_Annual', 'Credit_Value_Cumulative']:
                if c in fc_display.columns:
                    fc_display[c] = fc_display[c].round(0)
            for c in ['Credit_Price']:
                if c in fc_display.columns:
                    fc_display[c] = fc_display[c].round(2)

            fc_display = fc_display.rename(columns={
                'Scope1': 'Scope 1 tCO2-e', 'Baseline': 'Target',
                'SMC_Annual': 'SMC Annual', 'SMC_Cumulative': 'SMC Cumulative',
                'Credit_Price': 'Price ($/t)',
                'Credit_Value_Annual': 'Value Annual ($)',
                'Credit_Value_Cumulative': 'Value Cumulative ($)',
            })

            st.dataframe(fc_display, hide_index=True, width='stretch')
            st.download_button(
                label="Download forecast",
                data=fc_display.to_csv(index=False),
                file_name="smc_forecast_export.csv",
                mime="text/csv",
                key="dl_smc_forecast",
            )

    # === COMBINED LEDGER ===
    if view == "Combined":
        with st.expander("Combined Position (Forecast + Transactions)", expanded=True):

            ledger = combined_credit[['FY']].copy()

            # Forecast earned (before transactions)
            ledger['Forecast_Earned'] = forecast_credit['SMC_Annual'].values

            # Actual issuance and sales
            ledger['Actual_Issuance'] = combined_credit['SMC_Issuance'].values if 'SMC_Issuance' in combined_credit.columns else 0
            ledger['Actual_Sold'] = combined_credit['SMC_Sold'].values if 'SMC_Sold' in combined_credit.columns else 0

            # Net and cumulative
            ledger['Net_Annual'] = combined_credit['SMC_Annual'].values
            ledger['Cumulative_Balance'] = combined_credit['SMC_Cumulative'].values

            # Value columns
            if 'Credit_Price' in combined_credit.columns:
                ledger['Price'] = combined_credit['Credit_Price'].values
            if 'Credit_Value_Annual' in combined_credit.columns:
                ledger['Value_Annual'] = combined_credit['Credit_Value_Annual'].values
            if 'Credit_Value_Cumulative' in combined_credit.columns:
                ledger['Value_Cumulative'] = combined_credit['Credit_Value_Cumulative'].values

            # Sale revenue from transaction values (actual $ received)
            if not smc_txns.empty and 'Total_Value' in smc_txns.columns:
                sale_values = smc_txns[smc_txns['Type'] == 'Sale'].copy()
                if not sale_values.empty and sale_values['Total_Value'].notna().any():
                    sv_by_fy = sale_values.groupby('Applies_To_FY')['Total_Value'].sum()
                    ledger['Sale_Revenue'] = ledger['FY'].str.replace(
                        r'^[A-Z]+', '', regex=True).astype(int).map(sv_by_fy).fillna(0)

            # Format
            ledger_display = ledger.copy()
            for c in ['Forecast_Earned', 'Actual_Issuance', 'Actual_Sold',
                       'Net_Annual', 'Cumulative_Balance',
                       'Value_Annual', 'Value_Cumulative', 'Sale_Revenue']:
                if c in ledger_display.columns:
                    ledger_display[c] = ledger_display[c].round(0)
            if 'Price' in ledger_display.columns:
                ledger_display['Price'] = ledger_display['Price'].round(2)

            ledger_display = ledger_display.rename(columns={
                'Forecast_Earned': 'Forecast Earned',
                'Actual_Issuance': 'CER Issuance',
                'Actual_Sold': 'Sold',
                'Net_Annual': 'Net Annual',
                'Cumulative_Balance': 'Cumulative Balance',
                'Price': 'Price ($/t)',
                'Value_Annual': 'Value Annual ($)',
                'Value_Cumulative': 'Value Cumulative ($)',
                'Sale_Revenue': 'Sale Revenue ($)',
            })

            st.dataframe(ledger_display, hide_index=True, width='stretch')
            st.download_button(
                label="Download combined ledger",
                data=ledger_display.to_csv(index=False),
                file_name="smc_combined_ledger.csv",
                mime="text/csv",
                key="dl_smc_combined",
            )

            # Summary metrics
            final = combined_credit.iloc[-1]
            final_cum = final.get('SMC_Cumulative', 0)
            final_val = final.get('Credit_Value_Cumulative', 0)
            total_sold = abs(combined_credit['SMC_Sold'].sum()) if 'SMC_Sold' in combined_credit.columns else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Final Balance", f"{final_cum:,.0f} tCO2-e")
            c2.metric("Portfolio Value", f"{final_val:,.0f} AUD")
            c3.metric("Total Sold", f"{total_sold:,.0f} tCO2-e")
            c4.metric("As at", str(final['FY']))