"""
TabGhgCategories.py
Scope 3 composition, rendered inside the GHG emissions view.
Last updated: 2026-09-02

ARCHITECTURE:
    Display only, per the file conventions.  Every figure here is produced by
    the view aggregations in CalcGhgCategories.py and arrives as a frame; this module
    filters nothing, sums nothing and derives no share.  It formats and it
    plots.  CalcGhg.py is untouched: Scope 3 maths lives in CalcGhgCategories.py.

    There is no Scope 3 tab.  Scope 3 is one line of the inventory and is
    reported as one figure on the GHG view; this panel sits under it, closed,
    for the reader who needs the composition, the method behind each category
    or the audit trail.

PURPOSE:
    Scope 3 is the part of the inventory an assurer tests hardest, because
    almost none of it is measured.  Every number therefore carries its method,
    its factor and the source of that factor, and the categories that carry
    nothing say why: a documented exclusion, or data not yet supplied.

    Category 3 comes from the emissions calculation and is not recomputed.
    Scope 3 sits outside the Safeguard baseline and the NGER position, and
    nothing here feeds either.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from CalcGhgCategories import (
    CATEGORY_NAMES,
    annual_frame,
    category_headline,
    category_totals,
    implied_intensity_table,
    method_register,
    outstanding_table,
    physical_factor_status,
    present_categories,
    purchased_goods_table,
    rate_table,
    year_column,
)

# Palette, consistent with the other tabs.
GOLD_METALLIC = '#DBB12A'
BRIGHT_GOLD = '#E8AC41'
DARK_GOLDENROD = '#AE8B0F'
SEPIA = '#734B1A'
GRID_GREEN = '#2A9D8F'
SLATE = '#2C3E50'
STEEL = '#3498DB'
ASH = '#95A5A6'

CATEGORY_COLOURS = {
    1: GOLD_METALLIC,
    2: SEPIA,
    3: SLATE,
    4: BRIGHT_GOLD,
    5: GRID_GREEN,
    6: STEEL,
    7: DARK_GOLDENROD,
    10: ASH,
}


# =============================================================================
# Formatting
# =============================================================================

def _tonnes(value):
    return f'{value:,.0f}' if pd.notna(value) and abs(value) > 0.05 else '-'


def _dollars(value):
    return f'{value:,.0f}' if pd.notna(value) and abs(value) > 0.005 else '-'


def _percent(value, places=1):
    return f'{value:.{places}f}%' if pd.notna(value) else '-'


def _factor(value, unit):
    if pd.isna(value):
        return '-'
    return f"{value:,.3f} {unit or ''}".strip()


def _truncate(text, limit=160):
    text = '' if pd.isna(text) else str(text)
    return text if len(text) <= limit else text[:limit - 3] + '...'


def _layout(figure, title, ylab, height=420):
    figure.update_layout(
        title=title,
        yaxis_title=ylab,
        height=height,
        hovermode='x unified',
        plot_bgcolor='white',
        margin=dict(l=60, r=30, t=60, b=50),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='right', x=1),
    )
    figure.update_xaxes(showgrid=False, linecolor='#CCCCCC')
    figure.update_yaxes(gridcolor='#EEEEEE', zerolinecolor='#CCCCCC')
    return figure


# =============================================================================
# Headline
# =============================================================================

def _render_headline(result, year_type, display_year, period_label):
    st.subheader('Scope 3 position')

    summary = category_headline(result, year_type, display_year)
    if summary is None:
        st.info(f'No Scope 3 data for {period_label}.')
        return

    columns = st.columns(4)
    columns[0].metric(f'Total Scope 3 {period_label}',
                      f"{summary['total']:,.0f} t")
    columns[1].metric('Upstream, categories 1 to 8',
                      f"{summary['upstream']:,.0f} t")
    columns[2].metric('Downstream, categories 9 to 15',
                      f"{summary['downstream']:,.0f} t")
    columns[3].metric('Category 3 share',
                      f"{summary['cat3_share']:.0f}%",
                      help='Fuel and energy related activities, the only '
                           'category measured at transaction level.')

    st.caption(result.notes.get('boundary', ''))


# =============================================================================
# Category composition
# =============================================================================

def _render_composition(result, year_type, display_year, period_label):
    st.subheader('Composition by category')

    totals = category_totals(result, year_type, display_year)
    if totals.empty:
        st.info(f'No Scope 3 detail for {period_label}.')
        return

    chart = totals.sort_values('tCO2e')
    figure = go.Figure(go.Bar(
        x=chart['tCO2e'],
        y=[f'{c}  {n}' for c, n in zip(chart['Category'], chart['CategoryName'])],
        orientation='h',
        marker_color=[CATEGORY_COLOURS.get(int(c), ASH) for c in chart['Category']],
        text=[f'{v:,.0f}' for v in chart['tCO2e']],
        textposition='outside',
        hovertemplate='%{y}<br>%{x:,.0f} tCO2-e<extra></extra>',
    ))
    _layout(figure, f'Scope 3 by category, {period_label}', '',
            height=90 + 42 * max(len(chart), 3))
    figure.update_layout(xaxis_title='tCO2-e')
    st.plotly_chart(figure, width='stretch')

    st.dataframe(pd.DataFrame({
        'Cat': totals['Category'],
        'Name': totals['CategoryName'],
        'tCO2-e': totals['tCO2e'].map(_tonnes),
        'Share': totals['Share'].map(_percent),
        'Cumulative': totals['Cumulative'].map(_percent),
    }), hide_index=True, width='stretch')


# =============================================================================
# Trajectory
# =============================================================================

def _render_trajectory(result, year_type):
    st.subheader('Scope 3 across the mine life')

    annual = annual_frame(result, year_type)
    if annual.empty:
        return

    figure = go.Figure()
    for category in present_categories(result):
        column = f'Cat{category}'
        if column not in annual.columns:
            continue
        figure.add_trace(go.Bar(
            x=annual['Year'], y=annual[column],
            name=f'{category}  {CATEGORY_NAMES[category]}',
            marker_color=CATEGORY_COLOURS.get(category, ASH),
        ))
    figure.update_layout(barmode='stack')
    _layout(figure, 'Scope 3 by category and year', 'tCO2-e', height=460)
    figure.update_layout(xaxis_title=year_type)
    st.plotly_chart(figure, width='stretch')

    st.caption(result.notes.get('projection', ''))


# =============================================================================
# Method register
# =============================================================================

def _render_methods(result, year_type, display_year):
    st.subheader('Method and factor by category')
    st.caption('Every category in the standard, with the method applied, the '
               'factor source behind it and what it carries for the selected '
               'period.  A category showing nothing is either a documented '
               'exclusion or is awaiting data; both are stated here.')

    register = method_register(result, year_type, display_year)
    st.dataframe(pd.DataFrame({
        'Cat': register['Category'],
        'Name': register['CategoryName'],
        'Status': register['Status'],
        'tCO2-e': register['tCO2e'].map(_tonnes),
        'Method or rationale': register['Detail'].map(_truncate),
        'Factor source': register['FactorSource'].map(_truncate),
    }), hide_index=True, width='stretch', height=560)


# =============================================================================
# Category 1 detail
# =============================================================================

def _render_purchased_goods(result, year_type, display_year, period_label):
    st.subheader('Category 1 detail, purchased goods and services')

    table = purchased_goods_table(result, year_type, display_year)
    if table.empty:
        st.info(f'No Category 1 lines for {period_label}.')
    else:
        st.dataframe(pd.DataFrame({
            'Group': table['Group'],
            'Description': table['GroupDescription'],
            'Basis': table['Basis'],
            'Spend AUD': table['Spend_AUD'].map(_dollars),
            'Quantity': table['Quantity'].map(
                lambda v: f'{v:,.1f}' if pd.notna(v) and v else '-'),
            'Factor': [_factor(f, u) for f, u
                       in zip(table['Factor'], table['FactorUnit'])],
            'tCO2-e': table['tCO2e'].map(_tonnes),
            'Share': table['Share'].map(_percent),
            'Cumulative': table['Cumulative'].map(_percent),
            'Factor source': table['FactorSource'].map(_truncate),
        }), hide_index=True, width='stretch', height=420)

    coverage = result.coverage
    if 'recorded_spend_aud' in coverage:
        st.markdown('**Expenditure coverage, whole record**')
        st.markdown(
            f"- Recorded on inventory transactions: "
            f"${coverage['recorded_spend_aud']:,.0f}\n"
            f"- Charged as Scope 1 combustion and Category 3 well to tank, so "
            f"outside Category 1: ${coverage.get('excluded_by_design_aud', 0):,.0f}\n"
            f"- Priced into Category 1 on a spend factor: "
            f"${coverage.get('priced_spend_aud', 0):,.0f}\n"
            f"- Assessable expenditure carrying a factor: "
            f"{coverage.get('priced_share_pct', 0):.1f}%"
        )
        payable = coverage.get('accounts_payable_aud')
        if payable:
            st.caption(
                f'Accounts payable over the same review carries '
                f'${payable:,.0f}.  Inventory transactions are goods received '
                f'into stores and do not cover services invoiced directly, so '
                f'the two are not expected to agree.')


# =============================================================================
# Spend against physical
# =============================================================================

def _render_spend_against_physical(result):
    st.subheader('Spend based result against the physical quantity')
    st.caption('An EPA supply chain factor is an economic average for a '
               'commodity class produced in the United States.  Dividing the '
               'result by the quantity the same rows carry gives the '
               'intensity the factor implies, which can be read against a '
               'published physical factor for the same commodity.  A group '
               'sitting far from the physical literature is a candidate to '
               'move off dollars.')

    table = implied_intensity_table(result)
    if table.empty:
        st.info('No recorded spend line carries a mass or volume unit.')
    else:
        st.dataframe(pd.DataFrame({
            'Group': table['Group'],
            'Description': table['Description'],
            'Unit': table['UOM'],
            'Quantity': table['Quantity'].map(lambda v: f'{v:,.1f}'),
            'Spend AUD': table['Spend_AUD'].map(_dollars),
            'AUD per unit': table['AUD_per_unit'].map(lambda v: f'{v:,.2f}'),
            'tCO2-e': table['tCO2e'].map(_tonnes),
            'Implied tCO2-e per unit': table['Implied_tCO2e_per_unit'].map(
                lambda v: f'{v:,.4f}'),
        }), hide_index=True, width='stretch')
        st.caption('Recorded expenditure only.  A projected line inherits the '
                   'same intensity by construction, so including it would tell '
                   'us nothing.  Groups whose physicals are a count of items '
                   'are absent: a count cannot be compared with a factor per '
                   'tonne without a mass per item.')

    status = physical_factor_status(result)
    if not status.empty:
        counts = status['Basis'].value_counts()
        st.markdown(
            f"**Factor basis in force.**  "
            f"{int(counts.get('physical', 0))} product groups are charged on a "
            f"physical unit factor and {int(counts.get('spend', 0))} on spend.  "
            f"Moving a group across is a configuration change: add it to "
            f"`category_1.physical_unit_factors` in `ConfigScope3.yaml` and "
            f"rebuild `Scope3Factors.csv`."
        )
        with st.expander('Factor basis by product group', expanded=False):
            st.dataframe(status, hide_index=True, width='stretch', height=360)


# =============================================================================
# Conversion and projection basis
# =============================================================================

def _render_basis(result):
    st.subheader('Conversion and projection basis')

    st.markdown(f"**Currency.**  {result.notes.get('currency', '')}")
    st.markdown(f"**Projection.**  {result.notes.get('projection', '')}")

    rates = rate_table(result)
    if rates.empty:
        return

    with st.expander('Fitted dollar per unit rates', expanded=False):
        st.caption('Fitted from valued months in the window and applied to '
                   'budget quantities.  A line absent here projects nothing.')
        st.dataframe(pd.DataFrame({
            'Activity': rates['Activity'],
            'SubActivity': rates['SubActivity'],
            'Unit': rates['UOM'],
            'Product group': rates['ProductGroup'],
            'Months': rates['Months'],
            'Spend AUD': rates['Spend_AUD'].map(_dollars),
            'Quantity': rates['Quantity'].map(lambda v: f'{v:,.1f}'),
            'AUD per unit': rates['RateAudPerUnit'].map(
                lambda v: f'{v:,.2f}' if pd.notna(v) else '-'),
        }), hide_index=True, width='stretch', height=360)


# =============================================================================
# Open items and exclusions
# =============================================================================

def _render_open_items(result):
    st.subheader('Open items and documented exclusions')

    left, right = st.columns(2)

    with left:
        st.markdown('**Awaiting data or a decision**')
        outstanding = outstanding_table(result)
        if outstanding.empty:
            st.success('Nothing outstanding.')
        else:
            st.dataframe(outstanding.rename(columns={'Category': 'Cat'}),
                         hide_index=True, width='stretch', height=320)

    with right:
        st.markdown('**Documented exclusions**')
        if result.exclusions.empty:
            st.info('No exclusion is recorded.')
        else:
            st.dataframe(
                result.exclusions.rename(columns={'CategoryName': 'Name'}),
                hide_index=True, width='stretch', height=320)

    missing = result.coverage.get('registers_missing') or []
    if missing:
        st.error('Factor registers not found: ' + '; '.join(missing))


# =============================================================================
# Detail
# =============================================================================

def _render_detail(result):
    st.subheader('Detail')
    st.caption('One row per month, category and product group, carrying the '
               'quantity or expenditure, the rate applied, the factor and its '
               'source.  This is the audit trail for every figure above.')

    st.download_button(
        'Download the Scope 3 detail',
        data=result.detail.to_csv(index=False).encode('utf-8'),
        file_name='Scope3Detail.csv',
        mime='text/csv',
        key='scope3_detail_download',
    )

    with st.expander('Preview', expanded=False):
        st.dataframe(result.detail.head(400), hide_index=True,
                     width='stretch', height=380)


# =============================================================================
# Entry point
# =============================================================================

def render_scope3_panel(result, year_type='CY', display_year=None,
                        period_label='', error=''):
    """Render the Scope 3 composition panel.

    Called from the GHG view inside a closed expander.

    Args:
        result:       Scope3Result from CalcPrecompute
        year_type:    'FY' or 'CY', matching the sidebar selection
        display_year: the selected reporting year
        period_label: label for that period, used in chart titles
        error:        why the result is absent, where it is
    """
    st.caption('GHG Protocol Corporate Value Chain (Scope 3) Standard, all '
               'fifteen categories.  Scope 3 sits outside the Safeguard '
               'Mechanism baseline and the NGER position; nothing here '
               'affects either.')

    if result is None or result.detail.empty:
        if error:
            st.error(f'Scope 3 could not be computed.  {error}')
        else:
            st.warning(
                'Scope 3 has not been computed.  The most common cause is a '
                'cached run from before this tab existed: the projection is '
                'held for an hour, so clear the cache and rerun.  Use the '
                'Streamlit menu, top right, then Clear cache, then R.  If it '
                'persists, check that Data/ConfigScope3.yaml, '
                'Data/ReferenceInputs.yaml and Data/Scope3Factors.csv are '
                'present.  Both are distributed by PrepData.')
        return

    if display_year is None:
        display_year = int(result.detail[year_column(year_type)].max())

    _render_composition(result, year_type, display_year, period_label)
    st.markdown('---')
    _render_trajectory(result, year_type)
    st.markdown('---')
    _render_methods(result, year_type, display_year)
    st.markdown('---')
    _render_purchased_goods(result, year_type, display_year, period_label)
    st.markdown('---')
    _render_spend_against_physical(result)
    st.markdown('---')
    _render_basis(result)
    st.markdown('---')
    _render_open_items(result)
    st.markdown('---')
    _render_detail(result)
