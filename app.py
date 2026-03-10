"""
app.py
Ravenswood Gold Mine - Emissions Tracking Dashboard
Last Updated: 2026-02-05 21:08 AEDT
"""
# NOTE FOR CLAUDE: This file contains emojis. Use binary-safe editing (rb/wb) to prevent corruption.

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

# Import configuration (date constants only)
from config import (
    FSEI_ROM,
    FSEI_ELEC,
    CREDIT_START_DATE,
    DEFAULT_START_DATE,
    DEFAULT_END_MINING_DATE,
    DEFAULT_END_PROCESSING_DATE,
    DEFAULT_END_REHABILITATION_DATE,
    DEFAULT_CARBON_CREDIT_PRICE,
    DEFAULT_CREDIT_ESCALATION,
    DEFAULT_TAX_START_DATE,
    DEFAULT_TAX_RATE,
    DEFAULT_TAX_ESCALATION,
    DEFAULT_DISPLAY_YEAR,
    DEFAULT_YEAR_TYPE,
    DEFAULT_GRID_CONNECTION_DATE,
    DECLINE_RATE_PHASE2,
    DECLINE_RATE_PHASE1,
    SAFEGUARD_THRESHOLD
)
from calc_calendar import date_to_fy, date_to_cy
from loader_data import load_all_data
from projections import build_projection

# Import tab modules
from tab1_ghg import render_ghg_tab
from tab2_safeguard import render_safeguard_tab
from tab3_carbon_tax import render_carbon_tax_tab
from tab4_nger import render_nger_tab
from tab5_query import render_query_tab

