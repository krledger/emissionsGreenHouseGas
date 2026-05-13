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
from calc_calendar import date_to_fy, date_to_cy, period_filter
from config import DEFAULT_GRID_CONNECTION_DATE

# Gold color palette
GOLD_METALLIC = '#DBB12A'
BRIGHT_GOLD = '#E8AC41'
DARK_GOLDENROD = '#AE8B0F'
SEPIA = '#734B1A'
CAFE_NOIR = '#39250B'
GRID_GREEN = '#2A9D8F'
PHASE_MARKER = '#888888'


def _add_phase_markers(fig, years_list, grid_connected_date,
                       end_mining_date, end_processing_date, end_rehabilitation_date):
    """Add phase transition vertical lines and top-aligned labels to a chart."""
    _GRID_GREEN = '#2A9D8F'
    _PHASE_GREY = '#888888'
    # Detect year type from label prefix
    _is_fy = any(str(y).startswith('FY') for y in years_list)
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
        yr = str(date_to_fy(dt)) if _is_fy else str(date_to_cy(dt))
        if yr not in years_set:
            continue
        fig.add_shape(type="line", x0=yr, x1=yr, y0=0, y1=1, yref="paper",
                     line=dict(color=colour, width=1.5, dash=dash))
        fig.add_annotation(x=yr, y=1.0, yref="paper", text=label, showarrow=False,
                          yshift=10 + i * 14, font=dict(size=9, color=colour))


def _build_raw_data_summary(df, start_date, end_date):
    """Build raw data summary table showing consumption and emissions by fuel type."""

    year_data = period_filter(df[df['DataSet'] == 'Actual'], start_date, end_date).copy()

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



def _build_monthly_detail(df, start_date, end_date):
    """Build monthly detail table for the selected year with NGA factors shown."""
    year_data = period_filter(df, start_date, end_date).copy()

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


def render_ghg_tab(df, precomputed, projection,
                   start_date=None, end_date=None, period_label='',
                   end_mining_date=None, end_processing_date=None,
                   end_rehabilitation_date=None):
    """Render Total GHG Emissions tab.

    Args:
        df: Raw DataFrame from load_all_data() (for detail tables only)
        precomputed: PrecomputedData (for raw monthly data)
        projection: Annual data frame (selected by app.py)
        start_date/end_date: Display period dates
        period_label: Display label e.g. 'CY2025'
        end_*_date: Phase boundary dates (for chart markers)
    """

    grid_connected_date = DEFAULT_GRID_CONNECTION_DATE

    _em_str = end_mining_date.strftime('%d %b %Y')
    _ep_str = end_processing_date.strftime('%d %b %Y')

    st.subheader("Total Greenhouse Gas Emissions")
    st.caption(f"Mining ends {_em_str} | Processing ends {_ep_str}")

    # Show data info
    actual_count = len(df[df['DataSet'] == 'Actual'])
    source_data = df[df['DataSet'] == 'Actual']

    if len(source_data) > 0:
        date_min = source_data['Date'].min()
        date_max = source_data['Date'].max()
        st.caption(f"{actual_count:,} records | Date Range: {date_min.strftime('%Y-%m')} to {date_max.strftime('%Y-%m')}")
    else:
        st.caption("No records found")

    display_single_source(projection, df,
                          start_date=start_date, end_date=end_date,
                          period_label=period_label,
                          grid_connected_date=grid_connected_date,
                          end_mining_date=end_mining_date,
                          end_processing_date=end_processing_date,
                          end_rehabilitation_date=end_rehabilitation_date)


