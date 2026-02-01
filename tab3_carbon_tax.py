"""
tab3_carbon_tax.py
Carbon Tax Analysis tab - redesigned to match tabs 1 and 2
Last updated: 2026-02-02 09:50 AEST
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from projections import build_projection, carbon_tax_analysis


def render_carbon_tax_tab(df, selected_source, fsei_rom, fsei_elec,
                          start_fy, end_fy, grid_connected_fy,
                          end_mining_fy, end_processing_fy, end_rehabilitation_fy,
                          carbon_credit_price, credit_escalation,
                          tax_start_fy, tax_rate, tax_escalation,
                          credit_start_fy):
    """Render Carbon Tax Analysis tab

    Args:
        df: Unified DataFrame from load_all_data()
        selected_source: 'Base', 'NPI-NGERS', or 'All'
        fsei_rom: ROM emission intensity
        fsei_elec: Electricity generation emission intensity
        Phase parameters
        carbon_credit_price: SMC market price
        credit_escalation: Annual price increase
        tax_start_fy: Year tax starts
        tax_rate: Initial tax rate ($/tCO2-e)
        tax_escalation: Annual tax rate increase (not compound, just rate change)
        credit_start_fy: First year credits can be earned
    """

    st.subheader("💵 Carbon Tax Scenario Analysis")
    st.caption(f"Tax starts FY{tax_start_fy} at ${tax_rate:.2f}/tCO2-e, escalating {tax_escalation*100:.1f}% p.a. Based on Scope 1 emissions only.")

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

        # Apply carbon tax analysis
        tax_base = carbon_tax_analysis(proj_base, tax_start_fy, tax_rate, tax_escalation)
        tax_npi = carbon_tax_analysis(proj_npi, tax_start_fy, tax_rate, tax_escalation)

        display_tax_comparison(tax_base, tax_npi, display_year, tax_start_fy)

        # Prepare tax data list for combined data table
        tax_data_list = [('Base', tax_base), ('NPI-NGERS', tax_npi)]

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

        carbon_tax = carbon_tax_analysis(projection, tax_start_fy, tax_rate, tax_escalation)

        display_tax_single(carbon_tax, selected_source, tax_start_fy)

        # Prepare tax data list for combined data table
        tax_data_list = [(selected_source, carbon_tax)]

    # Combined Data Table at the end (appears once for all datasets)
    with st.expander("📋 Tax Data Table", expanded=False):
        combined_data = []

        for source_name, tax_data in tax_data_list:
            # Filter to tax period
            tax_period = tax_data[tax_data['FY_num'] >= tax_start_fy].copy()
            if len(tax_period) > 0:
                # Add source column
                tax_period.insert(0, 'Source', source_name)
                # Select columns
                tax_period = tax_period[['Source', 'FY', 'Scope1', 'Tax_Rate', 'Tax_Annual', 'Tax_Cumulative']]
                combined_data.append(tax_period)

        if combined_data:
            # Combine all datasets
            display_df = pd.concat(combined_data, ignore_index=True)

            # Format numbers
            display_df['Scope1'] = display_df['Scope1'].apply(lambda x: f"{x:,.0f}")
            display_df['Tax_Rate'] = display_df['Tax_Rate'].apply(lambda x: f"${x:.2f}")
            display_df['Tax_Annual'] = display_df['Tax_Annual'].apply(lambda x: f"${x:,.0f}")
            display_df['Tax_Cumulative'] = display_df['Tax_Cumulative'].apply(lambda x: f"${x:,.0f}")

            st.dataframe(display_df, hide_index=True, width="stretch", height=400)
        else:
            st.info(f"Tax period starts FY{tax_start_fy}")


def display_tax_single(carbon_tax, source_name, tax_start_fy, show_summary=True):
    """Display carbon tax analysis for single source

    Args:
        carbon_tax: Tax analysis DataFrame
        source_name: Dataset name
        tax_start_fy: First year of tax
        show_summary: If False, skip summary table (used in comparison mode)
    """

    # Gold color palette
    GOLD_METALLIC = '#DBB12A'      # Bars - cumulative
    CAFE_NOIR = '#39250B'          # Line - annual

    # Filter to tax period
    tax_data = carbon_tax[carbon_tax['FY_num'] >= tax_start_fy]

    # Summary table - single row with all data
    if show_summary:
        with st.expander("📊 Summary", expanded=True):
            display_year = st.session_state.get('display_year', 2025)
            year_data = tax_data[tax_data['FY'] == f'FY{display_year}']

            if len(year_data) == 0:
                st.warning(f"⚠️ No tax data for FY{display_year} (tax starts FY{tax_start_fy})")
            else:
                row = year_data.iloc[0]

                summary_data = [{
                    'Source': source_name,
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Tax Rate ($/tCO2-e)': f"${row['Tax_Rate']:.2f}",
                    'Tax Annual ($)': f"${row['Tax_Annual']:,.0f}",
                    'Tax Cumulative ($)': f"${row['Tax_Cumulative']:,.0f}"
                }]

                df_summary = pd.DataFrame(summary_data)
                st.dataframe(df_summary, hide_index=True, width="stretch")

    # Tax Liability chart - cumulative bars + annual line
    with st.expander("💰 Tax Liability", expanded=True):

        if len(tax_data) == 0:
            st.info(f"Tax period starts FY{tax_start_fy}")
        else:
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # Cumulative tax (bars)
            fig.add_trace(
                go.Bar(
                    x=tax_data['FY'],
                    y=tax_data['Tax_Cumulative'],
                    name='Cumulative Tax',
                    marker_color=GOLD_METALLIC,
                    opacity=0.8
                ),
                secondary_y=False
            )

            # Annual tax (line with dollar labels)
            # Format labels for display
            labels = []
            for val in tax_data['Tax_Annual']:
                if val >= 1_000_000:
                    labels.append(f"${val/1_000_000:.1f}M")
                elif val >= 1_000:
                    labels.append(f"${val/1_000:.0f}K")
                else:
                    labels.append(f"${val:.0f}")

            fig.add_trace(
                go.Scatter(
                    x=tax_data['FY'],
                    y=tax_data['Tax_Annual'],
                    name='Annual Tax',
                    mode='lines+markers+text',
                    line=dict(color=CAFE_NOIR, width=3),
                    marker=dict(size=6),
                    text=labels,
                    textposition='top center',
                    textfont=dict(size=10, color=CAFE_NOIR)
                ),
                secondary_y=True
            )

            fig.update_xaxes(title_text="Financial Year")
            fig.update_yaxes(title_text="Cumulative Tax ($AUD)", secondary_y=False)
            fig.update_yaxes(title_text="Annual Tax ($AUD)", secondary_y=True)
            fig.update_layout(
                title="Carbon Tax Liability",
                hovermode='x unified',
                height=400,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            st.plotly_chart(fig, width="stretch", key=f"tax_liability_{source_name}")

            # Summary caption
            if len(tax_data) > 0:
                final_year = tax_data['FY'].iloc[-1]
                final_cumulative = tax_data['Tax_Cumulative'].iloc[-1]
                final_rate = tax_data['Tax_Rate'].iloc[-1]
                st.caption(f"💵 {final_year} Cumulative Tax: ${final_cumulative:,.0f} AUD at ${final_rate:.2f}/tCO2-e")


def display_tax_comparison(tax_base, tax_npi, display_year, tax_start_fy):
    """Display tax comparison between Base and NPI-NGERS with combined charts"""

    # Gold color palette
    GOLD_METALLIC = '#DBB12A'
    CAFE_NOIR = '#39250B'

    # Filter to tax period
    tax_base_period = tax_base[tax_base['FY_num'] >= tax_start_fy]
    tax_npi_period = tax_npi[tax_npi['FY_num'] >= tax_start_fy]

    # Combined summary table
    with st.expander("📊 Summary", expanded=True):
        year_base = tax_base[tax_base['FY'] == f'FY{display_year}']
        year_npi = tax_npi[tax_npi['FY'] == f'FY{display_year}']

        summary_rows = []

        for source_name, year_data in [('Base', year_base), ('NPI-NGERS', year_npi)]:
            if len(year_data) > 0 and year_data.iloc[0]['FY_num'] >= tax_start_fy:
                row = year_data.iloc[0]
                summary_rows.append({
                    'Source': source_name,
                    'Scope 1 (tCO2-e)': f"{row['Scope1']:,.0f}",
                    'Tax Rate ($/tCO2-e)': f"${row['Tax_Rate']:.2f}",
                    'Tax Annual ($)': f"${row['Tax_Annual']:,.0f}",
                    'Tax Cumulative ($)': f"${row['Tax_Cumulative']:,.0f}"
                })
            else:
                summary_rows.append({
                    'Source': source_name,
                    'Scope 1 (tCO2-e)': 'N/A',
                    'Tax Rate ($/tCO2-e)': 'N/A',
                    'Tax Annual ($)': 'Not started',
                    'Tax Cumulative ($)': 'Not started'
                })

        if summary_rows:
            df_summary = pd.DataFrame(summary_rows)
            st.dataframe(df_summary, hide_index=True, width="stretch")

            # Variance summary
            if len(year_base) > 0 and len(year_npi) > 0:
                if year_base.iloc[0]['FY_num'] >= tax_start_fy and year_npi.iloc[0]['FY_num'] >= tax_start_fy:
                    diff_tax = year_npi.iloc[0]['Tax_Cumulative'] - year_base.iloc[0]['Tax_Cumulative']
                    if abs(diff_tax) > 0:
                        st.caption(f"Tax Variance: ${diff_tax:+,.0f} AUD")
        else:
            st.info(f"Tax period starts FY{tax_start_fy}")

    # Combined tax liability chart in single frame
    if len(tax_base_period) > 0 and len(tax_npi_period) > 0:
        with st.expander("💰 Tax Liability", expanded=True):

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
                    x=tax_base_period['FY'],
                    y=tax_base_period['Tax_Cumulative'],
                    name='Cumulative Tax',
                    marker_color=GOLD_METALLIC,
                    opacity=0.8,
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=False,
                row=1, col=1
            )

            # Format labels for Base annual line
            labels_base = []
            for val in tax_base_period['Tax_Annual']:
                if val >= 1_000_000:
                    labels_base.append(f"${val/1_000_000:.1f}M")
                elif val >= 1_000:
                    labels_base.append(f"${val/1_000:.0f}K")
                else:
                    labels_base.append(f"${val:.0f}")

            fig.add_trace(
                go.Scatter(
                    x=tax_base_period['FY'],
                    y=tax_base_period['Tax_Annual'],
                    name='Annual Tax',
                    mode='lines+markers+text',
                    line=dict(color=CAFE_NOIR, width=3),
                    marker=dict(size=6),
                    text=labels_base,
                    textposition='top center',
                    textfont=dict(size=9, color=CAFE_NOIR),
                    showlegend=False,
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=True,
                row=1, col=1
            )

            # NPI-NGERS (bottom chart) - use prime notation for proper hover labels
            fig.add_trace(
                go.Bar(
                    x=tax_npi_period['FY'],
                    y=tax_npi_period['Tax_Cumulative'],
                    name="Cumulative Tax'",
                    marker_color=GOLD_METALLIC,
                    opacity=0.8,
                    showlegend=False,
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=False,
                row=2, col=1
            )

            # Format labels for NPI annual line
            labels_npi = []
            for val in tax_npi_period['Tax_Annual']:
                if val >= 1_000_000:
                    labels_npi.append(f"${val/1_000_000:.1f}M")
                elif val >= 1_000:
                    labels_npi.append(f"${val/1_000:.0f}K")
                else:
                    labels_npi.append(f"${val:.0f}")

            fig.add_trace(
                go.Scatter(
                    x=tax_npi_period['FY'],
                    y=tax_npi_period['Tax_Annual'],
                    name="Annual Tax'",
                    mode='lines+markers+text',
                    line=dict(color=CAFE_NOIR, width=3),
                    marker=dict(size=6),
                    text=labels_npi,
                    textposition='top center',
                    textfont=dict(size=9, color=CAFE_NOIR),
                    showlegend=False,
                    hovertemplate='$%{y:,.0f}<extra></extra>'
                ),
                secondary_y=True,
                row=2, col=1
            )

            # Update axes
            fig.update_xaxes(title_text="Financial Year", row=2, col=1)
            fig.update_yaxes(title_text="Cumulative Tax ($AUD)", secondary_y=False, row=1, col=1)
            fig.update_yaxes(title_text="Annual Tax ($AUD)", secondary_y=True, row=1, col=1)
            fig.update_yaxes(title_text="Cumulative Tax ($AUD)", secondary_y=False, row=2, col=1)
            fig.update_yaxes(title_text="Annual Tax ($AUD)", secondary_y=True, row=2, col=1)

            fig.update_layout(
                height=700,
                hovermode='x unified',
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            st.plotly_chart(fig, width="stretch")

            # Summary caption
            if len(tax_base_period) > 0 and len(tax_npi_period) > 0:
                final_year_base = tax_base_period['FY'].iloc[-1]
                final_cumulative_base = tax_base_period['Tax_Cumulative'].iloc[-1]
                final_year_npi = tax_npi_period['FY'].iloc[-1]
                final_cumulative_npi = tax_npi_period['Tax_Cumulative'].iloc[-1]
                st.caption(f"💵 {final_year_base}: Base ${final_cumulative_base:,.0f} | NPI-NGERS ${final_cumulative_npi:,.0f}")