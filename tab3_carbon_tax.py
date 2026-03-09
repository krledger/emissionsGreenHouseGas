"""
tab3_carbon_tax.py
Carbon Tax Analysis tab — Scope 1 + Scope 2 pass-through
Last updated: 2026-03-09

Chart: Waterfall with S1/S2 stacked within each floating bar.
Uses barmode='overlay' with explicit base offsets so bars occupy the
same x position (not side-by-side).
"""

import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection, carbon_tax_analysis
from calc_calendar import date_to_fy, aggregate_by_year_type
from loader_nga import NGAFactorsByYear
from config import DEFAULT_GRID_CONNECTION_DATE, DEFAULT_EF2_DECLINE_RATE


def prepare_annual_for_tax(monthly, year_type='FY'):
    """Aggregate monthly data to annual and prepare for tax analysis display"""
    agg_dict = {
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum',
        'ROM_t': 'sum',
        'Grid_Electricity_kWh': 'sum',
        'Site_Electricity_kWh': 'sum',
    }

    if 'Phase' in monthly.columns:
        agg_dict['Phase'] = 'last'
    if 'Baseline' in monthly.columns:
        agg_dict['Baseline'] = 'sum'
    if 'SMC_Monthly' in monthly.columns:
        agg_dict['SMC_Monthly'] = 'sum'
    if 'SMC_Cumulative' in monthly.columns:
        agg_dict['SMC_Cumulative'] = 'last'

    annual = aggregate_by_year_type(monthly, year_type, agg_dict=agg_dict)
    annual['FY'] = annual['Year']
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']
    annual['Total'] = annual['Scope1'] + annual['Scope2'] + annual['Scope3']
    annual['Grid_Electricity_MWh'] = annual['Grid_Electricity_kWh'] / 1000.0
    annual['ROM_Mt'] = annual['ROM_t'] / 1_000_000
    if 'Phase' not in annual.columns:
        annual['Phase'] = 'Unknown'
    return annual


