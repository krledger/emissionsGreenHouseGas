"""
tab5_query.py
Data Query tab \u2014 interactive filtering and SMC reporting
Last updated: 2026-03-10

ARCHITECTURE (v2):
    Receives PrecomputedData from app.py.
    Emissions query: filters raw df (user-driven, fast pandas ops).
    SMC ledger: uses pre-computed projection, no build_projection call.
"""

import streamlit as st
import pandas as pd
from calc_precompute import build_safeguard_projection
from projections import apply_smc_transactions, smc_credit_value_analysis
from loader_data import load_smc_transactions
from calc_calendar import date_to_fy
from config import DEFAULT_GRID_CONNECTION_DATE, CREDIT_START_DATE
import os


def render_query_tab(df, precomputed,
                     carbon_credit_price=0, credit_escalation=0):
    """Render the Data Query tab.

    Two sections:
        1. Emissions Data Query \u2014 multi-select filters over full dataset
        2. SMC Ledger \u2014 all years, forecast vs actual vs combined

    Args:
        df: Raw DataFrame from load_all_data()
        precomputed: PrecomputedData from calc_precompute
        carbon_credit_price: SMC market price
        credit_escalation: Annual price escalation rate
    """

    _render_emissions_query(df, precomputed.year_factor_map)

    st.markdown("---")

    _render_smc_ledger(precomputed, carbon_credit_price, credit_escalation)


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

    # --- Dataset and resolution ---
    col_ds, col_res = st.columns(2)
    with col_ds:
        dataset_mode = st.radio("Dataset", ["Combined", "Actual", "Budget"],
                                horizontal=True, key="q_dataset_mode")
    with col_res:
        resolution = st.radio("Resolution", ["Annual", "Monthly"],
                              horizontal=True, key="q_resolution")

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

    # --- Apply dataset filter ---
    if dataset_mode == 'Combined':
        # Actuals take precedence; budget fills gaps per (Date, Description)
        actuals = df[df['DataSet'] == 'Actual'].copy()
        budget = df[df['DataSet'] == 'Budget'].copy()
        actual_keys = set(zip(actuals['Date'], actuals['Description']))
        budget_fill = budget[
            ~budget.apply(lambda r: (r['Date'], r['Description']) in actual_keys, axis=1)
        ]
        pool = pd.concat([actuals, budget_fill], ignore_index=True)
        pool['DataSet'] = pool['DataSet'].astype(str)  # drop categorical for mixed labels
    else:
        pool = df[df['DataSet'] == dataset_mode].copy()

    # --- Cascading multi-select filters ---
    # Date range applied first, then filters cascade top-to-bottom.
    pool = pool[
        ((pool['Year'] > start_year) |
         ((pool['Year'] == start_year) & (pool['Month'] >= start_month))) &
        ((pool['Year'] < end_year) |
         ((pool['Year'] == end_year) & (pool['Month'] <= end_month)))
    ]

    col1, col2 = st.columns(2)
    with col1:
        sel_descriptions = st.multiselect("Description",
                                           sorted(pool['Description'].dropna().unique().tolist()),
                                           key="q_desc")
    if sel_descriptions:
        pool = pool[pool['Description'].isin(sel_descriptions)]

    with col2:
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

    # --- Aggregate ---
    # Monthly: group by Year, Month and all category columns
    # Annual: group by FY and all category columns (NGER standard)
    category_cols = ['Description', 'Department', 'CostCentre',
                     'NGAFuel', 'UOM', 'State']
    # Include DataSet in groupby only when showing a single dataset
    # Combined mode merges actuals + budget fill, so splitting by DataSet
    # would undo the merge
    if dataset_mode != 'Combined':
        category_cols = ['DataSet'] + category_cols
    category_cols = [c for c in category_cols if c in filtered.columns]

    if resolution == 'Monthly':
        group_cols = ['Year', 'Month'] + category_cols
    else:
        group_cols = ['FY'] + category_cols

    agg_dict = {
        'Quantity': ('Quantity', 'sum'),
        'Scope1_tCO2e': ('Scope1_tCO2e', 'sum'),
        'Scope2_tCO2e': ('Scope2_tCO2e', 'sum'),
        'Scope3_tCO2e': ('Scope3_tCO2e', 'sum'),
    }
    if 'Energy_GJ' in filtered.columns:
        agg_dict['Energy_GJ'] = ('Energy_GJ', 'sum')

    agg = filtered.groupby(group_cols, observed=True, dropna=False).agg(**agg_dict).reset_index()

    # For NGA factor lookup we need an FY reference regardless of resolution
    if resolution == 'Monthly':
        # Derive FY from Year+Month for factor lookup (July+ = next FY)
        agg['_fy_lookup'] = agg.apply(
            lambda r: int(r['Year']) + 1 if int(r['Month']) >= 7 else int(r['Year']), axis=1
        )
    else:
        agg['_fy_lookup'] = agg['FY'].astype(int)

    # --- Enrich with NGA factors ---
    ef_s1, ef_s2, ef_s3, ef_energy, nga_years = [], [], [], [], []

    for _, row in agg.iterrows():
        fy = int(row['_fy_lookup'])
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

    # Drop the temp lookup column
    agg = agg.drop(columns=['_fy_lookup'])

    # --- Column ordering ---
    if resolution == 'Monthly':
        lead_cols = ['Year', 'Month']
        sort_cols = ['Year', 'Month', 'Description']
    else:
        lead_cols = ['FY']
        sort_cols = ['FY', 'Description']

    trail_cols = ['DataSet', 'Description', 'Department', 'CostCentre',
                  'NGAFuel', 'UOM', 'State', 'NGA_Year',
                  'Quantity', 'EF_S1_kgCO2e', 'EF_S2_kgCO2e', 'EF_S3_kgCO2e', 'Energy_per_unit',
                  'Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e', 'Total_tCO2e', 'Energy_GJ']
    col_order = lead_cols + [c for c in trail_cols if c in agg.columns]
    agg = agg[col_order].sort_values(
        [c for c in sort_cols if c in agg.columns]
    ).reset_index(drop=True)

    # Summary metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rows", f"{len(agg):,}")
    c2.metric("Scope 1", f"{agg['Scope1_tCO2e'].sum():,.0f} t")
    c3.metric("Scope 2", f"{agg['Scope2_tCO2e'].sum():,.0f} t")
    c4.metric("Scope 3", f"{agg['Scope3_tCO2e'].sum():,.0f} t")
    c5.metric("Total", f"{agg['Total_tCO2e'].sum():,.0f} t")

    # Format and display
    display = _format_emissions_table(agg, resolution)
    st.dataframe(display, hide_index=True, width='stretch', height=600)

    st.download_button(
        label="Download filtered data",
        data=display.to_csv(index=False),
        file_name="emissions_query_export.csv",
        mime="text/csv",
        key="dl_query_export",
    )