def display_single_source(projection, df, show_summary=True,
                          start_date=None, end_date=None, period_label='',
                          grid_connected_date=None, end_mining_date=None,
                          end_processing_date=None, end_rehabilitation_date=None):
    """Display charts and tables for single data source"""

    year_label = period_label

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
                    'Intensity (tCO2-e/t)': f"{row['Total_Intensity']:.4f}" if row['ROM_Mt'] > 0 else "N/A"
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
            xaxis_title="Year",
            yaxis_title="Emissions (tCO2-e)",
            hovermode='x unified',
            height=500
        )

        _add_phase_markers(fig, projection_display['Year'].tolist(),
                          grid_connected_date, end_mining_date, end_processing_date,
                          end_rehabilitation_date)

        st.plotly_chart(fig, width="stretch")

    # Emissions breakdown Pareto charts
    with st.expander("Emissions Breakdown", expanded=False):
        st.caption(f"Breakdown for {year_label}")

        fy_data = period_filter(df[df['DataSet'] == 'Actual'], start_date, end_date).copy()

        if len(fy_data) == 0:
            st.warning(f"No data available for {year_label}")
        else:
            col1, col2 = st.columns(2)

            with col1:
                cc_emissions = fy_data.groupby('CostCentre', observed=False).agg({
                    'Scope1_tCO2e': 'sum', 'Scope2_tCO2e': 'sum', 'Scope3_tCO2e': 'sum'
                }).reset_index()
                cc_emissions['Total'] = cc_emissions['Scope1_tCO2e'] + cc_emissions['Scope2_tCO2e'] + cc_emissions['Scope3_tCO2e']
                cc_emissions = cc_emissions[cc_emissions['Total'] > 0]
                cc_emissions = cc_emissions.sort_values('Total', ascending=False).reset_index(drop=True)
                cc_emissions['Cumulative_Pct'] = cc_emissions['Total'].cumsum() / cc_emissions['Total'].sum() * 100

                fig_cc = make_subplots(specs=[[{"secondary_y": True}]])
                fig_cc.add_trace(go.Bar(
                    x=cc_emissions['CostCentre'], y=cc_emissions['Total'],
                    name='Emissions (tCO2-e)',
                    marker_color=GOLD_METALLIC
                ), secondary_y=False)
                fig_cc.add_trace(go.Scatter(
                    x=cc_emissions['CostCentre'], y=cc_emissions['Cumulative_Pct'],
                    name='Cumulative %', mode='lines+markers',
                    line=dict(color=CAFE_NOIR, width=2),
                    marker=dict(size=5, color=CAFE_NOIR)
                ), secondary_y=True)
                fig_cc.update_layout(title="By Cost Centre", height=500, showlegend=True,
                                    legend=dict(font=dict(size=10)),
                                    margin=dict(t=60, b=40, l=20, r=20))
                fig_cc.update_yaxes(title_text="Emissions (tCO2-e)", secondary_y=False)
                fig_cc.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
                fig_cc.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_cc, width="stretch", key="pareto_cc")

            with col2:
                dept_emissions = fy_data.groupby('Department', observed=False).agg({
                    'Scope1_tCO2e': 'sum', 'Scope2_tCO2e': 'sum', 'Scope3_tCO2e': 'sum'
                }).reset_index()
                dept_emissions['Total'] = dept_emissions['Scope1_tCO2e'] + dept_emissions['Scope2_tCO2e'] + dept_emissions['Scope3_tCO2e']
                dept_emissions = dept_emissions[dept_emissions['Total'] > 0]
                dept_emissions = dept_emissions.sort_values('Total', ascending=False).reset_index(drop=True)
                dept_emissions['Cumulative_Pct'] = dept_emissions['Total'].cumsum() / dept_emissions['Total'].sum() * 100

                fig_dept = make_subplots(specs=[[{"secondary_y": True}]])
                fig_dept.add_trace(go.Bar(
                    x=dept_emissions['Department'], y=dept_emissions['Total'],
                    name='Emissions (tCO2-e)',
                    marker_color=GOLD_METALLIC
                ), secondary_y=False)
                fig_dept.add_trace(go.Scatter(
                    x=dept_emissions['Department'], y=dept_emissions['Cumulative_Pct'],
                    name='Cumulative %', mode='lines+markers',
                    line=dict(color=CAFE_NOIR, width=2),
                    marker=dict(size=5, color=CAFE_NOIR)
                ), secondary_y=True)
                fig_dept.update_layout(title="By Department", height=500, showlegend=True,
                                      legend=dict(font=dict(size=10)),
                                      margin=dict(t=60, b=40, l=20, r=20))
                fig_dept.update_yaxes(title_text="Emissions (tCO2-e)", secondary_y=False)
                fig_dept.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
                fig_dept.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_dept, width="stretch", key="pareto_dept")

    # Sunburst: Department (inner) -> Cost Centre (outer) emissions breakdown
    with st.expander("Emissions by Department & Cost Centre", expanded=False):
        st.caption(f"Emissions breakdown for {year_label} (actuals)")

        sun_data = period_filter(df[df['DataSet'] == 'Actual'], start_date, end_date).copy()

        if len(sun_data) == 0 or 'Department' not in sun_data.columns or 'CostCentre' not in sun_data.columns:
            st.warning(f"No data available for {year_label}")
        else:
            sun_data['Total'] = (
                sun_data['Scope1_tCO2e'] + sun_data['Scope2_tCO2e'] + sun_data['Scope3_tCO2e']
            )
            sun_grouped = sun_data.groupby(['Department', 'CostCentre'], observed=False)['Total'].sum().reset_index()
            sun_grouped = sun_grouped[sun_grouped['Total'] > 0].sort_values('Total', ascending=False)

            if len(sun_grouped) > 0:
                grand_total = sun_grouped['Total'].sum()
                _dept_threshold_pct = 2  # Departments below this % are bucketed into "Other"

                # Consolidate small departments into "Other"
                dept_totals = sun_grouped.groupby('Department')['Total'].sum().sort_values(ascending=False)
                major_depts = dept_totals[dept_totals / grand_total * 100 >= _dept_threshold_pct].index.tolist()
                minor_depts = dept_totals[dept_totals / grand_total * 100 < _dept_threshold_pct].index.tolist()

                if minor_depts:
                    sun_grouped['Department'] = sun_grouped['Department'].apply(
                        lambda d: d if d in major_depts else 'Other'
                    )
                    sun_grouped = sun_grouped.groupby(['Department', 'CostCentre'], as_index=False)['Total'].sum()
                    sun_grouped = sun_grouped[sun_grouped['Total'] > 0].sort_values('Total', ascending=False)

                # Build sunburst: Department (inner) -> Cost Centre (outer)
                sun_ids = []
                sun_labels = []
                sun_parents = []
                sun_values = []
                sun_colors = []

                dept_color_map = {}
                dept_colors = [
                    GOLD_METALLIC, BRIGHT_GOLD, DARK_GOLDENROD, SEPIA, CAFE_NOIR,
                    '#D4A017', '#C9AE5D', '#B8860B', '#9B7653', '#8B7355',
                ]
                dept_order = sun_grouped.groupby('Department')['Total'].sum().sort_values(ascending=False).index.tolist()
                for i, d in enumerate(dept_order):
                    dept_color_map[d] = dept_colors[i % len(dept_colors)]

                # Inner ring: Departments
                for d in dept_order:
                    d_total = sun_grouped[sun_grouped['Department'] == d]['Total'].sum()
                    pct = d_total / grand_total * 100
                    sun_ids.append(d)
                    sun_labels.append(f"{d}<br>{pct:.0f}%")
                    sun_parents.append('')
                    sun_values.append(d_total)
                    sun_colors.append(dept_color_map[d])

                # Outer ring: Cost Centres under each Department
                # Consolidate small cost centres within "Other" department
                for _, row in sun_grouped.iterrows():
                    cc_pct = row['Total'] / grand_total * 100
                    if row['Department'] == 'Other':
                        cc_name = 'Other'
                        cc_id = 'Other/Other'
                    else:
                        cc_name = row['CostCentre']
                        cc_id = f"{row['Department']}/{row['CostCentre']}"

                    if cc_id in sun_ids:
                        idx = sun_ids.index(cc_id)
                        sun_values[idx] += row['Total']
                        continue

                    if cc_pct >= 3:
                        label = f"{cc_name}<br>{row['Total']:,.0f}"
                    elif cc_pct >= 1:
                        label = cc_name
                    else:
                        label = ''
                    sun_ids.append(cc_id)
                    sun_labels.append(label)
                    sun_parents.append(row['Department'])
                    sun_values.append(row['Total'])
                    base = dept_color_map[row['Department']]
                    r, g, b = int(base[1:3], 16), int(base[3:5], 16), int(base[5:7], 16)
                    sun_colors.append(f'rgba({min(r+40,255)},{min(g+40,255)},{min(b+40,255)},0.85)')

                fig_sun = go.Figure(go.Sunburst(
                    ids=sun_ids,
                    labels=sun_labels,
                    parents=sun_parents,
                    values=sun_values,
                    marker=dict(colors=sun_colors, line=dict(width=1.5, color='white')),
                    branchvalues='total',
                    textinfo='label',
                    insidetextorientation='radial',
                    hovertemplate='%{label}<br>%{value:,.0f} tCO2-e<extra></extra>'
                ))

                fig_sun.update_layout(
                    title=f"Emissions by Department & Cost Centre ({year_label})",
                    height=550,
                    margin=dict(t=60, b=20, l=20, r=20),
                    font=dict(size=12)
                )

                col_sun, col_tbl = st.columns([3, 2])
                with col_sun:
                    st.plotly_chart(fig_sun, width="stretch", key="sunburst_dept_cc")

                with col_tbl:
                    # Department summary table
                    _dept_sums = sun_data.groupby('Department', observed=False)['Total'].sum().sort_values(ascending=False)
                    _dept_sums = _dept_sums[_dept_sums > 0]

                    tbl_rows = []
                    for dept, dept_total in _dept_sums.items():
                        dept_pct = dept_total / grand_total * 100
                        tbl_rows.append({
                            'Department': dept,
                            'tCO2-e': dept_total,
                            '%': dept_pct
                        })

                    _sun_tbl_df = pd.DataFrame(tbl_rows)
                    _sun_tbl_df['tCO2-e'] = _sun_tbl_df['tCO2-e'].apply(lambda x: f"{x:,.0f}")
                    _sun_tbl_df['%'] = _sun_tbl_df['%'].apply(lambda x: f"{x:.1f}")
                    st.dataframe(_sun_tbl_df, hide_index=True, width='stretch')

    # Emissions intensity charts
    # Emissions intensity - dual axis line chart (full lifecycle)
    with st.expander("Emissions Intensity", expanded=False):
        st.caption("Total emissions intensity - actuals and budget (full lifecycle)")

        # Calculate gold intensity per year across full projection
        # Gold recovered (oz) from raw df - deduplicated actual/budget
        _is_fy = projection['FY'].iloc[0].startswith('FY') if len(projection) > 0 else True
        _end_mining_yr = date_to_fy(end_mining_date) if _is_fy else date_to_cy(end_mining_date)
        _gold_intensity = []
        for _, row in projection.iterrows():
            fy_label = row['FY']
            # Use Date column from annual frame to derive period range
            _period_start = pd.Timestamp(row['Date'])
            if _is_fy:
                _period_end = _period_start + pd.DateOffset(years=1)
            else:
                _period_end = _period_start + pd.DateOffset(years=1)
            fy_raw = period_filter(df, _period_start, _period_end)

            # Deduplicate: prefer actuals over budget for overlapping months
            gold_oz = 0
            if 'CommonName' in fy_raw.columns:
                gold_mask = fy_raw['CommonName'].astype(str) == 'Gold recovered'
                if 'RowType' in fy_raw.columns:
                    gold_mask = gold_mask & (fy_raw['RowType'].astype(str) == 'production')
                gold_rows = fy_raw.loc[gold_mask].copy()
                if len(gold_rows) > 0 and 'DataSet' in gold_rows.columns:
                    gold_rows['_month'] = gold_rows['Date'].dt.to_period('M')
                    actual_months = set(gold_rows.loc[gold_rows['DataSet'] == 'Actual', '_month'])
                    gold_rows = gold_rows[
                        (gold_rows['DataSet'] == 'Actual') |
                        (~gold_rows['_month'].isin(actual_months))
                    ]
                    gold_oz = gold_rows['Quantity'].sum()

            total_e = row['Scope1'] + row['Scope2'] + row['Scope3']
            fy_num = int(fy_label.replace('FY', '').replace('CY', ''))
            gold_int = total_e / gold_oz if gold_oz > 0 and total_e > 0 else None
            _gold_intensity.append({
                'FY': fy_label,
                'Gold_oz': gold_oz,
                'Gold_Intensity': gold_int,
                'ROM_Intensity': total_e / (row['ROM_Mt'] * 1e6) if row['ROM_Mt'] > 0 and fy_num < _end_mining_yr else None
            })

        intensity_df = pd.DataFrame(_gold_intensity)

        if len(intensity_df) > 0:
            fig_int = make_subplots(specs=[[{"secondary_y": True}]])

            # Left axis (primary): tCO2-e per oz gold recovered
            gold_valid = intensity_df[intensity_df['Gold_Intensity'].notna()]
            if len(gold_valid) > 0:
                fig_int.add_trace(go.Scatter(
                    x=gold_valid['FY'], y=gold_valid['Gold_Intensity'],
                    name='tCO2-e / oz Au',
                    mode='lines+markers',
                    line=dict(color=GOLD_METALLIC, width=2.5, shape='spline', smoothing=0.7),
                    marker=dict(size=4)
                ), secondary_y=False)

                # Linear trend line for gold intensity (target trajectory)
                import numpy as np
                _gx = np.arange(len(gold_valid))
                _gy = gold_valid['Gold_Intensity'].values
                _coeffs = np.polyfit(_gx, _gy, 1)
                _trend_y = np.polyval(_coeffs, _gx) + 0.2
                fig_int.add_trace(go.Scatter(
                    x=gold_valid['FY'].values, y=_trend_y,
                    name='Gold Intensity Trend',
                    mode='lines',
                    line=dict(color=DARK_GOLDENROD, width=1.5, dash='dash'),
                    hoverinfo='skip'
                ), secondary_y=False)

            # Right axis (secondary): tCO2-e per tonne ROM
            rom_valid = intensity_df[intensity_df['ROM_Intensity'].notna()]
            if len(rom_valid) > 0:
                fig_int.add_trace(go.Scatter(
                    x=rom_valid['FY'], y=rom_valid['ROM_Intensity'],
                    name='tCO2-e / t ROM',
                    mode='lines+markers',
                    line=dict(color='#888888', width=2, shape='spline', smoothing=0.7),
                    marker=dict(size=4)
                ), secondary_y=True)

            fig_int.update_layout(
                title="Emissions Intensity - tCO2-e per Ounce Gold & per Tonne ROM",
                height=500, hovermode='x unified',
                legend=dict(orientation='h', yanchor='bottom', y=1.02,
                            xanchor='right', x=1)
            )
            fig_int.update_yaxes(title_text="tCO2-e / oz Au", secondary_y=False)
            fig_int.update_yaxes(title_text="tCO2-e / t ROM", secondary_y=True)
            fig_int.update_xaxes(title_text="Year")

            # Shaded phase regions using numeric xref positions
            _years_list = projection['FY'].tolist()
            _year_to_idx = {yr: i for i, yr in enumerate(_years_list)}
            _phase_boundaries = [
                (None, end_mining_date, "Mining", "rgba(42,157,143,0.08)"),
                (end_mining_date, end_processing_date, "Processing", "rgba(219,177,42,0.10)"),
                (end_processing_date, end_rehabilitation_date, "Rehabilitation", "rgba(136,136,136,0.10)"),
            ]
            for _pb_start, _pb_end, _pb_label, _pb_color in _phase_boundaries:
                if _pb_end is None:
                    continue
                if _pb_start is None:
                    _x0_cat = _years_list[0]
                elif _is_fy:
                    _x0_cat = f'FY{date_to_fy(_pb_start)}'
                else:
                    _x0_cat = f'CY{date_to_cy(_pb_start)}'
                if _is_fy:
                    _x1_cat = f'FY{date_to_fy(_pb_end)}'
                else:
                    _x1_cat = f'CY{date_to_cy(_pb_end)}'
                # Convert to numeric index positions for reliable rendering
                # First region extends left to -0.5, last extends right to +0.5
                # Boundaries between regions sit at the category centre (no overlap)
                _i0 = _year_to_idx.get(_x0_cat, 0) - 0.5 if _pb_start is None else _year_to_idx.get(_x0_cat, 0)
                _i1_default = len(_years_list) - 1
                _i1 = _year_to_idx.get(_x1_cat, _i1_default)
                fig_int.add_shape(
                    type="rect", x0=_i0, x1=_i1,
                    y0=0, y1=1, yref="paper",
                    fillcolor=_pb_color, layer="below", line_width=0
                )
                # Label inside shading, left-aligned
                _label_idx = max(_i0, -0.5) + 0.5
                _label_x = _years_list[max(int(_label_idx), 0)]
                fig_int.add_annotation(
                    x=_label_x, y=1.0, yref="paper",
                    text=_pb_label, showarrow=False,
                    font=dict(size=10, color='rgba(0,0,0,0.35)'),
                    xanchor="left", yanchor="bottom", xshift=6, yshift=4
                )

            st.plotly_chart(fig_int, width="stretch", key="intensity_dual")
        else:
            st.info("No intensity data available")

    if df is not None:
        with st.expander(f"\U0001f4cb Fuel Consumption Detail ({year_label})", expanded=False):
            raw_table = _build_raw_data_summary(df, start_date, end_date)
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
            detail_table = _build_monthly_detail(df, start_date, end_date)
            if detail_table is not None:
                st.dataframe(detail_table, hide_index=True, width="stretch", height=400)
            else:
                st.info(f"No emissions data for {year_label}")