def render_carbon_tax_tab(df, fsei_rom, fsei_elec,
                          start_date, end_date,
                          end_mining_date, end_processing_date, end_rehabilitation_date,
                          carbon_credit_price, credit_escalation,
                          tax_start_date, tax_rate, tax_escalation,
                          credit_start_date,
                          decline_rate_phase2, year_type='FY',
                          include_scope2=False):
    """Render Carbon Tax Analysis tab

    Args:
        include_scope2: If True, includes Scope 2 electricity pass-through
                        (sensitivity case).  If False, Scope 1 only (base case).
    """
    tax_start_fy = date_to_fy(tax_start_date)

    st.subheader("Carbon Tax Scenario Analysis")
    scope_label = "Scope 1 (direct) + Scope 2 (electricity pass-through)" if include_scope2 else "Scope 1 (direct emissions) only — base case"
    st.caption(
        f"Tax starts FY{tax_start_fy} ({tax_start_date.strftime('%d %b %Y')}) "
        f"at ${tax_rate:.2f}/tCO\u2082-e, escalating {tax_escalation*100:.1f}% p.a.  "
        f"{scope_label}."
    )

    display_year = st.session_state.get('display_year', 2025)

    # Load NGA factors for Scope 2 electricity emission factor lookup
    nga_folder = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(nga_folder, 'nga_factors.csv')):
        nga_folder = '/mnt/project'
    try:
        nga_by_year = NGAFactorsByYear(nga_folder)
    except FileNotFoundError:
        nga_by_year = None
        st.warning("nga_factors.csv not found — Scope 2 tax will not be calculated.")

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

    projection = prepare_annual_for_tax(monthly, year_type)
    # Base case: Scope 1 only (nga_by_year=None suppresses Scope 2)
    # Sensitivity case: include Scope 2 electricity pass-through
    carbon_tax = carbon_tax_analysis(
        projection, tax_start_fy, tax_rate, tax_escalation,
        nga_by_year=nga_by_year if include_scope2 else None,
        state='QLD',
        ef2_decline_rate=DEFAULT_EF2_DECLINE_RATE
    )

    display_tax_single(carbon_tax, tax_start_fy, year_type=year_type)

    # Data Table
    with st.expander("Tax Data Table", expanded=False):
        tax_period = carbon_tax[carbon_tax['FY_num'] >= tax_start_fy].copy()
        if len(tax_period) > 0:
            display_cols = ['FY', 'Scope1', 'Grid_MWh', 'NGA_EF2',
                           'Tax_Rate', 'S2_Cost_per_MWh',
                           'Tax_S1_Annual', 'Tax_S2_Annual', 'Tax_Annual',
                           'Tax_Cumulative']
            display_cols = [c for c in display_cols if c in tax_period.columns]
            display_df = tax_period[display_cols].copy()

            fmt_map = {
                'Scope1': lambda x: f"{x:,.0f}",
                'Grid_MWh': lambda x: f"{x:,.0f}",
                'NGA_EF2': lambda x: f"{x:.4f}",
                'Tax_Rate': lambda x: f"${x:.2f}",
                'S2_Cost_per_MWh': lambda x: f"${x:.2f}",
                'Tax_S1_Annual': lambda x: f"${x:,.0f}",
                'Tax_S2_Annual': lambda x: f"${x:,.0f}",
                'Tax_Annual': lambda x: f"${x:,.0f}",
                'Tax_Cumulative': lambda x: f"${x:,.0f}",
            }
            for col, fn in fmt_map.items():
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(fn)

            rename_map = {
                'Scope1': 'Scope 1 (tCO\u2082-e)',
                'Grid_MWh': 'Grid Elec (MWh)',
                'NGA_EF2': 'NGA EF\u2082 (t/MWh)',
                'Tax_Rate': 'Rate ($/t)',
                'S2_Cost_per_MWh': 'S2 $/MWh',
                'Tax_S1_Annual': 'S1 Tax ($)',
                'Tax_S2_Annual': 'S2 Tax ($)',
                'Tax_Annual': 'Total Tax ($)',
                'Tax_Cumulative': 'Cumulative ($)',
            }
            display_df = display_df.rename(columns=rename_map)
            st.dataframe(display_df, hide_index=True, width='stretch', height=400)
        else:
            st.info(f"Tax period starts FY{tax_start_fy}")


