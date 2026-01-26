"""
tab3_carbon_tax.py
Carbon Tax Analysis Tab with Plotly charts
Last updated: 2026-01-23 17:00 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from projections import build_projection_simple, carbon_tax_analysis
from config import COLORS, SCOPE_NAMES


def render_carbon_tax_tab(rom_df, energy_df, nga_factors, fsei_rom, fsei_elec,
                          start_fy, end_fy, grid_connected_fy,
                          end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                          carbon_credit_price, credit_escalation,
                          tax_start_fy, tax_rate, tax_escalation):
    """Render the Carbon Tax Analysis tab"""

    st.subheader("Carbon Tax Analysis")
    st.caption(f"Projection: FY{start_fy}—FY{end_fy}")
    st.caption(f"Tax Scenario: Introduction FY{tax_start_fy} @ ${tax_rate:.0f}/tCO₂-e, escalating {tax_escalation * 100:.1f}% p.a.")
    st.caption(f"Credit Market: ${carbon_credit_price:.0f}/tCO₂-e, escalating {credit_escalation * 100:.1f}% p.a.")

    # Build projection
    projection = build_projection_simple(
        start_fy, end_fy, rom_df, energy_df, nga_factors,
        fsei_rom, fsei_elec, grid_connected_fy,
        end_mining_fy, end_processing_fy, end_rehabilitation_fy
    )

    # Calculate carbon tax
    carbon_tax = carbon_tax_analysis(projection, tax_start_fy, tax_rate, tax_escalation)

    # Metrics
    display_tax_metrics(carbon_tax, projection, carbon_credit_price)

    # Charts
    display_tax_charts(carbon_tax, projection, carbon_credit_price, credit_escalation,
                      tax_start_fy, tax_rate, tax_escalation)

    # Table
    display_tax_table(carbon_tax)


def display_tax_metrics(carbon_tax, projection, carbon_credit_price):
    """Display carbon tax summary metrics"""

    with st.expander("💰 Summary", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Tax Liability", f"${carbon_tax['total_tax'] / 1e6:.1f}M")
            st.caption("Cumulative tax over period")
        with col2:
            st.metric("Tax NPV @ 10%", f"${carbon_tax['npv_10pct'] / 1e6:.1f}M")
            st.caption("Present value of tax")
        with col3:
            avg_annual = carbon_tax['total_tax'] / len(carbon_tax['df']) if len(carbon_tax['df']) > 0 else 0
            st.metric("Average Annual Tax", f"${avg_annual / 1e6:.1f}M")
            st.caption("Per year average")
        with col4:
            # Calculate total SMC credit value
            final_smc_credits = abs(projection['SMC_Cumulative'].iloc[-1])
            st.metric("SMC Credit Value", f"${final_smc_credits * carbon_credit_price / 1e6:.1f}M")
            st.caption(f"@ current ${carbon_credit_price:.0f}/t price")


def display_tax_charts(carbon_tax, projection, carbon_credit_price, credit_escalation,
                      tax_start_fy, tax_rate, tax_escalation):
    """Display Plotly charts for carbon tax analysis"""

    from plotly.subplots import make_subplots

    with st.expander("📈 Carbon Tax Analysis", expanded=True):
        # Merge tax data with projection data
        tax_df = carbon_tax['df'].copy()
        proj_df = projection[['FY', 'SMC_Annual', 'SMC_Cumulative']].copy()

        # Convert FY strings to years for merging
        tax_df['FY_year'] = tax_df['FY'].str.replace('FY', '').astype(int)
        proj_df['FY_year'] = proj_df['FY'].str.replace('FY', '').astype(int)

        # Merge
        combined = tax_df.merge(proj_df, on='FY_year', how='left')

        # Calculate cumulative tax
        combined['Tax_Cumulative_M'] = combined['Annual_Tax'].cumsum() / 1e6
        combined['Annual_Tax_M'] = combined['Annual_Tax'] / 1e6

        # Chart: Annual Carbon Tax with Cumulative on secondary axis
        st.subheader("Annual Carbon Tax & Cumulative Liability")

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Cumulative tax (bars on primary y-axis)
        fig.add_trace(
            go.Bar(
                x=combined['FY_year'],
                y=combined['Tax_Cumulative_M'],
                name='Cumulative Tax',
                marker=dict(
                    color='#E8D5B7',  # Light tan/beige
                    line=dict(width=0)
                ),
                hovertemplate='<b>FY%{x}</b><br>Cumulative: $%{y:.2f}M<extra></extra>'
            ),
            secondary_y=False
        )

        # Annual tax (line on secondary y-axis)
        fig.add_trace(
            go.Scatter(
                x=combined['FY_year'],
                y=combined['Annual_Tax_M'],
                mode='lines+markers',
                name='Annual Tax',
                line=dict(color=COLORS['power'], width=3),
                marker=dict(size=8),
                hovertemplate='<b>FY%{x}</b><br>Annual: $%{y:.2f}M<br>Rate: $%{customdata:.2f}/t<extra></extra>',
                customdata=combined['Tax_Rate']
            ),
            secondary_y=True
        )

        # Update axes
        fig.update_xaxes(title_text="Financial Year")
        fig.update_yaxes(title_text="Cumulative Tax ($M)", tickformat=',.0f', secondary_y=False)
        fig.update_yaxes(title_text="Annual Tax ($M)", tickformat=',.1f', secondary_y=True)

        fig.update_layout(
            height=400,
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig, width="stretch")
        st.caption(f"Tan bars: Cumulative tax liability | Amber line: Annual tax (starting FY{tax_start_fy} @ ${tax_rate:.0f}/t, escalating {tax_escalation*100:.1f}%/yr)")


def display_tax_table(carbon_tax):
    """Display annual tax projection table"""

    with st.expander("📊 Annual Tax Projection Table", expanded=False):
        tax_display = carbon_tax['df'].copy()
        tax_display['Tax_Rate'] = tax_display['Tax_Rate'].apply(lambda x: f"${x:.2f}")
        tax_display['Scope1'] = tax_display['Scope1'].apply(lambda x: f"{x:,.0f}")
        tax_display['Annual_Tax'] = tax_display['Annual_Tax'].apply(lambda x: f"${x:,.0f}")
        tax_display.columns = ['FY', 'Tax Rate', 'Scope 1 (tCO₂-e)', 'Annual Tax']

        st.dataframe(tax_display, width="stretch", hide_index=True)