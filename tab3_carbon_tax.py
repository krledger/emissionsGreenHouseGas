"""
tab3_carbon_tax.py
Carbon Tax Analysis tab - date-based architecture
Last updated: 2026-02-05 20:35 AEDT
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection, carbon_tax_analysis
from calc_calendar import date_to_fy, aggregate_by_year_type
from config import DEFAULT_GRID_CONNECTION_DATE


def prepare_annual_for_tax(monthly, year_type='FY'):
    """Aggregate monthly data to annual and prepare for tax analysis display

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
    if 'Phase' in monthly.columns:
        agg_dict['Phase'] = 'last'  # Take phase from last month of FY
    if 'Baseline' in monthly.columns:
        agg_dict['Baseline'] = 'sum'
    if 'SMC_Monthly' in monthly.columns:
        agg_dict['SMC_Monthly'] = 'sum'
    if 'SMC_Cumulative' in monthly.columns:
        agg_dict['SMC_Cumulative'] = 'last'

    # Aggregate monthly → annual (Tax Year/FY)
    annual = aggregate_by_year_type(monthly, year_type, agg_dict=agg_dict)

    # Add FY column as string for compatibility
    annual['FY'] = annual['Year']

    # Add compatibility columns
    annual['Scope1'] = annual['Scope1_tCO2e']
    annual['Scope2'] = annual['Scope2_tCO2e']
    annual['Scope3'] = annual['Scope3_tCO2e']
    annual['Total'] = annual['Scope1'] + annual['Scope2'] + annual['Scope3']

    # Convert ROM from tonnes to megatonnes
    annual['ROM_Mt'] = annual['ROM_t'] / 1_000_000

    # If Phase column is missing, add a default
    if 'Phase' not in annual.columns:
        annual['Phase'] = 'Unknown'

    return annual


def render_carbon_tax_tab(df, fsei_rom, fsei_elec,
                          start_date, end_date,
                          end_mining_date, end_processing_date, end_rehabilitation_date,
                          carbon_credit_price, credit_escalation,
                          tax_start_date, tax_rate, tax_escalation,
                          credit_start_date,
                          decline_rate_phase2, year_type='FY'):
    """Render Carbon Tax Analysis tab

    Args:
        df: Unified DataFrame from load_all_data()
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        Phase parameters (dates)
        carbon_credit_price: SMC market price
        credit_escalation: Annual price increase
        tax_start_date: Date tax starts
        tax_rate: Initial tax rate ($/tCO2-e)
        tax_escalation: Annual tax rate increase
        credit_start_date: First date credits can be earned
        decline_rate_phase2: Phase 2 decline rate
        year_type: 'FY' (Financial Year, July-June) or 'CY' (Calendar Year, Jan-Dec)
    """

    # Convert dates to FY for display
    tax_start_fy = date_to_fy(tax_start_date)
    credit_start_fy = date_to_fy(credit_start_date)

    st.subheader("Carbon Tax Scenario Analysis")
    st.caption(f"Tax starts FY{tax_start_fy} ({tax_start_date.strftime('%d %b %Y')}) at ${tax_rate:.2f}/tCO2-e, escalating {tax_escalation*100:.1f}% p.a. Based on Scope 1 emissions only.")

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
    projection = prepare_annual_for_tax(monthly, year_type)
    carbon_tax = carbon_tax_analysis(projection, tax_start_fy, tax_rate, tax_escalation)

    display_tax_single(carbon_tax, tax_start_fy, year_type=year_type)

    # Data Table
    with st.expander("Tax Data Table", expanded=False):
        tax_period = carbon_tax[carbon_tax['FY_num'] >= tax_start_fy].copy()
        if len(tax_period) > 0:
            display_df = tax_period[['FY', 'Scope1', 'Tax_Rate', 'Tax_Annual', 'Tax_Cumulative']].copy()

            # Format numbers
            display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
            display_df['Tax_Rate'] = display_df['Tax_Rate'].apply(lambda x: f"${x:.2f}")
            display_df['Tax_Annual'] = display_df['Tax_Annual'].apply(lambda x: f"${x:,.0f}")
            display_df['Tax_Cumulative'] = display_df['Tax_Cumulative'].apply(lambda x: f"${x:,.0f}")

            st.dataframe(display_df, hide_index=True, width="stretch", height=400)
        else:
            st.info(f"Tax period starts FY{tax_start_fy}")