def display_tax_single(carbon_tax, tax_start_fy, show_summary=True, year_type='FY'):
    """Display tax analysis — waterfall chart with stacked S1/S2.

    Uses barmode='overlay' with explicit base= on each trace so S1 and S2
    occupy the same x position.  S1 sits on the waterfall base, S2 sits
    on top of S1.  Connector lines link cumulative positions.
    """

    year_prefix = 'CY' if year_type == 'CY' else 'FY'
    display_year = st.session_state.get('display_year', 2025)
    year_label = f'{year_prefix}{display_year}'

    # Pastel palette
    GOLD_METALLIC = '#DBB12A'
    CAFE_NOIR = '#39250B'
    S1_COLOR = '#CA564B'       # Warm red-brown (tax = cost)
    S2_COLOR = '#D4A084'       # Dusty peach (electricity pass-through)
    CONNECTOR = 'rgba(138, 126, 107, 0.4)'

    tax_data = carbon_tax[carbon_tax['FY_num'] >= tax_start_fy]

    # --- Summary ---
    if show_summary:
        with st.expander("Summary", expanded=True):
            year_data = tax_data[tax_data['FY'] == year_label]
            if len(year_data) == 0:
                st.warning(f"No tax data for {year_label} (tax starts FY{tax_start_fy})")
            else:
                row = year_data.iloc[0]
                summary = {
                    'Scope 1 (tCO\u2082-e)': f"{row['Scope1']:,.0f}",
                    'Tax Rate ($/tCO\u2082-e)': f"${row['Tax_Rate']:.2f}",
                    'S1 Tax ($)': f"${row.get('Tax_S1_Annual', row.get('Tax_Annual', 0)):,.0f}",
                }
                if 'Grid_MWh' in row.index and row.get('Grid_MWh', 0) > 0:
                    summary['Grid Elec (MWh)'] = f"{row['Grid_MWh']:,.0f}"
                    summary['NGA EF\u2082 (t/MWh)'] = f"{row.get('NGA_EF2', 0):.4f}"
                    summary['S2 $/MWh'] = f"${row.get('S2_Cost_per_MWh', 0):.2f}"
                    summary['S2 Tax ($)'] = f"${row.get('Tax_S2_Annual', 0):,.0f}"
                summary['Total Tax ($)'] = f"${row['Tax_Annual']:,.0f}"
                summary['Cumulative ($)'] = f"${row['Tax_Cumulative']:,.0f}"
                st.dataframe(pd.DataFrame([summary]), hide_index=True, width='stretch')

    # --- Chart ---
    with st.expander("Tax Liability", expanded=True):
        if len(tax_data) == 0:
            st.info(f"Tax period starts FY{tax_start_fy}")
        else:
            tax_data = tax_data.copy()
            tax_data['Year_Display'] = tax_data['FY'].str.replace(r'^[A-Z]{2}', '', regex=True)

            has_s2 = ('Tax_S2_Annual' in tax_data.columns
                      and tax_data['Tax_S2_Annual'].sum() > 0)

            fig = go.Figure()

            # --- Waterfall calculations ---
            s1_vals = tax_data.get('Tax_S1_Annual', tax_data['Tax_Annual']).values
            s2_vals = tax_data['Tax_S2_Annual'].values if has_s2 else [0] * len(s1_vals)
            annual_vals = tax_data['Tax_Annual'].values
            cum_vals = tax_data['Tax_Cumulative'].values

            # Waterfall base: each bar floats at previous cumulative
            bases = []
            for i, (ann, cum) in enumerate(zip(annual_vals, cum_vals)):
                if ann >= 0:
                    bases.append(cum - ann)
                else:
                    bases.append(cum)

            # S2 base sits on top of S1 within the same waterfall position
            s2_bases = [b + abs(s1) for b, s1 in zip(bases, s1_vals)]

            # --- S1 bars (bottom layer) ---
            fig.add_trace(
                go.Bar(
                    x=tax_data['Year_Display'],
                    y=[abs(v) for v in s1_vals],
                    base=bases,
                    name='Scope 1 Tax',
                    marker_color=S1_COLOR,
                    marker_cornerradius=4,
                    opacity=0.9,
                    width=0.6,
                    customdata=[abs(v) for v in s1_vals],
                    hovertemplate='S1: $%{customdata:,.0f}<extra></extra>'
                )
            )

            # --- S2 bars (top layer, same x position) ---
            if has_s2:
                fig.add_trace(
                    go.Bar(
                        x=tax_data['Year_Display'],
                        y=[abs(v) for v in s2_vals],
                        base=s2_bases,
                        name='Scope 2 Tax (Electricity)',
                        marker_color=S2_COLOR,
                        marker_cornerradius=4,
                        opacity=0.9,
                        width=0.6,
                        customdata=[abs(v) for v in s2_vals],
                        hovertemplate='S2: $%{customdata:,.0f}<extra></extra>'
                    )
                )

            # --- Bar labels (total annual) ---
            bar_labels = []
            for v in annual_vals:
                if abs(v) >= 1_000_000:
                    bar_labels.append(f"${abs(v)/1_000_000:.1f}M")
                elif abs(v) >= 1_000:
                    bar_labels.append(f"${abs(v)/1_000:.0f}K")
                elif v != 0:
                    bar_labels.append(f"${abs(v):,.0f}")
                else:
                    bar_labels.append("")

            # Text labels at bar tops — use annotations not a scatter trace
            # so they scale correctly with the primary axis
            for i, label in enumerate(bar_labels):
                if label:
                    fig.add_annotation(
                        x=tax_data['Year_Display'].iloc[i],
                        y=bases[i],
                        text=label,
                        showarrow=False,
                        yshift=-14,
                        font=dict(size=10, color='rgba(57, 37, 11, 0.7)'),
                    )

            # --- Connector lines between bars ---
            for i in range(1, len(tax_data)):
                prev_cum = cum_vals[i - 1]
                fig.add_shape(
                    type="line",
                    x0=tax_data['Year_Display'].iloc[i - 1],
                    x1=tax_data['Year_Display'].iloc[i],
                    y0=prev_cum,
                    y1=prev_cum,
                    line=dict(color=CONNECTOR, width=1, dash='dot'),
                )

            # --- Cumulative line on secondary axis ---
            # Offset line above bars for visual separation
            max_cum = max(tax_data['Tax_Cumulative'].max(), 1)
            line_offset = max_cum * 0.08
            cum_vals_display = cum_vals + line_offset

            fig.add_trace(
                go.Scatter(
                    x=tax_data['Year_Display'],
                    y=cum_vals_display,
                    name='Cumulative Tax ($)',
                    mode='lines+markers',
                    line=dict(color=GOLD_METALLIC, width=3),
                    marker=dict(size=6, color=GOLD_METALLIC),
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                )
            )

            # --- Labels at 5-year intervals on cumulative line ---
            years_list = tax_data['Year_Display'].tolist()
            key_indices = set()
            for idx, yr in enumerate(years_list):
                try:
                    if int(yr) % 5 == 0:
                        key_indices.add(idx)
                except ValueError:
                    pass
            key_indices.add(len(years_list) - 1)

            for idx in key_indices:
                if idx < len(years_list) and cum_vals[idx] > 0:
                    val_m = cum_vals[idx] / 1e6
                    fig.add_annotation(
                        x=years_list[idx],
                        y=cum_vals_display[idx],

                        text=f"<b>${val_m:.1f}M</b>",
                        showarrow=False,
                        yshift=14,
                        font=dict(size=11, color=GOLD_METALLIC),
                    )

            # Zero line
            fig.add_hline(y=0, line_dash="solid", line_color="grey",
                         line_width=0.5)

            # Axis scaling — match original waterfall proportions
            fig.update_xaxes(
                title_text="Calendar Year" if year_type == "CY" else "Financial Year"
            )
            fig.update_yaxes(
                title_text="Tax Liability (AUD)",
                range=[0, max_cum * 1.5]
            )

            # barmode='overlay' is critical — both traces use explicit base=
            # so overlay lets them share the same x position
            fig.update_layout(
                title="Carbon Tax Liability \u2014 Scope 1 + Scope 2",
                hovermode='x unified',
                height=500,
                showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="right", x=1),
                barmode='overlay',
                bargap=0.15,
            )

            st.plotly_chart(fig, width='stretch', key="tax_liability")

            # Caption — use st.markdown with inline style to avoid
            # st.caption's markdown rendering mangling $ signs as LaTeX
            if len(tax_data) > 0:
                final_year = tax_data['FY'].iloc[-1]
                final_cumulative = tax_data['Tax_Cumulative'].iloc[-1]
                final_rate = tax_data['Tax_Rate'].iloc[-1]
                final_s1 = tax_data.get('Tax_S1_Cumulative',
                                        pd.Series([0])).iloc[-1]
                final_s2 = tax_data.get('Tax_S2_Cumulative',
                                        pd.Series([0])).iloc[-1]

                caption_text = (
                    f"{final_year} Cumulative: ${final_cumulative:,.0f} AUD "
                    f"at ${final_rate:.2f}/tCO\u2082-e"
                )
                if final_s2 > 0 and final_cumulative > 0:
                    s1_pct = final_s1 / final_cumulative * 100
                    s2_pct = final_s2 / final_cumulative * 100
                    caption_text += (
                        f" &nbsp;(S1: ${final_s1:,.0f} [{s1_pct:.0f}%] "
                        f"| S2: ${final_s2:,.0f} [{s2_pct:.0f}%])"
                    )
                st.markdown(
                    f'<p style="font-size:13px; color:#6B7280; margin-top:4px;">'
                    f'{caption_text}</p>',
                    unsafe_allow_html=True
                )