# PAGE CONFIG
st.set_page_config(
    page_title="Ravenswood Gold - Safeguard Mechanism Model",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Add print styles and button using components for better JavaScript support


# PRINT FUNCTIONALITY
st.markdown("""
<style>
@media print {
    /* Hide Streamlit UI */
    header, footer, [data-testid="stSidebar"], 
    [data-testid="stToolbar"], [data-testid="stDecoration"],
    .stDeployButton, iframe {
        display: none !important;
    }
    
    /* Page setup */
    @page {
        size: A4 landscape;
        margin: 1.5cm;
    }
    
    /* Content */
    .main .block-container {
        max-width: 100% !important;
        padding: 0.5rem !important;
    }
    
    /* Charts - no breaks, full width */
    .stPlotlyChart, .js-plotly-plot, .plot-container {
        page-break-inside: avoid !important;
        width: 100% !important;
        max-width: 100% !important;
    }
    
    /* Tables */
    .dataframe, table {
        page-break-inside: avoid !important;
        font-size: 9pt !important;
    }
    
    /* Headings */
    h1, h2, h3 {
        page-break-after: avoid !important;
    }
}
</style>
""", unsafe_allow_html=True)

# SIDEBAR SPACING
st.markdown("""
<style>
/* Tighten sidebar spacing */
[data-testid="stSidebar"] {
    padding-top: 2rem;
}

[data-testid="stSidebar"] .block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}

[data-testid="stSidebar"] .element-container {
    margin-bottom: 0.5rem;
}

[data-testid="stSidebar"] .stExpander {
    margin-bottom: 0.5rem;
    margin-top: 0.5rem;
}

[data-testid="stSidebar"] h2 {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
}

[data-testid="stSidebar"] .stMarkdown p {
    margin-bottom: 0.5rem;
}

[data-testid="stSidebar"] hr {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

# TITLE
st.title("🏭 Ravenswood Gold Mine - Safeguard Mechanism Model")
st.caption("Emissions tracking and Safeguard Mechanism compliance projections")

# DATA LOADING
@st.cache_data(ttl=3600, show_spinner="Loading emissions data...")
def load_data_cached():
    """Load unified data with caching"""
    return load_all_data()

# Check if consolidated CSV exists
csv_path = Path('consolidated_emissions_data.csv')
if not csv_path.exists():
    st.error("Missing required file: consolidated_emissions_data.csv")
    st.info("Please ensure the data file is in the same directory as this script.")
    st.stop()

# Load unified data
df = load_data_cached()

with st.sidebar:
    st.header("Configuration")

    # Key Constants (read-only, top of sidebar)
    with st.expander("Key Constants", expanded=True):
        _grid_str = DEFAULT_GRID_CONNECTION_DATE.strftime('%d %b %Y')
        _em_str = DEFAULT_END_MINING_DATE.strftime('%d %b %Y')
        _ep_str = DEFAULT_END_PROCESSING_DATE.strftime('%d %b %Y')
        _er_str = DEFAULT_END_REHABILITATION_DATE.strftime('%d %b %Y')
        _p1_pct = f"{DECLINE_RATE_PHASE1*100:.1f}"
        _p2_pct = f"{DECLINE_RATE_PHASE2*100:.3f}"
        _threshold = f"{SAFEGUARD_THRESHOLD:,}"
        st.markdown(
            "| Parameter | Value |\n"
            "|---|---|\n"
            f"| **FSEI ROM** | {FSEI_ROM:.4f} tCO2-e/t |\n"
            f"| **FSEI Electricity** | {FSEI_ELEC:.4f} tCO2-e/MWh |\n"
            f"| **Grid Connection** | {_grid_str} |\n"
            f"| **End Mining** | {_em_str} |\n"
            f"| **End Processing** | {_ep_str} |\n"
            f"| **End Rehabilitation** | {_er_str} |\n"
            f"| **Phase 1 Decline** | {_p1_pct}% p.a. (FY2024\u2013FY2030) |\n"
            f"| **Phase 2 Decline** | {_p2_pct}% p.a. (FY2031+) |\n"
            f"| **Safeguard Threshold** | {_threshold} tCO2-e |"
        )
        st.caption("CER approved Oct 2024.  All parameters from config.py.")

    st.markdown("---")

    # Display Year Selection
    with st.expander("Display Year", expanded=True):
        if 'display_year' not in st.session_state:
            st.session_state.display_year = DEFAULT_DISPLAY_YEAR

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

    # Year Type Selection (FY or CY)
    with st.expander("Year Type", expanded=True):
        # Build year_type_options with default first
        if DEFAULT_YEAR_TYPE == 'CY':
            year_type_options = {
                'CY': 'Calendar Year (Jan-Dec)',
                'FY': 'Financial Year (July-June)'
            }
        else:
            year_type_options = {
                'FY': 'Financial Year (July-June)',
                'CY': 'Calendar Year (Jan-Dec)'
            }

        selected_year_type = st.selectbox(
            "Year Boundary",
            options=list(year_type_options.keys()),
            format_func=lambda x: year_type_options[x],
            key='year_type',
            help="Financial Year for NGER compliance (July-June) or Calendar Year for financial reporting (Jan-Dec). Tab 2 (Safeguard) always uses Financial Year per legislation."
        )

        st.caption("SMC compliance calculations always use FY per legislation")

    # Constants locked to config (no user override)
    fsei_rom = FSEI_ROM
    fsei_elec = FSEI_ELEC
    decline_rate_phase2 = DECLINE_RATE_PHASE2

    # Phase dates locked to config constants (baked into CSV)
    start_date = DEFAULT_START_DATE
    end_date = DEFAULT_END_REHABILITATION_DATE
    end_mining_date = DEFAULT_END_MINING_DATE
    end_processing_date = DEFAULT_END_PROCESSING_DATE
    end_rehabilitation_date = DEFAULT_END_REHABILITATION_DATE


        # Carbon Credit Market
    with st.expander("Carbon Credit Market", expanded=False):
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


    # Carbon Tax Settings
    with st.expander("Carbon Tax Scenario", expanded=False):
        tax_start_fy = st.number_input(
            "Tax Start FY",
            value=date_to_fy(DEFAULT_TAX_START_DATE),
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
            20.0,
            DEFAULT_TAX_ESCALATION * 100,
            step=0.5
        ) / 100

        # Tax start date: 1 July of the selected FY (tax operates on FY)
        tax_start_date = datetime(tax_start_fy - 1, 7, 1)

        include_scope2 = st.checkbox(
            "Include Scope 2 electricity pass-through (sensitivity case)",
            value=False,
            help="Base case: industry-only tax, no electricity pass-through. "
                 "Sensitivity case: carbon tax applied to electricity generators, "
                 "cost passed through in wholesale prices via NGA Scope 2 emission factor."
        )



# TABS
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Total GHG Emissions",
    "Safeguard Mechanism",
    "Carbon Tax Analysis",
    "NGER Factors",
    "Data Query"
])


# RENDER TABS
with tab1:
    render_ghg_tab(
        df,
        fsei_rom, fsei_elec,
        start_date, end_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        decline_rate_phase2,
        selected_year_type
    )

with tab2:
    render_safeguard_tab(
        df,
        fsei_rom, fsei_elec,
        start_date, end_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        carbon_credit_price, credit_escalation,
        CREDIT_START_DATE,
        decline_rate_phase2,
        selected_year_type
    )

with tab3:
    render_carbon_tax_tab(
        df,
        fsei_rom, fsei_elec,
        start_date, end_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        carbon_credit_price, credit_escalation,
        tax_start_date, tax_rate, tax_escalation,
        CREDIT_START_DATE,
        decline_rate_phase2,
        selected_year_type,
        include_scope2=include_scope2
    )

with tab4:
    render_nger_tab()

with tab5:
    render_query_tab(
        df,
        fsei_rom=fsei_rom, fsei_elec=fsei_elec,
        start_date=start_date, end_date=end_date,
        end_mining_date=end_mining_date,
        end_processing_date=end_processing_date,
        end_rehabilitation_date=end_rehabilitation_date,
        carbon_credit_price=carbon_credit_price,
        credit_escalation=credit_escalation,
        credit_start_date=CREDIT_START_DATE,
        decline_rate_phase2=decline_rate_phase2
    )

# FOOTER
st.markdown("---")
st.caption("Safeguard Mechanism Compliance Model for Ravenswood Gold Mine")