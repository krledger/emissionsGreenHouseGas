"""
Tab7Lifecycle.py
Mine lifecycle assumptions, key dates and wind-down methodology.
Last updated: 2026-08-13

ARCHITECTURE:
    Display only.  Receives the loaded dataframe and the phase dates from
    App.py.  No emissions maths happens here -- the charts are physical
    throughput and activity levels, used as a sanity check that the wind-down
    assumptions produce a sensible operating story.

PURPOSE:
    Every lifecycle assumption in this model is otherwise invisible in the
    output: which dates are derived and which are inputs, which cost centres
    keep working after the pits close, what intensity reclaim rehandle runs at,
    when the grid connects and what the generator leaves behind.  This tab puts
    all of it on one page next to the physicals it drives.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from CalcCalendar import date_to_cy, date_to_fy

from CalcUnits import GRAMS_PER_TROY_OUNCE, TONNES_PER_KILOTONNE

# Kept as a name so the charts read unchanged.  The value is defined once,
# in CalcUnits, with every other unit in the model.
GRAMS_PER_TROY_OZ = GRAMS_PER_TROY_OUNCE

# Palette -- consistent with Tab1Ghg
GOLD_METALLIC = '#DBB12A'
BRIGHT_GOLD = '#E8AC41'
DARK_GOLDENROD = '#AE8B0F'
SEPIA = '#734B1A'
CAFE_NOIR = '#39250B'
GRID_GREEN = '#2A9D8F'
PHASE_GREY = '#888888'
MINING_ORANGE = '#E67E22'
PROCESSING_TEAL = '#16A085'
FIXED_GREY = '#7F8C8D'
ALERT_RED = '#C0392B'


# =============================================================================
# Activity groups
# =============================================================================
# Each group is (label, colour, matcher).  The matcher takes the dataframe and
# returns a boolean mask.  Grouping is by WORK TYPE, not by emission scope, so a
# user can see how each stream of activity declines across the lifecycle.

def _grp_rom(d):
    return (d['Activity'] == 'Mining') & (d['SubActivity'] == 'Ore ROM')


def _is_diesel(d):
    return (d['Activity'] == 'Combustion') & (d['SubActivity'] == 'Diesel')


def _grp_reclaim(d):
    # Diesel only -- a cost centre carries kL, tonnes, hours and 'Each', which
    # cannot be summed into one series.
    return _is_diesel(d) & d['CostCentre'].astype(str).isin(['Rehandling'])


def _grp_tsf(d):
    return _is_diesel(d) & d['CostCentre'].astype(str).isin(
        ['Tailings Disposal', 'NPE Dredge'])


def _grp_crushing(d):
    # Crusher FEED only.  The raw 'Ore Crushed' set carries both feed throughput
    # and product feed for every crusher, plus a parallel beneficiation series in
    # dmt -- summing them double counts the same tonnes two or three times.
    return (d['Activity'] == 'Crushing') & (d['SubActivity'] == 'Ore Crushed') & \
           (d['Description'].astype(str).str.contains('Feed Throughput', na=False))


def _grp_milling(d):
    return (d['Activity'] == 'Milling') & (d['SubActivity'] == 'Ore Milled')


def _grp_reagents(d):
    return (d['Activity'] == 'Reagent') & (d['UOM'].astype(str) == 't')


def _grp_grid(d):
    return (d['Activity'] == 'Electricity') & (d['SubActivity'] == 'Grid Power')


def _grp_gen(d):
    return _is_diesel(d) & (d['CostCentre'].astype(str) == 'Site Power Generation')


def _grp_fleet(d):
    return _is_diesel(d) & (d['Department'].astype(str).str.startswith('Mining'))


def _grp_light(d):
    return _is_diesel(d) & (d['CostCentre'].astype(str) == 'Light Vehicles')


ACTIVITY_GROUPS = [
    ('ROM ore mined',        MINING_ORANGE,   _grp_rom),
    ('Mining fleet diesel',  SEPIA,           _grp_fleet),
    ('Reclaim rehandle',     BRIGHT_GOLD,     _grp_reclaim),
    ('TSF / tailings',       CAFE_NOIR,       _grp_tsf),
    ('Crushing',             DARK_GOLDENROD,  _grp_crushing),
    ('Milling',              PROCESSING_TEAL, _grp_milling),
    ('Reagents',             '#5DADE2',       _grp_reagents),
    ('Grid electricity',     GRID_GREEN,      _grp_grid),
    ('Site generation',      ALERT_RED,       _grp_gen),
    ('Light vehicles',       FIXED_GREY,      _grp_light),
]


# =============================================================================
# Helpers
# =============================================================================

def _year_col(df, year_type):
    """Attach a plain integer year column for the chosen basis."""
    d = df.copy()
    if 'Date' in d.columns:
        dates = pd.to_datetime(d['Date'], errors='coerce')
    else:
        dates = pd.to_datetime(dict(year=d['Year'], month=d['Month'], day=1),
                               errors='coerce')
    if year_type == 'FY':
        d['_yr'] = [date_to_fy(x) if pd.notna(x) else np.nan for x in dates]
    else:
        d['_yr'] = [date_to_cy(x) if pd.notna(x) else np.nan for x in dates]
    return d.dropna(subset=['_yr'])


def _series(d, mask, year_type):
    """Annual total for a masked subset, on the chosen year basis."""
    sub = d[mask(d)]
    if len(sub) == 0:
        return pd.Series(dtype=float)
    return sub.groupby('_yr')['Quantity'].sum().sort_index()


def _phase_markers(fig, dates, y_ref='paper'):
    """Vertical phase markers on a numeric-year x axis."""
    for i, (dt, label, colour, dash) in enumerate(dates):
        if dt is None:
            continue
        x = dt.year + (dt.month - 1) / 12.0
        fig.add_shape(type='line', x0=x, x1=x, y0=0, y1=1, yref=y_ref,
                      line=dict(color=colour, width=1.5, dash=dash))
        fig.add_annotation(x=x, y=1.0, yref=y_ref, text=label, showarrow=False,
                           yshift=10 + i * 14, font=dict(size=9, color=colour))


def _fig_layout(fig, title, ylab, height=380):
    fig.update_layout(
        title=title, height=height,
        margin=dict(t=70, b=40, l=60, r=20),
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=-0.28, x=0),
        plot_bgcolor='white',
    )
    fig.update_xaxes(showgrid=False, title='Year')
    fig.update_yaxes(title=ylab, gridcolor='#EEEEEE', rangemode='tozero')
    return fig


# =============================================================================
# Sections
# =============================================================================

def _render_timeline(end_mining_date, end_processing_date,
                     end_rehabilitation_date, grid_connected_date, start_date):
    st.subheader('Lifecycle key dates')
    st.caption(
        'Mining and processing end dates are DERIVED in PrepData -- mining from '
        'the LOM ore table, processing from stockpile exhaustion.  End of '
        'rehabilitation is an INPUT: rehab duration is a decision, not a '
        'production outcome, and it sets the forecast horizon.  The dates below '
        'are what Config.py currently carries; if PrepData derives something '
        'different the forecast run prints a note.'
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Grid connection', grid_connected_date.strftime('%d %b %Y'), 'input')
    c2.metric('End of mining', end_mining_date.strftime('%d %b %Y'), 'derived — LOM ore table')
    c3.metric('End of processing', end_processing_date.strftime('%d %b %Y'), 'derived — stockpile exhaustion')
    c4.metric('End of rehabilitation', end_rehabilitation_date.strftime('%d %b %Y'), 'input — sets horizon')

    # Phase bar
    phases = [
        ('Mining',          start_date,              grid_connected_date,      MINING_ORANGE),
        ('Mining (Grid)',   grid_connected_date,     end_mining_date,          GRID_GREEN),
        ('Processing',      end_mining_date,         end_processing_date,      PROCESSING_TEAL),
        ('Rehabilitation',  end_processing_date,     end_rehabilitation_date,  SEPIA),
    ]
    fig = go.Figure()
    for label, a, b, colour in phases:
        if a is None or b is None:
            continue
        x0 = a.year + (a.month - 1) / 12.0
        x1 = b.year + (b.month - 1) / 12.0
        fig.add_trace(go.Bar(
            x=[x1 - x0], y=['Lifecycle'], base=x0, orientation='h',
            marker_color=colour, name=label,
            hovertemplate=f'{label}<br>%{{base:.1f}} to %{{x:.1f}} yrs<extra></extra>',
        ))
    fig.update_layout(
        barmode='stack', height=150, margin=dict(t=20, b=30, l=80, r=20),
        legend=dict(orientation='h', yanchor='bottom', y=-0.6, x=0),
        plot_bgcolor='white', showlegend=True,
    )
    fig.update_xaxes(title='Year', showgrid=False)
    fig.update_yaxes(showticklabels=False)
    st.plotly_chart(fig, width='stretch', key='lifecycle_phase_bar')


def _render_throughput(d, year_type, markers):
    """Sanity check: ROM -> crushed -> milled -> gold, and recovery."""
    st.subheader('📊 Throughput sanity check')
    st.caption(
        'Ore has to come from somewhere.  If milling continues after ROM ore '
        'stops, the difference is stockpile reclaim -- and there must be a '
        'rehandle line carrying the fuel to move it.  A gap here is the single '
        'most useful check on the wind-down assumptions.'
    )

    # Tonnes to kilotonnes for the chart axis.
    rom = _series(d, _grp_rom, year_type) / TONNES_PER_KILOTONNE
    crushed = _series(d, _grp_crushing_tonnes, year_type) / TONNES_PER_KILOTONNE
    milled = _series(d, _grp_milling, year_type) / TONNES_PER_KILOTONNE
    reclaim = _series(d, _grp_reclaim_tonnes, year_type) / TONNES_PER_KILOTONNE

    fig = go.Figure()
    for name, s, colour in [
        ('ROM ore mined', rom, MINING_ORANGE),
        ('Stockpile reclaim', reclaim, BRIGHT_GOLD),
        ('Ore crushed', crushed, DARK_GOLDENROD),
        ('Ore milled', milled, PROCESSING_TEAL),
    ]:
        if len(s) == 0:
            continue
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode='lines',
                                 line=dict(color=colour, width=2)))
    _phase_markers(fig, markers)
    st.plotly_chart(_fig_layout(fig, 'Ore movement by year', 'kt'),
                    width='stretch', key='lifecycle_throughput')

    # Gold and recovery
    contained = _series(d, lambda x: (x['Activity'] == 'Milling') &
                        (x['SubActivity'] == 'Ore Gold'), year_type) / GRAMS_PER_TROY_OZ
    poured = _series(d, lambda x: (x['Activity'] == 'Revenue') &
                     (x['SubActivity'] == 'Gold Poured'), year_type)
    sold = _series(d, lambda x: (x['Activity'] == 'Revenue') &
                   (x['SubActivity'] == 'Gold Sold'), year_type)

    # Head grade is the most unit-safe sanity check available: contained gold
    # over milled tonnes, both from the same source series.
    milled_t = _series(d, _grp_milling, year_type)
    if len(contained) and len(milled_t):
        grade = (contained * GRAMS_PER_TROY_OZ /
                 milled_t.reindex(contained.index)).replace(
            [np.inf, -np.inf], np.nan).dropna()
        if len(grade):
            figg = go.Figure()
            figg.add_trace(go.Scatter(x=grade.index, y=grade.values,
                                      name='Head grade', mode='lines',
                                      line=dict(color=SEPIA, width=2)))
            _phase_markers(figg, markers)
            st.plotly_chart(_fig_layout(figg, 'Mill head grade', 'g/t', height=300),
                            width='stretch', key='lifecycle_grade')

    fig2 = make_subplots(specs=[[{'secondary_y': True}]])
    if len(contained):
        fig2.add_trace(go.Bar(x=contained.index, y=contained.values,
                              name='Contained gold milled', marker_color='#E8E0C0'),
                       secondary_y=False)
    for name, s, colour in [('Gold poured', poured, GOLD_METALLIC),
                            ('Gold sold', sold, DARK_GOLDENROD)]:
        if len(s):
            fig2.add_trace(go.Scatter(x=s.index, y=s.values, name=name, mode='lines',
                                      line=dict(color=colour, width=2)),
                           secondary_y=False)
    if len(contained) and len(poured):
        rec = (poured / contained.reindex(poured.index) * 100).replace(
            [np.inf, -np.inf], np.nan).dropna()
        # Contained gold and gold poured are separate source series and do not
        # align at the shoulders of the mine life.  Anything outside a plausible
        # metallurgical band is a timing artefact, not a recovery result --
        # surface it rather than plotting a 1,000% year.
        odd = rec[(rec < 50) | (rec > 95)]
        rec = rec[(rec >= 50) & (rec <= 95)]
        if len(odd):
            st.warning(
                'Implied recovery falls outside 50-95% in ' +
                ', '.join(str(int(y)) for y in odd.index) +
                ', so those years are not plotted.  Gold poured is capped at '
                '200,000 oz/yr in the forecast (ForecastInput.yaml), so it runs '
                'flat while contained gold in mill feed varies with grade.  '
                'Implied recovery therefore reflects the cap, not metallurgy — '
                'treat this chart as a check on the gold model, not on the plant.'
            )
        if len(rec):
            fig2.add_trace(go.Scatter(x=rec.index, y=rec.values, name='Recovery %',
                                      mode='lines', line=dict(color=ALERT_RED,
                                                              width=2, dash='dot')),
                           secondary_y=True)
            fig2.update_yaxes(title='Recovery %', secondary_y=True,
                              range=[0, 100], showgrid=False)
    _phase_markers(fig2, markers)
    fig2.update_layout(title='Gold production and recovery', height=380,
                       margin=dict(t=70, b=40, l=60, r=60), hovermode='x unified',
                       legend=dict(orientation='h', yanchor='bottom', y=-0.28, x=0),
                       plot_bgcolor='white')
    fig2.update_xaxes(title='Year', showgrid=False)
    fig2.update_yaxes(title='oz', secondary_y=False, gridcolor='#EEEEEE',
                      rangemode='tozero')
    st.plotly_chart(fig2, width='stretch', key='lifecycle_gold')


def _grp_crushing_tonnes(d):
    return _grp_crushing(d)


def _grp_reclaim_tonnes(d):
    return (d['Activity'] == 'Mining') & (d['SubActivity'] == 'Ore Rehandle')


def _render_decline(d, year_type, markers):
    """Every activity stream as a percentage of its own peak."""
    st.subheader('Activity decline across the lifecycle')
    st.caption(
        'Each stream is shown as a percentage of its OWN peak year, so streams '
        'with very different units sit on one axis.  This is the shape of the '
        'wind-down: what stops at end of mining, what carries through to end of '
        'processing, and what is left running into rehabilitation.'
    )

    rows = []
    fig = go.Figure()
    for label, colour, matcher in ACTIVITY_GROUPS:
        s = _series(d, matcher, year_type)
        if len(s) == 0 or s.max() <= 0:
            continue
        pct = s / s.max() * 100.0
        fig.add_trace(go.Scatter(x=pct.index, y=pct.values, name=label, mode='lines',
                                 line=dict(color=colour, width=2)))
        nz = s[s > 0]
        rows.append({
            'Activity stream': label,
            'Peak year': int(s.idxmax()),
            'First year': int(nz.index.min()) if len(nz) else None,
            'Last year': int(nz.index.max()) if len(nz) else None,
            'Unit': ', '.join(sorted(set(d[matcher(d)]['UOM'].astype(str)))[:3]),
        })
    _phase_markers(fig, markers)
    st.plotly_chart(_fig_layout(fig, 'Activity level as % of own peak', '% of peak',
                                height=460),
                    width='stretch', key='lifecycle_decline')

    if rows:
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)


def _render_methodology(end_mining_date, end_processing_date,
                        end_rehabilitation_date, grid_connected_date):
    st.subheader('Wind-down methodology')
    st.caption(
        'These rules live in PrepData (Forecast/ForecastInput.yaml and '
        'Forecast/PlantConfig.yaml) and shape the budget physicals this model '
        'reads.  They are reproduced here so the assumptions travel with the '
        'emissions output.'
    )

    method = pd.DataFrame([
        {'Stream': 'Mining departments (general)',
         'Rule': 'Linear taper to zero over 3 years from end of mining',
         'Basis': 'phase_wind_down.mining.taper_years',
         'Source': 'Config input'},
        {'Stream': 'Reclaim rehandle (diesel)',
         'Rule': 'Demand-led: mill feed (kt) x haul intensity, intensity falling '
                 'from truck-to-ROM to loader-on-pad, then to zero through rehab',
         'Basis': 'continuing.driver.intensity_start/end_kl_per_kt',
         'Source': '>> CONFIRM — mining engineering'},
        {'Stream': 'TSF / tailings, dredge',
         'Rule': 'Taper to 30% of end-of-mining rate by end of processing, then '
                 'to zero over 2 years',
         'Basis': 'continuing.taper_to, closure_taper_years',
         'Source': '>> CONFIRM — closure team'},
        {'Stream': 'Rehandle consumables (tyres, greases)',
         'Rule': 'Percentage taper with TSF — not demand-driven',
         'Basis': 'continuing.taper_to',
         'Source': 'Immaterial to scope 1'},
        {'Stream': 'Site power generation',
         'Rule': '95% of generation displaced to grid at connection; 5% residual '
                 'retained',
         'Basis': 'major_projects.grid_power_integration',
         'Source': '>> CONFIRM — residual never switches off'},
        {'Stream': 'Processing, admin, exploration',
         'Rule': 'No wind-down defined — carried flat to end of rehabilitation',
         'Basis': 'phase_wind_down (absent)',
         'Source': '>> GAP'},
        {'Stream': 'Demolition and closure earthworks',
         'Rule': 'Not yet modelled',
         'Basis': 'closure profile pending',
         'Source': '>> GAP'},
    ])
    st.dataframe(method, width='stretch', hide_index=True)

    st.markdown('**Open items**')
    st.warning(
        'Assumptions still carrying placeholder values, in rough order of '
        'materiality:\n\n'
        '1. **Reclaim haul intensity** (kL/kt, start and end) — sets scope 1 for '
        'every year the mill runs on stockpile reclaim.\n'
        '2. **Demolition profile** — decommissioning and bulk earthworks sit at '
        'the front of rehabilitation, per ICMM and standard close-down provision '
        'treatment.  Fleet rate in kL/month is the single input needed.\n'
        '3. **Generator residual** — 5% of site generation continues to end of '
        'rehabilitation with nothing turning it off.\n'
        '4. **Processing and admin tail** — no taper defined, so light vehicles '
        'and crusher lines run flat through closure.\n'
        '5. **Contractor cost centres** — GL segments 46, 47, 48, 49 and 81 are '
        'unmapped and land in Mining Open Pit, so they wind down with mining '
        'regardless of what the work actually is.'
    )

    st.info(
        'Scope note: diesel supplied by the operation and burnt on site is '
        'scope 1 under operational control, including fuel burnt by contractors '
        'working under the operation\'s HSE and environmental policies.  It is '
        'scope 3 only where the contractor operates independently and buys its '
        'own fuel.  There is no path by which combusted diesel becomes scope 2.'
    )


# =============================================================================
# Entry point
# =============================================================================

def render_lifecycle_tab(df, start_date, end_mining_date, end_processing_date,
                         end_rehabilitation_date, grid_connected_date):
    """Render the lifecycle assumptions tab.

    Parameters
    ----------
    df : DataFrame          Full loaded dataset (Actual + Budget), monthly.
    start_date : datetime   Model start (Config.DEFAULT_START_DATE).
    end_*_date : datetime   Phase boundaries from Config.py.
    grid_connected_date : datetime
    """
    st.header('Mine lifecycle and wind-down assumptions')
    st.caption(
        'Physical activity behind the emissions forecast, and the rules that '
        'wind it down.  Display only — no emissions maths on this page.'
    )

    year_type = st.radio('Year basis', ['CY', 'FY'], horizontal=True,
                         key='lifecycle_year_type',
                         help='Mine planning is calendar-year; NGER reporting is '
                              'financial-year.')

    d = _year_col(df, year_type)
    if len(d) == 0:
        st.warning('No data available to build the lifecycle view.')
        return

    markers = [
        (grid_connected_date, 'Grid Connection', GRID_GREEN, 'dot'),
        (end_mining_date, 'End Mining', PHASE_GREY, 'dash'),
        (end_processing_date, 'End Processing', PHASE_GREY, 'dash'),
        (end_rehabilitation_date, 'End Rehab', PHASE_GREY, 'dash'),
    ]

    _render_timeline(end_mining_date, end_processing_date,
                     end_rehabilitation_date, grid_connected_date, start_date)
    st.markdown('---')
    _render_throughput(d, year_type, markers)
    st.markdown('---')
    _render_decline(d, year_type, markers)
    st.markdown('---')
    _render_methodology(end_mining_date, end_processing_date,
                        end_rehabilitation_date, grid_connected_date)
