"""
tab1_ghg.py
Total GHG Emissions tab - combined comparison charts
Last updated: 2026-02-05 20:32 AEDT
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection
from calc_calendar import date_to_fy, aggregate_by_year_type
from config import DEFAULT_GRID_CONNECTION_DATE
from config import CREDIT_START_DATE

# Gold color palette
GOLD_METALLIC = '#DBB12A'      # Primary - Scope 1
BRIGHT_GOLD = '#E8AC41'         # Secondary - Scope 2
DARK_GOLDENROD = '#AE8B0F'     # Tertiary - Scope 3
SEPIA = '#734B1A'              # Accent
CAFE_NOIR = '#39250B'          # Lines
GRID_GREEN = '#2A9D8F'         # Grid connection marker
PHASE_MARKER = '#888888'       # Phase transition markers


def _add_phase_markers(fig, years_list, grid_connected_date,
                       end_mining_date, end_processing_date, end_rehabilitation_date,
                       year_type='FY'):
    """Add phase transition vertical lines and top-aligned labels to a chart.

    Accepts dates directly and converts to FY or CY year number at render time
    based on the current year_type.  Output is a bare year number (e.g. "2037")
    to match the x-axis labels used in the charts.
    """
    from calc_calendar import date_to_fy, date_to_cy
    _GRID_GREEN = '#2A9D8F'
    _PHASE_GREY = '#888888'
    markers = [
        (grid_connected_date, "Grid Connection", _GRID_GREEN, "dot"),
        (end_mining_date, "End Mining", _PHASE_GREY, "dash"),
        (end_processing_date, "End Processing", _PHASE_GREY, "dash"),
        (end_rehabilitation_date, "End Rehab", _PHASE_GREY, "dash"),
    ]
    years_set = set(str(y) for y in years_list)
    for i, (dt, label, colour, dash) in enumerate(markers):
        if dt is None:
            continue
        # Convert date to bare year number matching x-axis
        yr = str(date_to_cy(dt)) if year_type == 'CY' else str(date_to_fy(dt))
        if yr not in years_set:
            continue
        fig.add_shape(type="line", x0=yr, x1=yr, y0=0, y1=1, yref="paper",
                     line=dict(color=colour, width=1.5, dash=dash))
        fig.add_annotation(x=yr, y=1.0, yref="paper", text=label, showarrow=False,
                          yshift=10 + i * 14, font=dict(size=9, color=colour))


def _build_raw_data_summary(df, display_year, year_type='FY'):
    """Build raw data summary table showing consumption and emissions by fuel type.

    Uses Description and UOM directly from the source CSV.
    No renaming or unit conversion - what you see is what is in the file.

    Energy (GJ) calculated from native units using ENERGY_GJ_PER_NATIVE from config.

    Args:
        df: Loaded DataFrame from load_all_data()
        display_year: Year number (e.g. 2025)
        year_type: 'FY' or 'CY'

    Returns:
        Formatted DataFrame or None if no data
    """

    # Filter to Actual data for the selected year
    if year_type == 'FY':
        year_data = df[(df['FY'] == display_year) & (df['DataSet'] == 'Actual')].copy()
    else:
        year_data = df[(df['Year'] == display_year) & (df['DataSet'] == 'Actual')].copy()

    if len(year_data) == 0:
        return None

    # Fuel items only: rows where NGAFuel is populated in the source CSV.
    # This automatically excludes ROM (ore), gold, milled tonnes etc.
    # No hardcoded list needed - the CSV is the single source of truth.
    has_fuel = year_data['NGAFuel'].notna() & (year_data['NGAFuel'] != '')
    year_data = year_data[has_fuel]
    if len(year_data) == 0:
        return None

    # Aggregate by Description
    agg_cols = {
        'Quantity': 'sum',
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum',
        'UOM': 'first',
    }
    if 'Energy_GJ' in year_data.columns:
        agg_cols['Energy_GJ'] = 'sum'
    summary = year_data.groupby('Description').agg(agg_cols).reset_index()

    # Sort by total emissions descending (biggest contributors first)
    summary['_total'] = summary[['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']].sum(axis=1)
    summary = summary.sort_values('_total', ascending=False).drop(columns=['_total'])

    # Filter out rows where all emission scopes are effectively zero
    emission_cols = ['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']
    summary = summary[summary[emission_cols].abs().sum(axis=1) > 0]
    if len(summary) == 0:
        return None

    # Energy content already calculated in apply_emissions_to_df from NGA factors
    summary['Energy (GJ)'] = summary['Energy_GJ'] if 'Energy_GJ' in summary.columns else 0

    # Build result table
    result = pd.DataFrame({
        'Description': summary['Description'],
        'UOM': summary['UOM'],
        'Quantity': summary['Quantity'],
        'Energy (GJ)': summary['Energy (GJ)'],
        'Scope 1 (tCO2-e)': summary['Scope1_tCO2e'],
        'Scope 2 (tCO2-e)': summary['Scope2_tCO2e'],
        'Scope 3 (tCO2-e)': summary['Scope3_tCO2e'],
    })

    # Format numbers: use 2dp for small values, 0dp for large
    def _fmt(x):
        if pd.isna(x) or not isinstance(x, (int, float)):
            return ''
        if abs(x) < 1:
            return f"{x:,.4f}"
        elif abs(x) < 100:
            return f"{x:,.2f}"
        return f"{x:,.0f}"

    result['Quantity'] = result['Quantity'].apply(_fmt)
    result['Energy (GJ)'] = result['Energy (GJ)'].apply(_fmt)
    result['Scope 1 (tCO2-e)'] = result['Scope 1 (tCO2-e)'].apply(_fmt)
    result['Scope 2 (tCO2-e)'] = result['Scope 2 (tCO2-e)'].apply(_fmt)
    result['Scope 3 (tCO2-e)'] = result['Scope 3 (tCO2-e)'].apply(_fmt)

    return result



def prepare_annual_for_display(monthly, year_type='FY'):
    """Aggregate monthly data to annual and prepare for display

    Aggregates monthly emissions data to annual, converts units
    and adds compatibility columns for existing display code.

    Args:
        monthly: Monthly DataFrame from build_projection
        year_type: 'FY' (Financial Year) or 'CY' (Calendar Year)

    Returns:
        Annual DataFrame with display-ready columns
    """
    # Define aggregation for different column types
    agg_dict = {
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum',
        'ROM_t': 'sum',
    }

    # Add optional columns if present
    if 'Site_Electricity_kWh' in monthly.columns:
        agg_dict['Site_Electricity_kWh'] = 'sum'
    if 'Grid_Electricity_kWh' in monthly.columns:
        agg_dict['Grid_Electricity_kWh'] = 'sum'
    if 'Baseline' in monthly.columns:
        agg_dict['Baseline'] = 'sum'
    if 'Baseline_Intensity' in monthly.columns:
        agg_dict['Baseline_Intensity'] = 'mean'  # Average intensity over year
    if 'Emission_Intensity' in monthly.columns:
        agg_dict['Emission_Intensity'] = 'mean'  # Average intensity over year
    if 'Phase' in monthly.columns:
        agg_dict['Phase'] = 'last'  # Take phase from last month of FY
    if 'SMC_Monthly' in monthly.columns:
        agg_dict['SMC_Monthly'] = 'sum'  # Sum monthly credits to annual
    if 'SMC_Cumulative' in monthly.columns:
        agg_dict['SMC_Cumulative'] = 'last'  # Take end-of-year cumulative
    if 'In_Safeguard' in monthly.columns:
        agg_dict['In_Safeguard'] = 'last'  # Take end-of-year status

    # Aggregate monthly → annual (Tax Year/FY)
    annual = aggregate_by_year_type(monthly, year_type, agg_dict=agg_dict)

    # Add FY column as string for compatibility
    annual['FY'] = annual['Year']

    # Add compatibility columns (display code expects these names)
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']
    annual['Total'] = annual['Scope1'] + annual['Scope2'] + annual['Scope3']

    # Convert ROM from tonnes to megatonnes
    annual['ROM_Mt'] = annual['ROM_t'] / 1_000_000

    # Recalculate emission intensity from annual totals (more accurate than averaging monthly)
    annual['Emission_Intensity'] = 0.0
    mask = annual['ROM_Mt'] > 0
    annual.loc[mask, 'Emission_Intensity'] = annual.loc[mask, 'Scope1'] / (annual.loc[mask, 'ROM_Mt'] * 1_000_000)

    # If Phase column is missing, add a default
    if 'Phase' not in annual.columns:
        annual['Phase'] = 'Unknown'

    # Ensure electricity columns exist (with 0 if missing)
    if 'Site_Electricity_kWh' not in annual.columns:
        annual['Site_Electricity_kWh'] = 0
    if 'Grid_Electricity_kWh' not in annual.columns:
        annual['Grid_Electricity_kWh'] = 0

    return annual


def render_ghg_tab(df, fsei_rom, fsei_elec,
                   start_date, end_date,
                   end_mining_date, end_processing_date, end_rehabilitation_date,
                   decline_rate_phase2, year_type='FY'):
    """Render Total GHG Emissions tab

    Args:
        df: Unified DataFrame from load_all_data()
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        start_date through end_rehabilitation_date: Projection dates
        decline_rate_phase2: Phase 2 decline rate
        year_type: 'FY' (Financial Year, July-June) or 'CY' (Calendar Year, Jan-Dec)
    """

    # Dates for display
    grid_connected_date = DEFAULT_GRID_CONNECTION_DATE
    _em_str = end_mining_date.strftime('%d %b %Y')
    _ep_str = end_processing_date.strftime('%d %b %Y')

    st.subheader("Total Greenhouse Gas Emissions")
    st.caption(f"Mining ends {_em_str} | Processing ends {_ep_str}")

    display_year = st.session_state.get('display_year', 2025)

    monthly = build_projection(
        df,
        end_mining_date=end_mining_date,
        end_processing_date=end_processing_date,
        end_rehabilitation_date=end_rehabilitation_date,
        fsei_rom=fsei_rom,
        fsei_elec=fsei_elec,
        credit_start_date=CREDIT_START_DATE,
        start_date=start_date,
        end_date=end_date,
        decline_rate_phase2=decline_rate_phase2
    )

    # Aggregate monthly → annual and prepare for display
    projection = prepare_annual_for_display(monthly, year_type)

    # Show data info
    actual_count = len(df[df['DataSet'] == 'Actual'])
    source_data = df[df['DataSet'] == 'Actual']

    if len(source_data) > 0:
        date_min = source_data['Date'].min()
        date_max = source_data['Date'].max()
        st.caption(f"{actual_count:,} records | Date Range: {date_min.strftime('%Y-%m')} to {date_max.strftime('%Y-%m')}")
    else:
        st.caption("No records found")

    display_single_source(projection, display_year, df, year_type=year_type, grid_connected_date=grid_connected_date, end_mining_date=end_mining_date, end_processing_date=end_processing_date, end_rehabilitation_date=end_rehabilitation_date)


def display_single_source(projection, display_year, df, show_summary=True, year_type='FY', grid_connected_date=None, end_mining_date=None, end_processing_date=None, end_rehabilitation_date=None):
    """Display charts and tables for single data source"""

    # Construct year label based on year_type
    year_prefix = 'CY' if year_type == 'CY' else 'FY'
    year_label = f'{year_prefix}{display_year}'

    # Summary table
    if show_summary:
        with st.expander("Emissions Summary", expanded=True):
            year_data = projection[projection['FY'] == year_label]

            if len(year_data) == 0:
                st.warning(f"No data for {year_label}")
            else:
                row = year_data.iloc[0]

                summary_data = [{
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Scope 2 (tCO2-e)': f"{row['Scope2']:,.0f}",
                    'Scope 3 (tCO2-e)': f"{row['Scope3']:,.0f}",
                    'Total (tCO2-e)': f"{row['Total']:,.0f}",
                    'Intensity (tCO2-e/t)': f"{row['Emission_Intensity']:.4f}" if row['ROM_Mt'] > 0 else "N/A"
                }]

                st.dataframe(pd.DataFrame(summary_data), hide_index=True, width="stretch")

        # Raw data summary table - consumption quantities and emissions by fuel type
        if df is not None:
            with st.expander(f"\U0001f4cb Fuel Consumption Detail ({year_label})", expanded=False):
                raw_table = _build_raw_data_summary(df, display_year, year_type)
                if raw_table is not None:
                    st.dataframe(raw_table, hide_index=True, width="stretch")
                else:
                    st.info(f"No actual data for {year_label}")

    # Charts
    with st.expander("Emissions Charts", expanded=True):

        # Prepare display years without FY
        projection_display = projection.copy()
        projection_display['Year'] = projection_display['FY'].str.replace(r'^[A-Z]+', '', regex=True)

        # Stacked area chart
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=projection_display['Year'],
            y=projection_display['Scope1'],
            name='Scope 1',
            mode='lines',
            fill='tonexty',
            line=dict(color=GOLD_METALLIC, width=2),
            stackgroup='one'
        ))

        fig.add_trace(go.Scatter(
            x=projection_display['Year'],
            y=projection_display['Scope2'],
            name='Scope 2',
            mode='lines',
            fill='tonexty',
            line=dict(color=BRIGHT_GOLD, width=2),
            stackgroup='one'
        ))

        fig.add_trace(go.Scatter(
            x=projection_display['Year'],
            y=projection_display['Scope3'],
            name='Scope 3',
            mode='lines',
            fill='tonexty',
            line=dict(color=DARK_GOLDENROD, width=2),
            stackgroup='one'
        ))

        fig.update_layout(
            title="Total GHG Emissions by Scope",
            xaxis_title="Calendar Year" if year_type == "CY" else "Financial Year",
            yaxis_title="Emissions (tCO2-e)",
            hovermode='x unified',
            height=500
        )

        # Phase transition markers (all at top)
        _add_phase_markers(fig, projection_display['Year'].tolist(),
                          grid_connected_date, end_mining_date, end_processing_date,
                          end_rehabilitation_date, year_type=year_type)

        st.plotly_chart(fig, width="stretch")

    # Emissions breakdown pie charts (Cost Centre and Department)
    with st.expander("Emissions Breakdown", expanded=False):
        st.caption(f"Breakdown for {year_label}")

        # Get FY data from df
        fy_data = df[(df['FY'] == display_year) & (df['DataSet'] == 'Actual')].copy()

        if len(fy_data) == 0:
            st.warning(f"No data available for FY{display_year}")
        else:
            col1, col2 = st.columns(2)

            # Gold color palette for pies
            gold_colors = [
                GOLD_METALLIC,      # #DBB12A
                BRIGHT_GOLD,        # #E8AC41
                DARK_GOLDENROD,     # #AE8B0F
                SEPIA,              # #734B1A
                CAFE_NOIR,          # #39250B
                '#D4A017',          # Metallic gold
                '#C9AE5D',          # Vegas gold
                '#B8860B',          # Dark goldenrod variant
                '#9B7653',          # Tan
                '#8B7355',          # Burlywood
                '#7D6D47',          # Other brown
            ]

            with col1:
                # Cost Centre breakdown
                cc_emissions = fy_data.groupby('CostCentre', observed=False).agg({
                    'Scope1_tCO2e': 'sum',
                    'Scope2_tCO2e': 'sum',
                    'Scope3_tCO2e': 'sum'
                }).reset_index()

                cc_emissions['Total'] = cc_emissions['Scope1_tCO2e'] + cc_emissions['Scope2_tCO2e'] + cc_emissions['Scope3_tCO2e']
                cc_emissions = cc_emissions.sort_values('Total', ascending=False)

                # Combine small values into "Other" (keep top 10)
                if len(cc_emissions) > 10:
                    top10 = cc_emissions.head(10)
                    other_total = cc_emissions.tail(len(cc_emissions) - 10)['Total'].sum()
                    if other_total > 0:
                        other_row = pd.DataFrame([{
                            'CostCentre': 'Other',
                            'Total': other_total
                        }])
                        cc_emissions = pd.concat([top10, other_row], ignore_index=True)

                fig_cc = go.Figure(data=[go.Pie(
                    labels=cc_emissions['CostCentre'],
                    values=cc_emissions['Total'],
                    hole=0.3,
                    rotation=310,
                    textposition='auto',
                    textinfo='label+percent',
                    insidetextorientation='auto',
                    marker=dict(colors=gold_colors[:len(cc_emissions)])
                )])

                fig_cc.update_layout(
                    title="By Cost Centre",
                    height=500,
                    showlegend=True,
                    legend=dict(font=dict(size=10)),
                    margin=dict(t=60, b=40, l=20, r=20)
                )

                st.plotly_chart(fig_cc, width="stretch", key="pie_cc")

            with col2:
                # Department breakdown
                dept_emissions = fy_data.groupby('Department', observed=False).agg({
                    'Scope1_tCO2e': 'sum',
                    'Scope2_tCO2e': 'sum',
                    'Scope3_tCO2e': 'sum'
                }).reset_index()

                dept_emissions['Total'] = dept_emissions['Scope1_tCO2e'] + dept_emissions['Scope2_tCO2e'] + dept_emissions['Scope3_tCO2e']
                dept_emissions = dept_emissions.sort_values('Total', ascending=False)

                # Combine small values into "Other" (keep top 8)
                if len(dept_emissions) > 8:
                    top8 = dept_emissions.head(8)
                    other_total = dept_emissions.tail(len(dept_emissions) - 8)['Total'].sum()
                    if other_total > 0:
                        other_row = pd.DataFrame([{
                            'Department': 'Other',
                            'Total': other_total
                        }])
                        dept_emissions = pd.concat([top8, other_row], ignore_index=True)

                fig_dept = go.Figure(data=[go.Pie(
                    labels=dept_emissions['Department'],
                    values=dept_emissions['Total'],
                    hole=0.3,
                    rotation=310,
                    textposition='auto',
                    textinfo='label+percent',
                    insidetextorientation='auto',
                    marker=dict(colors=gold_colors[:len(dept_emissions)])
                )])

                fig_dept.update_layout(
                    title="By Department",
                    height=500,
                    showlegend=True,
                    legend=dict(font=dict(size=10)),
                    margin=dict(t=60, b=40, l=20, r=20)
                )

                st.plotly_chart(fig_dept, width="stretch", key="pie_dept")

    # Data table (moved to bottom)
    with st.expander("Emissions Data Table", expanded=False):
        display_df = projection[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total']].copy()
        display_df['ROM_Mt'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}")
        display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope2'] = display_df['Scope2'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope3'] = display_df['Scope3'].apply(lambda x: f"{x:,.0f}")
        display_df['Total'] = display_df['Total'].apply(lambda x: f"{x:,.0f}")

        st.dataframe(display_df, hide_index=True, width="stretch", height=400)