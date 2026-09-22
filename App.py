"""
App.py
Ravenswood Gold Mine - Emissions Tracking Dashboard
Last Updated: 2026-03-23

ARCHITECTURE (v3 — reports what the Builder published):
    1. LoaderPublished.load_published_build()  → the published frames
    2. Tabs receive PrecomputedData and only filter/render
    3. Sidebar-dependent scenarios (Safeguard credit price) run
       lightweight functions on the published annual frames

    No inventory is computed here.  The Emissions Data Builder owns the
    method, the assumptions and the registers, and publishes the build; this
    application reads it.  A figure on this screen is a figure somebody
    reviewed and published, and the two programs cannot disagree.
"""
# NOTE FOR CLAUDE: This file contains emojis. Use binary-safe editing (rb/wb) to prevent corruption.

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

# Import configuration (date constants only)
from Config import (
    FSEI_ROM,
    FSEI_ELEC,
    CREDIT_START_DATE,
    DEFAULT_START_DATE,
    DEFAULT_END_MINING_DATE,
    DEFAULT_END_PROCESSING_DATE,
    DEFAULT_END_REHABILITATION_DATE,
    DEFAULT_CARBON_CREDIT_PRICE,
    DEFAULT_CREDIT_ESCALATION,
    DEFAULT_DISPLAY_YEAR,
    DEFAULT_YEAR_TYPE,
    DEFAULT_GRID_CONNECTION_DATE,
    DEFAULT_ACTUALS_TO_DATE,
    DECLINE_RATE_PHASE2,
    DECLINE_RATE_PHASE1,
    SAFEGUARD_THRESHOLD,
    MILESTONE_SOURCE
)
from CalcCalendar import date_to_fy, date_to_cy, year_to_date_range, label_from_dates, detect_year_type
from LoaderPublished import load_published_build, published_at
from CalcPrecompute import get_ghg_annual
from CalcDashboard import filter_options

# Import tab modules
from Tab1Ghg import render_ghg_tab
from Tab2Safeguard import render_safeguard_tab
# Tab4Nger is retired.  Its content, the Safeguard formula, the legislative
# mapping and the National Greenhouse Account factor set, is now carried as
# documents in the About tab.
from Tab5Query import render_query_tab
from Tab6Gri import render_gri_tab
from AboutPanel import render_about
from LoaderNga import nga_editions
from CalcNga import describe_edition_rule

# PAGE CONFIG
st.set_page_config(
    page_title="Ravenswood Gold - Emissions Model",
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

# TITLE
st.title("\U0001f3ed Ravenswood Gold Mine - Emissions Model")
st.caption("GHG emissions for the financial disclosure, calendar year.  "
           "Safeguard Mechanism compliance for the regulatory filing, financial year.")

# ═══════════════════════════════════════════════════════════════════════
# THE PUBLISHED BUILD (read once, cached on what was published)
# ═══════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Reading the published inventory...",
                   max_entries=1)
def read_published(stamp):
    """The published build.  Cached on the publication, so a new one is
    picked up the moment it is published and nothing else changes it."""
    return load_published_build()


def _published_stamp():
    """What identifies the publication on the record."""
    log = published_at()
    return f"{log.get('BuildID', '')}|{log.get('BuiltAt', '')}"


try:
    df, precomputed = read_published(_published_stamp())
except FileNotFoundError as absent:
    st.error(str(absent))
    st.caption("Run the Builder beside this application:")
    st.code("streamlit run AppBuilder.py --server.port 8502", language="bash")
    st.stop()

_build = published_at()
if _build:
    _built = str(_build.get('BuiltAt', '')).replace('T', ' ')[:16]
    _to = str(_build.get('ActualsTo', ''))[:10]
    st.caption(f"Reporting published build {_build.get('BuildID', '?')}, "
               f"published {_built}, recorded to {_to}.")

