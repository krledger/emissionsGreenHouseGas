"""
tab1_ghg.py
Total GHG Emissions Tab with Plotly charts
Last updated: 2026-01-08 10:00 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from emissions_calc import calculate_emissions
from projections import build_projection_simple
from config import COLORS, SCOPE_NAMES


def render_ghg_tab(rom_df, energy_df, nga_factors, baseline_intensity,
                   start_fy, end_fy, grid_connected_fy,
                   end_mining_fy, end_processing_fy, end_rehabilitation_fy):
    """Render the Total GHG Emissions tab"""

    st.subheader("Total Greenhouse Gas Emissions")
    st.caption(f"Projection Period: FY{start_fy}—FY{end_fy} | Mining ends FY{end_mining_fy} | Processing ends FY{end_processing_fy}")

    # Year Selection
    with st.expander("📅 Year Selection", expanded=True):
        col1, col2, col3 = st.columns(3)

        years = energy_df['Date'].dt.year.unique()
        available_fys = sorted([f"FY{y}" for y in years])

        with col1:
            selected_fy = st.selectbox(
                "Display Year (Actuals)",
                available_fys,
                index=len(available_fys)-1
            )

        with col2:
            prior_fy = st.selectbox(
                "Comparison Year",
                available_fys,
                index=max(0, len(available_fys)-2) if len(available_fys) > 1 else 0
            )

        with col3:
            # ROM Production input
            rom_year = int(selected_fy.replace('FY', ''))
            rom_production = rom_df[rom_df['Date'].dt.year == rom_year]['ROM'].sum() if rom_year in rom_df['Date'].dt.year.values else 0
            rom_mt = st.number_input(
                f"ROM Production (Mt) - {selected_fy}",
                value=float(rom_production / 1e6) if rom_production > 0 else 2.5,
                min_value=0.0,
                step=0.1,
                format="%.2f"
            )

    # Calculate emissions for selected years
    current_year = int(selected_fy.replace('FY', ''))
    prior_year = int(prior_fy.replace('FY', ''))

    current_emissions = calculate_emissions(energy_df, selected_fy, rom_mt * 1e6, nga_factors)

    prior_rom = rom_df[rom_df['Date'].dt.year == prior_year]['ROM'].sum()
    prior_emissions = calculate_emissions(energy_df, prior_fy, prior_rom, nga_factors)

    # Check for missing data
    if current_emissions is None:
        st.error(f"⚠️ No emissions data available for {selected_fy}")
        return

    if prior_emissions is None:
        st.warning(f"⚠️ No emissions data available for {prior_fy} (comparison year)")
        # Create a dummy prior with zeros for display
        prior_emissions = {
            'scope1': 0, 'scope2': 0, 'scope3': 0, 'total': 0,
            'fuel_kl': 0, 'grid_mwh': 0, 'site_mwh': 0
        }

    # Display metrics
    display_emissions_metrics(current_emissions, prior_emissions, selected_fy, prior_fy)

    # Notes
    st.caption("• Scope 3 emissions calculated using NGA factors: diesel Scope 3 = 0.669 tCO₂-e/kL, grid Scope 3 = 0.09 tCO₂-e/MWh")
    st.caption("• Grid Integration Impact: Total emissions remain approximately unchanged when grid connected.  Scope 1 decreases (~75,000 tCO₂-e from diesel generation removed) but Scope 2 increases (~60,000 tCO₂-e from grid electricity).  The benefit is reduced Safeguard Mechanism exposure")

    # Build projection
    projection = build_projection_simple(
        start_fy, end_fy, rom_df, energy_df, nga_factors,
        baseline_intensity, grid_connected_fy,
        end_mining_fy, end_processing_fy, end_rehabilitation_fy
    )

    # Charts
    display_emissions_charts(projection, grid_connected_fy)

    # Data table
    display_emissions_table(projection)


def display_emissions_metrics(current, prior, current_fy, prior_fy):
    """Display emission metrics comparison"""

    st.markdown("### 📊 Current Year Emissions")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        delta = current['scope1'] - prior['scope1']
        st.metric(
            SCOPE_NAMES['scope1'],
            f"{current['scope1']:,.0f} tCO₂-e",
            delta=f"{delta:+,.0f} tCO₂-e"
        )

    with col2:
        delta = current['scope2'] - prior['scope2']
        st.metric(
            SCOPE_NAMES['scope2'],
            f"{current['scope2']:,.0f} tCO₂-e",
            delta=f"{delta:+,.0f} tCO₂-e"
        )

    with col3:
        delta = current['scope3'] - prior['scope3']
        st.metric(
            SCOPE_NAMES['scope3'],
            f"{current['scope3']:,.0f} tCO₂-e",
            delta=f"{delta:+,.0f} tCO₂-e"
        )

    with col4:
        current_total = current['scope1'] + current['scope2'] + current['scope3']
        prior_total = prior['scope1'] + prior['scope2'] + prior['scope3']
        delta = current_total - prior_total
        st.metric(
            "Total",
            f"{current_total:,.0f} tCO₂-e",
            delta=f"{delta:+,.0f} tCO₂-e"
        )


def display_emissions_charts(projection, grid_connected_fy):
    """Display Plotly charts for emissions projection"""

    with st.expander("📈 Emissions Projection", expanded=True):

        # Chart 1: Stacked emissions by scope
        st.subheader("Total Emissions by Scope")

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=projection['FY'],
            y=projection['Scope1'],
            name=SCOPE_NAMES['scope1'],
            marker=dict(
                color=COLORS['scope1'],
                line=dict(width=0)
            ),
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        fig.add_trace(go.Bar(
            x=projection['FY'],
            y=projection['Scope2'],
            name=SCOPE_NAMES['scope2'],
            marker=dict(
                color=COLORS['scope2'],
                line=dict(width=0)
            ),
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        fig.add_trace(go.Bar(
            x=projection['FY'],
            y=projection['Scope3'],
            name=SCOPE_NAMES['scope3'],
            marker=dict(
                color=COLORS['scope3'],
                line=dict(width=0)
            ),
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        fig.update_layout(
            barmode='stack',
            height=400,
            xaxis_title='Financial Year',
            yaxis_title='Emissions (tCO₂-e)',
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig, width="stretch")
        st.caption("Navy: Scope 1 (Direct) | Blue: Scope 2 (Indirect) | Grey: Scope 3 (Value Chain)")

        # Chart 2: Scope 1 breakdown by source
        st.subheader("Scope 1 Emission Categories")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Power'],
            name='Power Generation',
            stackgroup='one',
            fillcolor=COLORS['power'],
            line=dict(width=0),  # No border lines
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Mining'],
            name='Mining',
            stackgroup='one',
            fillcolor=COLORS['mining'],
            line=dict(width=0),  # No border lines
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Processing'],
            name='Processing',
            stackgroup='one',
            fillcolor=COLORS['processing'],
            line=dict(width=0),  # No border lines
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=projection['FY'],
            y=projection['Fixed'],
            name='Fixed/Admin',
            stackgroup='one',
            fillcolor=COLORS['fixed'],
            line=dict(width=0),  # No border lines
            hovertemplate='%{y:,.0f} tCO₂-e<extra></extra>'
        ))

        # Add grid connection marker using add_shape (more reliable for categorical x-axis)
        fig.add_shape(
            type='line',
            x0=f'FY{grid_connected_fy}',
            x1=f'FY{grid_connected_fy}',
            y0=0,
            y1=1,
            yref='paper',
            line=dict(color='blue', width=2, dash='dash')
        )

        # Add annotation separately
        fig.add_annotation(
            x=f'FY{grid_connected_fy}',
            y=1,
            yref='paper',
            text='Grid Connected',
            showarrow=False,
            yshift=10
        )

        fig.update_layout(
            height=400,
            xaxis_title='Financial Year',
            yaxis_title='Scope 1 Emissions (tCO₂-e)',
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        st.plotly_chart(fig, width="stretch")
        st.caption("Stacked area shows Scope 1 emission sources over time | Blue line indicates grid connection")


def display_emissions_table(projection):
    """Display emissions data table"""

    with st.expander("📋 Annual Projection Data", expanded=False):
        display_df = projection[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total']].copy()

        # Format columns
        display_df['ROM (Mt)'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}" if x > 0 else "—")
        display_df['Scope 1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope 2'] = display_df['Scope2'].apply(lambda x: f"{x:,.0f}")
        display_df['Scope 3'] = display_df['Scope3'].apply(lambda x: f"{x:,.0f}")
        display_df['Total'] = display_df['Total'].apply(lambda x: f"{x:,.0f}")

        display_df = display_df[['FY', 'Phase', 'ROM (Mt)', 'Scope 1', 'Scope 2', 'Scope 3', 'Total']]

        st.dataframe(display_df, width="stretch", hide_index=True)