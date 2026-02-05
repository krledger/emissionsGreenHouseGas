"""
app.py
Ravenswood Gold Mine - Emissions Tracking Dashboard
Last Updated: 2026-02-05 21:08 AEDT
"""
# NOTE FOR CLAUDE: This file contains emojis. Use binary-safe editing (rb/wb) to prevent corruption.

import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
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
    DEFAULT_GRID_CONNECTION_DATE,
    DEFAULT_DISPLAY_YEAR,
    DEFAULT_YEAR_TYPE,
    DEFAULT_DATA_SOURCE,
    DECLINE_RATE_PHASE2
)
from calc_calendar import date_to_fy, fy_to_date_range
from loader_data import load_all_data
from projections import build_projection

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
    st.error("Ã¢ÂÅ’ Missing required file: consolidated_emissions_data.csv")
    st.info("Please ensure the data file is in the same directory as this script.")
    st.stop()

# Load unified data
df = load_data_cached()

with st.sidebar:
    st.header("⚙️ Configuration")

    # Display Year Selection
    with st.expander("📅 Display Year", expanded=True):
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
    with st.expander("📆 Year Type", expanded=True):
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

        st.caption("⚠️ Tab 2 (Safeguard) always uses FY per legislation")


    # Data Set Selection
    with st.expander("📊 Data Set", expanded=True):
        # Build source_options with default first
        if DEFAULT_DATA_SOURCE == 'Base':
            source_options = {
                'Base': 'Base',
                'NPI-NGERS': 'NPI-NGERS',
                'All': 'All Data Sets'
            }
        elif DEFAULT_DATA_SOURCE == 'NPI-NGERS':
            source_options = {
                'NPI-NGERS': 'NPI-NGERS',
                'Base': 'Base',
                'All': 'All Data Sets'
            }
        else:  # DEFAULT_DATA_SOURCE == 'All'
            source_options = {
                'All': 'All Data Sets',
                'Base': 'Base',
                'NPI-NGERS': 'NPI-NGERS'
            }

        selected_source = st.selectbox(
            "Select Data Set",
            options=list(source_options.keys()),
            format_func=lambda x: source_options[x],
            key='data_source',
            help="Choose which data set to display. 'All Data Sets' shows all datasets"
        )


    # Baseline Emission Intensity
    with st.expander("⚖️ Baseline Emission Intensity", expanded=False):
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



    # Baseline Decline Rates
    with st.expander("📉 Baseline Decline Rates", expanded=False):
        st.caption("Phase 1 (FY2024-FY2030): 4.9% (legislated)")

        decline_rate_phase2 = st.number_input(
            "Phase 2 Rate (FY2031-FY2050, %/year)",
            value=float(DECLINE_RATE_PHASE2 * 100),
            min_value=0.0,
            max_value=10.0,
            step=0.1,
            format="%.3f",
            help="Indicative decline rate for FY2031-FY2050 (legislated default: 3.285%)"
        ) / 100
        st.caption("After FY2050: Baseline remains flat")


    # Projection Period
    with st.expander("📈 Projection Period", expanded=True):
        start_fy = st.number_input(
            "Start FY",
            value=date_to_fy(DEFAULT_START_DATE),
            min_value=2020,
            max_value=2030,
            step=1,
            help="First year for projections"
        )

        end_mining_fy = st.number_input(
            "End Mining FY",
            value=date_to_fy(DEFAULT_END_MINING_DATE),
            min_value=2025,
            max_value=2055,
            step=1,
            help="Year when ore extraction ceases"
        )

        end_processing_fy = st.number_input(
            "End Processing FY",
            value=date_to_fy(DEFAULT_END_PROCESSING_DATE),
            min_value=2025,
            max_value=2055,
            step=1,
            help="Year when stockpile processing completes"
        )

        end_rehabilitation_fy = st.number_input(
            "End Rehabilitation FY",
            value=date_to_fy(DEFAULT_END_REHABILITATION_DATE),
            min_value=2025,
            max_value=2060,
            step=1,
            help="Year when site closure completes"
        )

        end_fy = end_rehabilitation_fy


    # Grid Connection
    with st.expander("⚡ Grid Connection", expanded=False):
        grid_connected_fy = st.number_input(
            "Grid Connection FY",
            value=date_to_fy(DEFAULT_GRID_CONNECTION_DATE),
            min_value=2025,
            max_value=2050,
            step=1,
            help="Year when grid electricity becomes available"
        )


    # Carbon Credit Market
    with st.expander("💰 Carbon Credit Market", expanded=False):
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
    with st.expander("💵 Carbon Tax Scenario", expanded=False):
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
            10.0,
            DEFAULT_TAX_ESCALATION * 100,
            step=0.5
        ) / 100

        # CONVERT FY INPUTS TO DATES
        # Convert FY numbers to dates for export and tabs
        start_date = fy_to_date_range(start_fy)[0]
        end_date = fy_to_date_range(end_fy)[0]
        grid_connected_date = fy_to_date_range(grid_connected_fy)[0]
        end_mining_date = fy_to_date_range(end_mining_fy)[0]
        end_processing_date = fy_to_date_range(end_processing_fy)[0]
        end_rehabilitation_date = fy_to_date_range(end_rehabilitation_fy)[0]
        tax_start_date = fy_to_date_range(tax_start_fy)[0]


    # Export Package
    with st.expander("📊 Export Data Tables", expanded=False):
        st.caption("💡 To save charts: Hover over any chart → Click camera icon")

        export_include_ghg = st.checkbox("Include GHG Emissions Tables", value=True)
        export_include_safeguard = st.checkbox("Include Safeguard Tables", value=True)
        export_include_tax = st.checkbox("Include Carbon Tax Tables", value=True)
        export_include_processed = st.checkbox("Include Processed Input Data", value=True)

        # Download button - only builds when pressed
        if st.button("📥 Generate Excel Export", type="primary", use_container_width=True):
            with st.spinner("Building Excel file..."):
                try:
                    # Build monthly projection
                    monthly_df = build_projection(
                        df=df,
                        fsei_rom=fsei_rom,
                        fsei_elec=fsei_elec,
                        start_date=start_date,
                        end_date=end_date,
                        end_mining_date=end_mining_date,
                        end_processing_date=end_processing_date,
                        end_rehabilitation_date=end_rehabilitation_date,
                        grid_connected_date=grid_connected_date,
                        credit_start_date=CREDIT_START_DATE,
                        decline_rate_phase2=decline_rate_phase2
                    )

                    # Aggregate monthly → annual (FY) for export
                    from calc_calendar import aggregate_by_year_type

                    # Define aggregation to preserve all columns
                    agg_dict = {
                        'Scope1_tCO2e': 'sum',
                        'Scope2_tCO2e': 'sum',
                        'Scope3_tCO2e': 'sum',
                        'ROM_t': 'sum',
                    }

                    # Add optional columns if present
                    if 'Baseline' in monthly_df.columns:
                        agg_dict['Baseline'] = 'sum'
                    if 'Baseline_Intensity' in monthly_df.columns:
                        agg_dict['Baseline_Intensity'] = 'mean'
                    if 'Emission_Intensity' in monthly_df.columns:
                        agg_dict['Emission_Intensity'] = 'mean'
                    if 'Phase' in monthly_df.columns:
                        agg_dict['Phase'] = 'last'
                    if 'SMC_Monthly' in monthly_df.columns:
                        agg_dict['SMC_Monthly'] = 'sum'
                    if 'SMC_Cumulative' in monthly_df.columns:
                        agg_dict['SMC_Cumulative'] = 'last'
                    if 'In_Safeguard' in monthly_df.columns:
                        agg_dict['In_Safeguard'] = 'last'

                    annual_df = aggregate_by_year_type(monthly_df, 'FY', agg_dict=agg_dict)

                    # Add compatibility columns
                    annual_df['FY'] = annual_df['Year']
                    annual_df['Scope1'] = annual_df['Scope1_tCO2e']
                    annual_df['Scope2'] = annual_df['Scope2_tCO2e']
                    annual_df['Scope3'] = annual_df['Scope3_tCO2e']
                    annual_df['Total'] = annual_df['Scope1'] + annual_df['Scope2'] + annual_df['Scope3']
                    annual_df['ROM_Mt'] = annual_df['ROM_t'] / 1_000_000

                    # Recalculate emission intensity
                    annual_df['Emission_Intensity'] = 0.0
                    mask = annual_df['ROM_Mt'] > 0
                    annual_df.loc[mask, 'Emission_Intensity'] = annual_df.loc[mask, 'Scope1'] / (annual_df.loc[mask, 'ROM_Mt'] * 1_000_000)

                    # Rename SMC_Monthly to SMC_Annual for compatibility
                    if 'SMC_Monthly' in annual_df.columns:
                        annual_df['SMC_Annual'] = annual_df['SMC_Monthly']

                    # If Phase column is missing, add a default
                    if 'Phase' not in annual_df.columns:
                        annual_df['Phase'] = 'Unknown'

                    projection_df = annual_df

                    # Create Excel file in memory
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:

                        # Tab 1: GHG Emissions
                        if export_include_ghg:
                            # Summary
                            year_data = projection_df[projection_df['FY'] == 'FY2025']
                            if len(year_data) > 0:
                                row = year_data.iloc[0]
                                ghg_summary = pd.DataFrame([{
                                    'ROM_Mt': row['ROM_Mt'],
                                    'Scope1_tCO2e': row['Scope1'],
                                    'Scope2_tCO2e': row['Scope2'],
                                    'Scope3_tCO2e': row['Scope3'],
                                    'Total_tCO2e': row['Total'],
                                    'Intensity_tCO2e_per_t': row['Emission_Intensity']
                                }])
                                ghg_summary.to_excel(writer, sheet_name='GHG_Summary', index=False)

                            # Full data
                            ghg_data = projection_df[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total']].copy()
                            ghg_data.to_excel(writer, sheet_name='GHG_Data', index=False)

                        # Tab 2: Safeguard
                        if export_include_safeguard:
                            # Summary
                            year_data = projection_df[projection_df['FY'] == 'FY2025']
                            if len(year_data) > 0:
                                row = year_data.iloc[0]
                                safeguard_summary = pd.DataFrame([{
                                    'ROM_Mt': row['ROM_Mt'],
                                    'Scope1_tCO2e': row['Scope1'],
                                    'Baseline_tCO2e': row['Baseline'],
                                    'Emission_Intensity': row['Emission_Intensity'],
                                    'Baseline_Intensity': row['Baseline_Intensity'],
                                    'SMC_Annual': row.get('SMC_Annual', 0),
                                    'SMC_Cumulative': row.get('SMC_Cumulative', 0)
                                }])
                                safeguard_summary.to_excel(writer, sheet_name='Safeguard_Summary', index=False)

                            # Full data
                            safeguard_cols = ['FY', 'ROM_Mt', 'Scope1', 'Baseline', 'Exceedance',
                                            'Emission_Intensity', 'Baseline_Intensity']
                            available = [c for c in safeguard_cols if c in projection_df.columns]
                            if available:
                                projection_df[available].to_excel(writer, sheet_name='Safeguard_Data', index=False)

                            # SMC Credits
                            if 'SMC_Annual' in projection_df.columns:
                                smc_cols = ['FY', 'SMC_Annual', 'SMC_Cumulative', 'SMC_Value_Annual', 'SMC_Value_Cumulative']
                                available = [c for c in smc_cols if c in projection_df.columns]
                                if available:
                                    projection_df[available].to_excel(writer, sheet_name='SMC_Credits', index=False)

                        # Tab 3: Carbon Tax
                        if export_include_tax:
                            if 'Tax_Liability' in projection_df.columns:
                                # Summary
                                year_data = projection_df[projection_df['FY'] == 'FY2025']
                                if len(year_data) > 0:
                                    row = year_data.iloc[0]
                                    tax_summary = pd.DataFrame([{
                                        'Scope1_tCO2e': row['Scope1'],
                                        'Tax_Rate_per_tonne': row.get('Tax_Rate_per_tonne', tax_rate),
                                        'Tax_Liability_Annual': row['Tax_Liability'],
                                        'Tax_Cumulative': row.get('Tax_Cumulative', 0)
                                    }])
                                    tax_summary.to_excel(writer, sheet_name='Tax_Summary', index=False)

                                # Full data
                                tax_cols = ['FY', 'Scope1', 'Tax_Rate_per_tonne', 'Tax_Liability', 'Tax_Cumulative']
                                available = [c for c in tax_cols if c in projection_df.columns]
                                if available:
                                    projection_df[available].to_excel(writer, sheet_name='Tax_Data', index=False)

                        # Processed input data
                        if export_include_processed:
                            if selected_source == 'All':
                                export_df = df[df['DataSet'].isin(['Base', 'NPI-NGERS'])].copy()
                            else:
                                export_df = df[df['DataSet'] == selected_source].copy()
                            export_df.to_excel(writer, sheet_name='Processed_Input', index=False)

                    # Get Excel data
                    excel_data = output.getvalue()

                    # Download button
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f'ravenswood_emissions_{timestamp}.xlsx'

                    st.download_button(
                        label="💾 Download Excel File",
                        data=excel_data,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )

                    st.success("✓ Excel file generated successfully!")

                except Exception as e:
                    st.error(f"Error generating export: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())


# TABS
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Total GHG Emissions",
    "🛡️ Safeguard Mechanism",
    "💰 Carbon Tax Analysis",
    "📋 NGER Factors"
])


# RENDER TABS
with tab1:
    render_ghg_tab(
        df, selected_source,
        fsei_rom, fsei_elec,
        start_date, end_date,
        grid_connected_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        decline_rate_phase2,
        selected_year_type
    )

with tab2:
    render_safeguard_tab(
        df, selected_source,
        fsei_rom, fsei_elec,
        start_date, end_date,
        grid_connected_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        carbon_credit_price, credit_escalation,
        CREDIT_START_DATE,
        decline_rate_phase2
    )

with tab3:
    render_carbon_tax_tab(
        df, selected_source,
        fsei_rom, fsei_elec,
        start_date, end_date,
        grid_connected_date,
        end_mining_date, end_processing_date, end_rehabilitation_date,
        carbon_credit_price, credit_escalation,
        tax_start_date, tax_rate, tax_escalation,
        CREDIT_START_DATE,
        decline_rate_phase2,
        selected_year_type
    )

with tab4:
    render_nger_tab()

# FOOTER
st.markdown("---")
st.caption("Â© 2024-2026 Decision Chaos | Safeguard Mechanism Compliance Model for Ravenswood Gold Mine")