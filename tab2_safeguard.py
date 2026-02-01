"""
tab2_safeguard.py
Safeguard Mechanism tab - simplified for unified data architecture
Last updated: 2026-02-02 09:50 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection
from config import COLORS, DECLINE_RATE, DECLINE_FROM, DECLINE_TO


def render_safeguard_tab(df, selected_source, fsei_rom, fsei_elec,
                         start_fy, end_fy, grid_connected_fy,
                         end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                         carbon_credit_price, credit_escalation, credit_start_fy):
    """Render Safeguard Mechanism tab

    Args:
        df: Unified DataFrame from load_all_data()
        selected_source: 'Base', 'NPI-NGERS', or 'All'
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        Phase parameters
        carbon_credit_price: SMC market price (initial year)
        credit_escalation: Annual credit price escalation rate (decimal)
        credit_start_fy: First year credits can be earned
    """

    st.subheader("🛡️ Safeguard Mechanism Analysis")
    st.caption(f"Baseline Intensity: ROM {fsei_rom:.4f} + Elec {fsei_elec:.4f} × 0.00874 MWh/t = 0.0256 tCO2-e/t | Declining at {DECLINE_RATE*100:.1f}% p.a. (FY{DECLINE_FROM}-FY{DECLINE_TO})")

    display_year = st.session_state.get('display_year', 2025)

    # Multiple datasets selected - show combined comparison charts
    if selected_source == 'All':

        proj_base = build_projection(
            df, dataset='Base',
            end_mining_fy=end_mining_fy,
            end_processing_fy=end_processing_fy,
            end_rehabilitation_fy=end_rehabilitation_fy,
            grid_connected_fy=grid_connected_fy,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_fy=credit_start_fy,
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
            credit_start_fy=credit_start_fy,
            start_fy=start_fy,
            end_fy=end_fy
        )

        # Apply credit value escalation
        from projections import smc_credit_value_analysis
        proj_base = smc_credit_value_analysis(proj_base, credit_start_fy, carbon_credit_price, credit_escalation)
        proj_npi = smc_credit_value_analysis(proj_npi, credit_start_fy, carbon_credit_price, credit_escalation)

        display_safeguard_comparison(proj_base, proj_npi, display_year, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec)

        # Prepare projections list for combined data table
        projections_list = [('Base', proj_base), ('NPI-NGERS', proj_npi)]

    # Single source mode
    else:
        projection = build_projection(
            df, dataset=selected_source,
            end_mining_fy=end_mining_fy,
            end_processing_fy=end_processing_fy,
            end_rehabilitation_fy=end_rehabilitation_fy,
            grid_connected_fy=grid_connected_fy,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_fy=credit_start_fy,
            start_fy=start_fy,
            end_fy=end_fy
        )

        display_safeguard_single(projection, display_year, selected_source, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec)

        # Prepare projections list for combined data table
        projections_list = [(selected_source, projection)]

    # Combined Data Table at the end (appears once for all datasets)
    with st.expander("📋 Safeguard Data Table", expanded=False):
        combined_data = []

        for source_name, proj in projections_list:
            # Add source column to each projection
            proj_copy = proj[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Baseline',
                             'Emission_Intensity', 'Baseline_Intensity',
                             'SMC_Annual', 'SMC_Cumulative']].copy()
            proj_copy.insert(0, 'Source', source_name)
            combined_data.append(proj_copy)

        # Combine all datasets
        display_df = pd.concat(combined_data, ignore_index=True)

        # Format numbers
        display_df['ROM_Mt'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}")
        display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
        display_df['Baseline'] = display_df['Baseline'].apply(lambda x: f"{x:,.0f}")
        display_df['Emission_Intensity'] = display_df['Emission_Intensity'].apply(lambda x: f"{x:.4f}")
        display_df['Baseline_Intensity'] = display_df['Baseline_Intensity'].apply(lambda x: f"{x:.4f}")
        display_df['SMC_Annual'] = display_df['SMC_Annual'].apply(lambda x: f"{x:,.0f}")
        display_df['SMC_Cumulative'] = display_df['SMC_Cumulative'].apply(lambda x: f"{x:,.0f}")

        st.dataframe(display_df, hide_index=True, width="stretch", height=400)


def display_safeguard_single(projection, display_year, source_name, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec, show_summary=True):
    """Display safeguard analysis for single source

    Args:
        show_summary: If False, skip the summary table (used in comparison mode)
    """

    # Apply credit value escalation
    from projections import smc_credit_value_analysis
    projection = smc_credit_value_analysis(projection, credit_start_fy, carbon_credit_price, credit_escalation)

    # Gold color palette
    GOLD_METALLIC = '#DBB12A'      # Primary - ROM, main bars
    BRIGHT_GOLD = '#E8AC41'         # Secondary - Site electricity
    DARK_GOLDENROD = '#AE8B0F'     # Tertiary - Grid electricity
    SEPIA = '#734B1A'              # Accent - Credits
    CAFE_NOIR = '#39250B'          # Lines, text
    GRID_GREEN = '#2A9D8F'         # Grid connection marker

    # Summary table - single row with all data
    if show_summary:
        with st.expander("📊 Summary", expanded=True):
            year_data = projection[projection['FY'] == f'FY{display_year}']

            if len(year_data) == 0:
                st.warning(f"⚠️ No data for FY{display_year}")
            else:
                row = year_data.iloc[0]

                smc_annual = row['SMC_Annual'] if row['FY'].replace('FY','').isdigit() and int(row['FY'].replace('FY','')) >= credit_start_fy else 0

                # Calculate intensity components
                SITE_GENERATION_RATIO = 0.008735  # MWh/t ROM

                # Baseline components
                baseline_rom_component = fsei_rom
                baseline_elec_component = SITE_GENERATION_RATIO * fsei_elec
                baseline_total = row['Baseline_Intensity']

                # Actual intensity components (if ROM > 0)
                if row['ROM_Mt'] > 0:
                    actual_total = row['Emission_Intensity']
                    site_mwh = row['Site_Electricity_kWh'] / 1000
                    actual_site_gen_ratio = site_mwh / (row['ROM_Mt'] * 1_000_000)
                    actual_elec_component = actual_site_gen_ratio * fsei_elec
                    actual_rom_component = actual_total - actual_elec_component
                else:
                    actual_total = 0.0
                    actual_rom_component = 0.0
                    actual_elec_component = 0.0

                # Single row with all data
                summary_data = [{
                    'Source': source_name,
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Baseline Int-Total': f"{baseline_total:.4f}",
                    'Actual Int-Total': f"{actual_total:.4f}" if row['ROM_Mt'] > 0 else "N/A",
                    'Baseline Int-ROM': f"{baseline_rom_component:.4f}",
                    'Actual Int-ROM': f"{actual_rom_component:.4f}" if row['ROM_Mt'] > 0 else "N/A",
                    'Baseline Int-Elec': f"{baseline_elec_component:.4f}",
                    'Actual Int-Elec': f"{actual_elec_component:.4f}" if row['ROM_Mt'] > 0 else "N/A",
                    'SMC Annual': f"{smc_annual:,.0f}",
                    'SMC Cumulative': f"{row['SMC_Cumulative']:,.0f}"
                }]

                df_summary = pd.DataFrame(summary_data)
                st.dataframe(df_summary, hide_index=True, width="stretch")

    # ROM and Electricity charts (side by side)
    with st.expander("📊 ROM Production & Electricity Consumption", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            # ROM Production
            fig_rom = go.Figure()

            fig_rom.add_trace(go.Bar(
                x=projection['FY'],
                y=projection['ROM_Mt'],
                name='ROM Production',
                marker_color=GOLD_METALLIC
            ))

            # Add grid connection marker
            if grid_connected_fy and f'FY{grid_connected_fy}' in projection['FY'].values:
                fig_rom.add_shape(
                    type="line",
                    x0=f'FY{grid_connected_fy}',
                    x1=f'FY{grid_connected_fy}',
                    y0=0,
                    y1=1,
                    yref="paper",
                    line=dict(color=GRID_GREEN, width=2, dash="dot")
                )
                fig_rom.add_annotation(
                    x=f'FY{grid_connected_fy}',
                    y=1,
                    yref="paper",
                    text="Grid",
                    showarrow=False,
                    yshift=10,
                    font=dict(size=10)
                )

            fig_rom.update_layout(
                title="ROM Production (Mt)",
                xaxis_title="Financial Year",
                yaxis_title="ROM (Mt)",
                height=400,
                showlegend=False
            )

            st.plotly_chart(fig_rom, width="stretch")

        with col2:
            # Electricity Consumption
            fig_elec = go.Figure()

            # Convert to MWh
            site_mwh = projection['Site_Electricity_kWh'] / 1000
            grid_mwh = projection['Grid_Electricity_kWh'] / 1000

            # Grid electricity (bottom of stack)
            fig_elec.add_trace(go.Bar(
                x=projection['FY'],
                y=grid_mwh,
                name='Grid Purchase',
                marker_color=DARK_GOLDENROD,
                opacity=0.9
            ))

            # Site electricity (top of stack)
            fig_elec.add_trace(go.Bar(
                x=projection['FY'],
                y=site_mwh,
                name='Site Generation',
                marker_color=BRIGHT_GOLD,
                opacity=0.9
            ))

            # Add grid connection marker
            if grid_connected_fy and f'FY{grid_connected_fy}' in projection['FY'].values:
                fig_elec.add_shape(
                    type="line",
                    x0=f'FY{grid_connected_fy}',
                    x1=f'FY{grid_connected_fy}',
                    y0=0,
                    y1=1,
                    yref="paper",
                    line=dict(color=GRID_GREEN, width=2, dash="dot")
                )
                fig_elec.add_annotation(
                    x=f'FY{grid_connected_fy}',
                    y=1,
                    yref="paper",
                    text="Grid",
                    showarrow=False,
                    yshift=10,
                    font=dict(size=10)
                )

            fig_elec.update_layout(
                title="Electricity Consumption (MWh)",
                xaxis_title="Financial Year",
                yaxis_title="Electricity (MWh)",
                height=400,
                barmode='stack',
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            st.plotly_chart(fig_elec, width="stretch")

    # Scope 1 Emissions & Emission Intensity (dual-axis)
    with st.expander("📈 Scope 1 Emissions & Emission Intensity", expanded=True):
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Scope 1 Emissions (bars) - consistent gold
        fig.add_trace(
            go.Bar(
                x=projection['FY'],
                y=projection['Scope1'],
                name='Scope 1 Emissions',
                marker_color=GOLD_METALLIC,
                opacity=0.8
            ),
            secondary_y=False
        )

        # Actual Intensity (line) - consistent dark line
        fig.add_trace(
            go.Scatter(
                x=projection['FY'],
                y=projection['Emission_Intensity'],
                name='Actual Intensity',
                mode='lines+markers',
                line=dict(color=CAFE_NOIR, width=3),
                marker=dict(size=6)
            ),
            secondary_y=True
        )

        # Baseline Intensity (dashed line) - black for regulatory standard
        fig.add_trace(
            go.Scatter(
                x=projection['FY'],
                y=projection['Baseline_Intensity'],
                name='Baseline',
                mode='lines',
                line=dict(color='black', width=2, dash='dash')
            ),
            secondary_y=True
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
                text="Grid Connected",
                showarrow=False,
                yshift=10
            )

        fig.update_xaxes(title_text="Financial Year")
        fig.update_yaxes(title_text="Scope 1 Emissions (tCO2-e)", secondary_y=False)
        fig.update_yaxes(title_text="Emission Intensity (tCO2-e/t)", secondary_y=True)

        fig.update_layout(
            height=500,
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        st.plotly_chart(fig, width="stretch")

    # Cumulative SMC Credits
    with st.expander("💰 SMC Credits & Value", expanded=True):

        # Filter to credit period
        credit_data = projection[projection['FY'].str.replace('FY','').astype(int) >= credit_start_fy].copy()

        if len(credit_data) == 0:
            st.info("No SMC credits yet - credit period starts FY{credit_start_fy}")
        else:
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # Cumulative credits (simple bars)
            fig.add_trace(
                go.Bar(
                    x=credit_data['FY'],
                    y=credit_data['SMC_Cumulative'],
                    name='Cumulative Credits',
                    marker_color=GOLD_METALLIC,
                    opacity=0.8
                ),
                secondary_y=False
            )

            # Credit Value line with $ labels
            fig.add_trace(
                go.Scatter(
                    x=credit_data['FY'],
                    y=credit_data['Credit_Value_Cumulative'],
                    name='Credit Value ($)',
                    mode='lines+markers+text',
                    line=dict(color=CAFE_NOIR, width=3),
                    marker=dict(size=10, color=CAFE_NOIR),
                    text=credit_data['Credit_Value_Cumulative'].apply(lambda x: f"${x/1e6:.1f}M"),
                    textposition='top center',
                    textfont=dict(size=10, color='black')
                ),
                secondary_y=True
            )

            fig.update_xaxes(title_text="Financial Year")
            fig.update_yaxes(title_text="Cumulative Credits (tCO2-e)", secondary_y=False)
            fig.update_yaxes(title_text=f"Credit Value (AUD, {credit_escalation*100:.1f}% p.a.)", secondary_y=True)

            fig.update_layout(
                height=400,
                hovermode='x unified',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            st.plotly_chart(fig, width="stretch")

            # Summary stats
            final_credits = credit_data.iloc[-1]['SMC_Cumulative']
            final_value = credit_data.iloc[-1]['Credit_Value_Cumulative']
            final_price = credit_data.iloc[-1]['Credit_Price']
            final_year = credit_data.iloc[-1]['FY']

            st.caption(f"📊 {final_year} Cumulative: {final_credits:,.0f} tCO2-e worth ${final_value:,.0f} AUD (price escalated to ${final_price:.2f}/tCO2-e)")


def display_safeguard_comparison(proj_base, proj_npi, display_year, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec):
    """Display safeguard comparison between Base and NPI-NGERS with combined charts"""

    # Gold color palette
    GOLD_METALLIC = '#DBB12A'
    BRIGHT_GOLD = '#E8AC41'
    DARK_GOLDENROD = '#AE8B0F'
    CAFE_NOIR = '#39250B'
    GRID_GREEN = '#2A9D8F'

    # Combined summary table
    with st.expander("📊 Summary", expanded=True):
        year_base = proj_base[proj_base['FY'] == f'FY{display_year}']
        year_npi = proj_npi[proj_npi['FY'] == f'FY{display_year}']

        if len(year_base) == 0 or len(year_npi) == 0:
            st.warning(f"⚠️ No data for FY{display_year}")
        else:
            row_base = year_base.iloc[0]
            row_npi = year_npi.iloc[0]

            # Calculate intensity components for both datasets
            SITE_GENERATION_RATIO = 0.008735
            summary_rows = []

            for source_name, row in [('Base', row_base), ('NPI-NGERS', row_npi)]:
                smc_annual = row['SMC_Annual'] if row['FY'].replace('FY','').isdigit() and int(row['FY'].replace('FY','')) >= credit_start_fy else 0

                baseline_rom_component = fsei_rom
                baseline_elec_component = SITE_GENERATION_RATIO * fsei_elec
                baseline_total = row['Baseline_Intensity']

                if row['ROM_Mt'] > 0:
                    actual_total = row['Emission_Intensity']
                    site_mwh = row['Site_Electricity_kWh'] / 1000
                    actual_site_gen_ratio = site_mwh / (row['ROM_Mt'] * 1_000_000)
                    actual_elec_component = actual_site_gen_ratio * fsei_elec
                    actual_rom_component = actual_total - actual_elec_component
                else:
                    actual_total = 0.0
                    actual_rom_component = 0.0
                    actual_elec_component = 0.0

                summary_rows.append({
                    'Source': source_name,
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Baseline Int-Total': f"{baseline_total:.4f}",
                    'Actual Int-Total': f"{actual_total:.4f}" if row['ROM_Mt'] > 0 else "N/A",
                    'SMC Annual': f"{smc_annual:,.0f}",
                    'SMC Cumulative': f"{row['SMC_Cumulative']:,.0f}"
                })

            df_summary = pd.DataFrame(summary_rows)
            st.dataframe(df_summary, hide_index=True, width="stretch")

            # Variance summary
            diff_smc = row_npi['SMC_Cumulative'] - row_base['SMC_Cumulative']
            if abs(diff_smc) > 0:
                st.caption(f"SMC Variance: {diff_smc:+,.0f} tCO2-e")

    # ROM Production & Electricity charts combined
    with st.expander("📊 ROM Production & Electricity Consumption", expanded=True):

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Base - ROM Production', 'Base - Electricity',
                          'NPI-NGERS - ROM Production', 'NPI-NGERS - Electricity'),
            vertical_spacing=0.15,
            horizontal_spacing=0.12,
            row_heights=[0.5, 0.5]
        )

        # Base ROM (row 1, col 1)
        fig.add_trace(
            go.Bar(
                x=proj_base['FY'],
                y=proj_base['ROM_Mt'],
                name='ROM Production',
                marker_color=GOLD_METALLIC,
                opacity=0.8,
                hovertemplate='%{y:.2f} Mt<extra></extra>'
            ),
            row=1, col=1
        )

        # Base Electricity (row 1, col 2) - stacked
        site_mwh_base = proj_base['Site_Electricity_kWh'] / 1000
        grid_mwh_base = proj_base['Grid_Electricity_kWh'] / 1000

        fig.add_trace(
            go.Bar(
                x=proj_base['FY'],
                y=grid_mwh_base,
                name='Grid',
                marker_color=DARK_GOLDENROD,
                opacity=0.9,
                hovertemplate='%{y:,.0f} MWh<extra></extra>'
            ),
            row=1, col=2
        )

        fig.add_trace(
            go.Bar(
                x=proj_base['FY'],
                y=site_mwh_base,
                name='Site',
                marker_color=BRIGHT_GOLD,
                opacity=0.9,
                hovertemplate='%{y:,.0f} MWh<extra></extra>'
            ),
            row=1, col=2
        )

        # NPI ROM (row 2, col 1) - use prime notation
        fig.add_trace(
            go.Bar(
                x=proj_npi['FY'],
                y=proj_npi['ROM_Mt'],
                name="ROM Production'",
                marker_color=GOLD_METALLIC,
                opacity=0.8,
                showlegend=False,
                hovertemplate='%{y:.2f} Mt<extra></extra>'
            ),
            row=2, col=1
        )

        # NPI Electricity (row 2, col 2) - stacked with prime notation
        site_mwh_npi = proj_npi['Site_Electricity_kWh'] / 1000
        grid_mwh_npi = proj_npi['Grid_Electricity_kWh'] / 1000

        fig.add_trace(
            go.Bar(
                x=proj_npi['FY'],
                y=grid_mwh_npi,
                name="Grid'",
                marker_color=DARK_GOLDENROD,
                opacity=0.9,
                showlegend=False,
                hovertemplate='%{y:,.0f} MWh<extra></extra>'
            ),
            row=2, col=2
        )

        fig.add_trace(
            go.Bar(
                x=proj_npi['FY'],
                y=site_mwh_npi,
                name="Site'",
                marker_color=BRIGHT_GOLD,
                opacity=0.9,
                showlegend=False,
                hovertemplate='%{y:,.0f} MWh<extra></extra>'
            ),
            row=2, col=2
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year", row=2, col=1)
        fig.update_xaxes(title_text="Financial Year", row=2, col=2)
        fig.update_yaxes(title_text="ROM (Mt)", row=1, col=1)
        fig.update_yaxes(title_text="Electricity (MWh)", row=1, col=2)
        fig.update_yaxes(title_text="ROM (Mt)", row=2, col=1)
        fig.update_yaxes(title_text="Electricity (MWh)", row=2, col=2)

        # Set barmode for electricity columns
        fig.update_layout(
            height=650,
            barmode='stack',
            hovermode='x unified',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # Add grid connection markers to all electricity charts
        if grid_connected_fy and f'FY{grid_connected_fy}' in proj_base['FY'].values:
            for row_num in [1, 2]:
                fig.add_shape(
                    type="line",
                    x0=f'FY{grid_connected_fy}',
                    x1=f'FY{grid_connected_fy}',
                    y0=0,
                    y1=1,
                    yref=f"y{2 if row_num==1 else 4} domain",
                    line=dict(color=GRID_GREEN, width=2, dash="dot"),
                    row=row_num, col=2
                )
                fig.add_annotation(
                    x=f'FY{grid_connected_fy}',
                    y=1,
                    yref=f"y{2 if row_num==1 else 4} domain",
                    text="Grid",
                    showarrow=False,
                    yshift=10,
                    font=dict(size=9),
                    row=row_num, col=2
                )

        st.plotly_chart(fig, width="stretch")

    # Scope 1 Emissions & Intensity combined
    with st.expander("📈 Scope 1 Emissions & Emission Intensity", expanded=True):

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Base', 'NPI-NGERS'),
            specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
            vertical_spacing=0.15,
            row_heights=[0.5, 0.5]
        )

        # Base (top chart)
        fig.add_trace(
            go.Bar(
                x=proj_base['FY'],
                y=proj_base['Scope1'],
                name='Scope 1',
                marker_color=GOLD_METALLIC,
                opacity=0.8,
                hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
            ),
            secondary_y=False,
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=proj_base['FY'],
                y=proj_base['Emission_Intensity'],
                name='Actual',
                mode='lines+markers',
                line=dict(color=CAFE_NOIR, width=3),
                marker=dict(size=6),
                hovertemplate='%{y:.5f} tCO2-e/t<extra></extra>'
            ),
            secondary_y=True,
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=proj_base['FY'],
                y=proj_base['Baseline_Intensity'],
                name='Baseline',
                mode='lines',
                line=dict(color='black', width=2, dash='dash'),
                hovertemplate='%{y:.5f} tCO2-e/t<extra></extra>'
            ),
            secondary_y=True,
            row=1, col=1
        )

        # NPI (bottom chart) - use prime notation for proper hover labels
        fig.add_trace(
            go.Bar(
                x=proj_npi['FY'],
                y=proj_npi['Scope1'],
                name="Scope 1'",
                marker_color=GOLD_METALLIC,
                opacity=0.8,
                showlegend=False,
                hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
            ),
            secondary_y=False,
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=proj_npi['FY'],
                y=proj_npi['Emission_Intensity'],
                name="Actual'",
                mode='lines+markers',
                line=dict(color=CAFE_NOIR, width=3),
                marker=dict(size=6),
                showlegend=False,
                hovertemplate='%{y:.5f} tCO2-e/t<extra></extra>'
            ),
            secondary_y=True,
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=proj_npi['FY'],
                y=proj_npi['Baseline_Intensity'],
                name="Baseline'",
                mode='lines',
                line=dict(color='black', width=2, dash='dash'),
                showlegend=False,
                hovertemplate='%{y:.5f} tCO2-e/t<extra></extra>'
            ),
            secondary_y=True,
            row=2, col=1
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year", row=2, col=1)
        fig.update_yaxes(title_text="Scope 1 (tCO2-e)", secondary_y=False, row=1, col=1)
        fig.update_yaxes(title_text="Intensity (tCO2-e/t)", secondary_y=True, row=1, col=1)
        fig.update_yaxes(title_text="Scope 1 (tCO2-e)", secondary_y=False, row=2, col=1)
        fig.update_yaxes(title_text="Intensity (tCO2-e/t)", secondary_y=True, row=2, col=1)

        fig.update_layout(
            height=700,
            hovermode='x unified',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

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
                yref="y3 domain",
                line=dict(color=GRID_GREEN, width=2, dash="dot"),
                row=2, col=1
            )
            fig.add_annotation(
                x=f'FY{grid_connected_fy}',
                y=1,
                yref="y3 domain",
                text="Grid",
                showarrow=False,
                yshift=10,
                row=2, col=1
            )

        st.plotly_chart(fig, width="stretch")

    # Combined SMC credits chart in single frame
    with st.expander("💰 SMC Credits & Value", expanded=True):

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Base', 'NPI-NGERS'),
            specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
            vertical_spacing=0.15,
            row_heights=[0.5, 0.5]
        )

        # Base (top chart)
        fig.add_trace(
            go.Bar(
                x=proj_base['FY'],
                y=proj_base['SMC_Cumulative'],
                name='SMC Credits',
                marker_color=GOLD_METALLIC,
                opacity=0.8,
                hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
            ),
            secondary_y=False,
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=proj_base['FY'],
                y=proj_base['Credit_Value_Cumulative'],
                name='Credit Value',
                mode='lines+markers',
                line=dict(color=CAFE_NOIR, width=3),
                marker=dict(size=6),
                hovertemplate='$%{y:,.0f}<extra></extra>'
            ),
            secondary_y=True,
            row=1, col=1
        )

        # NPI-NGERS (bottom chart) - use prime notation for proper hover labels
        fig.add_trace(
            go.Bar(
                x=proj_npi['FY'],
                y=proj_npi['SMC_Cumulative'],
                name="SMC Credits'",
                marker_color=GOLD_METALLIC,
                opacity=0.8,
                showlegend=False,
                hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
            ),
            secondary_y=False,
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=proj_npi['FY'],
                y=proj_npi['Credit_Value_Cumulative'],
                name="Credit Value'",
                mode='lines+markers',
                line=dict(color=CAFE_NOIR, width=3),
                marker=dict(size=6),
                showlegend=False,
                hovertemplate='$%{y:,.0f}<extra></extra>'
            ),
            secondary_y=True,
            row=2, col=1
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year", row=2, col=1)
        fig.update_yaxes(title_text="Cumulative Credits (tCO2-e)", secondary_y=False, row=1, col=1)
        fig.update_yaxes(title_text="Cumulative Value ($AUD)", secondary_y=True, row=1, col=1)
        fig.update_yaxes(title_text="Cumulative Credits (tCO2-e)", secondary_y=False, row=2, col=1)
        fig.update_yaxes(title_text="Cumulative Value ($AUD)", secondary_y=True, row=2, col=1)

        fig.update_layout(
            height=700,
            hovermode='x unified',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

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
                yref="y3 domain",
                line=dict(color=GRID_GREEN, width=2, dash="dot"),
                row=2, col=1
            )
            fig.add_annotation(
                x=f'FY{grid_connected_fy}',
                y=1,
                yref="y3 domain",
                text="Grid",
                showarrow=False,
                yshift=10,
                row=2, col=1
            )

        st.plotly_chart(fig, width="stretch")