def _format_emissions_table(agg, resolution='Annual'):
    """Round and rename columns for display. Values stay numeric for clean Excel import."""
    display = agg.copy()

    # Monthly resolution: convert month number to short name
    if resolution == 'Monthly' and 'Month' in display.columns:
        import calendar
        display['Month'] = display['Month'].apply(
            lambda m: calendar.month_abbr[int(m)] if pd.notna(m) and 1 <= int(m) <= 12 else ''
        )
    round_map = {
        'Quantity': 1, 'EF_S1_kgCO2e': 4, 'EF_S2_kgCO2e': 4,
        'EF_S3_kgCO2e': 4, 'Energy_per_unit': 4,
        'Scope1_tCO2e': 1, 'Scope2_tCO2e': 1, 'Scope3_tCO2e': 1,
        'Total_tCO2e': 1, 'Energy_GJ': 1,
    }
    for c, d in round_map.items():
        if c in display.columns:
            # Upcast float32 -> float64 before rounding (float32 round artefacts)
            display[c] = display[c].astype('float64').round(d)

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



# =====================================================================
# SECTION 2: SMC LEDGER
# =====================================================================

def _render_smc_ledger(precomputed, carbon_credit_price, credit_escalation):
    """SMC ledger: forecast, actual transactions and combined view.

    Uses pre-computed annual projection \u2014 no build_projection call.
    """

    st.caption("Safeguard Mechanism Credits \u2014 forecast, actual transactions and combined position.")

    credit_start_fy = date_to_fy(CREDIT_START_DATE)

    view = st.radio("View", ["Combined", "Forecast Only", "Transactions Only"],
                     horizontal=True, key="smc_view")

    # \u2500\u2500 Pre-computed annual FY projection \u2500\u2500
    annual = precomputed.annual_fy.copy()

    # Raw forecast (before transactions)
    forecast_raw = annual.copy()
    if 'SMC_Monthly' in forecast_raw.columns and 'SMC_Annual' not in forecast_raw.columns:
        forecast_raw['SMC_Annual'] = forecast_raw['SMC_Monthly']
    forecast_raw['SMC_Cumulative'] = forecast_raw['SMC_Annual'].cumsum()
    forecast_raw = smc_credit_value_analysis(
        forecast_raw, credit_start_fy, carbon_credit_price, credit_escalation)

    # \u2500\u2500 Load transactions \u2500\u2500
    smc_txns = precomputed.smc_transactions

    # \u2500\u2500 Combined (forecast + transactions) \u2500\u2500
    combined = annual.copy()
    if 'SMC_Monthly' in combined.columns and 'SMC_Annual' not in combined.columns:
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