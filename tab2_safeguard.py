"""
tab2_safeguard.py
Safeguard Mechanism tab - date-based architecture
Last updated: 2026-02-05 16:45 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection, smc_credit_value_analysis
from calc_calendar import date_to_fy, aggregate_by_year_type
from config import COLORS, DECLINE_RATE, DECLINE_FROM, DECLINE_TO, SAFEGUARD_THRESHOLD


def prepare_annual_for_safeguard(monthly):
    """Aggregate monthly data to annual and prepare for Safeguard display

    Args:
        monthly: Monthly DataFrame from build_projection

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
    if 'Phase' in monthly.columns:
        agg_dict['Phase'] = 'last'  # Take phase from last month of FY
    if 'SMC_Monthly' in monthly.columns:
        agg_dict['SMC_Monthly'] = 'sum'  # Sum to annual
    if 'SMC_Cumulative' in monthly.columns:
        agg_dict['SMC_Cumulative'] = 'last'  # End-of-year value
    if 'In_Safeguard' in monthly.columns:
        agg_dict['In_Safeguard'] = 'last'  # End-of-year status
    if 'Exit_FY' in monthly.columns:
        agg_dict['Exit_FY'] = 'first'  # Same for all months in year
    if 'SMC_Phase' in monthly.columns:
        agg_dict['SMC_Phase'] = 'last'  # End-of-year phase status

    # Aggregate monthly -> annual (always Tax Year/FY for Safeguard - legislated)
    annual = aggregate_by_year_type(monthly, 'FY', agg_dict=agg_dict)

    # Add FY column as string for compatibility
    annual['FY'] = annual['Year']

    # Add compatibility columns
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']
    annual['Total'] = annual['Scope1'] + annual['Scope2'] + annual['Scope3']

    # Convert ROM from tonnes to megatonnes
    annual['ROM_Mt'] = annual['ROM_t'] / 1_000_000

    # SMC columns should already be correct from monthly aggregation
    if 'SMC_Monthly' in annual.columns:
        annual['SMC_Annual'] = annual['SMC_Monthly']

    # If Phase column is missing, add a default
    if 'Phase' not in annual.columns:
        annual['Phase'] = 'Unknown'

    # Ensure electricity columns exist (with 0 if missing)
    if 'Site_Electricity_kWh' not in annual.columns:
        annual['Site_Electricity_kWh'] = 0
    if 'Grid_Electricity_kWh' not in annual.columns:
        annual['Grid_Electricity_kWh'] = 0

    return annual


