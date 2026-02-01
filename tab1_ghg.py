"""
tab1_ghg.py
Total GHG Emissions tab - combined comparison charts
Last updated: 2026-02-02 09:50 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection
from config import CREDIT_START_FY

# Gold color palette
GOLD_METALLIC = '#DBB12A'      # Primary - Scope 1
BRIGHT_GOLD = '#E8AC41'         # Secondary - Scope 2
DARK_GOLDENROD = '#AE8B0F'     # Tertiary - Scope 3
SEPIA = '#734B1A'              # Accent
CAFE_NOIR = '#39250B'          # Lines
GRID_GREEN = '#2A9D8F'         # Grid connection marker


def render_ghg_tab(df, selected_source, fsei_rom, fsei_elec,
                   start_fy, end_fy, grid_connected_fy,
                   end_mining_fy, end_processing_fy, end_rehabilitation_fy):
    """Render Total GHG Emissions tab

    Args:
        df: Unified DataFrame from load_all_data()
        selected_source: 'Base', 'NPI-NGERS', or 'All'
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        start_fy through end_rehabilitation_fy: Projection parameters
    """

    st.subheader("Total Greenhouse Gas Emissions")
    st.caption(f"Projection Period: FY{start_fy}—FY{end_fy} | Mining ends FY{end_mining_fy} | Processing ends FY{end_processing_fy}")

    display_year = st.session_state.get('display_year', 2025)

    # Comparison mode
    if selected_source == 'All':

        # Build projections for both sources
        proj_base = build_projection(
            df, dataset='Base',
            end_mining_fy=end_mining_fy,
            end_processing_fy=end_processing_fy,
            end_rehabilitation_fy=end_rehabilitation_fy,
            grid_connected_fy=grid_connected_fy,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_fy=CREDIT_START_FY,
            start_fy=start_fy,
            end_fy=end_fy
        )

        proj_npi = build_projection(
            df, dataset='NPI-NGERS',
            end_mining_fy=end_mining_fy,
            end_processing_fy=end_processing_fy,
            end_rehabilitation_fy=end_rehabilitation_fy,
            grid_connected_fy=grid_connected_fy,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_fy=CREDIT_START_FY,
            start_fy=start_fy,
            end_fy=end_fy
        )

        display_comparison(proj_base, proj_npi, display_year, grid_connected_fy, df)
        return

    # Single source mode
    projection = build_projection(
        df, dataset=selected_source,
        end_mining_fy=end_mining_fy,
        end_processing_fy=end_processing_fy,
        end_rehabilitation_fy=end_rehabilitation_fy,
        grid_connected_fy=grid_connected_fy,
        fsei_rom=fsei_rom,
        fsei_elec=fsei_elec,
        credit_start_fy=CREDIT_START_FY,
        start_fy=start_fy,
        end_fy=end_fy
    )

    # Show data info
    actual_count = len(df[df['DataSet'] == selected_source])
    source_data = df[df['DataSet'] == selected_source]

    if len(source_data) > 0:
        date_min = source_data['Date'].min()
        date_max = source_data['Date'].max()
        st.caption(f"📊 {actual_count:,} records | Date Range: {date_min.strftime('%Y-%m')} to {date_max.strftime('%Y-%m')}")
    else:
        st.caption(f"📊 No records found for {selected_source}")

    display_single_source(projection, display_year, selected_source, grid_connected_fy, df)


def display_single_source(projection, display_year, source_name, grid_connected_fy, df, show_summary=True):
    """Display charts and tables for single data source"""

    # Summary table
    if show_summary:
        with st.expander("📊 Emissions Summary", expanded=True):
            year_data = projection[projection['FY'] == f'FY{display_year}']

            if len(year_data) == 0:
                st.warning(f"⚠️ No data for FY{display_year}")
            else:
                row = year_data.iloc[0]

                summary_data = [{
                    'Source': source_name,
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Scope 2 (tCO2-e)': f"{row['Scope2']:,.0f}",
                    'Scope 3 (tCO2-e)': f"{row['Scope3']:,.0f}",
                    'Total (tCO2-e)': f"{row['Total']:,.0f}",
                    'Intensity (tCO2-e/t)': f"{row['Emission_Intensity']:.4f}" if row['ROM_Mt'] > 0 else "N/A"
                }]

                st.dataframe(pd.DataFrame(summary_data), hide_index=True, width="stretch")

    # Charts
    with st.expander("📈 Emissions Charts", expanded=True):

        # Stacked area chart
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Scope1'],
            name='Scope 1',
            mode='lines',
            fill='tonexty',
            line=dict(color=GOLD_METALLIC, width=2),
            stackgroup='one'
        ))

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Scope2'],
            name='Scope 2',
            mode='lines',
            fill='tonexty',
            line=dict(color=BRIGHT_GOLD, width=2),
            stackgroup='one'
        ))

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Scope3'],
            name='Scope 3',
            mode='lines',
            fill='tonexty',
            line=dict(color=DARK_GOLDENROD, width=2),
            stackgroup='one'
        ))

        fig.update_layout(
            title="Total GHG Emissions by Scope",
            xaxis_title="Financial Year",
            yaxis_title="Emissions (tCO2-e)",
            hovermode='x unified',
            height=500
        )

        # Add grid connection marker
        if grid_connected_fy and f'FY{grid_connected_fy}' in projection['FY'].values:
            fig.add_shape(
                type="line",
                x0=f'FY{grid_connected_fy}',
                x1=f'FY{grid_connected_fy}',
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color=GRID_GREEN, width=2, dash="dot")
            )
            fig.add_annotation(
                x=f'FY{grid_connected_fy}',
                y=1,
                yref="paper",
                text="Grid Connection",
                showarrow=False,
                yshift=10
            )

        st.plotly_chart(fig, width="stretch")

    # Emissions breakdown pie charts (Cost Centre and Department)
    with st.expander("🥧 Emissions Breakdown", expanded=False):
        st.caption(f"Breakdown for FY{display_year}")

        # Get FY data from df
        fy_data = df[(df['FY'] == display_year) & (df['DataSet'] == source_name)].copy()

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
                cc_emissions = fy_data.groupby('CostCentre').agg({
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
                    textposition='auto',
                    textinfo='label+percent',
                    marker=dict(colors=gold_colors[:len(cc_emissions)])
                )])

                fig_cc.update_layout(
                    title="By Cost Centre",
                    height=500,
                    showlegend=True,
                    margin=dict(t=60, b=100, l=20, r=20)
                )

                st.plotly_chart(fig_cc, width="stretch", key=f"pie_cc_{source_name}")

            with col2:
                # Department breakdown
                dept_emissions = fy_data.groupby('Department').agg({
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
                    textposition='auto',
                    textinfo='label+percent',
                    marker=dict(colors=gold_colors[:len(dept_emissions)])
                )])

                fig_dept.update_layout(
                    title="By Department",
                    height=500,
                    showlegend=True,
                    margin=dict(t=60, b=100, l=20, r=20)
                )

                st.plotly_chart(fig_dept, width="stretch", key=f"pie_dept_{source_name}")

    # Data table (moved to bottom)
    with st.expander("📋 Emissions Data Table", expanded=False):
        display_df = projection[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total']].copy()
        display_df['ROM_Mt'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}")
        display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope2'] = display_df['Scope2'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope3'] = display_df['Scope3'].apply(lambda x: f"{x:,.0f}")
        display_df['Total'] = display_df['Total'].apply(lambda x: f"{x:,.0f}")

        st.dataframe(display_df, hide_index=True, width="stretch", height=400)


def display_comparison(proj_base, proj_npi, display_year, grid_connected_fy, df):
    """Display comparison between Base and NPI-NGERS with combined charts"""

    # Combined summary table
    with st.expander("📊 Summary", expanded=True):
        year_base = proj_base[proj_base['FY'] == f'FY{display_year}']
        year_npi = proj_npi[proj_npi['FY'] == f'FY{display_year}']

        if len(year_base) == 0 or len(year_npi) == 0:
            st.warning(f"⚠️ No data for FY{display_year}")
        else:
            row_base = year_base.iloc[0]
            row_npi = year_npi.iloc[0]

            # Create comparison table
            comparison_data = [
                {
                    'Source': 'Base',
                    'ROM (Mt)': f"{row_base['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row_base['Scope1']:,.0f}",
                    'Scope 2 (tCO2-e)': f"{row_base['Scope2']:,.0f}",
                    'Scope 3 (tCO2-e)': f"{row_base['Scope3']:,.0f}",
                    'Total (tCO2-e)': f"{row_base['Total']:,.0f}",
                    'Intensity (tCO2-e/t)': f"{row_base['Emission_Intensity']:.4f}" if row_base['ROM_Mt'] > 0 else "N/A"
                },
                {
                    'Source': 'NPI-NGERS',
                    'ROM (Mt)': f"{row_npi['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row_npi['Scope1']:,.0f}",
                    'Scope 2 (tCO2-e)': f"{row_npi['Scope2']:,.0f}",
                    'Scope 3 (tCO2-e)': f"{row_npi['Scope3']:,.0f}",
                    'Total (tCO2-e)': f"{row_npi['Total']:,.0f}",
                    'Intensity (tCO2-e/t)': f"{row_npi['Emission_Intensity']:.4f}" if row_npi['ROM_Mt'] > 0 else "N/A"
                }
            ]

            df_comparison = pd.DataFrame(comparison_data)
            st.dataframe(df_comparison, hide_index=True, width="stretch")

            # Variance summary
            diff_total = row_npi['Total'] - row_base['Total']
            pct_diff = ((row_npi['Total'] - row_base['Total']) / row_base['Total'] * 100) if row_base['Total'] > 0 else 0
            if abs(pct_diff) > 0.1:
                st.caption(f"Variance: {diff_total:+,.0f} tCO2-e ({pct_diff:+.1f}%)")

    # Combined comparison charts in single frame
    with st.expander("📈 Emissions Charts", expanded=True):

        # Stacked vertical comparison
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Base', 'NPI-NGERS'),
            vertical_spacing=0.12,
            row_heights=[0.5, 0.5]
        )

        # Base (top chart)
        fig.add_trace(go.Scatter(
            x=proj_base['FY'], y=proj_base['Scope1'],
            name='Scope 1', line=dict(color=GOLD_METALLIC, width=2),
            fill='tonexty', stackgroup='base',
            hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=proj_base['FY'], y=proj_base['Scope2'],
            name='Scope 2', line=dict(color=BRIGHT_GOLD, width=2),
            fill='tonexty', stackgroup='base',
            hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=proj_base['FY'], y=proj_base['Scope3'],
            name='Scope 3', line=dict(color=DARK_GOLDENROD, width=2),
            fill='tonexty', stackgroup='base',
            hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
        ), row=1, col=1)

        # NPI (bottom chart) - use prime notation for proper hover labels
        fig.add_trace(go.Scatter(
            x=proj_npi['FY'], y=proj_npi['Scope1'],
            name="Scope 1'",
            line=dict(color=GOLD_METALLIC, width=2),
            fill='tonexty', stackgroup='npi', showlegend=False,
            hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=proj_npi['FY'], y=proj_npi['Scope2'],
            name="Scope 2'",
            line=dict(color=BRIGHT_GOLD, width=2),
            fill='tonexty', stackgroup='npi', showlegend=False,
            hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=proj_npi['FY'], y=proj_npi['Scope3'],
            name="Scope 3'",
            line=dict(color=DARK_GOLDENROD, width=2),
            fill='tonexty', stackgroup='npi', showlegend=False,
            hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
        ), row=2, col=1)

        fig.update_layout(
            height=700,
            hovermode='x unified',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_xaxes(title_text="Financial Year", row=2, col=1)
        fig.update_yaxes(title_text="Emissions (tCO2-e)", row=1, col=1)
        fig.update_yaxes(title_text="Emissions (tCO2-e)", row=2, col=1)

        # Add grid connection markers to both charts
        if grid_connected_fy and f'FY{grid_connected_fy}' in proj_base['FY'].values:
            # Top chart (Base)
            fig.add_shape(
                type="line",
                x0=f'FY{grid_connected_fy}',
                x1=f'FY{grid_connected_fy}',
                y0=0,
                y1=1,
                yref="y domain",
                line=dict(color=GRID_GREEN, width=2, dash="dot"),
                row=1, col=1
            )
            fig.add_annotation(
                x=f'FY{grid_connected_fy}',
                y=1,
                yref="y domain",
                text="Grid",
                showarrow=False,
                yshift=10,
                row=1, col=1
            )
            # Bottom chart (NPI-NGERS)
            fig.add_shape(
                type="line",
                x0=f'FY{grid_connected_fy}',
                x1=f'FY{grid_connected_fy}',
                y0=0,
                y1=1,
                yref="y2 domain",
                line=dict(color=GRID_GREEN, width=2, dash="dot"),
                row=2, col=1
            )
            fig.add_annotation(
                x=f'FY{grid_connected_fy}',
                y=1,
                yref="y2 domain",
                text="Grid",
                showarrow=False,
                yshift=10,
                row=2, col=1
            )

        st.plotly_chart(fig, width="stretch")

    # Emissions breakdown pie charts (Cost Centre and Department)
    with st.expander("🥧 Emissions Breakdown", expanded=False):
        st.caption(f"Breakdown for FY{display_year}")

        # Get FY data from df (actuals + budget)
        fy_data = df[df['FY'] == display_year].copy()

        if len(fy_data) == 0:
            st.warning(f"No data available for FY{display_year}")
        else:
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

            # Cost Centre breakdown
            st.markdown("**By Cost Centre**")
            col1, col2 = st.columns(2)

            for idx, (dataset, col) in enumerate([('Base', col1), ('NPI-NGERS', col2)]):
                dataset_data = fy_data[fy_data['DataSet'] == dataset]

                if len(dataset_data) == 0:
                    continue

                # Aggregate emissions by Cost Centre
                cc_emissions = dataset_data.groupby('CostCentre', observed=False).agg({
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

                with col:
                    st.markdown(f"*{dataset}*")

                    fig_pie = go.Figure(data=[go.Pie(
                        labels=cc_emissions['CostCentre'],
                        values=cc_emissions['Total'],
                        hole=0.3,
                        textposition='auto',
                        textinfo='label+percent',
                        marker=dict(colors=gold_colors[:len(cc_emissions)])
                    )])

                    fig_pie.update_layout(
                        height=450,
                        showlegend=False,
                        margin=dict(t=30, b=100, l=20, r=20)
                    )

                    st.plotly_chart(fig_pie, width="stretch", key=f"pie_cc_comp_{dataset}")

            # Department breakdown
            st.markdown("**By Department**")
            col3, col4 = st.columns(2)

            for idx, (dataset, col) in enumerate([('Base', col3), ('NPI-NGERS', col4)]):
                dataset_data = fy_data[fy_data['DataSet'] == dataset]

                if len(dataset_data) == 0:
                    continue

                # Aggregate emissions by Department
                dept_emissions = dataset_data.groupby('Department', observed=False).agg({
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

                with col:
                    st.markdown(f"*{dataset}*")

                    fig_pie = go.Figure(data=[go.Pie(
                        labels=dept_emissions['Department'],
                        values=dept_emissions['Total'],
                        hole=0.3,
                        textposition='auto',
                        textinfo='label+percent',
                        marker=dict(colors=gold_colors[:len(dept_emissions)])
                    )])

                    fig_pie.update_layout(
                        height=450,
                        showlegend=False,
                        margin=dict(t=30, b=100, l=20, r=20)
                    )

                    st.plotly_chart(fig_pie, width="stretch", key=f"pie_dept_comp_{dataset}")