# ═══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("Filters")
    st.caption("These apply across the model.  The Safeguard and GRI views "
               "are always facility wide and whole of period, because that is "
               "what is reported; a department or scope filter narrows the GHG "
               "view only.")

    st.caption(f"Milestones: {MILESTONE_SOURCE}")

    st.markdown("---")

    # The Builder is a separate application, not a tab.  It owns the
    # emissions methodology, the assumptions, the capital register and the
    # credit ledger, and it publishes the inventory this application reports.
    # This view keeps working whether or not it is running.
    with st.expander("Emissions Data Builder", expanded=False):
        try:
            from ExportEmissionsTable import published_summary
            st.caption(published_summary())
        except Exception:                        # pragma: no cover
            st.caption("No published build")
        st.caption(
            "Builds the inventory, holds the assumptions and the capital "
            "register, and publishes what this application reports.  Run it "
            "beside this one:")
        st.code("streamlit run AppBuilder.py --server.port 8502",
                language="bash")

    st.markdown("---")

    # Reporting basis is fixed.  The GHG view reports calendar years,
    # which is the corporate reporting period, and the Safeguard view reports
    # financial years, which is what the legislation requires.  Only the year
    # is a choice, so there is no control for something that cannot change.
    with st.expander("Reporting year", expanded=True):
        if 'display_year' not in st.session_state:
            st.session_state.display_year = DEFAULT_DISPLAY_YEAR

        _period_type = 'CY'
        st.session_state['period_type'] = _period_type

        display_year = st.number_input(
            "Year",
            min_value=2020,
            max_value=2049,
            value=st.session_state.display_year,
            step=1,
        )
        st.session_state.display_year = display_year

        _start_date, _end_date = year_to_date_range(display_year, _period_type)
        _period_label = label_from_dates(_start_date, _end_date)

        st.session_state.start_date = _start_date
        st.session_state.end_date = _end_date
        st.session_state.period_label = _period_label

        st.caption(f"GHG and GRI report CY{display_year}.  "
                   f"Safeguard reports FY{display_year} per the legislation.")

    # Department and scope.  Options come from the data, so a department
    # that stops reporting leaves the list on its own.  There is no actual
    # against budget choice: the projection fills forward from the last closed
    # month on its own and a reader does not pick between them.
    _options = filter_options(df)

    with st.expander("Narrow the GHG view", expanded=False):
        selected_departments = st.multiselect(
            "Departments", _options['departments'], default=[],
            help="Empty means every department.")
        selected_scopes = st.multiselect(
            "Scopes", ['Scope 1', 'Scope 2', 'Scope 3'], default=[],
            help="Empty means every scope.")

    _department_filter = selected_departments or None
    _scope_filter = selected_scopes or None
    if _department_filter or _scope_filter:
        st.caption("A filter is active.  The GHG view is narrowed; the "
                   "Safeguard and GRI views are not.")


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



# Frame selection - decide once, pass down
display_start = st.session_state.get('start_date')
display_end = st.session_state.get('end_date')
period_label = st.session_state.get('period_label', '')
# Two pipelines, two frames, and no view reads the other's.
# GHG inventory: Scopes 1, 2 and 3 on the GHG Protocol, calendar year.
ghg_frame = get_ghg_annual(precomputed, year_type='CY')

# Regulatory filing: NGER Scope 1, financial year, for the Safeguard view.
nger_frame = precomputed.annual_fy.copy()


# ═══════════════════════════════════════════════════════════════════════
# TABS — receive pre-computed data, filter and render only
# ═══════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab6, tab9 = st.tabs([
    "GHG Emissions",
    "Safeguard Mechanism",
    "GRI 14 Reporting",
    "Data Query",
    "About"
])