def render_safeguard_tab(df, selected_source, fsei_rom, fsei_elec,
                         start_date, end_date, grid_connected_date,
                         end_mining_date, end_processing_date, end_rehabilitation_date,
                         carbon_credit_price, credit_escalation, credit_start_date,
                         decline_rate_phase2=None):
    """Render Safeguard Mechanism tab (always uses Tax Year/FY)

    Args:
        df: Unified DataFrame from load_all_data()
        selected_source: 'Base', 'NPI-NGERS', or 'All'
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        Phase parameters (dates)
        carbon_credit_price: SMC market price (initial year)
        credit_escalation: Annual credit price escalation rate (decimal)
        credit_start_date: First date credits can be earned
        decline_rate_phase2: Optional Phase 2 decline rate override
    """

    # Convert dates to FY for display
    start_fy = date_to_fy(start_date)
    end_fy = date_to_fy(end_date)
    grid_connected_fy = date_to_fy(grid_connected_date)
    credit_start_fy = date_to_fy(credit_start_date)

    st.subheader("🛡️ Safeguard Mechanism Analysis")
    st.caption(f"FSEI: ROM {fsei_rom:.4f} tCO2-e/t | Elec {fsei_elec:.4f} tCO2-e/MWh | Baseline declining {DECLINE_RATE*100:.1f}% p.a. (FY{DECLINE_FROM}–FY{DECLINE_TO})")

    display_year = st.session_state.get('display_year', 2025)

    # Multiple datasets selected - show combined comparison charts
    if selected_source == 'All':

        monthly_base = build_projection(
            df, dataset='Base',
            end_mining_date=end_mining_date,
            end_processing_date=end_processing_date,
            end_rehabilitation_date=end_rehabilitation_date,
            grid_connected_date=grid_connected_date,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_date=credit_start_date,
            start_date=start_date,
            end_date=end_date,
            decline_rate_phase2=decline_rate_phase2
        )

        monthly_npi = build_projection(
            df, dataset='NPI-NGERS',
            end_mining_date=end_mining_date,
            end_processing_date=end_processing_date,
            end_rehabilitation_date=end_rehabilitation_date,
            grid_connected_date=grid_connected_date,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_date=credit_start_date,
            start_date=start_date,
            end_date=end_date,
            decline_rate_phase2=decline_rate_phase2
        )

        # Aggregate monthly -> annual
        proj_base = prepare_annual_for_safeguard(monthly_base)
        proj_npi = prepare_annual_for_safeguard(monthly_npi)

        # Apply credit value escalation
        proj_base = smc_credit_value_analysis(proj_base, credit_start_fy, carbon_credit_price, credit_escalation)
        proj_npi = smc_credit_value_analysis(proj_npi, credit_start_fy, carbon_credit_price, credit_escalation)

        display_safeguard_comparison(proj_base, proj_npi, display_year, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec)

        # Prepare projections list for combined data table
        projections_list = [('Base', proj_base), ('NPI-NGERS', proj_npi)]

    # Single source mode
    else:
        monthly = build_projection(
            df, dataset=selected_source,
            end_mining_date=end_mining_date,
            end_processing_date=end_processing_date,
            end_rehabilitation_date=end_rehabilitation_date,
            grid_connected_date=grid_connected_date,
            fsei_rom=fsei_rom,
            fsei_elec=fsei_elec,
            credit_start_date=credit_start_date,
            start_date=start_date,
            end_date=end_date,
            decline_rate_phase2=decline_rate_phase2
        )

        # Aggregate monthly -> annual
        projection = prepare_annual_for_safeguard(monthly)

        # Apply credit value escalation
        projection = smc_credit_value_analysis(projection, credit_start_fy, carbon_credit_price, credit_escalation)

        display_safeguard_single(projection, display_year, selected_source, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec)

        # Prepare projections list for combined data table
        projections_list = [(selected_source, projection)]

    # Combined Data Table at the end (appears once for all datasets)
    with st.expander("📋 Safeguard Data Table", expanded=False):
        combined_data = []

        for source_name, proj in projections_list:
            # Add source column to each projection
            cols = ['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Baseline',
                    'SMC_Annual', 'SMC_Cumulative',
                    'Credit_Price', 'Credit_Value_Annual', 'Credit_Value_Cumulative']
            # Only include columns that exist (credit values need smc_credit_value_analysis)
            cols = [c for c in cols if c in proj.columns]
            proj_copy = proj[cols].copy()
            proj_copy.insert(0, 'Source', source_name)
            combined_data.append(proj_copy)

        # Combine all datasets
        display_df = pd.concat(combined_data, ignore_index=True)

        # Format numbers
        display_df['ROM_Mt'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}")
        display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
        display_df.rename(columns={'Baseline': 'Target'}, inplace=True)
        display_df['Target'] = display_df['Target'].apply(lambda x: f"{x:,.0f}")
        display_df['SMC_Annual'] = display_df['SMC_Annual'].apply(lambda x: f"{x:,.0f}")
        display_df['SMC_Cumulative'] = display_df['SMC_Cumulative'].apply(lambda x: f"{x:,.0f}")
        if 'Credit_Price' in display_df.columns:
            display_df.rename(columns={
                'Credit_Price': 'SMC Price ($/t)',
                'Credit_Value_Annual': 'SMC $ Annual',
                'Credit_Value_Cumulative': 'SMC $ Cumulative'
            }, inplace=True)
            display_df['SMC Price ($/t)'] = display_df['SMC Price ($/t)'].apply(lambda x: f"${x:,.2f}")
            display_df['SMC $ Annual'] = display_df['SMC $ Annual'].apply(lambda x: f"${x:,.0f}")
            display_df['SMC $ Cumulative'] = display_df['SMC $ Cumulative'].apply(lambda x: f"${x:,.0f}")

        st.dataframe(display_df, hide_index=True, width="stretch", height=400)


