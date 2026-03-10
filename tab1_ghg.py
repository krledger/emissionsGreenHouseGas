"""
tab1_ghg.py
Total GHG Emissions tab - combined comparison charts
Last updated: 2026-03-10

ARCHITECTURE (v2):
    Receives PrecomputedData from app.py.
    No build_projection, no NGA loading, no annual aggregation.
    Display and filter only.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from calc_calendar import date_to_fy, date_to_cy
from calc_precompute import get_annual
from config import DEFAULT_GRID_CONNECTION_DATE, CREDIT_START_DATE

# Gold color palette
GOLD_METALLIC = '#DBB12A'
BRIGHT_GOLD = '#E8AC41'
DARK_GOLDENROD = '#AE8B0F'
SEPIA = '#734B1A'
CAFE_NOIR = '#39250B'
GRID_GREEN = '#2A9D8F'
PHASE_MARKER = '#888888'


def _add_phase_markers(fig, years_list, grid_connected_date,
                       end_mining_date, end_processing_date, end_rehabilitation_date,
                       year_type='FY'):
    """Add phase transition vertical lines and top-aligned labels to a chart."""
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
        yr = str(date_to_cy(dt)) if year_type == 'CY' else str(date_to_fy(dt))
        if yr not in years_set:
            continue
        fig.add_shape(type="line", x0=yr, x1=yr, y0=0, y1=1, yref="paper",
                     line=dict(color=colour, width=1.5, dash=dash))
        fig.add_annotation(x=yr, y=1.0, yref="paper", text=label, showarrow=False,
                          yshift=10 + i * 14, font=dict(size=9, color=colour))


def _build_raw_data_summary(df, display_year, year_type='FY'):
    """Build raw data summary table showing consumption and emissions by fuel type."""

    if year_type == 'FY':
        year_data = df[(df['FY'] == display_year) & (df['DataSet'] == 'Actual')].copy()
    else:
        year_data = df[(df['Year'] == display_year) & (df['DataSet'] == 'Actual')].copy()

    if len(year_data) == 0:
        return None

    has_fuel = year_data['NGAFuel'].notna() & (year_data['NGAFuel'] != '')
    year_data = year_data[has_fuel]
    if len(year_data) == 0:
        return None

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

    summary['_total'] = summary[['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']].sum(axis=1)
    summary = summary.sort_values('_total', ascending=False).drop(columns=['_total'])

    emission_cols = ['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']
    summary = summary[summary[emission_cols].abs().sum(axis=1) > 0]
    if len(summary) == 0:
        return None

    summary['Energy (GJ)'] = summary['Energy_GJ'] if 'Energy_GJ' in summary.columns else 0

    result = pd.DataFrame({
        'Description': summary['Description'],
        'UOM': summary['UOM'],
        'Quantity': summary['Quantity'],
        'Energy (GJ)': summary['Energy (GJ)'],
        'Scope 1 (tCO2-e)': summary['Scope1_tCO2e'],
        'Scope 2 (tCO2-e)': summary['Scope2_tCO2e'],
        'Scope 3 (tCO2-e)': summary['Scope3_tCO2e'],
    })

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



def _build_monthly_detail(df, display_year, year_type='FY'):
    """Build monthly detail table for the selected year with NGA factors shown."""
    if year_type == 'FY':
        year_data = df[df['FY'] == display_year].copy()
    else:
        year_data = df[df['Year'] == display_year].copy()

    if len(year_data) == 0:
        return None

    has_fuel = year_data['NGAFuel'].notna() & (year_data['NGAFuel'] != '')
    year_data = year_data[has_fuel]
    if len(year_data) == 0:
        return None

    year_data['EF_S1_kgCO2e'] = 0.0
    year_data['EF_S2_kgCO2e'] = 0.0
    year_data['EF_S3_kgCO2e'] = 0.0
    qty_mask = year_data['Quantity'].abs() > 0
    if qty_mask.any():
        year_data.loc[qty_mask, 'EF_S1_kgCO2e'] = (
            year_data.loc[qty_mask, 'Scope1_tCO2e'] / year_data.loc[qty_mask, 'Quantity'] * 1000
        )
        year_data.loc[qty_mask, 'EF_S2_kgCO2e'] = (
            year_data.loc[qty_mask, 'Scope2_tCO2e'] / year_data.loc[qty_mask, 'Quantity'] * 1000
        )
        year_data.loc[qty_mask, 'EF_S3_kgCO2e'] = (
            year_data.loc[qty_mask, 'Scope3_tCO2e'] / year_data.loc[qty_mask, 'Quantity'] * 1000
        )

    import calendar
    year_data['Month_Name'] = year_data['Month'].apply(
        lambda m: calendar.month_abbr[int(m)] if pd.notna(m) and 1 <= int(m) <= 12 else ''
    )

    result = pd.DataFrame({
        'Month': year_data['Month_Name'],
        'DataSet': year_data['DataSet'],
        'Description': year_data['Description'],
        'Department': year_data['Department'],
        'CostCentre': year_data['CostCentre'],
        'NGAFuel': year_data['NGAFuel'],
        'UOM': year_data['UOM'],
        'Quantity': year_data['Quantity'],
        'EF S1 (kgCO2e/unit)': year_data['EF_S1_kgCO2e'],
        'EF S2 (kgCO2e/unit)': year_data['EF_S2_kgCO2e'],
        'EF S3 (kgCO2e/unit)': year_data['EF_S3_kgCO2e'],
        'Scope 1 (tCO2-e)': year_data['Scope1_tCO2e'],
        'Scope 2 (tCO2-e)': year_data['Scope2_tCO2e'],
        'Scope 3 (tCO2-e)': year_data['Scope3_tCO2e'],
        'Energy (GJ)': year_data['Energy_GJ'] if 'Energy_GJ' in year_data.columns else 0,
    })

    month_order = {calendar.month_abbr[i]: i for i in range(1, 13)}
    result['_month_sort'] = result['Month'].map(month_order).fillna(0)
    result = result.sort_values(['_month_sort', 'Description', 'CostCentre']).drop(columns=['_month_sort'])
    result = result.reset_index(drop=True)

    return result


def render_ghg_tab(df, precomputed, year_type,
                   end_mining_date, end_processing_date, end_rehabilitation_date):
    """Render Total GHG Emissions tab.

    Args:
        df: Raw DataFrame from load_all_data() (for detail tables only)
        precomputed: PrecomputedData from calc_precompute
        year_type: 'FY' or 'CY'
        end_*_date: Phase boundary dates (for chart markers)
    """

    grid_connected_date = DEFAULT_GRID_CONNECTION_DATE
    _em_str = end_mining_date.strftime('%d %b %Y')
    _ep_str = end_processing_date.strftime('%d %b %Y')

    st.subheader("Total Greenhouse Gas Emissions")
    st.caption(f"Mining ends {_em_str} | Processing ends {_ep_str}")

    display_year = st.session_state.get('display_year', 2025)

    # Use pre-computed annual projection — no build_projection call
    projection = get_annual(precomputed, year_type)

    # Show data info
    actual_count = len(df[df['DataSet'] == 'Actual'])
    source_data = df[df['DataSet'] == 'Actual']

    if len(source_data) > 0:
        date_min = source_data['Date'].min()
        date_max = source_data['Date'].max()
        st.caption(f"{actual_count:,} records | Date Range: {date_min.strftime('%Y-%m')} to {date_max.strftime('%Y-%m')}")
    else:
        st.caption("No records found")

    display_single_source(projection, display_year, df, year_type=year_type,
                          grid_connected_date=grid_connected_date,
                          end_mining_date=end_mining_date,
                          end_processing_date=end_processing_date,
                          end_rehabilitation_date=end_rehabilitation_date)


def display_single_source(projection, display_year, df, show_summary=True, year_type='FY',
                          grid_connected_date=None, end_mining_date=None,
                          end_processing_date=None, end_rehabilitation_date=None):
    """Display charts and tables for single data source"""

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

    # Charts
    with st.expander("Emissions Charts", expanded=True):

        projection_display = projection.copy()
        projection_display['Year'] = projection_display['FY'].str.replace(r'^[A-Z]+', '', regex=True)

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

        _add_phase_markers(fig, projection_display['Year'].tolist(),
                          grid_connected_date, end_mining_date, end_processing_date,
                          end_rehabilitation_date, year_type=year_type)

        st.plotly_chart(fig, width="stretch")

    # Emissions breakdown pie charts
    with st.expander("Emissions Breakdown", expanded=False):
        st.caption(f"Breakdown for {year_label}")

        fy_data = df[(df['FY'] == display_year) & (df['DataSet'] == 'Actual')].copy()

        if len(fy_data) == 0:
            st.warning(f"No data available for FY{display_year}")
        else:
            col1, col2 = st.columns(2)

            gold_colors = [
                GOLD_METALLIC, BRIGHT_GOLD, DARK_GOLDENROD, SEPIA, CAFE_NOIR,
                '#D4A017', '#C9AE5D', '#B8860B', '#9B7653', '#8B7355', '#7D6D47',
            ]

            with col1:
                cc_emissions = fy_data.groupby('CostCentre', observed=False).agg({
                    'Scope1_tCO2e': 'sum', 'Scope2_tCO2e': 'sum', 'Scope3_tCO2e': 'sum'
                }).reset_index()
                cc_emissions['Total'] = cc_emissions['Scope1_tCO2e'] + cc_emissions['Scope2_tCO2e'] + cc_emissions['Scope3_tCO2e']
                cc_emissions = cc_emissions.sort_values('Total', ascending=False)

                if len(cc_emissions) > 10:
                    top10 = cc_emissions.head(10)
                    other_total = cc_emissions.tail(len(cc_emissions) - 10)['Total'].sum()
                    if other_total > 0:
                        other_row = pd.DataFrame([{'CostCentre': 'Other', 'Total': other_total}])
                        cc_emissions = pd.concat([top10, other_row], ignore_index=True)

                fig_cc = go.Figure(data=[go.Pie(
                    labels=cc_emissions['CostCentre'], values=cc_emissions['Total'],
                    hole=0.3, rotation=310, textposition='auto', textinfo='label+percent',
                    insidetextorientation='auto',
                    marker=dict(colors=gold_colors[:len(cc_emissions)])
                )])
                fig_cc.update_layout(title="By Cost Centre", height=500, showlegend=True,
                                    legend=dict(font=dict(size=10)),
                                    margin=dict(t=60, b=40, l=20, r=20))
                st.plotly_chart(fig_cc, width="stretch", key="pie_cc")

            with col2:
                dept_emissions = fy_data.groupby('Department', observed=False).agg({
                    'Scope1_tCO2e': 'sum', 'Scope2_tCO2e': 'sum', 'Scope3_tCO2e': 'sum'
                }).reset_index()
                dept_emissions['Total'] = dept_emissions['Scope1_tCO2e'] + dept_emissions['Scope2_tCO2e'] + dept_emissions['Scope3_tCO2e']
                dept_emissions = dept_emissions.sort_values('Total', ascending=False)

                if len(dept_emissions) > 8:
                    top8 = dept_emissions.head(8)
                    other_total = dept_emissions.tail(len(dept_emissions) - 8)['Total'].sum()
                    if other_total > 0:
                        other_row = pd.DataFrame([{'Department': 'Other', 'Total': other_total}])
                        dept_emissions = pd.concat([top8, other_row], ignore_index=True)

                fig_dept = go.Figure(data=[go.Pie(
                    labels=dept_emissions['Department'], values=dept_emissions['Total'],
                    hole=0.3, rotation=310, textposition='auto', textinfo='label+percent',
                    insidetextorientation='auto',
                    marker=dict(colors=gold_colors[:len(dept_emissions)])
                )])
                fig_dept.update_layout(title="By Department", height=500, showlegend=True,
                                      legend=dict(font=dict(size=10)),
                                      margin=dict(t=60, b=40, l=20, r=20))
                st.plotly_chart(fig_dept, width="stretch", key="pie_dept")

        if df is not None:
            with st.expander(f"\U0001f4cb Fuel Consumption Detail ({year_label})", expanded=False):
                raw_table = _build_raw_data_summary(df, display_year, year_type)
                if raw_table is not None:
                    st.dataframe(raw_table, hide_index=True, width="stretch")
                else:
                    st.info(f"No actual data for {year_label}")

    with st.expander("Emissions Data Table", expanded=False):
        display_df = projection[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total']].copy()
        display_df['ROM_Mt'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}")
        display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope2'] = display_df['Scope2'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope3'] = display_df['Scope3'].apply(lambda x: f"{x:,.0f}")
        display_df['Total'] = display_df['Total'].apply(lambda x: f"{x:,.0f}")

        st.dataframe(display_df, hide_index=True, width="stretch", height=400)

    if df is not None:
        with st.expander(f"\U0001f4e5 Monthly Emission Detail ({year_label})", expanded=False):
            detail_table = _build_monthly_detail(df, display_year, year_type)
            if detail_table is not None:
                st.dataframe(detail_table, hide_index=True, width="stretch", height=400)
            else:
                st.info(f"No emissions data for {year_label}")