# RENDER TABS
with tab1:
    # The GHG view reads the GHG inventory and nothing else: Scopes 1, 2 and
    # 3 on the GHG Protocol, calendar year.  There is no fallback to the NGER
    # frames.  A build published without the GHG frames is reported as such,
    # because an NGER figure shown under a GHG heading is a wrong figure.
    _ghg_missing = [name for name, frame in (
        ('Ghg', precomputed.ghg_df),
        ('GhgAnnualCY', ghg_frame),
        ('GhgMonthly', precomputed.ghg_monthly),
    ) if frame is None or len(frame) == 0]
    if _ghg_missing:
        st.error("The published build does not carry the GHG inventory this "
                 "view reports (" + ", ".join(_ghg_missing) + ").  Publish "
                 "again from the Emissions Data Builder.")
    else:
        render_ghg_tab(
            precomputed.ghg_df, precomputed, ghg_frame,
            start_date=display_start, end_date=display_end,
            period_label=period_label,
            end_mining_date=end_mining_date,
            end_processing_date=end_processing_date,
            end_rehabilitation_date=end_rehabilitation_date,
            year_type=_period_type,
            display_year=display_year,
            dataset='Actual',
            departments=_department_filter,
            scopes=_scope_filter,
        )

with tab2:
    # The legislated parameters, beside the baseline they govern.
    with st.expander("Key constants and legislated parameters", expanded=False):
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
        st.caption("CER approved Oct 2024.  Safeguard parameters from "
                   "Config.py; milestones from Data/LOM.yaml.")
        st.caption(f"Milestones: {MILESTONE_SOURCE}")

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

    render_safeguard_tab(
        df, precomputed, nger_frame,
        fsei_rom, fsei_elec,
        carbon_credit_price, credit_escalation,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        display_year=display_year,
    )

with tab3:
    render_gri_tab(df, precomputed, ghg_frame,
                   start_date=display_start, end_date=display_end,
                   period_label=period_label)

with tab6:
    render_query_tab(
        df, precomputed, nger_frame,
        carbon_credit_price=carbon_credit_price,
        credit_escalation=credit_escalation,
    )

with tab9:
    # Release history and the documents that govern the model, read in place
    # rather than downloaded.
    try:
        from ExportEmissionsTable import published_summary as _about_build
        _about_build_line = _about_build()
    except Exception:                            # pragma: no cover - defensive
        _about_build_line = 'not available'
    render_about(
        app_name="Ravenswood Gold Emissions Calculator",
        changelog="Changelog.md",
        description="Emissions tracking, Safeguard Mechanism compliance and "
                    "value chain projections for the Ravenswood Gold Mine.",
        documents=[
            ("GHG emissions method", "Documentation/GhgEmissionsMethod.md"),
            ("Safeguard Mechanism method", "Documentation/SafeguardMechanismMethod.md"),
            ("GRI 14 method", "Documentation/Gri14Method.md"),
            ("Scope 3 method", "Documentation/Scope3Method.md"),
            ("NGER and NGA factors", "Documentation/NgerFactors.md"),
            ("Life of mine milestones", "Data/LOM.yaml"),
            ("Scope 3 parameters", "Reference/ReferenceInputs.yaml"),
            ("Assumptions", "Data/Assumptions.yaml"),
            ("Scope 3 factors", "Reference/Factors.csv"),
            ("Scope 3 items", "Reference/Items.csv"),
            ("Method reference", "Claude outputs/EmissionsCalculatorMethodReference.docx"),
        ],
        facts={
            "Milestones": MILESTONE_SOURCE,
            "Actuals to": DEFAULT_ACTUALS_TO_DATE.strftime('%d %b %Y')
                          if DEFAULT_ACTUALS_TO_DATE else 'not stated',
            "Model horizon": DEFAULT_END_REHABILITATION_DATE.strftime('%d %b %Y'),
            "Records loaded": f"{len(df):,}",
            "Published build": _about_build_line,
            "NGA factor editions": describe_edition_rule(nga_editions()),
        },
    )


# FOOTER
st.markdown("---")
_footer_left, _footer_right = st.columns([3, 2])
_footer_left.caption(
    "Emissions Model for Ravenswood Gold Mine")
# Which published inventory these figures come from, stated unobtrusively.
# A reader who needs to reproduce a number needs the build it came from.
try:
    from ExportEmissionsTable import published_summary as _published_summary
    _footer_right.caption(
        f"<div style='text-align:right'>{_published_summary()}</div>",
        unsafe_allow_html=True)
except Exception:                                # pragma: no cover - defensive
    pass