"""
app.py
Streamlit UI for Ravenswood Gold Safeguard Mechanism Model
Last updated: 2026-02-02 02:00 AEST

Simplified architecture with unified data loading
Run with: streamlit run app.py
"""

import streamlit as st
from pathlib import Path

# Import configuration
from config import (
    FSEI_ROM,
    FSEI_ELEC,
    CREDIT_START_FY,
    DEFAULT_START_FY,
    DEFAULT_END_MINING_FY,
    DEFAULT_END_PROCESSING_FY,
    DEFAULT_END_REHABILITATION_FY,
    DEFAULT_CARBON_CREDIT_PRICE,
    DEFAULT_CREDIT_ESCALATION,
    DEFAULT_TAX_START_FY,
    DEFAULT_TAX_RATE,
    DEFAULT_TAX_ESCALATION,
    DEFAULT_GRID_CONNECTION_FY
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
    page_icon="🏭",  # 🏭
    layout="wide",
    initial_sidebar_state="expanded"
)

# TITLE
st.title("🏭 Ravenswood Gold Mine - Safeguard Mechanism Model")
st.caption("Emissions tracking and Safeguard Mechanism compliance projections")

# SIDEBAR - Configuration
with st.sidebar:
    st.header("⚙️ Configuration")  # ⚙️

    # Display Year Selection
    st.subheader("📅 Display Year")  # 📅
    if 'display_year' not in st.session_state:
        st.session_state.display_year = 2025

    display_year = st.number_input(
        "Year to Display",
        min_value=2020,
        max_value=2035,
        value=st.session_state.display_year,
        step=1,
        help="Select the financial year to display in charts and summaries"
    )
    st.session_state.display_year = display_year

    st.markdown("---")

    # Data Set Selection
    st.subheader("📊 Data Set")
    source_options = {
        'Base': 'Base',
        'NPI-NGERS': 'NPI-NGERS',
        'All': 'All Data Sets'
    }

    selected_source = st.selectbox(
        "Select Data Set",
        options=list(source_options.keys()),
        format_func=lambda x: source_options[x],
        key='data_source',
        help="Choose which data set to display. 'All Data Sets' shows all datasets"
    )

    st.markdown("---")

    # Baseline Emission Intensity
    st.subheader("⚖️ Baseline Emission Intensity")  # ⚖️
    fsei_rom = st.number_input(
        "FSEI ROM (tCO2-e/t ore)",
        value=float(FSEI_ROM),
        format="%.4f",
        help="Facility Specific Emission Intensity for ROM production"
    )
    st.caption("CER Approved: 0.0177 tCO2-e/t ROM (October 2024)")

    fsei_elec = st.number_input(
        "FSEI Electricity (tCO2-e/MWh)",
        value=float(FSEI_ELEC),
        format="%.4f",
        help="Facility Specific Emission Intensity for on-site electricity generation"
    )
    st.caption("CER Approved: 0.9081 tCO2-e/MWh (October 2024)")

    st.markdown("---")

    # Projection Period
    st.subheader("📈 Projection Period")  # 📈
    start_fy = st.number_input(
        "Start FY",
        value=DEFAULT_START_FY,
        min_value=2020,
        max_value=2030,
        step=1,
        help="First year for projections"
    )

    end_mining_fy = st.number_input(
        "End Mining FY",
        value=DEFAULT_END_MINING_FY,
        min_value=2025,
        max_value=2055,
        step=1,
        help="Year when ore extraction ceases"
    )

    end_processing_fy = st.number_input(
        "End Processing FY",
        value=DEFAULT_END_PROCESSING_FY,
        min_value=2025,
        max_value=2055,
        step=1,
        help="Year when stockpile processing completes"
    )

    end_rehabilitation_fy = st.number_input(
        "End Rehabilitation FY",
        value=DEFAULT_END_REHABILITATION_FY,
        min_value=2025,
        max_value=2060,
        step=1,
        help="Year when site closure completes"
    )

    end_fy = end_rehabilitation_fy

    st.markdown("---")

    # Grid Connection
    st.subheader("⚡ Grid Connection")  # ⚡
    grid_connected_fy = st.number_input(
        "Grid Connection FY",
        value=DEFAULT_GRID_CONNECTION_FY,
        min_value=2025,
        max_value=2050,
        step=1,
        help="Year when grid electricity becomes available"
    )

    st.markdown("---")

    # Carbon Credit Market
    st.subheader("💰 Carbon Credit Market")  # 💰
    carbon_credit_price = st.number_input(
        "SMC Credit Price ($/tCO2-e)",
        value=float(DEFAULT_CARBON_CREDIT_PRICE),
        min_value=0.0,
        step=5.0,
        help="Market price for Safeguard Mechanism Credits"
    )

    credit_escalation = st.slider(
        "Credit Price Escalation (%/year)",
        0.0,
        15.0,
        DEFAULT_CREDIT_ESCALATION * 100,
        step=0.5
    ) / 100

    st.markdown("---")

    # Carbon Tax Settings
    st.subheader("💵 Carbon Tax Scenario")  # 💵
    tax_start_fy = st.number_input(
        "Tax Start FY",
        value=DEFAULT_TAX_START_FY,
        min_value=2025,
        max_value=2050,
        step=1
    )

    tax_rate = st.number_input(
        "Initial Tax Rate ($/tCO2-e)",
        value=float(DEFAULT_TAX_RATE),
        min_value=0.0,
        step=5.0
    )

    tax_escalation = st.slider(
        "Tax Rate Escalation (%/year)",
        0.0,
        10.0,
        DEFAULT_TAX_ESCALATION * 100,
        step=0.5
    ) / 100

# TABS
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Total GHG Emissions",  # 📊
    "🛡️ Safeguard Mechanism",  # 🛡️
    "💰 Carbon Tax Analysis",  # 💰
    "📋 NGER Factors"  # 📋
])

# DATA LOADING
@st.cache_data(ttl=3600, show_spinner="Loading emissions data...")
def load_data_cached():
    """Load unified data with caching"""
    return load_all_data()

# Check if consolidated CSV exists
csv_path = Path('consolidated_emissions_data.csv')
if not csv_path.exists():
    st.error("❌ Missing required file: consolidated_emissions_data.csv")
    st.info("Please ensure the data file is in the same directory as this script.")
    st.stop()

# Load unified data
df = load_data_cached()

# RENDER TABS
with tab1:
    render_ghg_tab(
        df, selected_source,
        fsei_rom, fsei_elec,
        start_fy, end_fy,
        grid_connected_fy,
        end_mining_fy, end_processing_fy, end_rehabilitation_fy
    )

with tab2:
    render_safeguard_tab(
        df, selected_source,
        fsei_rom, fsei_elec,
        start_fy, end_fy,
        grid_connected_fy,
        end_mining_fy, end_processing_fy, end_rehabilitation_fy,
        carbon_credit_price, credit_escalation,
        CREDIT_START_FY
    )

with tab3:
    render_carbon_tax_tab(
        df, selected_source,
        fsei_rom, fsei_elec,
        start_fy, end_fy,
        grid_connected_fy,
        end_mining_fy, end_processing_fy, end_rehabilitation_fy,
        carbon_credit_price, credit_escalation,
        tax_start_fy, tax_rate, tax_escalation,
        CREDIT_START_FY
    )

with tab4:
    render_nger_tab()

# FOOTER
st.markdown("---")
st.caption("© 2024-2026 Ravenswood Gold Mine | Safeguard Mechanism Compliance Model")