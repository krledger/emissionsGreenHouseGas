"""
app.py
Streamlit UI for Ravenswood Gold Safeguard Mechanism Model
Last updated: 2026-01-27 17:00 AEST

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from pathlib import Path

# Import configuration and data loaders
from config import (
    DEFAULT_PATHS,
    FSEI_ROM, FSEI_ELEC,
    DECLINE_RATE, DECLINE_FROM, DECLINE_TO,
    DEFAULT_START_FY,
    DEFAULT_END_MINING_FY,
    DEFAULT_END_PROCESSING_FY,
    DEFAULT_END_REHABILITATION_FY,
    DEFAULT_CARBON_CREDIT_PRICE,
    DEFAULT_CREDIT_ESCALATION,
    DEFAULT_TAX_START_FY,
    DEFAULT_TAX_RATE,
    DEFAULT_TAX_ESCALATION,
    DEFAULT_GRID_CONNECTION_FY,
    DEFAULT_FY_START_MONTH,
    get_fy_description,
    get_fy_end_month,
    get_fy_month_name
)
from data_loader import load_all_data

# Import tab modules
from tab1_ghg import render_ghg_tab
from tab2_safeguard import render_safeguard_tab
from tab3_carbon_tax import render_carbon_tax_tab
from tab4_nger import render_nger_tab

# PAGE CONFIG
st.set_page_config(
    page_title="Ravenswood Gold - Safeguard Mechanism Model",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# TITLE
st.title("🏭 Ravenswood Gold Mine - Safeguard Mechanism Model")
st.caption("Emissions tracking and Safeguard Mechanism compliance projections")

# SIDEBAR - Configuration
st.sidebar.header("⚙️ Configuration")
# Fiscal Year Configuration
st.sidebar.subheader("📆 Fiscal Year")

# Month options
month_options = {
    1: "January (Calendar Year)",
    7: "July (NGER Financial Year)"
}

# Initialize session state for FY start month
if 'fy_start_month' not in st.session_state:
    st.session_state.fy_start_month = DEFAULT_FY_START_MONTH

# Selectbox for FY start month
selected_month = st.sidebar.selectbox(
    "FY Start Month",
    options=list(month_options.keys()),
    format_func=lambda x: month_options[x],
    index=list(month_options.keys()).index(st.session_state.fy_start_month) if st.session_state.fy_start_month in month_options else 0,
    help="Select the first month of your fiscal year. End month is automatically 12 months later."
)

# Update session state
st.session_state.fy_start_month = selected_month

# Display fiscal year description
fy_desc = get_fy_description(selected_month)
end_month = get_fy_end_month(selected_month)


st.sidebar.caption("⚠️ Safeguard tab always uses NGER FY (July—June)")
st.sidebar.markdown("---")

# Baseline Emission Intensity (Dual FSEI)
st.sidebar.subheader("Baseline Emission Intensity")
fsei_rom = st.sidebar.number_input(
    "FSEI ROM (tCO₂-e/t ore)",
    value=float(FSEI_ROM),
    format="%.4f",
    help="Facility Specific Emission Intensity for ROM production"
)
fsei_elec = st.sidebar.number_input(
    "FSEI Electricity (tCO₂-e/MWh)",
    value=float(FSEI_ELEC),
    format="%.4f",
    help="Facility Specific Emission Intensity for on-site diesel generation"
)
st.sidebar.caption(f"Baseline = (ROM × {fsei_rom:.4f}) + (Site MWh × {fsei_elec:.4f})")
st.sidebar.caption(f"Declining at {DECLINE_RATE * 100:.1f}% p.a. from FY{DECLINE_FROM}—FY{DECLINE_TO}")

# Projection Period
st.sidebar.subheader("Projection Period")
start_fy = st.sidebar.number_input(
    "Start FY",
    value=DEFAULT_START_FY,
    min_value=2020,
    max_value=2030,
    step=1,
    help="First year for projections"
)

end_mining_fy = st.sidebar.number_input(
    "End Mining FY",
    value=DEFAULT_END_MINING_FY,
    min_value=2025,
    max_value=2055,
    step=1,
    help="Year when ore extraction ceases"
)

end_processing_fy = st.sidebar.number_input(
    "End Processing FY",
    value=DEFAULT_END_PROCESSING_FY,
    min_value=2025,
    max_value=2055,
    step=1,
    help="Year when stockpile processing completes"
)

end_rehabilitation_fy = st.sidebar.number_input(
    "End Rehabilitation FY",
    value=DEFAULT_END_REHABILITATION_FY,
    min_value=2025,
    max_value=2060,
    step=1,
    help="Year when site closure completes (also End FY for projections)"
)

# End FY is the rehabilitation end year
end_fy = end_rehabilitation_fy



# Carbon Credit Market
st.sidebar.subheader("Carbon Credit Market")
carbon_credit_price = st.sidebar.number_input(
    "SMC Credit Price ($/tCO₂-e)",
    value=float(DEFAULT_CARBON_CREDIT_PRICE),
    min_value=0.0,
    step=5.0,
    help="Market price for Safeguard Mechanism Credits"
)

credit_escalation = st.sidebar.slider(
    "Credit Price Escalation (%/year)",
    0.0,
    15.0,
    DEFAULT_CREDIT_ESCALATION * 100,
    step=0.5,
    help="Annual increase in carbon credit prices"
) / 100



# Carbon Tax Settings
st.sidebar.subheader("Carbon Tax Scenario")
tax_start_fy = st.sidebar.number_input(
    "Tax Start FY",
    value=DEFAULT_TAX_START_FY,
    min_value=2025,
    max_value=2050,
    step=1,
    help="Year when carbon tax is introduced"
)

tax_rate = st.sidebar.number_input(
    "Initial Tax Rate ($/tCO₂-e)",
    value=float(DEFAULT_TAX_RATE),
    min_value=0.0,
    step=5.0,
    help="Carbon tax rate at introduction"
)

tax_escalation = st.sidebar.slider(
    "Tax Rate Escalation (%/year)",
    0.0,
    10.0,
    DEFAULT_TAX_ESCALATION * 100,
    step=0.5,
    help="Annual increase in carbon tax rate"
) / 100



# Grid Connection
st.sidebar.subheader("Grid Connection")
grid_connected_fy = st.sidebar.number_input(
    "Grid Connection FY",
    value=DEFAULT_GRID_CONNECTION_FY,
    min_value=2025,
    max_value=2050,
    step=1,
    help="Year when grid electricity becomes available (diesel generation stops)"
)



# TABS - Main Navigation
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Total GHG Emissions",
    "🛡️ Safeguard Mechanism",
    "💰 Carbon Tax Analysis",
    "📋 NGER Factors"
])

# DATA LOADING (runs once for all tabs)

# Check files exist
missing_files = []
for name, path in DEFAULT_PATHS.items():
    if name == 'nga':
        # For NGA files, check if ANY year file exists (2021-2025)
        nga_found = False
        for year in range(2021, 2026):
            # Try with hyphens first
            nga_path = f'national-greenhouse-account-factors-{year}.xlsx'
            if Path(nga_path).exists():
                nga_found = True
                break
            # Try without hyphens
            nga_path = f'nationalgreenhouseaccountfactors{year}.xlsx'
            if Path(nga_path).exists():
                nga_found = True
                break
        if not nga_found:
            missing_files.append('national-greenhouse-account-factors-YYYY.xlsx (any year 2021-2025)')
    else:
        if not Path(path).exists():
            missing_files.append(path)

if missing_files:
    st.error(f"Missing required files: {', '.join(missing_files)}")
    st.info("Please ensure all data files are in the same directory as this script.")
    st.stop()

# Load all data
with st.spinner('Loading data...'):
    rom_df, energy_df, nga_factors = load_all_data(DEFAULT_PATHS, st.session_state.fy_start_month)

    # Load separate NGER FY data for Safeguard tab (always July-June)
    from config import NGER_FY_START_MONTH
    if st.session_state.fy_start_month != NGER_FY_START_MONTH:
        rom_df_nger, energy_df_nger, _ = load_all_data(DEFAULT_PATHS, NGER_FY_START_MONTH)
    else:
        rom_df_nger = rom_df
        energy_df_nger = energy_df

# Log viewer function with modal dialog
@st.dialog("📋 Data Loading Log", width="large")
def show_log_viewer():
    """Display data loading log in a modal dialog"""
    import os
    log_path = os.path.abspath('data_loading.log')

    try:
        with open('data_loading.log', 'r', encoding='utf-8') as f:
            log_contents = f.read()

        if log_contents:
            lines = log_contents.split('\n')

            # Show statistics
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Lines", len(lines))
            with col2:
                error_count = sum(1 for line in lines if 'ERROR' in line)
                st.metric("Errors", error_count, delta=None if error_count == 0 else "Issues found", delta_color="inverse")

            st.divider()

            # Show full log in scrollable text area
            st.text_area(
                "Log Contents (scroll to view all)",
                value=log_contents,
                height=500,
                disabled=True,
                label_visibility="collapsed"
            )

            st.caption(f"📁 Full path: `{log_path}`")

        else:
            st.info("Log file is empty. No data has been loaded yet.")

    except FileNotFoundError:
        st.warning("⚠️ Log file not found. It will be created on the next data load.")
    except Exception as e:
        st.error(f"❌ Error reading log: {str(e)}")

    if st.button("Close", type="primary", use_container_width=True):
        st.rerun()

# Add log viewer button in sidebar
with st.sidebar:
    st.divider()
    if st.button("📋 View Data Loading Log", use_container_width=True):
        show_log_viewer()

# Render each tab
with tab1:
    render_ghg_tab(rom_df, energy_df, nga_factors, fsei_rom, fsei_elec,
                   start_fy, end_fy, grid_connected_fy,
                   end_mining_fy, end_processing_fy, end_rehabilitation_fy)

with tab2:
    render_safeguard_tab(rom_df_nger, energy_df_nger, nga_factors, fsei_rom, fsei_elec,
                        start_fy, end_fy, grid_connected_fy,
                        end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                        carbon_credit_price)

with tab3:
    render_carbon_tax_tab(rom_df, energy_df, nga_factors, fsei_rom, fsei_elec,
                         start_fy, end_fy, grid_connected_fy,
                         end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                         carbon_credit_price, credit_escalation,
                         tax_start_fy, tax_rate, tax_escalation)

with tab4:
    render_nger_tab()

# FOOTER
st.markdown("---")
st.caption("Ravenswood Gold Mine | Safeguard Mechanism Model | Last updated: 2026-01-23")