def display_safeguard_single(projection, display_year, source_name, carbon_credit_price, credit_escalation, credit_start_fy, grid_connected_fy, fsei_rom, fsei_elec, show_summary=True):
    """Display safeguard analysis for single source

    Args:
        show_summary: If False, skip the summary table (used in comparison mode)
    """

    # Note: smc_credit_value_analysis already applied by render_safeguard_tab
    # before calling this function - do not apply again

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

                # Summary: actual vs baseline in tCO2-e (the gap = credits/surrenders)
                baseline = row['Baseline'] if 'Baseline' in row.index else 0
                summary_data = [{
                    'Source': source_name,
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Target (tCO2-e)': f"{baseline:,.0f}",
                    'SMC Annual': f"{smc_annual:,.0f}",
                    'SMC Cumulative': f"{row['SMC_Cumulative']:,.0f}"
                }]

                df_summary = pd.DataFrame(summary_data)
                st.dataframe(df_summary, hide_index=True, width="stretch")

    # ROM and Electricity charts (side by side)
    with st.expander("📊 ROM Production & Electricity Consumption", expanded=True):
        col1, col2 = st.columns(2)

        # Prepare display years without FY
        proj_display = projection.copy()
        proj_display['Year'] = proj_display['FY'].str.replace('FY', '')

        with col1:
            # ROM Production
            fig_rom = go.Figure()

            fig_rom.add_trace(go.Bar(
                x=proj_display['Year'],
                y=proj_display['ROM_Mt'],
                name='ROM Production',
                marker_color=GOLD_METALLIC
            ))

            # Add grid connection marker
            if grid_connected_fy:
                grid_year = str(grid_connected_fy)
                if grid_year in proj_display['Year'].values:
                    fig_rom.add_shape(
                        type="line",
                        x0=grid_year,
                        x1=grid_year,
                        y0=0,
                        y1=1,
                        yref="paper",
                        line=dict(color=GRID_GREEN, width=2, dash="dot")
                    )
                    fig_rom.add_annotation(
                        x=grid_year,
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
            site_mwh = proj_display['Site_Electricity_kWh'] / 1000
            grid_mwh = proj_display['Grid_Electricity_kWh'] / 1000

            # Grid electricity (bottom of stack)
            fig_elec.add_trace(go.Bar(
                x=proj_display['Year'],
                y=grid_mwh,
                name='Grid Purchase',
                marker_color=DARK_GOLDENROD,
                opacity=0.9
            ))

            # Site electricity (top of stack)
            fig_elec.add_trace(go.Bar(
                x=proj_display['Year'],
                y=site_mwh,
                name='Site Generation',
                marker_color=BRIGHT_GOLD,
                opacity=0.9
            ))

            # Add grid connection marker
            if grid_connected_fy:
                grid_year = str(grid_connected_fy)
                if grid_year in proj_display['Year'].values:
                    fig_elec.add_shape(
                        type="line",
                        x0=grid_year,
                        x1=grid_year,
                        y0=0,
                        y1=1,
                        yref="paper",
                        line=dict(color=GRID_GREEN, width=2, dash="dot")
                    )
                    fig_elec.add_annotation(
                        x=grid_year,
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

    # Scope 1 Emissions vs Baseline Target (dual-axis)
    with st.expander("📊 Scope 1 Emissions vs Baseline Target", expanded=True):
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Prepare display years without FY
        projection_display = projection.copy()
        projection_display['Year'] = projection_display['FY'].str.replace('FY', '')

        # Determine Safeguard periods
        safeguard_years = projection_display[projection_display['In_Safeguard'] == True]['Year'].tolist()
        exit_fy = projection_display['Exit_FY'].iloc[0] if 'Exit_FY' in projection_display.columns and projection_display['Exit_FY'].notna().any() else None

        # Add shaded boxes FIRST (background layer)
        # Box 1: Safeguard years (light gray)
        if len(safeguard_years) > 0:
            fig.add_vrect(
                x0=safeguard_years[0],
                x1=safeguard_years[-1],
                fillcolor="rgba(144, 238, 144, 0.2)",  # Light green
                opacity=1,
                layer="below",
                line_width=0,
                annotation_text="Safeguard Period (≥100k tCO₂-e)",
                annotation_position="top left",
                annotation_font_size=10
            )

        # Opt-in period shown by bar colour change (blue tint)

        # Scope 1 Actual Emissions - separate trace per SMC phase for legend
        phase_config = [
            ('Safeguard', GOLD_METALLIC, True),
            ('Opt-In',    '#B0B0B0',     True),      # Medium grey
            ('Exited',    '#000000',     True),       # Black
        ]
        safeguard_phases = {'Pre-Safeguard', 'Safeguard'}
        for phase_name, colour, show in phase_config:
            if 'SMC_Phase' in projection_display.columns:
                if phase_name == 'Safeguard':
                    mask = projection_display['SMC_Phase'].isin(safeguard_phases)
                else:
                    mask = projection_display['SMC_Phase'] == phase_name
                phase_df = projection_display[mask]
            else:
                phase_df = projection_display if phase_name == 'Safeguard' else pd.DataFrame()

            if len(phase_df) > 0:
                fig.add_trace(
                    go.Bar(
                        x=phase_df['Year'],
                        y=phase_df['Scope1'],
                        name=phase_name,
                        marker_color=colour,
                        opacity=0.8,
                        showlegend=show,
                        hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
                    ),
                    secondary_y=False
                )

        # Baseline Target (same axis) - the gap = credits or surrenders
        if 'Baseline' in projection_display.columns:
            fig.add_trace(
                go.Scatter(
                    x=projection_display['Year'],
                    y=projection_display['Baseline'],
                    name='Target',
                    mode='lines+markers',
                    line=dict(color=CAFE_NOIR, width=3, dash='dash'),
                    marker=dict(size=5),
                    hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
                ),
                secondary_y=False
            )

        # 100k Safeguard threshold reference line
        fig.add_hline(
            y=SAFEGUARD_THRESHOLD, line_dash="dot",
            line_color="rgba(192, 57, 43, 0.5)", line_width=1.5,
            annotation_text="100k Threshold",
            annotation_position="bottom right",
            annotation_font=dict(size=9, color="rgba(192, 57, 43, 0.6)"),
            secondary_y=False
        )

        # Add grid connection marker
        if grid_connected_fy:
            grid_year = str(grid_connected_fy)
            if grid_year in projection_display['Year'].values:
                fig.add_shape(
                    type="line",
                    x0=grid_year,
                    x1=grid_year,
                    y0=0,
                    y1=1,
                    yref="paper",
                    line=dict(color=GRID_GREEN, width=2, dash="dot")
                )
                fig.add_annotation(
                    x=grid_year,
                    y=1,
                    yref="paper",
                    text="Grid Connected",
                    showarrow=False,
                    yshift=10
                )

        fig.update_xaxes(title_text="Financial Year")
        fig.update_yaxes(title_text="Scope 1 Emissions (tCO2-e)", secondary_y=False)
        fig.update_yaxes(visible=False, secondary_y=True)

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
            # Prepare display years
            credit_data['Year'] = credit_data['FY'].str.replace('FY', '')

            # Determine Safeguard periods
            safeguard_years = credit_data[credit_data['In_Safeguard'] == True]['Year'].tolist()
            exit_fy = credit_data['Exit_FY'].iloc[0] if 'Exit_FY' in credit_data.columns and credit_data['Exit_FY'].notna().any() else None

            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # --- Phase-shaded background regions ---
            if 'SMC_Phase' in credit_data.columns:
                # Safeguard period (covered, >= 100k)
                sg_years = credit_data[credit_data['SMC_Phase'] == 'Safeguard']['Year'].tolist()
                if sg_years:
                    fig.add_vrect(
                        x0=sg_years[0], x1=sg_years[-1],
                        fillcolor="rgba(144, 238, 144, 0.15)",
                        layer="below", line_width=0,
                        annotation_text="Safeguard",
                        annotation_position="top left",
                        annotation_font=dict(size=10, color="rgba(0,100,0,0.6)")
                    )
                # Opt-in period (below threshold, credits only per s58B)
                optin_years = credit_data[credit_data['SMC_Phase'] == 'Opt-In']['Year'].tolist()
                if optin_years:
                    fig.add_vrect(
                        x0=optin_years[0], x1=optin_years[-1],
                        fillcolor="rgba(100, 149, 237, 0.12)",
                        layer="below", line_width=0,
                        annotation_text="Opt-In (s58B)",
                        annotation_position="top left",
                        annotation_font=dict(size=10, color="rgba(65,105,225,0.7)")
                    )
                # Exited period (no credits)
                exited_years = credit_data[credit_data['SMC_Phase'] == 'Exited']['Year'].tolist()
                if exited_years:
                    fig.add_vrect(
                        x0=exited_years[0], x1=exited_years[-1],
                        fillcolor="rgba(200, 200, 200, 0.15)",
                        layer="below", line_width=0,
                        annotation_text="Exited",
                        annotation_position="top left",
                        annotation_font=dict(size=10, color="rgba(128,128,128,0.7)")
                    )

            # --- Waterfall chart: bars float at cumulative position ---
            # Calculate base (bottom) of each waterfall bar
            annual_vals = credit_data['SMC_Annual'].values
            cum_vals = credit_data['SMC_Cumulative'].values
            bases = []
            for i, (ann, cum) in enumerate(zip(annual_vals, cum_vals)):
                if ann >= 0:
                    bases.append(cum - ann)  # Credit: base at previous cumulative
                else:
                    bases.append(cum)  # Surrender: base at new (lower) cumulative
            bar_colors = ['#2A9D8F' if v >= 0 else '#CA564B' for v in annual_vals]
            bar_heights = [abs(v) for v in annual_vals]

            # Waterfall bars (floating) with rounded corners and labels
            bar_labels = []
            for v in annual_vals:
                if abs(v) >= 1000:
                    bar_labels.append(f"{v/1000:+,.0f}k")
                elif v != 0:
                    bar_labels.append(f"{v:+,.0f}")
                else:
                    bar_labels.append("")

            fig.add_trace(
                go.Bar(
                    x=credit_data['Year'],
                    y=bar_heights,
                    base=bases,
                    name='Annual SMC',
                    marker_color=bar_colors,
                    marker_cornerradius=4,
                    opacity=0.9,
                    text=bar_labels,
                    textposition='outside',
                    textfont=dict(size=11, color='rgba(57, 37, 11, 0.8)'),
                    constraintext='none',
                    hovertext=[f"{v:,.0f} tCO2-e ({'credit' if v >= 0 else 'surrender'})" for v in annual_vals],
                    hovertemplate='%{hovertext}<extra></extra>'
                ),
                secondary_y=False
            )

            # Connector lines between bars (dashed, linking closing to opening)
            for i in range(1, len(credit_data)):
                prev_cum = cum_vals[i - 1]
                fig.add_shape(
                    type="line",
                    x0=credit_data['Year'].iloc[i - 1],
                    x1=credit_data['Year'].iloc[i],
                    y0=prev_cum,
                    y1=prev_cum,
                    line=dict(color='rgba(138, 126, 107, 0.4)', width=1, dash='dot'),
                )

            # Cumulative value line on secondary axis
            fig.add_trace(
                go.Scatter(
                    x=credit_data['Year'],
                    y=credit_data['Credit_Value_Cumulative'],
                    name='Cumulative Value ($)',
                    mode='lines+markers',
                    line=dict(color=GOLD_METALLIC, width=3),
                    marker=dict(size=6, color=GOLD_METALLIC),
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=True
            )

            # Labels on value line at 5-year intervals (2025, 2030, 2035, ...)
            years_list = credit_data['Year'].tolist()
            value_vals = credit_data['Credit_Value_Cumulative'].values
            key_indices = set()
            for idx, yr in enumerate(years_list):
                if int(yr) % 5 == 0:
                    key_indices.add(idx)
            # Always include last year
            key_indices.add(len(years_list) - 1)

            for idx in key_indices:
                if idx < len(years_list) and value_vals[idx] > 0:
                    val_m = value_vals[idx] / 1e6
                    cum_k = cum_vals[idx] / 1000
                    # $ value label (top line)
                    # $ value (top line, above data point)
                    fig.add_annotation(
                        x=years_list[idx],
                        y=value_vals[idx],
                        yref='y2',
                        text=f"<b>${val_m:.1f}M</b>",
                        showarrow=False,
                        yshift=-16,
                        font=dict(size=11, color=GOLD_METALLIC),
                    )
                    # tCO2 (below $, still above line)
                    fig.add_annotation(
                        x=years_list[idx],
                        y=value_vals[idx],
                        yref='y2',
                        text=f"<b>({cum_k:.0f}k)</b>",
                        showarrow=False,
                        yshift=-30,
                        font=dict(size=11, color=GOLD_METALLIC),
                    )

            # Zero line
            fig.add_hline(y=0, line_dash="solid", line_color="grey", line_width=0.5, secondary_y=False)

            # Grid connection marker
            if grid_connected_fy and str(grid_connected_fy) in years_list:
                fig.add_vline(
                    x=str(grid_connected_fy),
                    line_dash="dot", line_color=GRID_GREEN, line_width=2
                )

            fig.update_xaxes(title_text="Financial Year")
            fig.update_yaxes(title_text="SMC Balance (tCO2-e)", secondary_y=False)
            fig.update_yaxes(title_text=f"Cumulative Value (AUD, {credit_escalation*100:.1f}% p.a.)", secondary_y=True)

            # Scale axes so waterfall bars sit in lower portion, value line in upper
            # Left axis: extend range so bars use ~55% of chart height
            # Right axis: compress range so line sits at ~80% chart height
            max_cum = max(credit_data['SMC_Cumulative'].max(), 1)
            max_value = max(credit_data['Credit_Value_Cumulative'].max(), 1)
            # Left axis: bars use ~65% height.  Right axis: line at ~80% height
            fig.update_yaxes(
                secondary_y=False,
                range=[0, max_cum * 1.55],
            )
            fig.update_yaxes(
                secondary_y=True,
                range=[0, max_value * 1.25],
            )

            fig.update_layout(
                height=500,
                hovermode='x unified',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                bargap=0.15,
            )

            st.plotly_chart(fig, width="stretch")

            # Summary stats
            final_credits = credit_data.iloc[-1]['SMC_Cumulative']
            final_value = credit_data.iloc[-1]['Credit_Value_Cumulative']
            final_price = credit_data.iloc[-1]['Credit_Price']
            final_year = credit_data.iloc[-1]['FY']
            total_surrenders = credit_data[credit_data['SMC_Annual'] < 0]['SMC_Annual'].sum()

            summary_parts = [f"{final_year} Net Cumulative: {final_credits:,.0f} tCO2-e"]
            summary_parts.append(f"Value: ${final_value:,.0f} AUD (price: ${final_price:.2f}/tCO2-e)")
            if total_surrenders < 0:
                summary_parts.append(f"Total surrenders: {abs(total_surrenders):,.0f} tCO2-e")

            st.caption(" | ".join(summary_parts))


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

            summary_rows = []

            for source_name, row in [('Base', row_base), ('NPI-NGERS', row_npi)]:
                smc_annual = row['SMC_Annual'] if row['FY'].replace('FY','').isdigit() and int(row['FY'].replace('FY','')) >= credit_start_fy else 0
                baseline = row['Baseline'] if 'Baseline' in row.index else 0
                summary_rows.append({
                    'Source': source_name,
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Target (tCO2-e)': f"{baseline:,.0f}",
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

    # Scope 1 Emissions vs Baseline Target
    with st.expander("📊 Scope 1 Emissions vs Baseline Target", expanded=True):

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Base', 'NPI-NGERS'),
            specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
            vertical_spacing=0.15,
            row_heights=[0.5, 0.5]
        )

        # Base (top chart) - per-phase bar traces
        safeguard_phases = {'Pre-Safeguard', 'Safeguard'}
        for phase_name, colour in [('Safeguard', GOLD_METALLIC), ('Opt-In', '#B0B0B0'), ('Exited', '#000000')]:
            if 'SMC_Phase' in proj_base.columns:
                mask = proj_base['SMC_Phase'].isin(safeguard_phases) if phase_name == 'Safeguard' else (proj_base['SMC_Phase'] == phase_name)
                pdf = proj_base[mask]
            else:
                pdf = proj_base if phase_name == 'Safeguard' else pd.DataFrame()
            if len(pdf) > 0:
                fig.add_trace(
                    go.Bar(x=pdf['FY'], y=pdf['Scope1'], name=phase_name,
                           marker_color=colour, opacity=0.8,
                           hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'),
                    secondary_y=False, row=1, col=1
                )

        if 'Baseline' in proj_base.columns:
            fig.add_trace(
                go.Scatter(
                    x=proj_base['FY'],
                    y=proj_base['Baseline'],
                    name='Target',
                    mode='lines+markers',
                    line=dict(color=CAFE_NOIR, width=3, dash='dash'),
                    marker=dict(size=5),
                    hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
                ),
                secondary_y=False,
                row=1, col=1
            )

        # 100k threshold
        fig.add_hline(
            y=SAFEGUARD_THRESHOLD, line_dash="dot",
            line_color="rgba(192, 57, 43, 0.5)", line_width=1,
            secondary_y=False, row=1, col=1
        )

        # NPI (bottom chart) - per-phase bar traces (no legend duplication)
        for phase_name, colour in [('Safeguard', GOLD_METALLIC), ('Opt-In', '#B0B0B0'), ('Exited', '#000000')]:
            if 'SMC_Phase' in proj_npi.columns:
                mask = proj_npi['SMC_Phase'].isin(safeguard_phases) if phase_name == 'Safeguard' else (proj_npi['SMC_Phase'] == phase_name)
                pdf = proj_npi[mask]
            else:
                pdf = proj_npi if phase_name == 'Safeguard' else pd.DataFrame()
            if len(pdf) > 0:
                fig.add_trace(
                    go.Bar(x=pdf['FY'], y=pdf['Scope1'], name=phase_name,
                           marker_color=colour, opacity=0.8, showlegend=False,
                           hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'),
                    secondary_y=False, row=2, col=1
                )

        if 'Baseline' in proj_npi.columns:
            fig.add_trace(
                go.Scatter(
                    x=proj_npi['FY'],
                    y=proj_npi['Baseline'],
                    name="Target'",
                    mode='lines+markers',
                    line=dict(color=CAFE_NOIR, width=3, dash='dash'),
                    marker=dict(size=5),
                    showlegend=False,
                    hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
                ),
                secondary_y=False,
                row=2, col=1
            )

        # 100k threshold on NPI chart
        fig.add_hline(
            y=SAFEGUARD_THRESHOLD, line_dash="dot",
            line_color="rgba(192, 57, 43, 0.5)", line_width=1,
            secondary_y=False, row=2, col=1
        )

        # Placeholder for secondary axis compatibility
        fig.add_trace(
            go.Scatter(x=[], y=[], showlegend=False),
            secondary_y=True,
            row=2, col=1
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year", row=2, col=1)
        fig.update_yaxes(title_text="Scope 1 (tCO2-e)", secondary_y=False, row=1, col=1)
        fig.update_yaxes(visible=False, secondary_y=True, row=1, col=1)
        fig.update_yaxes(title_text="Scope 1 (tCO2-e)", secondary_y=False, row=2, col=1)
        fig.update_yaxes(visible=False, secondary_y=True, row=2, col=1)

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

        # Helper to add waterfall SMC traces for a dataset
        def add_smc_traces(proj, row, show_legend=True, name_suffix=''):
            annual_vals = proj['SMC_Annual'].values
            cum_vals = proj['SMC_Cumulative'].values
            fy_vals = proj['FY'].tolist()
            value_vals = proj['Credit_Value_Cumulative'].values

            # Calculate waterfall bases
            bases = []
            for i, (ann, cum) in enumerate(zip(annual_vals, cum_vals)):
                if ann >= 0:
                    bases.append(cum - ann)
                else:
                    bases.append(cum)
            bar_colors = ['#2A9D8F' if v >= 0 else '#CA564B' for v in annual_vals]
            bar_heights = [abs(v) for v in annual_vals]

            # Waterfall bars with rounded corners and labels
            bar_labels = []
            for v in annual_vals:
                if abs(v) >= 1000:
                    bar_labels.append(f"{v/1000:+,.0f}k")
                elif v != 0:
                    bar_labels.append(f"{v:+,.0f}")
                else:
                    bar_labels.append("")

            fig.add_trace(
                go.Bar(
                    x=fy_vals,
                    y=bar_heights,
                    base=bases,
                    name=f'Annual SMC{name_suffix}',
                    marker_color=bar_colors,
                    marker_cornerradius=4,
                    opacity=0.9,
                    text=bar_labels,
                    textposition='outside',
                    textfont=dict(size=10, color='rgba(57, 37, 11, 0.8)'),
                    constraintext='none',
                    showlegend=show_legend,
                    hovertext=[f"{v:,.0f} tCO2-e" for v in annual_vals],
                    hovertemplate='%{hovertext}<extra></extra>'
                ),
                secondary_y=False, row=row, col=1
            )

            # Connector lines
            for i in range(1, len(fy_vals)):
                prev_cum = cum_vals[i - 1]
                fig.add_shape(
                    type="line",
                    x0=fy_vals[i - 1], x1=fy_vals[i],
                    y0=prev_cum, y1=prev_cum,
                    line=dict(color='rgba(138, 126, 107, 0.4)', width=1, dash='dot'),
                    row=row, col=1
                )

            # Value line
            fig.add_trace(
                go.Scatter(
                    x=fy_vals,
                    y=value_vals,
                    name=f'Cumulative Value{name_suffix}',
                    mode='lines+markers',
                    line=dict(color=GOLD_METALLIC, width=3),
                    marker=dict(size=4),
                    showlegend=show_legend,
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=True, row=row, col=1
            )

            # Zero line
            fig.add_hline(y=0, line_dash="solid", line_color="grey", line_width=0.5,
                          secondary_y=False, row=row, col=1)

        # Base (top chart)
        add_smc_traces(proj_base, row=1, show_legend=True)
        # NPI-NGERS (bottom chart)
        add_smc_traces(proj_npi, row=2, show_legend=False, name_suffix="'")

        # Update axes
        fig.update_xaxes(title_text="Financial Year", row=2, col=1)
        fig.update_yaxes(title_text="SMC Credits / Surrenders (tCO2-e)", secondary_y=False, row=1, col=1)
        fig.update_yaxes(title_text="Cumulative Value ($AUD)", secondary_y=True, row=1, col=1)
        fig.update_yaxes(title_text="SMC Credits / Surrenders (tCO2-e)", secondary_y=False, row=2, col=1)
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