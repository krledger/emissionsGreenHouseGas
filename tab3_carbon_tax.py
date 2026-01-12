"""
tab3_carbon_tax.py
Carbon Tax Analysis Tab with Plotly charts
Last updated: 2026-01-08 10:00 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from projections import build_projection_simple, carbon_tax_analysis
from config import COLORS, SCOPE_NAMES


def render_carbon_tax_tab(rom_df, energy_df, nga_factors, baseline_intensity,
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
        baseline_intensity, grid_connected_fy,
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

    with st.expander("📈 Credits vs Tax Liability", expanded=True):
        # Merge tax data with projection data
        tax_df = carbon_tax['df'].copy()
        proj_df = projection[['FY', 'SMC_Annual', 'SMC_Cumulative']].copy()

        # Convert FY strings to years for merging
        tax_df['FY_year'] = tax_df['FY'].str.replace('FY', '').astype(int)
        proj_df['FY_year'] = proj_df['FY'].str.replace('FY', '').astype(int)

        # Merge
        combined = tax_df.merge(proj_df, on='FY_year', how='left')

        # Calculate cumulative SMC credits (physical quantity)
        combined['SMC_Credits_Cumulative_tCO2'] = (-1 * combined['SMC_Cumulative']).abs()

        # Calculate SMC credit market value with escalation
        years_from_start = combined['FY_year'] - combined['FY_year'].min()
        combined['Credit_Price'] = carbon_credit_price * ((1 + credit_escalation) ** years_from_start)
        combined['SMC_Credits_Value_M'] = combined['SMC_Credits_Cumulative_tCO2'] * combined['Credit_Price'] / 1e6

        # Calculate cumulative tax
        combined['Tax_Cumulative_M'] = combined['Annual_Tax'].cumsum() / 1e6
        combined['Annual_Tax_M'] = combined['Annual_Tax'] / 1e6

        # Chart 1: Cumulative Values - Credits vs Tax
        st.subheader("Cumulative SMC Credit Value vs Tax Liability")

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=combined['FY_year'],
            y=combined['SMC_Credits_Value_M'],
            name='SMC Credit Value',
            marker=dict(
                color=COLORS['credits'],
                line=dict(width=0)
            ),
            offsetgroup=1,
            hovertemplate='<b>FY%{x}</b><br>Credit Value: $%{y:.2f}M<extra></extra>'
        ))

        fig.add_trace(go.Bar(
            x=combined['FY_year'],
            y=combined['Tax_Cumulative_M'],
            name='Tax Liability',
            marker=dict(
                color=COLORS['deficit'],
                line=dict(width=0)
            ),
            offsetgroup=2,
            hovertemplate='<b>FY%{x}</b><br>Tax Liability: $%{y:.2f}M<extra></extra>'
        ))

        fig.update_layout(
            height=350,
            xaxis_title='Financial Year',
            yaxis_title='Cumulative Value ($M)',
            yaxis_tickformat=',.0f',
            barmode='group',
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig, width="stretch")
        st.caption(f"Green: SMC Credit Market Value (starting ${carbon_credit_price:.0f}/t, escalating {credit_escalation*100:.1f}%/yr) | Dark red: Cumulative Tax Liability")

        # Chart 2: Annual Tax Rate
        st.subheader("Annual Carbon Tax")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=combined['FY_year'],
            y=combined['Annual_Tax_M'],
            mode='lines+markers',
            name='Annual Tax',
            line=dict(color=COLORS['power'], width=3),
            marker=dict(size=8),
            hovertemplate='<b>FY%{x}</b><br>Tax: $%{y:.2f}M<br>Rate: $%{customdata:.2f}/t<extra></extra>',
            customdata=combined['Tax_Rate']
        ))

        fig.update_layout(
            height=300,
            xaxis_title='Financial Year',
            yaxis_title='Annual Tax ($M)',
            yaxis_tickformat=',.1f',
            hovermode='x unified',
            showlegend=False
        )

        st.plotly_chart(fig, width="stretch")
        st.caption(f"Amber line: Annual tax liability starting FY{tax_start_fy} at ${tax_rate:.0f}/t, escalating {tax_escalation*100:.1f}%/yr")


def display_tax_table(carbon_tax):
    """Display annual tax projection table"""

    with st.expander("📊 Annual Tax Projection Table", expanded=False):
        tax_display = carbon_tax['df'].copy()
        tax_display['Tax_Rate'] = tax_display['Tax_Rate'].apply(lambda x: f"${x:.2f}")
        tax_display['Scope1'] = tax_display['Scope1'].apply(lambda x: f"{x:,.0f}")
        tax_display['Annual_Tax'] = tax_display['Annual_Tax'].apply(lambda x: f"${x:,.0f}")
        tax_display.columns = ['FY', 'Tax Rate', 'Scope 1 (tCO₂-e)', 'Annual Tax']

        st.dataframe(tax_display, width="stretch", hide_index=True)