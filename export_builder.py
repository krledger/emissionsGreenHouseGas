"""
export_builder.py
Build ALL charts and data tables for export - matches screenshots EXACTLY
Last updated: 2026-02-04 19:30 AEST
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from config import COLORS, SAFEGUARD_THRESHOLD, SITE_GENERATION_RATIO
from calc_calendar import period_filter, year_to_date_range


# Gold color palette from tabs
GOLD_METALLIC = '#DBB12A'
BRIGHT_GOLD = '#E8AC41'
DARK_GOLDENROD = '#AE8B0F'
SEPIA = '#734B1A'
CAFE_NOIR = '#39250B'
GRID_GREEN = '#2A9D8F'


def build_ghg_charts(df, selected_source, projection, grid_connected_fy, display_year=2025):
    """
    Build Tab 1 charts matching screenshot EXACTLY

    Returns:
        Dict of {filename: figure}
    """
    charts = {}

    # Chart 1: Stacked Area - Total GHG Emissions by Scope (Screenshot 4)
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=projection['FY'],
        y=projection['Scope1'],
        name='Scope 1',
        mode='lines',
        fill='tonexty',
        line=dict(color=GOLD_METALLIC, width=2),
        stackgroup='one'
    ))

    fig.add_trace(go.Scatter(
        x=projection['FY'],
        y=projection['Scope2'],
        name='Scope 2',
        mode='lines',
        fill='tonexty',
        line=dict(color=BRIGHT_GOLD, width=2),
        stackgroup='one'
    ))

    fig.add_trace(go.Scatter(
        x=projection['FY'],
        y=projection['Scope3'],
        name='Scope 3',
        mode='lines',
        fill='tonexty',
        line=dict(color=DARK_GOLDENROD, width=2),
        stackgroup='one'
    ))

    fig.update_layout(
        title="Total GHG Emissions by Scope",
        xaxis_title="Financial Year",
        yaxis_title="Emissions (tCOâ‚‚-e)",
        hovermode='x unified',
        height=500,
        template='plotly_white',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )

    # Grid connection marker
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
            text="Grid Connection",
            showarrow=False,
            yshift=10
        )

    charts['tab1_total_ghg_emissions_by_scope.png'] = fig

    # Chart 2: Cost Centre Pie
    source_name = selected_source if selected_source != 'All' else 'Base'
    _sd, _ed = year_to_date_range(display_year, 'FY')
    fy_data = period_filter(df[df['DataSet'] == source_name], _sd, _ed).copy()

    if not fy_data.empty and 'CostCentre' in fy_data.columns:
        cc_totals = fy_data.groupby('CostCentre')['Quantity'].sum().reset_index()
        cc_totals = cc_totals[cc_totals['Quantity'] > 0]
        cc_totals = cc_totals.sort_values('Quantity', ascending=False).reset_index(drop=True)
        cc_totals['Cumulative_Pct'] = cc_totals['Quantity'].cumsum() / cc_totals['Quantity'].sum() * 100

        fig_cc = make_subplots(specs=[[{"secondary_y": True}]])
        fig_cc.add_trace(go.Bar(
            x=cc_totals['CostCentre'], y=cc_totals['Quantity'],
            name='Emissions (tCO2-e)',
            marker_color=GOLD_METALLIC
        ), secondary_y=False)
        fig_cc.add_trace(go.Scatter(
            x=cc_totals['CostCentre'], y=cc_totals['Cumulative_Pct'],
            name='Cumulative %', mode='lines+markers',
            line=dict(color=CAFE_NOIR, width=2),
            marker=dict(size=5, color=CAFE_NOIR)
        ), secondary_y=True)

        fig_cc.update_layout(
            title=f"Emissions by Cost Centre - FY{display_year}",
            height=500, template='plotly_white'
        )
        fig_cc.update_yaxes(title_text="Emissions (tCO2-e)", secondary_y=False)
        fig_cc.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
        fig_cc.update_xaxes(tickangle=-45)

        charts['tab1_emissions_by_cost_centre.png'] = fig_cc

    # Chart 3: Department Pie
    if not fy_data.empty and 'Department' in fy_data.columns:
        dept_totals = fy_data.groupby('Department')['Quantity'].sum().reset_index()
        dept_totals = dept_totals[dept_totals['Quantity'] > 0]
        dept_totals = dept_totals.sort_values('Quantity', ascending=False).reset_index(drop=True)
        dept_totals['Cumulative_Pct'] = dept_totals['Quantity'].cumsum() / dept_totals['Quantity'].sum() * 100

        fig_dept = make_subplots(specs=[[{"secondary_y": True}]])
        fig_dept.add_trace(go.Bar(
            x=dept_totals['Department'], y=dept_totals['Quantity'],
            name='Emissions (tCO2-e)',
            marker_color=GOLD_METALLIC
        ), secondary_y=False)
        fig_dept.add_trace(go.Scatter(
            x=dept_totals['Department'], y=dept_totals['Cumulative_Pct'],
            name='Cumulative %', mode='lines+markers',
            line=dict(color=CAFE_NOIR, width=2),
            marker=dict(size=5, color=CAFE_NOIR)
        ), secondary_y=True)

        fig_dept.update_layout(
            title=f"Emissions by Department - FY{display_year}",
            height=500, template='plotly_white'
        )
        fig_dept.update_yaxes(title_text="Emissions (tCO2-e)", secondary_y=False)
        fig_dept.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
        fig_dept.update_xaxes(tickangle=-45)

        charts['tab1_emissions_by_department.png'] = fig_dept

    # Chart 4: Sunburst - Department (inner) / Cost Centre (outer)
    if not fy_data.empty and 'Department' in fy_data.columns and 'CostCentre' in fy_data.columns:
        sun_grouped = fy_data.groupby(['Department', 'CostCentre'])['Quantity'].sum().reset_index()
        sun_grouped = sun_grouped[sun_grouped['Quantity'] > 0].sort_values('Quantity', ascending=False)

        if len(sun_grouped) > 0:
            grand_total = sun_grouped['Quantity'].sum()
            dept_colors_list = [GOLD_METALLIC, BRIGHT_GOLD, DARK_GOLDENROD, SEPIA, CAFE_NOIR]
            dept_order = sun_grouped.groupby('Department')['Quantity'].sum().sort_values(ascending=False).index.tolist()
            dept_color_map = {d: dept_colors_list[i % len(dept_colors_list)] for i, d in enumerate(dept_order)}

            sun_ids, sun_labels, sun_parents, sun_values, sun_colors = [], [], [], [], []

            for d in dept_order:
                d_total = sun_grouped[sun_grouped['Department'] == d]['Quantity'].sum()
                pct = d_total / grand_total * 100
                sun_ids.append(d)
                sun_labels.append(f"{d} {pct:.0f}%")
                sun_parents.append('')
                sun_values.append(d_total)
                sun_colors.append(dept_color_map[d])

            for _, row in sun_grouped.iterrows():
                cc_id = f"{row['Department']}/{row['CostCentre']}"
                pct = row['Quantity'] / grand_total * 100
                label = f"{row['CostCentre']} {row['Quantity']:,.0f}" if pct >= 3 else (row['CostCentre'] if pct >= 1 else '')
                sun_ids.append(cc_id)
                sun_labels.append(label)
                sun_parents.append(row['Department'])
                sun_values.append(row['Quantity'])
                base = dept_color_map[row['Department']]
                r, g, b = int(base[1:3], 16), int(base[3:5], 16), int(base[5:7], 16)
                sun_colors.append(f'rgba({min(r+40,255)},{min(g+40,255)},{min(b+40,255)},0.85)')

            fig_sun = go.Figure(go.Sunburst(
                ids=sun_ids, labels=sun_labels, parents=sun_parents, values=sun_values,
                marker=dict(colors=sun_colors, line=dict(width=1.5, color='white')),
                branchvalues='total', textinfo='label',
                insidetextorientation='radial'
            ))
            fig_sun.update_layout(
                title=f"Emissions by Department & Cost Centre - FY{display_year}",
                height=600, template='plotly_white',
                margin=dict(t=60, b=20, l=20, r=20)
            )
            charts['tab1_emissions_dept_cc_sunburst.png'] = fig_sun

    return charts


def build_ghg_tables(projection, df, selected_source, display_year=2025):
    """
    Build Tab 1 data tables (Summary + Data Table + Breakdowns)

    Returns:
        Dict of {filename: dataframe}
    """
    tables = {}
    timestamp = datetime.now().strftime('%Y%m%d')

    # Table 1: Emissions Summary (current year)
    year_data = projection[projection['FY'] == f'FY{display_year}']
    if len(year_data) > 0:
        row = year_data.iloc[0]
        source_name = selected_source if selected_source != 'All' else 'Base'

        summary = pd.DataFrame([{
            'Source': source_name,
            'ROM_Mt': f"{row['ROM_Mt']:.2f}",
            'Scope1_tCO2e': f"{row['Scope1']:,.0f}",
            'Scope2_tCO2e': f"{row['Scope2']:,.0f}",
            'Scope3_tCO2e': f"{row['Scope3']:,.0f}",
            'Total_tCO2e': f"{row['Total']:,.0f}",
            'Intensity_tCO2e_per_t': f"{row['Total_Intensity']:.4f}" if row['ROM_Mt'] > 0 else "N/A"
        }])

        tables[f'tab1_emissions_summary_FY{display_year}_{timestamp}.csv'] = summary

    # Table 2: Emissions Data Table (all years)
    data_table = projection[['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2', 'Scope3', 'Total']].copy()
    data_table.columns = ['FY', 'Phase', 'ROM_Mt', 'Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e', 'Total_tCO2e']
    tables[f'tab1_emissions_data_table_{timestamp}.csv'] = data_table

    # Table 3: Cost Centre Breakdown (current year)
    source_name = selected_source if selected_source != 'All' else 'Base'
    _sd, _ed = year_to_date_range(display_year, 'FY')
    fy_data = period_filter(df[df['DataSet'] == source_name], _sd, _ed).copy()

    if not fy_data.empty and 'CostCentre' in fy_data.columns:
        cc_breakdown = fy_data.groupby('CostCentre')['Quantity'].sum().reset_index()
        cc_breakdown.columns = ['CostCentre', 'Emissions_tCO2e']
        cc_breakdown = cc_breakdown.sort_values('Emissions_tCO2e', ascending=False)
        tables[f'tab1_cost_centre_breakdown_FY{display_year}_{timestamp}.csv'] = cc_breakdown

    # Table 4: Department Breakdown (current year)
    if not fy_data.empty and 'Department' in fy_data.columns:
        dept_breakdown = fy_data.groupby('Department')['Quantity'].sum().reset_index()
        dept_breakdown.columns = ['Department', 'Emissions_tCO2e']
        dept_breakdown = dept_breakdown.sort_values('Emissions_tCO2e', ascending=False)
        tables[f'tab1_department_breakdown_FY{display_year}_{timestamp}.csv'] = dept_breakdown

    return tables


def build_safeguard_charts(projection_df, fsei_rom, fsei_elec, grid_connected_fy):
    """
    Build Tab 2 charts matching screenshots EXACTLY

    Returns:
        Dict of {filename: figure}
    """
    charts = {}

    # Chart 1: Scope 1 Emissions & Emission Intensity (Screenshot 2)
    # This is the key chart - bars + dual intensity lines
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Bars - Scope 1 Emissions
    fig.add_trace(go.Bar(
        x=projection_df['FY'],
        y=projection_df['Scope1'],
        name='Scope 1 Emissions',
        marker_color=GOLD_METALLIC,
        showlegend=True
    ), secondary_y=False)

    # Line - Actual Intensity (solid)
    fig.add_trace(go.Scatter(
        x=projection_df['FY'],
        y=projection_df['Total_Intensity'],
        name='Actual Intensity',
        line=dict(color=CAFE_NOIR, width=3),
        mode='lines+markers',
        marker=dict(size=5)
    ), secondary_y=True)

    # Line - Baseline Intensity (dashed)
    fig.add_trace(go.Scatter(
        x=projection_df['FY'],
        y=projection_df['Baseline_Intensity'],
        name='Baseline',
        line=dict(color=CAFE_NOIR, width=3, dash='dash'),
        mode='lines'
    ), secondary_y=True)

    # Grid connection marker
    if grid_connected_fy and f'FY{grid_connected_fy}' in projection_df['FY'].values:
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

    fig.update_layout(
        title='Scope 1 Emissions & Emission Intensity',
        height=600,
        template='plotly_white',
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )

    fig.update_yaxes(title_text='Scope 1 Emissions (tCOâ‚‚-e)', secondary_y=False)
    fig.update_yaxes(title_text='Emission Intensity (tCOâ‚‚-e/t)', secondary_y=True)
    fig.update_xaxes(title_text='Financial Year')

    charts['tab2_scope1_emissions_and_intensity.png'] = fig

    # Chart 2: SMC Credits & Value (Screenshot 3)
    # Cumulative credits bars + value line
    if 'SMC_Cumulative' in projection_df.columns and 'SMC_Value_Cumulative' in projection_df.columns:
        fig2 = make_subplots(specs=[[{"secondary_y": True}]])

        # Bars - Cumulative Credits
        fig2.add_trace(go.Bar(
            x=projection_df['FY'],
            y=projection_df['SMC_Cumulative'],
            name='Cumulative Credits',
            marker_color=GOLD_METALLIC,
            text=projection_df['SMC_Cumulative'].round(0),
            textposition='none'  # Values shown on line instead
        ), secondary_y=False)

        # Line - Credit Value
        fig2.add_trace(go.Scatter(
            x=projection_df['FY'],
            y=projection_df['SMC_Value_Cumulative'],
            name='Credit Value ($)',
            line=dict(color=CAFE_NOIR, width=3),
            mode='lines+markers+text',
            marker=dict(size=6),
            text=['$' + f"{v/1_000_000:.1f}M" for v in projection_df['SMC_Value_Cumulative']],
            textposition='top center',
            textfont=dict(size=10)
        ), secondary_y=True)

        fig2.update_layout(
            title='SMC Credits & Value',
            height=600,
            template='plotly_white',
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
        )

        fig2.update_yaxes(title_text='Cumulative Credits (tCOâ‚‚-e)', secondary_y=False)
        fig2.update_yaxes(title_text='Credit Value (AUD, 3.0% p.a.)', secondary_y=True)
        fig2.update_xaxes(title_text='Financial Year')

        charts['tab2_smc_credits_and_value.png'] = fig2

    # Chart 3: SMC Credits Annual
    if 'SMC_Annual' in projection_df.columns:
        fig3 = go.Figure()

        fig3.add_trace(go.Bar(
            x=projection_df['FY'],
            y=projection_df['SMC_Annual'],
            marker_color=COLORS['credits'],
            text=projection_df['SMC_Annual'].round(0),
            textposition='outside',
            texttemplate='%{text:,.0f}'
        ))

        fig3.update_layout(
            title='SMC Credits - Annual Generation',
            xaxis_title='Financial Year',
            yaxis_title='Annual Credits (tCOâ‚‚-e)',
            height=600,
            template='plotly_white',
            showlegend=False
        )

        charts['tab2_smc_credits_annual.png'] = fig3

    # Chart 4: Baseline Exceedance
    if 'Exceedance' in projection_df.columns:
        fig4 = go.Figure()

        colors = [COLORS['deficit'] if x > 0 else COLORS['credits']
                 for x in projection_df['Exceedance']]

        fig4.add_trace(go.Bar(
            x=projection_df['FY'],
            y=projection_df['Exceedance'],
            marker_color=colors,
            showlegend=False,
            text=projection_df['Exceedance'].round(0),
            textposition='outside',
            texttemplate='%{text:,.0f}'
        ))

        fig4.add_hline(y=0, line_dash='solid', line_color='black', line_width=1)

        fig4.update_layout(
            title='Baseline Exceedance/Underage',
            xaxis_title='Financial Year',
            yaxis_title='Exceedance (tCOâ‚‚-e)',
            height=600,
            template='plotly_white'
        )

        charts['tab2_baseline_exceedance.png'] = fig4

    return charts


def build_safeguard_tables(projection_df, fsei_rom, fsei_elec, display_year=2025):
    """
    Build Tab 2 data tables (Summary + Data Table + Intensity)

    Returns:
        Dict of {filename: dataframe}
    """
    tables = {}
    timestamp = datetime.now().strftime('%Y%m%d')

    # Table 1: Safeguard Summary (current year)
    year_data = projection_df[projection_df['FY'] == f'FY{display_year}']
    if len(year_data) > 0:
        row = year_data.iloc[0]

        # SITE_GENERATION_RATIO imported from config.py (0.008735 MWh/t ROM)
        baseline_rom_component = fsei_rom
        baseline_elec_component = SITE_GENERATION_RATIO * fsei_elec
        baseline_total = row['Baseline_Intensity']

        if row['ROM_Mt'] > 0:
            actual_total = row['Scope1_Intensity']
            site_mwh = row['Site_Electricity_kWh'] / 1000
            actual_site_gen_ratio = site_mwh / (row['ROM_Mt'] * 1_000_000)
            actual_elec_component = actual_site_gen_ratio * fsei_elec
            actual_rom_component = actual_total - actual_elec_component
        else:
            actual_total = 0.0
            actual_rom_component = 0.0
            actual_elec_component = 0.0

        summary = pd.DataFrame([{
            'ROM_Mt': f"{row['ROM_Mt']:.2f}",
            'Scope1_tCO2e': f"{row['Scope1']:,.0f}",
            'Baseline_Intensity_Total': f"{baseline_total:.4f}",
            'Actual_Intensity_Total': f"{actual_total:.4f}" if row['ROM_Mt'] > 0 else "N/A",
            'Baseline_Intensity_ROM': f"{baseline_rom_component:.4f}",
            'Actual_Intensity_ROM': f"{actual_rom_component:.4f}" if row['ROM_Mt'] > 0 else "N/A",
            'Baseline_Intensity_Elec': f"{baseline_elec_component:.4f}",
            'Actual_Intensity_Elec': f"{actual_elec_component:.4f}" if row['ROM_Mt'] > 0 else "N/A",
            'SMC_Annual': f"{row.get('SMC_Annual', 0):,.0f}",
            'SMC_Cumulative': f"{row.get('SMC_Cumulative', 0):,.0f}"
        }])

        tables[f'tab2_safeguard_summary_FY{display_year}_{timestamp}.csv'] = summary

    # Table 2: Safeguard Data Table (all years)
    data_cols = ['FY', 'ROM_Mt', 'Scope1', 'Baseline', 'Scope1_Intensity',
                 'Baseline_Intensity', 'SMC_Annual', 'SMC_Cumulative']
    available_cols = [col for col in data_cols if col in projection_df.columns]
    if available_cols:
        data_table = projection_df[available_cols].copy()
        tables[f'tab2_safeguard_data_table_{timestamp}.csv'] = data_table

    # Table 3: Intensity Breakdown (all years)
    intensity_cols = ['FY', 'ROM_Intensity', 'Elec_Intensity', 'Scope1_Intensity', 'Baseline_Intensity']
    available_intensity = [col for col in intensity_cols if col in projection_df.columns]
    if available_intensity:
        intensity_table = projection_df[available_intensity].copy()
        tables[f'tab2_intensity_breakdown_{timestamp}.csv'] = intensity_table

    return tables


def build_carbon_tax_charts(projection_df, tax_rate, tax_escalation, tax_start_fy):
    """
    Build Tab 3 charts matching screenshot EXACTLY

    Returns:
        Dict of {filename: figure}
    """
    charts = {}

    if 'Tax_Liability' not in projection_df.columns:
        return charts

    # Chart 1: Combined Tax Chart (Screenshot 1)
    # Cumulative bars + Annual line
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Bars - Cumulative Tax
    fig.add_trace(go.Bar(
        x=projection_df['FY'],
        y=projection_df['Tax_Cumulative'] / 1_000_000,
        name='Cumulative Tax',
        marker_color=GOLD_METALLIC,
        showlegend=True
    ), secondary_y=False)

    # Line - Annual Tax
    fig.add_trace(go.Scatter(
        x=projection_df['FY'],
        y=projection_df['Tax_Liability'] / 1_000_000,
        name='Annual Tax',
        line=dict(color=CAFE_NOIR, width=3),
        mode='lines+markers+text',
        marker=dict(size=5),
        text=['$' + f"{v/1_000_000:.1f}M" if v > 0 else '' for v in projection_df['Tax_Liability']],
        textposition='top center',
        textfont=dict(size=10)
    ), secondary_y=True)

    fig.update_layout(
        title='Carbon Tax Liability',
        height=600,
        template='plotly_white',
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )

    fig.update_yaxes(title_text='Cumulative Tax ($AUD)', secondary_y=False)
    fig.update_yaxes(title_text='Annual Tax ($AUD)', secondary_y=True)
    fig.update_xaxes(title_text='Financial Year')

    charts['tab3_carbon_tax_liability.png'] = fig

    return charts


def build_carbon_tax_tables(projection_df, display_year=2025):
    """
    Build Tab 3 data tables (Summary + Data Table)

    Returns:
        Dict of {filename: dataframe}
    """
    tables = {}
    timestamp = datetime.now().strftime('%Y%m%d')

    if 'Tax_Liability' not in projection_df.columns:
        return tables

    # Table 1: Tax Summary (current year)
    year_data = projection_df[projection_df['FY'] == f'FY{display_year}']
    if len(year_data) > 0:
        row = year_data.iloc[0]

        summary = pd.DataFrame([{
            'Scope1_tCO2e': f"{row['Scope1']:,.0f}",
            'Tax_Rate_per_tonne': f"${row.get('Tax_Rate_per_tonne', 0):.2f}",
            'Tax_Liability_Annual': f"${row['Tax_Liability']:,.0f}",
            'Tax_Cumulative': f"${row.get('Tax_Cumulative', 0):,.0f}"
        }])

        tables[f'tab3_tax_summary_FY{display_year}_{timestamp}.csv'] = summary

    # Table 2: Tax Data Table (all years)
    tax_cols = ['FY', 'Scope1', 'Tax_Rate_per_tonne', 'Tax_Liability', 'Tax_Cumulative']
    available_cols = [col for col in tax_cols if col in projection_df.columns]
    if available_cols:
        data_table = projection_df[available_cols].copy()
        tables[f'tab3_tax_data_table_{timestamp}.csv'] = data_table

    return tables


def build_export_data(df, projection_df, selected_source, include_processed_data=True):
    """
    Build ALL data for export - charts and tables from all tabs

    Returns:
        Dict of {filename: dataframe}
    """
    data = {}
    timestamp = datetime.now().strftime('%Y%m%d')

    # Processed input data
    if include_processed_data:
        if selected_source == 'All':
            export_df = df[df['DataSet'].isin(['Base', 'NPI-NGERS'])].copy()
            filename = f'processed_input_data_All_{timestamp}.csv'
        else:
            export_df = df[df['DataSet'] == selected_source].copy()
            filename = f'processed_input_data_{selected_source}_{timestamp}.csv'

        data[filename] = export_df

    # Tab tables
    data.update(build_ghg_tables(projection_df, df, selected_source))
    data.update(build_safeguard_tables(projection_df, 0.0177, 0.9081))  # Default FSEIs
    data.update(build_carbon_tax_tables(projection_df))

    return data


def create_metadata(selected_source, fsei_rom, fsei_elec, start_fy, end_fy,
                    grid_connected_fy, carbon_credit_price, credit_escalation,
                    tax_rate, tax_escalation, tax_start_fy, decline_rate_phase2):
    """Create metadata for README"""
    return {
        'Export Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Data Source': selected_source,
        'Baseline FSEI - ROM': f'{fsei_rom:.4f} tCOâ‚‚-e/t',
        'Baseline FSEI - Electricity': f'{fsei_elec:.4f} tCOâ‚‚-e/MWh',
        'Projection Period': f'FY{start_fy} to FY{end_fy}',
        'Grid Connection': f'FY{grid_connected_fy}' if grid_connected_fy else 'Not planned',
        'SMC Credit Price': f'${carbon_credit_price:.2f}/tCOâ‚‚-e',
        'SMC Price Escalation': f'{credit_escalation*100:.1f}%/year',
        'Carbon Tax Rate': f'${tax_rate:.2f}/tCOâ‚‚-e',
        'Tax Escalation': f'{tax_escalation*100:.1f}%/year',
        'Tax Start Year': f'FY{tax_start_fy}',
        'Baseline Decline Phase 1': '4.9%/year (FY2024-FY2030)',
        'Baseline Decline Phase 2': f'{decline_rate_phase2*100:.3f}%/year' if decline_rate_phase2 else '3.285%/year',
    }