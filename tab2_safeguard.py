"""
tab2_safeguard.py
Safeguard Mechanism Tab with Plotly charts
Last updated: 2026-01-27 17:00 AEST

NOTE: This tab ALWAYS uses NGER Financial Year (July-June) as required by legislation.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

from projections import build_projection_simple
from config import DECLINE_RATE, DECLINE_FROM, DECLINE_TO, COLORS, SCOPE_NAMES, NGER_FY_START_MONTH


def render_safeguard_tab(rom_df, energy_df, nga_factors, fsei_rom, fsei_elec,
                         start_fy, end_fy, grid_connected_fy,
                         end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                         carbon_credit_price, credit_start_fy):
    """Render the Safeguard Mechanism tab

    NOTE: This tab always uses NGER FY (July-June) regardless of sidebar setting.
    """

    st.subheader("Safeguard Mechanism Compliance")
    # Subtitle removed - not helpful

    # Build projection (always uses NGER FY for Safeguard)
    projection = build_projection_simple(
        start_fy, end_fy, rom_df, energy_df, nga_factors,
        fsei_rom, fsei_elec, grid_connected_fy,
        end_mining_fy, end_processing_fy, end_rehabilitation_fy,
        credit_start_fy
    )

    # Calculate safeguard threshold
    safeguard_threshold = 100000  # tCO2-e
    projection['In_Safeguard'] = projection['Scope1'] >= safeguard_threshold

    # Summary metrics
    display_safeguard_metrics(projection, carbon_credit_price)

    # Charts
    display_safeguard_charts(projection, grid_connected_fy, carbon_credit_price)

    # Data table
    display_safeguard_table(projection, safeguard_threshold, carbon_credit_price)

    # Report generation
    display_report_generator(projection)


def display_safeguard_metrics(projection, carbon_credit_price):
    """Display safeguard compliance metrics"""

    with st.expander("📊 Compliance Summary", expanded=True):
        col1, col2, col3, col4 = st.columns(4)

        total_smc_credits = abs(projection['SMC_Cumulative'].iloc[-1])
        years_in_safeguard = projection['In_Safeguard'].sum()
        avg_intensity = projection[projection['ROM_Mt'] > 0]['Emission_Intensity'].mean()

        # Find safeguard entry and exit years
        safeguard_years = projection[projection['In_Safeguard']]['FY'].tolist()
        entry_year = safeguard_years[0] if safeguard_years else "—"
        exit_year = safeguard_years[-1] if safeguard_years else "—"

        with col1:
            st.metric("Total SMC Credits", f"{total_smc_credits:,.0f} tCO₂-e")
            st.caption(f"Worth ${total_smc_credits * carbon_credit_price:,.0f}")

        with col2:
            st.metric("Years in Safeguard", f"{years_in_safeguard}")
            st.caption(f"Scope 1 ≥ 100,000 tCO₂-e")

        with col3:
            st.metric("Avg Intensity", f"{avg_intensity:.4f} tCO₂-e/t")
            st.caption("While producing ROM")

        with col4:
            if len(safeguard_years) > 0:
                st.metric("Safeguard Period", f"{entry_year}—{exit_year}")
            else:
                st.metric("Safeguard Exit", "—")
            st.caption("Entry to exit")


def display_safeguard_charts(projection, grid_connected_fy, carbon_credit_price):
    """Display Plotly charts for safeguard compliance

    Includes:
    - Horizontal line at 100,000 tCO2-e threshold
    - Vertical shading for 10-year grace period from grid connection
    """

    # Don't filter - show ALL years including processing/rehab
    safeguard_df = projection.copy()

    if len(safeguard_df) == 0:
        st.warning("No projection data available")
        return

    with st.expander("📈 Safeguard Position", expanded=True):

        # Chart 1: ROM Production (only show years with ROM > 0)
        rom_df = safeguard_df[safeguard_df['ROM_Mt'] > 0].copy()

        if len(rom_df) > 0:
            st.subheader("ROM Production")

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=rom_df['FY'],
                y=rom_df['ROM_Mt'],
                name='ROM Production',
                marker=dict(
                    color=COLORS['rom'],
                    line=dict(width=0)  # No border
                ),
                hovertemplate='<b>%{x}</b><br>ROM: %{y:.2f} Mt<extra></extra>'
            ))

            fig.update_layout(
                height=300,
                xaxis_title='Financial Year',
                yaxis_title='ROM Production (Mt)',
                yaxis_tickformat='.1f',
                showlegend=False
            )

            st.plotly_chart(fig, width="stretch")
            # Caption removed

        # Chart 2: Emissions and Intensity (Dual Axis) - ALL years for bars
        st.subheader("Scope 1 Emissions & Emission Intensity")

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Scope 1 emissions (bars on primary y-axis) - ALL years
        fig.add_trace(
            go.Bar(
                x=safeguard_df['FY'],
                y=safeguard_df['Scope1'],
                name='Scope 1 Emissions',
                marker=dict(
                    color='#BDC3C7',  # Light gray bars
                    line=dict(width=0)  # No border
                ),
                hovertemplate='<b>%{x}</b><br>Scope 1: %{y:,.0f} tCO₂-e<extra></extra>',
                yaxis='y'
            ),
            secondary_y=False
        )

        # For intensity lines, only show years with ROM > 0
        intensity_df = safeguard_df[safeguard_df['ROM_Mt'] > 0].copy()

        if len(intensity_df) > 0:
            # Actual intensity (line on secondary y-axis)
            fig.add_trace(
                go.Scatter(
                    x=intensity_df['FY'],
                    y=intensity_df['Emission_Intensity'],
                    name='Actual Intensity',
                    mode='lines+markers',
                    line=dict(color=COLORS['actual_intensity'], width=3),
                    marker=dict(size=8),
                    hovertemplate='<b>%{x}</b><br>Actual: %{y:.4f} tCO₂-e/t<extra></extra>',
                    yaxis='y2'
                ),
                secondary_y=True
            )

            # Baseline intensity (line on secondary y-axis) - wider and more visible
            fig.add_trace(
                go.Scatter(
                    x=intensity_df['FY'],
                    y=intensity_df['Baseline_Intensity'],
                    name='Baseline',
                    mode='lines',
                    line=dict(color=COLORS['baseline'], width=3, dash='dash'),
                    hovertemplate='<b>%{x}</b><br>Baseline: %{y:.4f} tCO₂-e/t<extra></extra>',
                    yaxis='y2'
                ),
                secondary_y=True
            )

        # Add grid connection marker
        fig.add_shape(
            type='line',
            x0=f'FY{grid_connected_fy}',
            x1=f'FY{grid_connected_fy}',
            y0=0,
            y1=1,
            yref='paper',
            line=dict(color='green', width=2, dash='dot')
        )

        fig.add_annotation(
            x=f'FY{grid_connected_fy}',
            y=1,
            yref='paper',
            text='Grid Connected',
            showarrow=False,
            yshift=10
        )

        # Add 100,000 tCO2-e safeguard threshold line (red dashed)
        # Only span the actual data range, not the full plot width
        fig.add_trace(
            go.Scatter(
                x=safeguard_df['FY'],
                y=[100000] * len(safeguard_df),
                mode='lines',
                line=dict(color='red', width=2, dash='dash'),
                showlegend=False,
                hoverinfo='skip',
                yaxis='y'
            )
        )



        # Add 10-year grace period shading from grid connection
        grace_period_end = grid_connected_fy + 10
        fig.add_vrect(
            x0=f'FY{grid_connected_fy}',
            x1=f'FY{grace_period_end}',
            fillcolor='lightgreen',
            opacity=0.2,
            layer='below',
            line_width=0
        )

        fig.add_annotation(
            x=f'FY{grid_connected_fy + 5}',
            y=0.95,
            yref='paper',
            text='10-Year Grace Period',
            showarrow=False,
            font=dict(color='darkgreen', size=10)
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year")
        fig.update_yaxes(title_text="Scope 1 Emissions (tCO₂-e)", tickformat=',.0f', secondary_y=False)
        fig.update_yaxes(title_text="Emission Intensity (tCO₂-e/t)", tickformat='.4f', secondary_y=True)

        fig.update_layout(
            height=400,
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig, width="stretch")
        # Caption removed

        # Chart 3: Cumulative SMC Credits (Dual Axis)
        st.subheader("Cumulative SMC Credits")

        # Display credits as positive
        safeguard_df['Credits_Display'] = (-1 * safeguard_df['SMC_Cumulative']).abs()
        safeguard_df['Credits_Value'] = safeguard_df['Credits_Display'] * carbon_credit_price

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Tonnes on primary y-axis (bars)
        fig.add_trace(
            go.Bar(
                x=safeguard_df['FY'],
                y=safeguard_df['Credits_Display'],
                name='Credits (tCO₂-e)',
                marker=dict(
                    color=COLORS['credits'],
                    line=dict(width=0)
                ),
                hovertemplate='<b>%{x}</b><br>Credits: %{y:,.0f} tCO₂-e<extra></extra>',
                yaxis='y'
            ),
            secondary_y=False
        )

        # Dollars on secondary y-axis (markers with dollar labels)
        fig.add_trace(
            go.Scatter(
                x=safeguard_df['FY'],
                y=safeguard_df['Credits_Value'],
                name='Credit Value ($)',
                mode='markers+text',
                marker=dict(size=10, color='darkgreen', symbol='circle'),
                text=safeguard_df['Credits_Value'].apply(lambda x: f'${x/1000000:.2f}M'),
                textposition='top center',
                textfont=dict(size=9, color='darkgreen'),
                hovertemplate='<b>%{x}</b><br>Value: $%{y:,.0f}<extra></extra>',
                yaxis='y2'
            ),
            secondary_y=True
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year")
        fig.update_yaxes(title_text="Credits (tCO₂-e)", tickformat=',.0f', secondary_y=False)
        fig.update_yaxes(title_text="Credit Value ($)", tickformat='$,.0f', secondary_y=True)

        fig.update_layout(
            height=400,
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig, width="stretch")
        # Caption removed


def display_safeguard_table(projection, safeguard_threshold, carbon_credit_price):
    """Display safeguard compliance table"""

    with st.expander("📋 Annual Safeguard Compliance Data", expanded=False):
        sm_display = projection[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Baseline', 'Emission_Intensity',
                                 'Baseline_Intensity', 'SMC_Annual', 'SMC_Cumulative', 'In_Safeguard',
                                 'Is_Actual', 'ROM_Is_Actual', 'Emissions_Is_Actual']].copy()

        # Format columns
        sm_display['ROM (Mt)'] = sm_display['ROM_Mt'].apply(lambda x: f"{x:.2f}" if x > 0 else "—")
        sm_display['Scope 1 (tCO₂-e)'] = sm_display['Scope1'].apply(lambda x: f"{x:,.0f}")
        sm_display['Baseline (tCO₂-e)'] = sm_display['Baseline'].apply(lambda x: f"{x:,.0f}" if x > 0 else "—")
        sm_display['Actual Int'] = sm_display['Emission_Intensity'].apply(lambda x: f"{x:.4f}" if x > 0 else "—")
        sm_display['Baseline Int'] = sm_display['Baseline_Intensity'].apply(lambda x: f"{x:.4f}" if x > 0 else "—")
        sm_display['Annual SMC'] = sm_display['SMC_Annual'].apply(lambda x: f"{x:+,.0f}")
        sm_display['Cumulative SMC (tCO₂-e)'] = sm_display['SMC_Cumulative'].apply(lambda x: f"{x:+,.0f}")
        sm_display['Cumulative SMC ($)'] = sm_display['SMC_Cumulative'].apply(
            lambda x: f"${abs(x) * carbon_credit_price:,.0f}" if x != 0 else "$0"
        )
        sm_display['In Safeguard'] = sm_display['In_Safeguard'].apply(lambda x: '✓' if x else '—')

        # Data source indicators
        def format_data_source(row):
            if row['Is_Actual']:
                return '✓ Actual'
            elif row['ROM_Is_Actual'] and not row['Emissions_Is_Actual']:
                return '⚠ ROM actual, Emissions projected'
            elif not row['ROM_Is_Actual'] and row['Emissions_Is_Actual']:
                return '⚠ ROM projected, Emissions actual'
            else:
                return '📊 Projected'

        sm_display['Data Source'] = sm_display.apply(format_data_source, axis=1)

        sm_display = sm_display[['FY', 'Phase', 'Data Source', 'ROM (Mt)', 'Scope 1 (tCO₂-e)', 'Baseline (tCO₂-e)',
                                'Actual Int', 'Baseline Int', 'Annual SMC', 'Cumulative SMC (tCO₂-e)', 'Cumulative SMC ($)', 'In Safeguard']]

        st.dataframe(sm_display, width="stretch", hide_index=True)

        st.caption("🌍 **Data Source:** ✓ Actual = from ROM.csv & Energy.csv | 📊 Projected = modeled | ⚠ = mixed")
        st.caption("🌍 **In Safeguard:** ✓ = Scope 1 ≥ 100,000 tCO₂-e (subject to Safeguard Mechanism)")


def display_report_generator(projection):
    """Display compliance report generation section"""

    with st.expander("📄 Generate Compliance Report", expanded=False):
        st.markdown("**Annual Safeguard Compliance Report**")
        st.markdown("Generate a detailed report for NGER submission including emissions breakdown, baseline comparison, and SMC position.")

        col1, col2 = st.columns([2, 1])

        with col1:
            years_list = projection[projection['ROM_Mt'] > 0]['FY'].tolist()
            if years_list:
                report_year = st.selectbox("Select Financial Year", years_list, key='report_year_select')
            else:
                st.info("No production years available for report generation")
                return

        with col2:
            if st.button("Generate Report", type="primary"):
                try:
                    from report_generator import generate_safeguard_report

                    # Get year data
                    year_data = projection[projection['FY'] == report_year].iloc[0]

                    # Generate report
                    report_path = generate_safeguard_report(
                        year_data.to_dict(),
                        f"Safeguard_Compliance_Report_{report_year}.docx"
                    )

                    if report_path and report_path.exists():
                        with open(report_path, 'rb') as f:
                            st.download_button(
                                label=f"📥 Download {report_year} Report",
                                data=f,
                                file_name=f"Safeguard_Compliance_Report_{report_year}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            )
                        st.success(f"✦ Report generated successfully for {report_year}")
                    else:
                        st.error("Failed to generate report")

                except Exception as e:
                    st.error(f"Error generating report: {str(e)}")

        st.caption("Report includes: Emissions summary, baseline comparison, SMC position, compliance status, and notes")