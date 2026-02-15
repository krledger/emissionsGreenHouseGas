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
from config import DECLINE_RATE_PHASE1, DECLINE_PHASE1_START, DECLINE_PHASE2_END, SAFEGUARD_THRESHOLD, DEFAULT_GRID_CONNECTION_DATE



def prepare_annual_for_safeguard(monthly, year_type='FY'):
    """Aggregate monthly data to annual and prepare for Safeguard display

    Args:
        monthly: Monthly DataFrame from build_projection
        year_type: 'FY' or 'CY' - aggregation boundary

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

    # Aggregate monthly -> annual
    annual = aggregate_by_year_type(monthly, year_type, agg_dict=agg_dict)

    # Add FY column as string for compatibility (works for both FY and CY labels)
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


def _add_phase_markers(fig, years_list, grid_connected_date,
                       end_mining_date, end_processing_date, end_rehabilitation_date,
                       year_type='FY'):
    """Add phase transition vertical lines and top-aligned labels to a chart.

    Accepts dates directly and converts to bare year number at render time.
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
        yr = str(date_to_cy(dt)) if year_type == 'CY' else str(date_to_fy(dt))
        if yr not in years_set:
            continue
        fig.add_shape(type="line", x0=yr, x1=yr, y0=0, y1=1, yref="paper",
                     line=dict(color=colour, width=1.5, dash=dash))
        fig.add_annotation(x=yr, y=1.0, yref="paper", text=label, showarrow=False,
                          yshift=10 + i * 14, font=dict(size=9, color=colour))


def render_safeguard_tab(df, fsei_rom, fsei_elec,
                         start_date, end_date,
                         end_mining_date, end_processing_date, end_rehabilitation_date,
                         carbon_credit_price, credit_escalation, credit_start_date,
                         decline_rate_phase2=None, year_type='FY'):
    """Render Safeguard Mechanism tab

    NOTE: Safeguard Mechanism operates on Financial Year (July-June) per legislation.
    The year_type parameter is accepted for interface compatibility but ALWAYS forced to 'FY'.

    Args:
        df: Unified DataFrame from load_all_data()
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        Phase parameters (dates)
        carbon_credit_price: SMC market price (initial year)
        credit_escalation: Annual credit price escalation rate (decimal)
        credit_start_date: First date credits can be earned
        decline_rate_phase2: Optional Phase 2 decline rate override
        year_type: Ignored - always uses 'FY' per Safeguard legislation
    """
    # Safeguard Mechanism operates on Financial Year per legislation
    year_type = 'FY'

    grid_connected_date = DEFAULT_GRID_CONNECTION_DATE
    credit_start_fy = date_to_fy(credit_start_date)

    st.subheader("Safeguard Mechanism Analysis")
    st.caption(f"FSEI: ROM {fsei_rom:.4f} tCO2-e/t | Elec {fsei_elec:.4f} tCO2-e/MWh | Baseline declining {DECLINE_RATE_PHASE1*100:.1f}% p.a. (FY{DECLINE_PHASE1_START}–FY{DECLINE_PHASE2_END})")

    display_year = st.session_state.get('display_year', 2025)

    monthly = build_projection(
        df,
        end_mining_date=end_mining_date,
        end_processing_date=end_processing_date,
        end_rehabilitation_date=end_rehabilitation_date,
        fsei_rom=fsei_rom,
        fsei_elec=fsei_elec,
        credit_start_date=credit_start_date,
        start_date=start_date,
        end_date=end_date,
        decline_rate_phase2=decline_rate_phase2
    )

    # Aggregate monthly -> annual
    projection = prepare_annual_for_safeguard(monthly, year_type=year_type)

    # Apply credit value escalation
    projection = smc_credit_value_analysis(projection, credit_start_fy, carbon_credit_price, credit_escalation)

    display_safeguard_single(projection, display_year, carbon_credit_price, credit_escalation, credit_start_fy, fsei_rom, fsei_elec, df=df, year_type=year_type, grid_connected_date=grid_connected_date, end_mining_date=end_mining_date, end_processing_date=end_processing_date, end_rehabilitation_date=end_rehabilitation_date)

    # Data Table
    with st.expander("Safeguard Data Table", expanded=False):
        cols = ['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Baseline',
                'SMC_Annual', 'SMC_Cumulative',
                'Credit_Price', 'Credit_Value_Annual', 'Credit_Value_Cumulative']
        cols = [c for c in cols if c in projection.columns]
        display_df = projection[cols].copy()

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