def display_tax_single(carbon_tax, tax_start_fy, show_summary=True, year_type='FY'):
    """Display tax analysis for single data source

    Waterfall chart style matching SMC Credits & Value chart:
    - Floating bars show annual tax (green = tax owed, red = refund/credit)
    - Gold line shows cumulative tax liability on secondary axis
    - Connector lines link bar tops between years
    - Labels at 5-year intervals on cumulative line
    """

    # Construct year label based on year_type
    year_prefix = 'CY' if year_type == 'CY' else 'FY'
    display_year = st.session_state.get('display_year', 2025)
    year_label = f'{year_prefix}{display_year}'

    # Gold color palette
    GOLD_METALLIC = '#DBB12A'
    CAFE_NOIR = '#39250B'

    # Filter to tax period
    tax_data = carbon_tax[carbon_tax['FY_num'] >= tax_start_fy]

    # Summary table
    if show_summary:
        with st.expander("Summary", expanded=True):
            year_data = tax_data[tax_data['FY'] == year_label]

            if len(year_data) == 0:
                st.warning(f"No tax data for {year_label} (tax starts FY{tax_start_fy})")
            else:
                row = year_data.iloc[0]

                summary_data = [{
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Tax Rate ($/tCO2-e)': f"${row['Tax_Rate']:.2f}",
                    'Tax Annual ($)': f"${row['Tax_Annual']:,.0f}",
                    'Tax Cumulative ($)': f"${row['Tax_Cumulative']:,.0f}"
                }]

                df_summary = pd.DataFrame(summary_data)
                st.dataframe(df_summary, hide_index=True, width="stretch")

    # Tax Liability chart - waterfall style (matching SMC Credits & Value)
    with st.expander("Tax Liability", expanded=True):

        if len(tax_data) == 0:
            st.info(f"Tax period starts FY{tax_start_fy}")
        else:
            # Prepare display years
            tax_data = tax_data.copy()
            tax_data['Year'] = tax_data['FY'].str.replace(r'^[A-Z]{2}', '', regex=True)

            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # --- Waterfall bars: annual tax floating at cumulative position ---
            annual_vals = tax_data['Tax_Annual'].values
            cum_vals = tax_data['Tax_Cumulative'].values

            # Calculate base (bottom) of each waterfall bar
            bases = []
            for i, (ann, cum) in enumerate(zip(annual_vals, cum_vals)):
                if ann >= 0:
                    bases.append(cum - ann)  # Tax: base at previous cumulative
                else:
                    bases.append(cum)  # Refund: base at new (lower) cumulative

            # Green = tax owed, Red = refund/credit offset
            bar_colors = ['#CA564B' if v >= 0 else '#2A9D8F' for v in annual_vals]
            bar_heights = [abs(v) for v in annual_vals]

            # Bar labels
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

            fig.add_trace(
                go.Bar(
                    x=tax_data['Year'],
                    y=bar_heights,
                    base=bases,
                    name='Annual Tax',
                    marker_color=bar_colors,
                    marker_cornerradius=4,
                    opacity=0.9,
                    text=bar_labels,
                    textposition='outside',
                    textfont=dict(size=11, color='rgba(57, 37, 11, 0.8)'),
                    constraintext='none',
                    hovertext=[f"${v:,.0f} ({'tax' if v >= 0 else 'refund'})" for v in annual_vals],
                    hovertemplate='%{hovertext}<extra></extra>'
                ),
                secondary_y=False
            )

            # Connector lines between bars
            for i in range(1, len(tax_data)):
                prev_cum = cum_vals[i - 1]
                fig.add_shape(
                    type="line",
                    x0=tax_data['Year'].iloc[i - 1],
                    x1=tax_data['Year'].iloc[i],
                    y0=prev_cum,
                    y1=prev_cum,
                    line=dict(color='rgba(138, 126, 107, 0.4)', width=1, dash='dot'),
                )

            # Cumulative value line on secondary axis
            fig.add_trace(
                go.Scatter(
                    x=tax_data['Year'],
                    y=cum_vals,
                    name='Cumulative Tax ($)',
                    mode='lines+markers',
                    line=dict(color=GOLD_METALLIC, width=3),
                    marker=dict(size=6, color=GOLD_METALLIC),
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=True
            )

            # Labels at 5-year intervals on cumulative line
            years_list = tax_data['Year'].tolist()
            key_indices = set()
            for idx, yr in enumerate(years_list):
                if int(yr) % 5 == 0:
                    key_indices.add(idx)
            key_indices.add(len(years_list) - 1)  # Always include last year

            for idx in key_indices:
                if idx < len(years_list) and cum_vals[idx] > 0:
                    val_m = cum_vals[idx] / 1e6
                    fig.add_annotation(
                        x=years_list[idx],
                        y=cum_vals[idx],
                        yref='y2',
                        text=f"<b>${val_m:.1f}M</b>",
                        showarrow=False,
                        yshift=-16,
                        font=dict(size=11, color=GOLD_METALLIC),
                    )

            # Zero line
            fig.add_hline(y=0, line_dash="solid", line_color="grey", line_width=0.5, secondary_y=False)

            # Axis scaling: bars in upper portion, cumulative line below
            max_cum = max(tax_data['Tax_Cumulative'].max(), 1)
            fig.update_xaxes(title_text="Calendar Year" if year_type == "CY" else "Financial Year")
            fig.update_yaxes(title_text="Tax Liability (AUD)", secondary_y=False,
                           range=[0, max_cum * 1.55])
            fig.update_yaxes(title_text="Cumulative Tax ($AUD)", secondary_y=True,
                           range=[0, max_cum * 1.25])

            fig.update_layout(
                hovermode='x unified',
                height=500,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=0.95),
                bargap=0.15,
            )

            st.plotly_chart(fig, width="stretch", key="tax_liability")

            # Summary caption
            if len(tax_data) > 0:
                final_year = tax_data['FY'].iloc[-1]
                final_cumulative = tax_data['Tax_Cumulative'].iloc[-1]
                final_rate = tax_data['Tax_Rate'].iloc[-1]
                st.caption(f"{final_year} Cumulative Tax: ${final_cumulative:,.0f} AUD at ${final_rate:.2f}/tCO2-e")