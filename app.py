"""
app.py
Ravenswood Gold Mine - Emissions Tracking Dashboard
Last Updated: 2026-03-23

ARCHITECTURE (v2 — precompute on load):
    1. load_all_data()          → raw monthly DataFrame (cached)
    2. precompute_all()         → all derived data computed ONCE (cached)
    3. Tabs receive PrecomputedData and only filter/render
    4. Sidebar-dependent calcs (carbon tax, SMC valuation) run lightweight
       functions on pre-aggregated annual data — not raw data
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
from calc_calendar import date_to_fy, date_to_cy, year_to_date_range, label_from_dates, detect_year_type
from loader_data import load_all_data
from calc_precompute import precompute_all, get_annual

# Import tab modules
from tab1_ghg import render_ghg_tab
from tab2_safeguard import render_safeguard_tab
from tab3_carbon_tax import render_carbon_tax_tab
from tab4_nger import render_nger_tab
from tab5_query import render_query_tab
from tab6_gri import render_gri_tab

# PAGE CONFIG
st.set_page_config(
    page_title="Ravenswood Gold - Safeguard Mechanism Model",
    page_icon="\U0001f3ed",
    layout="wide",
    initial_sidebar_state="expanded"
)


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

# ═══════════════════════════════════════════════════════════════════════
# ACCESS CONTROL
# ======================================================================

import hashlib
import hmac

try:
    _ACCESS_HASH = st.secrets["auth"]["access_hash"]
except (KeyError, FileNotFoundError):
    _ACCESS_HASH = ""  # No secrets configured - auth will always fail
_MAX_AUTH_ATTEMPTS = 5

def _check_passphrase(phrase):
    candidate = hashlib.sha256(phrase.strip().encode()).hexdigest()
    return hmac.compare_digest(candidate, _ACCESS_HASH)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_attempts" not in st.session_state:
    st.session_state.auth_attempts = 0

if not st.session_state.authenticated:
    st.title("\U0001f512 Ravenswood Gold Mine")
    st.caption("Enter the passphrase to access the dashboard")

    if st.session_state.auth_attempts >= _MAX_AUTH_ATTEMPTS:
        st.error("Too many failed attempts. Restart the application.")
        st.stop()

    passphrase = st.text_input("Passphrase", type="password",
                               placeholder="Enter passphrase...")
    if passphrase:
        if _check_passphrase(passphrase):
            st.session_state.authenticated = True
            st.session_state.auth_attempts = 0
            st.session_state.data_passphrase = passphrase.strip()
            st.rerun()
        else:
            st.session_state.auth_attempts += 1
            remaining = _MAX_AUTH_ATTEMPTS - st.session_state.auth_attempts
            if remaining > 0:
                st.error(f"Incorrect passphrase. {remaining} attempts remaining.")
            else:
                st.error("Too many failed attempts. Restart the application.")
    st.stop()


# TITLE
st.title("\U0001f3ed Ravenswood Gold Mine - Safeguard Mechanism Model")
st.caption("Emissions tracking and Safeguard Mechanism compliance projections")

# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING + PRECOMPUTATION (cached — runs once per session/hour)
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner="Loading emissions data...")
def load_data_cached(_passphrase):
    """Load unified data with caching.

    _passphrase is underscore-prefixed so Streamlit does not hash it.
    """
    return load_all_data(passphrase=_passphrase)

@st.cache_resource(ttl=3600, show_spinner="Pre-computing projections...")
def precompute_cached(_df, _passphrase):
    """Pre-compute all derived data.

    _df and _passphrase are underscore-prefixed to tell Streamlit
    not to hash them.
    """
    return precompute_all(
        _df,
        fsei_rom=FSEI_ROM,
        fsei_elec=FSEI_ELEC,
        start_date=DEFAULT_START_DATE,
        end_date=DEFAULT_END_REHABILITATION_DATE,
        end_mining_date=DEFAULT_END_MINING_DATE,
        end_processing_date=DEFAULT_END_PROCESSING_DATE,
        end_rehabilitation_date=DEFAULT_END_REHABILITATION_DATE,
        credit_start_date=CREDIT_START_DATE,
        decline_rate_phase2=DECLINE_RATE_PHASE2,
        passphrase=_passphrase,
    )


# Check if source data files exist (plain CSV or encrypted .enc)
_data_dir = Path(__file__).resolve().parent / 'Data'
_actual_path = _data_dir / 'operations_metrics_actual.csv'
_budget_path = _data_dir / 'operations_metrics_budget.csv'
_missing = [
    p.name for p in [_actual_path, _budget_path]
    if not p.exists() and not Path(str(p) + '.enc').exists()
]
if _missing:
    st.error(f"Missing required file(s): {', '.join(_missing)}")
    st.info("Please ensure the data files are in the same directory as this script.")
    st.stop()

# Load unified data
df = load_data_cached(st.session_state.get('data_passphrase'))

# Pre-compute ALL derived data (projections, annual aggregations, source tables)
precomputed = precompute_cached(df, st.session_state.get('data_passphrase'))


# ═══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════

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

    # Reporting Period Selection
    with st.expander("Reporting Period", expanded=True):
        if 'display_year' not in st.session_state:
            st.session_state.display_year = DEFAULT_DISPLAY_YEAR

        # Period type selector
        _period_type = st.radio(
            "Period type",
            ['CY', 'FY'],
            index=0 if DEFAULT_YEAR_TYPE == 'CY' else 1,
            format_func=lambda x: 'Calendar Year (Jan-Dec)' if x == 'CY' else 'Financial Year (Jul-Jun)',
            horizontal=True,
            key='period_type'
        )

        display_year = st.number_input(
            "Year",
            min_value=2020,
            max_value=2045,
            value=st.session_state.display_year,
            step=1,
            help="Select year for charts and summaries"
        )
        st.session_state.display_year = display_year

        # Compute dates from selection
        _start_date, _end_date = year_to_date_range(display_year, _period_type)
        _period_label = label_from_dates(_start_date, _end_date)

        st.session_state.start_date = _start_date
        st.session_state.end_date = _end_date
        st.session_state.period_label = _period_label

        st.caption(f"Period: {_start_date.strftime('%d %b %Y')} to {(_end_date - pd.Timedelta(days=1)).strftime('%d %b %Y')}")
        st.caption("Safeguard tab always uses FY per legislation")


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



# Frame selection - decide once, pass down
# Data frame: user-selected period (CY or FY) for tab1, tab3, tab4, tab6
display_start = st.session_state.get('start_date')
display_end = st.session_state.get('end_date')
period_label = st.session_state.get('period_label', '')
data_frame = get_annual(precomputed, start_date=display_start)

# NGER frame: always FY for Safeguard (tab2)
nger_frame = precomputed.annual_fy.copy()


# ═══════════════════════════════════════════════════════════════════════
# TABS — receive pre-computed data, filter and render only
# ═══════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Total GHG Emissions",
    "Safeguard Mechanism",
    "GRI 14 Reporting",
    "Carbon Tax Analysis",
    "NGER Factors",
    "Data Query"
])


# RENDER TABS
with tab1:
    render_ghg_tab(
        df, precomputed, data_frame,
        start_date=display_start, end_date=display_end,
        period_label=period_label,
        end_mining_date=end_mining_date,
        end_processing_date=end_processing_date,
        end_rehabilitation_date=end_rehabilitation_date,
    )

with tab2:
    render_safeguard_tab(
        df, precomputed, nger_frame,
        fsei_rom, fsei_elec,
        carbon_credit_price, credit_escalation,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        display_year=display_year,
    )

with tab3:
    render_gri_tab(df, precomputed, data_frame,
                   start_date=display_start, end_date=display_end,
                   period_label=period_label)

with tab4:
    render_carbon_tax_tab(
        precomputed, data_frame,
        tax_start_fy, tax_rate, tax_escalation,
        include_scope2,
        period_label=period_label,
        end_mining_date=end_mining_date,
        end_processing_date=end_processing_date,
        end_rehabilitation_date=end_rehabilitation_date,
    )

with tab5:
    render_nger_tab()

with tab6:
    render_query_tab(
        df, precomputed, nger_frame,
        carbon_credit_price=carbon_credit_price,
        credit_escalation=credit_escalation,
    )

# FOOTER
st.markdown("---")
st.caption("Safeguard Mechanism Compliance Model for Ravenswood Gold Mine")