def display_safeguard_single(projection, display_year, carbon_credit_price, credit_escalation, credit_start_fy, fsei_rom, fsei_elec, show_summary=True, df=None, year_type='FY', grid_connected_date=None, end_mining_date=None, end_processing_date=None, end_rehabilitation_date=None):
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

    # Year label based on year_type
    year_prefix = 'CY' if year_type == 'CY' else 'FY'
    year_label = f'{year_prefix}{display_year}'

    # Summary table - single row with all data
    if show_summary:
        with st.expander("Summary", expanded=True):
            year_data = projection[projection['FY'] == year_label]

            if len(year_data) == 0:
                st.warning(f"No data for {year_label}")
            else:
                row = year_data.iloc[0]

                # Extract year number for credit comparison
                year_num_str = row['FY'].replace('FY','').replace('CY','')
                smc_annual = row['SMC_Annual'] if year_num_str.isdigit() and int(year_num_str) >= credit_start_fy else 0

                # Summary: actual vs baseline in tCO2-e (the gap = credits/surrenders)
                baseline = row['Baseline'] if 'Baseline' in row.index else 0
                summary_data = [{
                    'ROM (Mt)': f"{row['ROM_Mt']:.2f}",
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Target (tCO2-e)': f"{baseline:,.0f}",
                    'SMC Annual': f"{smc_annual:,.0f}",
                    'SMC Cumulative': f"{row['SMC_Cumulative']:,.0f}"
                }]

                df_summary = pd.DataFrame(summary_data)
                st.dataframe(df_summary, hide_index=True, width="stretch")



    # ROM and Electricity charts (side by side)
    with st.expander("ROM Production & Electricity Consumption", expanded=True):
        col1, col2 = st.columns(2)

        # Prepare display years without FY
        proj_display = projection.copy()
        proj_display['Year'] = proj_display['FY'].str.replace(r'^[A-Z]+', '', regex=True)
        years_list = proj_display['Year'].tolist()

        with col1:
            # ROM Production
            fig_rom = go.Figure()

            fig_rom.add_trace(go.Bar(
                x=proj_display['Year'],
                y=proj_display['ROM_Mt'],
                name='ROM Production',
                marker_color=GOLD_METALLIC
            ))

            fig_rom.update_layout(
                title="ROM Production (Mt)",
                xaxis_title="Financial Year",
                yaxis_title="ROM (Mt)",
                height=400,
                showlegend=False
            )

            _add_phase_markers(fig_rom, years_list, grid_connected_date, end_mining_date, end_processing_date, end_rehabilitation_date, year_type=year_type)
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

            fig_elec.update_layout(
                title="Electricity Consumption (MWh)",
                xaxis_title="Financial Year",
                yaxis_title="Electricity (MWh)",
                height=400,
                barmode='stack',
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            _add_phase_markers(fig_elec, years_list, grid_connected_date, end_mining_date, end_processing_date, end_rehabilitation_date, year_type=year_type)
            st.plotly_chart(fig_elec, width="stretch")

    # Scope 1 Emissions vs Baseline Target (dual-axis)
    with st.expander("Scope 1 Emissions vs Baseline Target", expanded=True):
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Prepare display years without FY
        projection_display = projection.copy()
        projection_display['Year'] = projection_display['FY'].str.replace(r'^[A-Z]+', '', regex=True)
        years_list = projection_display['Year'].tolist()

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
                annotation_text="Safeguard Period (≥100k tCO2-e)",
                annotation_position="top left",
                annotation_font_size=10
            )

        # Opt-in period shown by bar colour change (blue tint)

        # Scope 1 Actual Emissions - separate trace per SMC phase for legend
        # Scope 1 Emissions - single trace with per-bar colours by SMC phase
        # Using one trace avoids Plotly grouped-bar positioning issues where
        # bars shift or disappear when phases change (e.g. moving grid year).
        phase_colour_map = {
            'Pre-Safeguard': GOLD_METALLIC,
            'Safeguard':     GOLD_METALLIC,
            'Gap':           '#E67E22',     # Amber - below 100k, s58B not available
            'Opt-In':        '#B0B0B0',     # Medium grey
            'Exited':        '#000000',     # Black
        }
        if 'SMC_Phase' in projection_display.columns:
            bar_colours = projection_display['SMC_Phase'].map(phase_colour_map).fillna(GOLD_METALLIC).tolist()
        else:
            bar_colours = GOLD_METALLIC

        fig.add_trace(
            go.Bar(
                x=projection_display['Year'],
                y=projection_display['Scope1'],
                name='Scope 1',
                marker_color=bar_colours,
                opacity=0.8,
                showlegend=False,
                hovertemplate='%{y:,.0f} tCO2-e<extra></extra>'
            ),
            secondary_y=False
        )

        # Invisible scatter traces for phase legend entries
        legend_phases = [
            ('Safeguard', GOLD_METALLIC),
            ('Gap',       '#E67E22'),
            ('Opt-In',    '#B0B0B0'),
            ('Exited',    '#000000'),
        ]
        if 'SMC_Phase' in projection_display.columns:
            active_phases = set(projection_display['SMC_Phase'].unique())
            active_phases.discard('Pre-Safeguard')  # Shown as Safeguard colour
        else:
            active_phases = {'Safeguard'}

        for phase_name, colour in legend_phases:
            if phase_name in active_phases or (phase_name == 'Safeguard' and 'Pre-Safeguard' in active_phases):
                fig.add_trace(
                    go.Bar(
                        x=[None], y=[None],
                        name=phase_name,
                        marker_color=colour,
                        showlegend=True,
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

        fig.update_xaxes(title_text="Calendar Year" if year_type == "CY" else "Financial Year")
        fig.update_yaxes(title_text="Scope 1 Emissions (tCO2-e)", secondary_y=False)
        fig.update_yaxes(visible=False, secondary_y=True)

        fig.update_layout(
            height=500,
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        _add_phase_markers(fig, years_list, grid_connected_date, end_mining_date, end_processing_date, end_rehabilitation_date, year_type=year_type)
        st.plotly_chart(fig, width="stretch")

    # Cumulative SMC Credits
    with st.expander("SMC Credits & Value", expanded=True):

        # Filter to credit period
        credit_data = projection[projection['FY'].str.replace(r'^[A-Z]+', '', regex=True).astype(int) >= credit_start_fy].copy()

        if len(credit_data) == 0:
            st.info("No SMC credits yet - credit period starts FY{credit_start_fy}")
        else:
            # Prepare display years
            credit_data['Year'] = credit_data['FY'].str.replace(r'^[A-Z]+', '', regex=True)

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
            if grid_connected_date:
                _gc_yr = str(date_to_fy(grid_connected_date))
                if _gc_yr in years_list:
                    fig.add_vline(
                        x=_gc_yr,
                        line_dash="dot", line_color=GRID_GREEN, line_width=2
                    )

            fig.update_xaxes(title_text="Calendar Year" if year_type == "CY" else "Financial Year")
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

            _add_phase_markers(fig, years_list, grid_connected_date, end_mining_date, end_processing_date, end_rehabilitation_date, year_type=year_type)
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