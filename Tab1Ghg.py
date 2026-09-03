"""
Tab1Ghg.py
Total GHG Emissions tab - combined comparison charts
Last updated: 2026-03-10

ARCHITECTURE (v2):
    Receives PrecomputedData from App.py.
    No build_projection, no NGA loading, no annual aggregation.
    Display and filter only.
"""

import math

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from CalcCalendar import period_filter
from Tab8Scope3 import render_scope3_panel
import CalcDashboard as dash

# The dashboard defines its own palette below, at SCOPE_HEX.  The constants
# that used to sit here served the charts this page no longer draws; the
# other tabs carry their own copies.


def _build_raw_data_summary(df, start_date, end_date):
    """Build raw data summary table showing consumption and emissions by fuel type."""

    year_data = period_filter(df[df['DataSet'] == 'Actual'], start_date, end_date).copy()

    if len(year_data) == 0:
        return None

    has_fuel = year_data['NGAFuel'].notna() & (year_data['NGAFuel'] != '')
    year_data = year_data[has_fuel]
    if len(year_data) == 0:
        return None

    agg_cols = {
        'Quantity': 'sum',
        'Scope1_tCO2e': 'sum',
        'Scope2_tCO2e': 'sum',
        'Scope3_tCO2e': 'sum',
        'UOM': 'first',
    }
    if 'Energy_GJ' in year_data.columns:
        agg_cols['Energy_GJ'] = 'sum'
    summary = year_data.groupby('Description', observed=True).agg(
        agg_cols).reset_index()

    summary['_total'] = summary[['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']].sum(axis=1)
    summary = summary.sort_values('_total', ascending=False).drop(columns=['_total'])

    emission_cols = ['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']
    summary = summary[summary[emission_cols].abs().sum(axis=1) > 0]
    if len(summary) == 0:
        return None

    summary['Energy (GJ)'] = summary['Energy_GJ'] if 'Energy_GJ' in summary.columns else 0

    result = pd.DataFrame({
        'Description': summary['Description'],
        'UOM': summary['UOM'],
        'Quantity': summary['Quantity'],
        'Energy (GJ)': summary['Energy (GJ)'],
        'Scope 1 (tCO2-e)': summary['Scope1_tCO2e'],
        'Scope 2 (tCO2-e)': summary['Scope2_tCO2e'],
        'Scope 3 (tCO2-e)': summary['Scope3_tCO2e'],
    })

    def _fmt(x):
        if pd.isna(x) or not isinstance(x, (int, float)):
            return ''
        if abs(x) < 1:
            return f"{x:,.4f}"
        elif abs(x) < 100:
            return f"{x:,.2f}"
        return f"{x:,.0f}"

    result['Quantity'] = result['Quantity'].apply(_fmt)
    result['Energy (GJ)'] = result['Energy (GJ)'].apply(_fmt)
    result['Scope 1 (tCO2-e)'] = result['Scope 1 (tCO2-e)'].apply(_fmt)
    result['Scope 2 (tCO2-e)'] = result['Scope 2 (tCO2-e)'].apply(_fmt)
    result['Scope 3 (tCO2-e)'] = result['Scope 3 (tCO2-e)'].apply(_fmt)

    return result



def _build_monthly_detail(df, start_date, end_date):
    """Build monthly detail table for the selected year with NGA factors shown."""
    year_data = period_filter(df, start_date, end_date).copy()

    if len(year_data) == 0:
        return None

    has_fuel = year_data['NGAFuel'].notna() & (year_data['NGAFuel'] != '')
    year_data = year_data[has_fuel]
    if len(year_data) == 0:
        return None

    year_data['EF_S1_kgCO2e'] = 0.0
    year_data['EF_S2_kgCO2e'] = 0.0
    year_data['EF_S3_kgCO2e'] = 0.0
    qty_mask = year_data['Quantity'].abs() > 0
    if qty_mask.any():
        year_data.loc[qty_mask, 'EF_S1_kgCO2e'] = (
            year_data.loc[qty_mask, 'Scope1_tCO2e'] / year_data.loc[qty_mask, 'Quantity'] * 1000
        )
        year_data.loc[qty_mask, 'EF_S2_kgCO2e'] = (
            year_data.loc[qty_mask, 'Scope2_tCO2e'] / year_data.loc[qty_mask, 'Quantity'] * 1000
        )
        year_data.loc[qty_mask, 'EF_S3_kgCO2e'] = (
            year_data.loc[qty_mask, 'Scope3_tCO2e'] / year_data.loc[qty_mask, 'Quantity'] * 1000
        )

    import calendar
    year_data['Month_Name'] = year_data['Month'].apply(
        lambda m: calendar.month_abbr[int(m)] if pd.notna(m) and 1 <= int(m) <= 12 else ''
    )

    result = pd.DataFrame({
        'Month': year_data['Month_Name'],
        'DataSet': year_data['DataSet'],
        'Description': year_data['Description'],
        'Department': year_data['Department'],
        'CostCentre': year_data['CostCentre'],
        'NGAFuel': year_data['NGAFuel'],
        'UOM': year_data['UOM'],
        'Quantity': year_data['Quantity'],
        'EF S1 (kgCO2e/unit)': year_data['EF_S1_kgCO2e'],
        'EF S2 (kgCO2e/unit)': year_data['EF_S2_kgCO2e'],
        'EF S3 (kgCO2e/unit)': year_data['EF_S3_kgCO2e'],
        'Scope 1 (tCO2-e)': year_data['Scope1_tCO2e'],
        'Scope 2 (tCO2-e)': year_data['Scope2_tCO2e'],
        'Scope 3 (tCO2-e)': year_data['Scope3_tCO2e'],
        'Energy (GJ)': year_data['Energy_GJ'] if 'Energy_GJ' in year_data.columns else 0,
    })

    month_order = {calendar.month_abbr[i]: i for i in range(1, 13)}
    result['_month_sort'] = result['Month'].map(month_order).fillna(0)
    result = result.sort_values(['_month_sort', 'Description', 'CostCentre']).drop(columns=['_month_sort'])
    result = result.reset_index(drop=True)

    return result


# =============================================================================
# DASHBOARD
# =============================================================================
# One page, drawn as a single responsive component rather than a stack of
# framework widgets.  A framework chart sizes itself to a column that does not
# know the window width, which is how a chart runs off the screen; a canvas
# that resizes with its own container does not.
#
# Display only.  Every figure comes from CalcDashboard as plain data and is
# handed to the page as JSON; nothing is derived here.

# The component renders in its own frame and does not inherit the app's
# theme, so the palette is passed in and set as variables.  A light panel
# inside a dark app reads as a bug.

DASHBOARD_CSS = """
:root{--bg:#fff;--ink:#1f2328;--muted:#6b7280;--line:#e5e7eb;
      --line-soft:#f3f4f6;--grid:#eceef1;--hover:#f9fafb;--total:#374151;
      --lift:0 1px 2px rgba(16,24,40,.05),0 6px 16px -6px rgba(16,24,40,.12);
      --lift-hi:0 2px 4px rgba(16,24,40,.06),0 14px 30px -10px rgba(16,24,40,.18);
      --sheen:linear-gradient(180deg,rgba(255,255,255,.9),rgba(255,255,255,0))}
[data-theme="dark"]{--bg:#1a1c1f;--ink:#e8eaed;--muted:#9aa0a6;--line:#33363b;
      --line-soft:#2a2d31;--grid:#31353a;--hover:#22252a;--total:#8a9099;
      --lift:0 1px 2px rgba(0,0,0,.4),0 6px 18px -6px rgba(0,0,0,.55);
      --lift-hi:0 2px 6px rgba(0,0,0,.45),0 16px 34px -10px rgba(0,0,0,.65);
      --sheen:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,0))}
*{box-sizing:border-box}
body{margin:0;font:13px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,
     Helvetica,Arial,sans-serif;color:var(--ink);background:transparent}
.hd{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
    flex-wrap:wrap;margin-bottom:14px}
.hd h1{font-size:20px;font-weight:600;margin:0}
.hd p{margin:2px 0 0;font-size:12px;color:var(--muted)}
.stamp{font-size:12px;color:var(--muted);white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
      gap:10px;margin-bottom:14px}
.kpi{background:var(--bg);border:1px solid var(--line);border-radius:18px;
     padding:11px 15px;border-left-width:4px;border-left-style:solid;
     box-shadow:var(--lift);position:relative;overflow:hidden;
     transition:box-shadow .18s ease,transform .18s ease}
.kpi::before{content:"";position:absolute;inset:0 0 auto 0;height:52%;
     background:var(--sheen);pointer-events:none;border-radius:18px 18px 0 0}
.kpi:hover{box-shadow:var(--lift-hi);transform:translateY(-1px)}
.kpi .lb{font-size:11px;color:var(--muted);margin:0 0 3px}
.kpi .vl{font-size:21px;font-weight:600;margin:0;font-variant-numeric:tabular-nums}
.kpis.lead .kpi{padding:15px 17px}
.kpis.lead .kpi .lb{font-size:12px}
.kpis.lead .kpi .vl{font-size:30px}
.kpis.lead .kpi .un{font-size:13px}
.kpis.lead .kpi .dl{font-size:12px}
.kpi .un{font-size:11px;color:var(--muted);font-weight:400;white-space:nowrap}
.kpi .vl{white-space:nowrap}
.kpi .dl{font-size:11px;margin:3px 0 0}
.dn{color:#16a34a}.up{color:#ef4444}.fl{color:var(--muted)}
.grid{display:grid;gap:12px;margin-bottom:12px}
.g21{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}
.g211{grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)}
.g11{grid-template-columns:repeat(2,minmax(0,1fr))}
.g111{grid-template-columns:repeat(3,minmax(0,1fr))}
@media(max-width:1100px){.g211{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}
@media(max-width:980px){.g21,.g11,.g211,.g111{
      grid-template-columns:minmax(0,1fr)}}
.card{background:var(--bg);border:1px solid var(--line);border-radius:20px;
      padding:16px 18px;min-width:0;overflow:hidden;box-shadow:var(--lift);
      position:relative;transition:box-shadow .18s ease}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:64px;
      background:var(--sheen);pointer-events:none;
      border-radius:20px 20px 0 0}
.card:hover{box-shadow:var(--lift-hi)}
.card>*{position:relative}
.card h2{font-size:13px;font-weight:600;margin:0}
.card p.sub{font-size:11px;color:var(--muted);margin:2px 0 10px}
svg{display:block;width:100%;height:auto;overflow:visible}
.lg{display:flex;flex-wrap:wrap;gap:12px;font-size:11px;color:var(--muted);
    margin:8px 0 0}
.lg i{display:inline-block;width:9px;height:9px;border-radius:2px;
      margin-right:5px;vertical-align:-1px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;font-weight:500;color:var(--muted);font-size:11px;
   border-bottom:1px solid var(--line);padding:0 6px 6px 0}
td{padding:6px 6px 6px 0;border-bottom:1px solid var(--line-soft);
   font-variant-numeric:tabular-nums}
td.n,th.n{text-align:right}
tr:last-child td{border-bottom:none}
.sm{font-size:10px;color:var(--muted)}
.hit{cursor:default}
.hit:hover{filter:brightness(1.06)}
#tip{position:fixed;z-index:99;pointer-events:none;opacity:0;
     transition:opacity .09s ease;background:var(--ink);color:var(--bg);
     border-radius:10px;padding:8px 11px;font-size:12px;line-height:1.5;
     box-shadow:0 8px 24px -6px rgba(0,0,0,.45);max-width:280px;
     font-variant-numeric:tabular-nums}
#tip b{display:block;font-size:12px;font-weight:600;margin-bottom:3px;
     opacity:.95}
#tip span{display:block;opacity:.85;white-space:pre}
.lcw{margin-top:4px}
.lc{display:grid;grid-template-columns:1fr auto auto;
    grid-template-areas:"n v s" "b b b";gap:3px 8px;padding:11px 0;
    border-bottom:1px solid var(--line-soft)}
.lc:last-child{border-bottom:none}
.lc .ln{grid-area:n;font-size:15px;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap}
.lc .ly{display:none}
.lc .lb{grid-area:b;display:flex;gap:2px;min-width:0;height:24px;
        margin-top:3px}
.lc .lb i{display:block;height:26px;border-radius:7px;overflow:hidden;
          color:#fff;font-size:11px;font-weight:600;font-style:normal;
          display:flex;align-items:center;justify-content:center;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.28);cursor:default}
.lc .lb i:hover{filter:brightness(1.07)}
.lc .lb i{height:24px}
.lc .lv{grid-area:v;text-align:right;font-size:15px;
        font-variant-numeric:tabular-nums}
.lc .ls{grid-area:s;width:52px;text-align:right;font-size:13px;
        color:var(--muted);font-variant-numeric:tabular-nums}
.lc.plan{border-top:1px solid var(--line);border-bottom:none;margin-top:4px}
.lc.plan .ln,.lc.plan .lv,.lc.plan .ls{font-weight:600}
.lc.plan .ls{color:var(--ink)}
.note{font-size:11px;color:var(--muted);margin:10px 0 0}
.tn{display:flex;align-items:center;gap:10px;padding:7px 0;
    border-bottom:1px solid var(--line-soft)}
.tn:hover{background:var(--hover)}
.tn{padding:9px 0}
.tn .nm{flex:none;width:220px;font-size:15px;display:flex;align-items:center;
        gap:6px;min-width:0}
.tn .nm span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tn .ax{flex:1;display:flex;gap:1px;min-width:0;height:20px}
.tn .ax i{display:block;height:20px;border-radius:6px;
        box-shadow:inset 0 1px 0 rgba(255,255,255,.25)}
.tn .vv{flex:none;width:90px;text-align:right;font-size:15px;
        font-variant-numeric:tabular-nums}
.tn .sh{flex:none;width:58px;text-align:right;font-size:13px;
        color:var(--muted);font-variant-numeric:tabular-nums}
.narrow{max-width:100%}
details>summary{list-style:none;cursor:pointer}
details>summary::-webkit-details-marker{display:none}
details>summary .tn .nm{font-weight:600}
details>summary .cv{display:inline-block;width:12px;color:var(--muted);
    transition:transform .15s ease;flex:none}
details[open]>summary .cv{transform:rotate(90deg)}
.child .nm{padding-left:22px;font-size:13px;color:var(--muted);font-weight:400}
.child .ax,.child .ax i{height:14px}
.child .ax i{border-radius:5px}
.child .vv{font-size:13px}
.child .vv{color:var(--muted)}
"""

# Height of the frame the panel is drawn in.  Set so the whole dashboard is
# visible without a scrollbar inside the frame at the widths the app is used
# at; a narrow window stacks the cards and scrolls, which is correct there.
DASHBOARD_HEIGHT = 2080

SCOPE_HEX = {'scope1': '#2A78D6', 'scope2': '#EB6834', 'scope3': '#1BAF7A'}
SOURCE_HEX = ['#2A78D6', '#EB6834', '#1BAF7A', '#7C5CD6', '#D6A22A',
              '#3AA6B9', '#C05680', '#9CA3AF']
AXIS_HEX = 'var(--muted)'
GRID_HEX = 'var(--grid)'
PRIOR_HEX = 'var(--muted)'
TOTAL_HEX = 'var(--ink)'
TOTAL_BAR = 'var(--total)'


# ---------------------------------------------------------------------
# SVG PRIMITIVES
# ---------------------------------------------------------------------
# The charts are drawn server side as SVG.  A chart library would have to be
# fetched from the internet at render time, and a dashboard that goes blank
# because a content delivery network is unreachable is worse than no
# dashboard.  SVG scales with its container, so nothing runs off the screen.

def _escape(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _nice_ceiling(value):
    """A round number at or above value, for an axis top."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        if value <= step * magnitude:
            return step * magnitude
    return 10 * magnitude


def _thousands(value):
    """Axis label: 120000 reads as 120k."""
    if value >= 1000:
        return f'{value / 1000:,.0f}k'
    return f'{value:,.0f}'


def _text(x, y, content, size=10, fill=AXIS_HEX, anchor='start', weight=400):
    # Colour goes through style rather than the fill attribute, because a CSS
    # variable is only resolved in a property, not in a presentation
    # attribute.
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'style="fill:{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{_escape(content)}</text>')


def _legend(entries):
    items = ''.join(
        f'<span><i style="background:{colour}"></i>{_escape(label)}</span>'
        for label, colour in entries)
    return f'<div class="lg">{items}</div>'




# ---------------------------------------------------------------------
# CHARTS
# ---------------------------------------------------------------------

def _chart_trend(payload, width=760, height=250):
    """Monthly stack by scope, with the prior year total as a dashed line."""
    months = payload['months']
    if not months:
        return '<p class="sub">No monthly detail for the period.</p>'

    left, right, top, bottom = 46, 8, 10, 24
    plot_w = width - left - right
    plot_h = height - top - bottom

    stacks = [sum(payload['series'][k][i] or 0 for k in
                  ('scope1', 'scope2', 'scope3')) for i in range(len(months))]
    priors = [p for p in payload['prior'] if p is not None]
    ceiling = _nice_ceiling(max(stacks + priors) if (stacks or priors) else 1)

    def y_of(value):
        return top + plot_h - (value / ceiling) * plot_h

    parts = []
    for step in range(5):
        value = ceiling * step / 4
        y = y_of(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
                     f'y2="{y:.1f}" style="stroke:{GRID_HEX}" '
                     f'stroke-width="1"/>')
        parts.append(_text(left - 6, y + 3, _thousands(value), anchor='end'))

    slot = plot_w / len(months)
    bar = min(slot * 0.62, 30)
    for index, label in enumerate(months):
        x = left + slot * index + (slot - bar) / 2
        base = top + plot_h
        for key in ('scope1', 'scope2', 'scope3'):
            value = payload['series'][key][index] or 0
            if value <= 0:
                continue
            h = (value / ceiling) * plot_h
            base -= h
            parts.append(f'<rect x="{x:.1f}" y="{base:.1f}" width="{bar:.1f}" '
                         f'height="{h:.1f}" rx="4" fill="{SCOPE_HEX[key]}"/>')
        parts.append(_text(left + slot * index + slot / 2, height - 8, label,
                           anchor='middle'))

    points = [(left + slot * i + slot / 2, y_of(v))
              for i, v in enumerate(payload['prior']) if v is not None]
    if len(points) > 1:
        path = ' '.join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}'
                        for i, (x, y) in enumerate(points))
        parts.append(f'<path d="{path}" fill="none" '
                     f'style="stroke:{PRIOR_HEX}" stroke-width="1.5" '
                     f'stroke-dasharray="4 4"/>')

    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


PHASE_TINT = {
    'Mining': 'rgba(42,120,214,0.09)',
    'Processing': 'rgba(235,104,52,0.09)',
    'Rehabilitation': 'rgba(124,92,214,0.09)',
    'Closed': 'rgba(156,163,175,0.09)',
}


def _tip(heading, lines):
    """Cursor tooltip content, as an attribute on the shape it belongs to.

    A native SVG title element only appears after the pointer has been still
    for about a second and is easy to miss entirely, so the panel carries its
    own tooltip.  The script that draws it is a dozen lines at the foot of
    the page and fetches nothing.
    """
    payload = '|'.join([str(heading)] + [str(line) for line in lines])
    return f'data-tip="{_escape(payload)}"'


def _scope_lines(segments, total=None):
    """Standard tooltip body: a line per scope, then the total."""
    lines = [f'{name}   {value:,.0f} tCO2-e' for name, value in segments]
    if total is not None:
        lines.append(f'Total   {total:,.0f} tCO2-e')
    return lines


def _chart_years(payload, width=1060, height=330):
    """Every year of the plan, stacked by scope, over the shaded phases.

    The plan runs to 2049, so the year is the readable grain.  Phases are
    shaded behind the bars and milestones marked on the axis, so a change in
    the profile can be read against the event that causes it.
    """
    years = payload.get('years') or []
    if not years:
        return '<p class="sub">No annual detail to plot.</p>'

    left, right, top, bottom = 52, 12, 30, 46
    plot_w = width - left - right
    plot_h = height - top - bottom

    totals = [r['total'] or 0 for r in years]
    ceiling = _nice_ceiling(max(totals) if totals else 1)
    slot = plot_w / len(years)

    def y_of(value):
        return top + plot_h - (value / ceiling) * plot_h

    parts = []

    # Phase shading first, so everything else sits over it.
    for band in payload.get('bands') or []:
        x = left + slot * band['start']
        w = slot * (band['end'] - band['start'] + 1)
        tint = PHASE_TINT.get(band['phase'], PHASE_TINT['Closed'])
        parts.append(f'<rect x="{x:.1f}" y="{top}" width="{w:.1f}" '
                     f'height="{plot_h:.1f}" fill="{tint}"/>')
        if w > 54:
            parts.append(_text(x + w / 2, top - 16, band['phase'], size=10,
                               anchor='middle'))

    for step in range(5):
        value = ceiling * step / 4
        y = y_of(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
                     f'y2="{y:.1f}" style="stroke:{GRID_HEX}" '
                     f'stroke-width="1"/>')
        parts.append(_text(left - 7, y + 3, _thousands(value), anchor='end'))

    bar = min(slot * 0.68, 34)
    every = 1 if len(years) <= 16 else 2
    for index, record in enumerate(years):
        x = left + slot * index + (slot - bar) / 2
        base = top + plot_h
        segments = []
        for key, name in (('scope1', 'Scope 1'), ('scope2', 'Scope 2'),
                          ('scope3', 'Scope 3')):
            value = record.get(key) or 0
            if value <= 0:
                continue
            h = (value / ceiling) * plot_h
            base -= h
            segments.append((key, name, value, base, h))
        tip = _tip(f"{record['label']}  \u00b7  {record['basis'].lower()}",
                   _scope_lines([(n, v) for _, n, v, _, _ in segments],
                                record['total'] or 0)
                   + ([f"Ore   {record['rom_mt']:,.2f} Mt"]
                      if record.get('rom_mt') else [])
                   + ([f"Gold   {record['gold_oz']:,.0f} oz"]
                      if record.get('gold_oz') else []))
        parts.append(f'<g class="hit" {tip}>' + ''.join(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar:.1f}" '
            f'height="{h:.1f}" rx="4" fill="{SCOPE_HEX[key]}"/>'
            for key, _, _, y, h in segments)
            # An invisible column over the whole slot, so the pointer finds
            # the year anywhere in it rather than only on the bar itself.
            + f'<rect x="{left + slot * index:.1f}" y="{top}" '
              f'width="{slot:.1f}" height="{plot_h:.1f}" fill="transparent"/>'
            + '</g>')
        if index % every == 0:
            parts.append(_text(left + slot * index + slot / 2, height - 26,
                               str(record['year'] or record['label']), size=9,
                               anchor='middle'))

    # Where the record stops and the forecast begins.  Drawn as a divider
    # with a label on each side rather than by fading the forecast bars: a
    # bar that is paler for no stated reason reads as a rendering fault.
    boundary = payload.get('forecast_from')
    if boundary:
        x = left + slot * (boundary['position'] + 0.5)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
                     f'y2="{top + plot_h}" style="stroke:var(--ink)" '
                     f'stroke-width="1.5" opacity="0.35"/>')
        parts.append(_text(x - 7, top + 13, 'Recorded', size=9, anchor='end',
                           fill=TOTAL_HEX))
        parts.append(_text(x + 7, top + 13, 'Forecast', size=9,
                           fill=TOTAL_HEX))
        parts.append(f'<rect class="hit" x="{x - 5:.1f}" y="{top}" '
                     f'width="10" height="{plot_h:.1f}" fill="transparent" '
                     + _tip('Forecast from',
                            [boundary['date'],
                             'Recorded to the left, budget to the right'])
                     + '/>')

    # Milestones, positioned on the fractional year so a mid year event is
    # not drawn as though it happened in January.  Labels alternate between
    # two lines, because end of mining and end of processing sit two years
    # apart and would otherwise print over each other.
    for order, mark in enumerate(payload.get('marks') or []):
        x = left + slot * (mark['position'] + 0.5)
        parts.append(f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" '
                     f'y2="{top + plot_h}" style="stroke:var(--ink)" '
                     f'stroke-width="1" stroke-dasharray="3 3" '
                     f'opacity="0.55"/>')
        parts.append(f'<rect class="hit" x="{x - 5:.1f}" y="{top - 4}" '
                     f'width="10" height="{plot_h + 4:.1f}" fill="transparent" '
                     f'{_tip(mark["label"], [mark["date"]])}/>')
        # An end label is pulled inside the frame rather than centred, so
        # the last milestone is not cut off by the edge of the chart.
        anchor = 'middle'
        if x > left + plot_w - 50:
            anchor, x = 'end', left + plot_w
        elif x < left + 50:
            anchor, x = 'start', left
        y = height - 16 if order % 2 == 0 else height - 5
        parts.append(f'<text x="{x:.1f}" y="{y}" font-size="9" '
                     f'style="fill:var(--ink)" text-anchor="{anchor}" '
                     f'opacity="0.75">{_escape(mark["label"])}</text>')

    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


def _chart_lifecycle(payload):
    """The plan by phase, each phase a stacked bar of its scopes.

    Mining is around nine tenths of the plan, so a chart that draws phases
    against each other on one scale, a ring above all, leaves the other two
    as slivers that cannot be read.  Each phase gets the full width instead:
    the bar carries the scope mix within that phase, which is legible whether
    the phase is nine tenths of the plan or one hundredth, and the magnitude
    is carried by the figure and the share beside it.
    """
    buckets = payload.get('lifecycle') or []
    if not buckets:
        return '<p class="sub">No lifecycle detail to plot.</p>'
    phases = [b for b in buckets if b['label'] != 'Life of mine']
    plan = next((b for b in buckets if b['label'] == 'Life of mine'), None)
    grand = (plan['total'] if plan else sum(b['total'] or 0 for b in phases)) or 1.0

    def _row(bucket, is_plan):
        total = bucket['total'] or 0
        share = total / grand * 100
        segments = []
        for key, name in (('scope1', 'Scope 1'), ('scope2', 'Scope 2'),
                          ('scope3', 'Scope 3')):
            value = bucket.get(key) or 0
            if value <= 0:
                continue
            portion = value / total * 100 if total else 0
            tip = _tip(f"{bucket['label']}  \u00b7  {name}",
                       [f'{value:,.0f} tCO2-e',
                        f'{portion:.1f}% of the phase',
                        f'{value / grand * 100:.1f}% of the life of mine'])
            label = (f'<b>{portion:.0f}%</b>' if portion >= 9 else '')
            segments.append(
                f'<i style="width:{portion:.2f}%;background:{SCOPE_HEX[key]}" '
                f'{tip}>{label}</i>')
        if not segments:
            segments = ['<span class="sm">nil</span>']
        return (
            f'<div class="lc{" plan" if is_plan else ""}">'
            f'<span class="ln">{_escape(bucket["label"])}</span>'
            f'<span class="ly">{bucket["years"]} yr</span>'
            f'<span class="lb">{"".join(segments)}</span>'
            f'<span class="lv">{total:,.0f}</span>'
            f'<span class="ls">{share:.1f}%</span></div>')

    rows = [_row(bucket, False) for bucket in phases]
    if plan is not None:
        rows.append(_row(plan, True))
    return '<div class="lcw">' + ''.join(rows) + '</div>'


GOLD_HEX = '#7C5CD6'
ROM_HEX = '#D6A22A'


def _axis_value(value, places):
    """Axis label at the precision the measure is read to."""
    if value >= 1000:
        return _thousands(value)
    return f'{value:,.{places}f}'


def _chart_intensity(payload, width=1060, height=300):
    """Both intensity measures across the plan, on their own axes.

    Tonnes per ounce and kilograms per tonne of ore are three orders of
    magnitude apart, so one axis would flatten one of them.  Each line is
    read against the axis in its own colour.
    """
    years = payload.get('intensity_years') or []
    points = [r for r in years if r['gold'] is not None or r['rom'] is not None]
    if len(points) < 2:
        return '<p class="sub">No intensity series to plot.</p>'

    left, right, top, bottom = 56, 64, 28, 44
    plot_w = width - left - right
    plot_h = height - top - bottom

    gold_values = [r['gold'] for r in points if r['gold'] is not None]
    rom_values = [r['rom'] for r in points if r['rom'] is not None]
    gold_top = _nice_ceiling(max(gold_values)) if gold_values else 1.0
    rom_top = _nice_ceiling(max(rom_values)) if rom_values else 1.0

    slot = plot_w / max(len(points) - 1, 1)
    parts = []

    # The plan phases, shaded behind the lines on the same footing as the
    # emissions chart above, so a turn in the intensity can be read against
    # the phase it happens in.  Bands are located by year rather than by
    # index, because this chart carries only the years that have a reading.
    index_of = {record['year']: index for index, record in enumerate(points)}
    for band in payload.get('bands') or []:
        band_years = [y['year'] for y in (payload.get('years') or [])
                      [band['start']:band['end'] + 1]]
        seats = [index_of[y] for y in band_years if y in index_of]
        if not seats:
            continue
        x_from = left + slot * (min(seats) - 0.5)
        x_to = left + slot * (max(seats) + 0.5)
        x_from, x_to = max(x_from, left), min(x_to, left + plot_w)
        tint = PHASE_TINT.get(band['phase'], PHASE_TINT['Closed'])
        parts.append(f'<rect x="{x_from:.1f}" y="{top}" '
                     f'width="{x_to - x_from:.1f}" height="{plot_h:.1f}" '
                     f'fill="{tint}"/>')
        if x_to - x_from > 54:
            parts.append(_text((x_from + x_to) / 2, top - 12, band['phase'],
                               size=10, anchor='middle'))

    for step in range(5):
        share = step / 4
        y = top + plot_h - share * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
                     f'y2="{y:.1f}" style="stroke:{GRID_HEX}" '
                     f'stroke-width="1"/>')
        parts.append(_text(left - 7, y + 3, _axis_value(gold_top * share, 1),
                           anchor='end', fill=GOLD_HEX))
        parts.append(_text(left + plot_w + 7, y + 3,
                           _axis_value(rom_top * share, 0), fill=ROM_HEX))

    parts.append(_text(left - 7, top - 12, 't/oz Au', size=9, anchor='end',
                       fill=GOLD_HEX))
    parts.append(_text(left + plot_w + 7, top - 12, 'kg/t ROM', size=9,
                       fill=ROM_HEX))

    def _line(key, ceiling, colour):
        # Runs of consecutive readings, so a year with no denominator breaks
        # the line rather than being bridged across.
        runs, run = [], []
        for index, record in enumerate(points):
            value = record[key]
            if value is None:
                if len(run) > 1:
                    runs.append(run)
                run = []
                continue
            y = top + plot_h - (value / ceiling) * plot_h if ceiling else top
            run.append((left + slot * index, y))
        if len(run) > 1:
            runs.append(run)

        drawn = []
        for stroke in runs:
            path = ' '.join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}'
                            for i, (x, y) in enumerate(stroke))
            drawn.append(f'<path d="{path}" fill="none" stroke="{colour}" '
                         f'stroke-width="2.4" stroke-linecap="round" '
                         f'stroke-linejoin="round"/>')
            for x, y in stroke:
                drawn.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" '
                             f'fill="{colour}" stroke="var(--bg)" '
                             f'stroke-width="1.5"/>')
        return ''.join(drawn)

    parts.append(_line('gold', gold_top, GOLD_HEX))
    parts.append(_line('rom', rom_top, ROM_HEX))

    # One hit column per year carrying both readings, so the pointer does not
    # have to find a four pixel dot.
    for index, record in enumerate(points):
        lines = []
        if record['gold'] is not None:
            lines.append(f"Per ounce   {record['gold']:,.2f} t CO2-e/oz Au")
        if record['rom'] is not None:
            lines.append(f"Per tonne   {record['rom']:,.1f} kg CO2-e/t ROM")
        parts.append(
            f'<rect class="hit" x="{left + slot * index - slot / 2:.1f}" '
            f'y="{top}" width="{slot:.1f}" height="{plot_h:.1f}" '
            f'fill="transparent" '
            + _tip(f"{record['label']}  \u00b7  {record['basis'].lower()}",
                   lines) + '/>')

    every = 1 if len(points) <= 16 else 2
    for index, record in enumerate(points):
        if index % every:
            continue
        parts.append(_text(left + slot * index, height - 22,
                           str(record['year'] or record['label']), size=9,
                           anchor='middle'))

    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


def _chart_scope(payload, width=330, height=250):
    """Each scope against the period total."""
    names = ['Scope 1', 'Scope 2', 'Scope 3', 'Total']
    values = [payload['cards'][n]['value'] or 0 for n in names]
    ceiling = _nice_ceiling(max(values) if values else 1)

    left, right, top, bottom = 46, 8, 16, 34
    plot_w = width - left - right
    plot_h = height - top - bottom
    colours = [SCOPE_HEX['scope1'], SCOPE_HEX['scope2'], SCOPE_HEX['scope3'],
               TOTAL_BAR]

    parts = []
    for step in range(5):
        value = ceiling * step / 4
        y = top + plot_h - (value / ceiling) * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
                     f'y2="{y:.1f}" style="stroke:{GRID_HEX}" '
                     f'stroke-width="1"/>')
        parts.append(_text(left - 6, y + 3, _thousands(value), anchor='end'))

    slot = plot_w / len(names)
    bar = min(slot * 0.56, 46)
    for index, (name, value, colour) in enumerate(zip(names, values, colours)):
        h = (value / ceiling) * plot_h if ceiling else 0
        x = left + slot * index + (slot - bar) / 2
        y = top + plot_h - h
        share = payload['cards'][name]['share']
        tip = _tip(name, [f'{value:,.0f} tCO2-e']
                   + ([f'{share:.1f}% of the period total']
                      if share is not None else []))
        parts.append(f'<rect class="hit" x="{x:.1f}" y="{y:.1f}" '
                     f'width="{bar:.1f}" height="{h:.1f}" rx="6" '
                     f'style="fill:{colour}" {tip}/>')
        parts.append(_text(x + bar / 2, y - 5, f'{value:,.0f}', size=10,
                           anchor='middle', fill=TOTAL_HEX))
        parts.append(_text(x + bar / 2, height - 18, name, anchor='middle'))
        if share is not None:
            parts.append(_text(x + bar / 2, height - 6, f'{share:.0f}%',
                               size=9, anchor='middle'))

    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


def _chart_sources(payload, width=420, height=280):
    """Share of the period by source, as a ring."""
    sources = payload['sources']
    if not sources:
        return '<p class="sub">No source detail for the period.</p>'

    total = sum(s['total'] or 0 for s in sources) or 1.0
    cx, cy = 106, height / 2
    outer, inner = 88, 52

    parts = []
    angle = -math.pi / 2
    for index, source in enumerate(sources):
        fraction = (source['total'] or 0) / total
        if fraction <= 0:
            continue
        sweep = fraction * 2 * math.pi
        end = angle + sweep
        large = 1 if sweep > math.pi else 0
        x1, y1 = cx + outer * math.cos(angle), cy + outer * math.sin(angle)
        x2, y2 = cx + outer * math.cos(end), cy + outer * math.sin(end)
        x3, y3 = cx + inner * math.cos(end), cy + inner * math.sin(end)
        x4, y4 = cx + inner * math.cos(angle), cy + inner * math.sin(angle)
        colour = SOURCE_HEX[index % len(SOURCE_HEX)]
        parts.append(
            f'<path class="hit" d="M{x1:.1f},{y1:.1f} A{outer},{outer} 0 '
            f'{large},1 {x2:.1f},{y2:.1f} L{x3:.1f},{y3:.1f} '
            f'A{inner},{inner} 0 {large},0 {x4:.1f},{y4:.1f} Z" '
            f'fill="{colour}" '
            + _tip(source['label'], [f"{source['total']:,.0f} tCO2-e",
                                     f"{source['share']:.1f}% of the period"])
            + '/>')
        angle = end

    parts.append(_text(cx, cy - 2, f'{total:,.0f}', size=17, anchor='middle',
                       fill=TOTAL_HEX, weight=600))
    parts.append(_text(cx, cy + 14, 'tCO2-e', size=10, anchor='middle'))

    row = 0
    for index, source in enumerate(sources):
        colour = SOURCE_HEX[index % len(SOURCE_HEX)]
        y = 24 + row * 31
        parts.append(f'<rect x="220" y="{y - 9}" width="10" height="10" '
                     f'rx="3" fill="{colour}"/>')
        label = source['label']
        if len(label) > 24:
            label = label[:23] + '…'
        parts.append(_text(236, y, label, size=11, fill=TOTAL_HEX))
        parts.append(_text(236, y + 13,
                           f"{source['share']:.1f}%  ·  "
                           f"{source['total']:,.0f} t", size=10))
        row += 1

    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


# ---------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------

def _movement_html(movement, against):
    """The vs prior year line.  A fall in emissions is the good direction."""
    if movement is None:
        return '<p class="dl fl">no prior period</p>'
    if abs(movement) < 0.05:
        return '<p class="dl fl">level on prior period</p>'
    style = 'dn' if movement < 0 else 'up'
    arrow = '↓' if movement < 0 else '↑'
    return (f'<p class="dl {style}">{arrow} {abs(movement):.1f}% {against}</p>')


def _kpi(label, value, unit, movement, against, colour, places=0):
    if value is None:
        shown = '-'
    elif places:
        shown = f'{value:,.{places}f}'
    else:
        shown = f'{value:,.0f}'
    unit_html = f' <span class="un">{_escape(unit)}</span>' if unit else ''
    return (f'<div class="kpi" style="border-left-color:{colour}">'
            f'<p class="lb">{_escape(label)}</p>'
            f'<p class="vl">{shown}{unit_html}</p>'
            f'{_movement_html(movement, against)}</div>')


def _tree_row(record, scale, is_child):
    """One line of the breakdown: name, proportion bar, value, share."""
    bars = []
    for key in ('scope1', 'scope2', 'scope3'):
        value = record.get(key) or 0
        if value <= 0:
            continue
        width = value / scale * 100 if scale else 0
        name = {'scope1': 'Scope 1', 'scope2': 'Scope 2',
                'scope3': 'Scope 3'}[key]
        bars.append(
            f'<i style="width:{width:.2f}%;background:{SCOPE_HEX[key]}" '
            + _tip(f"{record['label']}  \u00b7  {name}",
                   [f'{value:,.0f} tCO2-e',
                    f"{value / (record['total'] or 1) * 100:.1f}% of the line"])
            + '></i>')
    if not bars:
        bars = ['<span style="font-size:11px;color:var(--muted)">'
                'nil allocated</span>']

    chevron = '' if is_child else '<span class="cv">&#9656;</span>'
    share = record.get('share')
    return (
        f'<div class="tn{" child" if is_child else ""}">'
        f'<span class="nm">{chevron}<span>{_escape(record["label"])}</span></span>'
        f'<span class="ax">{"".join(bars)}</span>'
        f'<span class="vv">{record["total"]:,.0f}</span>'
        f'<span class="sh">{"" if share is None else f"{share:.1f}%"}</span>'
        f'</div>')


def _tree_html(payload):
    """Departments, each collapsing to its cost centres.

    Native details and summary elements, so it opens and closes without a
    script.  Every bar is scaled to the largest department, so a cost centre
    can be read against the department above it and against every other line
    on the page.
    """
    rows = payload['tree']
    if not rows:
        return '<p class="sub">No emissions recorded for the period.</p>'

    scale = payload.get('tree_scale') or 1.0
    blocks = []
    index = 0
    while index < len(rows):
        parent = rows[index]
        index += 1
        children = []
        while index < len(rows) and rows[index]['depth'] == 1:
            children.append(rows[index])
            index += 1

        summary = _tree_row(parent, scale, is_child=False)
        if not children:
            # Nothing to expand, so the row is not a disclosure.
            blocks.append(summary.replace('<span class="cv">&#9656;</span>',
                                          '<span class="cv"></span>'))
            continue
        body = ''.join(_tree_row(child, scale, is_child=True)
                       for child in children)
        blocks.append(f'<details><summary>{summary}</summary>{body}</details>')

    legend = _legend([('Scope 1', SCOPE_HEX['scope1']),
                      ('Scope 2', SCOPE_HEX['scope2']),
                      ('Scope 3', SCOPE_HEX['scope3'])])
    return ''.join(blocks) + legend


def _dashboard_html(payload):
    """The dashboard page.  Self contained: no script, no external request."""
    cards = payload['cards']
    gold = payload['intensity']['gold']
    rom = payload['intensity']['rom']
    against = f"vs {cards['Total']['prior_label']}" if cards['Total']['prior_label'] else 'vs prior year'

    kpis = ''.join([
        _kpi('Total emissions', cards['Total']['value'], 'tCO2-e',
             cards['Total']['movement'], against, TOTAL_HEX),
        _kpi('Scope 1', cards['Scope 1']['value'], 'tCO2-e',
             cards['Scope 1']['movement'], against, SCOPE_HEX['scope1']),
        _kpi('Scope 2', cards['Scope 2']['value'], 'tCO2-e',
             cards['Scope 2']['movement'], against, SCOPE_HEX['scope2']),
        _kpi('Scope 3', cards['Scope 3']['value'], 'tCO2-e',
             cards['Scope 3']['movement'], against, SCOPE_HEX['scope3']),
        _kpi('Intensity per ounce', gold['headline'], 't/oz Au',
             gold['movement'], against, TOTAL_HEX, gold['places']),
        _kpi('Intensity per tonne', rom['headline'], 'kg/t ROM',
             rom['movement'], against, TOTAL_HEX, rom['places']),
    ])

    scope_legend = _legend([('Scope 1', SCOPE_HEX['scope1']),
                            ('Scope 2', SCOPE_HEX['scope2']),
                            ('Scope 3', SCOPE_HEX['scope3']),
                            ])
    stack_legend = _legend([('Scope 1', SCOPE_HEX['scope1']),
                            ('Scope 2', SCOPE_HEX['scope2']),
                            ('Scope 3', SCOPE_HEX['scope3'])])
    intensity_legend = _legend([('Per ounce of gold, t CO2-e/oz Au', GOLD_HEX),
                                ('Per tonne of ore, kg CO2-e/t ROM', ROM_HEX)])

    theme = payload.get('theme', 'light')
    return f"""<!doctype html><html data-theme="{theme}"><head><meta charset="utf-8">
<style>{DASHBOARD_CSS}</style></head><body>
<div class="hd">
  <div><h1>GHG emissions</h1>
       <p>All scopes, against the life of mine plan</p></div>
  <span class="stamp">{_escape(payload['period'])} &middot; tCO2-e &middot;
        {_escape(payload.get('coverage', ''))}</span>
</div>

<div class="kpis lead">{kpis}</div>

<div class="card" style="margin-bottom:12px">
  <div style="display:flex;align-items:baseline;justify-content:space-between">
    <h2>Emissions over the life of mine</h2>
    <span class="stamp">Hover a bar for the year</span>
  </div>
  <p class="sub">By year, stacked by scope, shaded by plan phase.  The
     divider marks where the record stops and the budget takes over</p>
  {_chart_years(payload)}
  {scope_legend}
</div>

<div class="grid g211">
  <div class="card">
    <div style="display:flex;align-items:baseline;justify-content:space-between">
      <h2>By department and cost centre</h2>
      <span class="stamp">Expand a department</span>
    </div>
    <p class="sub">{_escape(payload['period'])}.  Bars are scaled to the
       largest department, so any line reads against any other</p>
    <div class="narrow">{_tree_html(payload)}</div>
  </div>
  <div class="card">
    <h2>By lifecycle phase</h2>
    <p class="sub">Each bar is the scope mix within that phase</p>
    {_chart_lifecycle(payload)}
    {stack_legend}
  </div>
  <div class="card">
    <h2>By scope</h2>
    <p class="sub">Contribution to {_escape(payload['period'])}</p>
    {_chart_scope(payload)}
  </div>
</div>

<div class="grid g11">
  <div class="card">
    <div style="display:flex;align-items:baseline;justify-content:space-between">
      <h2>Intensity over the life of mine</h2>
      <span class="stamp">Hover a point for the year</span>
    </div>
    <p class="sub">By year, each measure on its own axis, over the shaded plan
       phases.  Ore stops at the last full year of mining, because a closing
       year divides a full year of emissions by part of a year of ore.  Gold
       runs to the end of processing</p>
    {_chart_intensity(payload, width=560, height=300)}
    {intensity_legend}
  </div>
  <div class="card">
    <h2>Top emission sources</h2>
    <p class="sub">Share of {_escape(payload['period'])}</p>
    {_chart_sources(payload)}
  </div>
</div>

<p class="note">{_escape(payload.get('note', ''))}</p>
<div id="tip"></div>
<script>
// The panel draws its own tooltip.  A native SVG title only appears after
// the pointer has been still for about a second, which reads as no tooltip
// at all.  Nothing here is fetched; it is a dozen lines against the shapes
// already on the page.
(function () {{
  var tip = document.getElementById('tip');
  document.addEventListener('mousemove', function (event) {{
    var host = event.target.closest ? event.target.closest('[data-tip]') : null;
    if (!host) {{ tip.style.opacity = 0; return; }}
    var lines = host.getAttribute('data-tip').split('|');
    tip.innerHTML = '<b>' + lines[0] + '</b>' + lines.slice(1)
        .map(function (line) {{ return '<span>' + line + '</span>'; }}).join('');
    tip.style.opacity = 1;
    var box = tip.getBoundingClientRect();
    var x = event.clientX + 16, y = event.clientY + 16;
    if (x + box.width > window.innerWidth - 8) x = event.clientX - box.width - 16;
    if (y + box.height > window.innerHeight - 8) y = event.clientY - box.height - 16;
    tip.style.left = Math.max(8, x) + 'px';
    tip.style.top = Math.max(8, y) + 'px';
  }});
  document.addEventListener('mouseleave', function () {{ tip.style.opacity = 0; }});
}})();
</script>
</body></html>"""


def render_dashboard(df, precomputed, projection, period_label,
                     year_type='CY', dataset='Actual', departments=None,
                     scopes=None, coverage=''):
    """Draw the GHG dashboard."""
    payload = dash.dashboard_payload(
        df, precomputed, projection, period_label,
        departments=departments, scopes=scopes)

    if payload['cards']['Total']['value'] is None:
        st.info(f'No emissions recorded for {period_label}.')
        return

    payload['coverage'] = coverage
    payload['note'] = (
        'Scope 1 and Scope 2 come from the operations physicals under National '
        'Greenhouse Account factors.  Scope 3 is all fifteen GHG Protocol '
        'categories.  Recorded where the record reaches, budget beyond it.  '
        'Figures may not sum exactly due to rounding.')

    # The frame does not inherit the app's theme, so it is passed in.  A light
    # panel inside a dark app reads as a bug.
    try:
        payload['theme'] = ('dark' if st.get_option('theme.base') == 'dark'
                            else 'light')
    except Exception:
        payload['theme'] = 'light'

    # Tall enough that the wide layout does not scroll inside its own
    # frame.  A narrow window stacks the cards and scrolls, which is the
    # right behaviour on a small screen.
    #
    # Streamlit deprecates st.components.v1.html in favour of st.iframe, but
    # st.iframe takes a URL rather than markup, so it is not a replacement
    # for a page rendered in place.  This call stays until Streamlit offers
    # one that renders markup in a frame.  The frame matters: the panel
    # carries its own stylesheet with element selectors, which would reach
    # the whole application if it were rendered inline.
    components.html(_dashboard_html(payload), height=DASHBOARD_HEIGHT,
                    scrolling=True)
def render_ghg_tab(df, precomputed, projection,
                   start_date=None, end_date=None, period_label='',
                   end_mining_date=None, end_processing_date=None,
                   end_rehabilitation_date=None,
                   year_type='CY', display_year=None,
                   dataset='Actual', departments=None, scopes=None):
    """Render the GHG Emissions tab, all scopes.

    Args:
        df: Raw DataFrame from load_all_data() (for detail tables only)
        precomputed: PrecomputedData (for raw monthly data and Scope 3)
        projection: Annual data frame (selected by App.py)
        start_date/end_date: Display period dates
        period_label: Display label e.g. 'CY2025'
        end_*_date: Phase boundary dates (for chart markers)
        year_type/display_year: reporting basis, for the Scope 3 panel
    """

    _em_str = end_mining_date.strftime('%d %b %Y')
    _ep_str = end_processing_date.strftime('%d %b %Y')

    # The dashboard frame carries the heading and the coverage line, so
    # nothing is repeated above it.
    source_data = df[df['DataSet'] == 'Actual']
    coverage = ''
    if len(source_data) > 0:
        coverage = (f"{len(source_data):,} recorded rows to "
                    f"{source_data['Date'].max():%b %Y} \u00b7 mining ends "
                    f"{_em_str} \u00b7 processing ends {_ep_str}")

    # ── Dashboard ────────────────────────────────────────────────────
    render_dashboard(df, precomputed, projection, period_label,
                     year_type=year_type, dataset=dataset,
                     departments=departments, scopes=scopes,
                     coverage=coverage)

    st.markdown('---')

    # ── Detail, below the dashboard ──────────────────────────────────
    display_single_source(projection, df,
                          start_date=start_date, end_date=end_date,
                          period_label=period_label)

    # Scope 3 is one figure on this page.  Its composition, the method behind
    # each category and the audit trail sit underneath, closed, for the reader
    # who needs them.
    with st.expander("Scope 3 composition and method", expanded=False):
        render_scope3_panel(
            getattr(precomputed, 'scope3', None),
            year_type=year_type,
            display_year=display_year,
            period_label=period_label,
            error=getattr(precomputed, 'scope3_error', ''),
        )


def display_single_source(projection, df,
                          start_date=None, end_date=None, period_label=''):
    """Detail tables under the dashboard.

    The charts that used to sit here are gone: the dashboard above answers
    the same questions, in one place and in one visual language.  What is
    left is the tabular detail, for the reader who wants the numbers rather
    than the picture.
    """

    year_label = period_label

    if df is not None:
        with st.expander(f"\U0001f4cb Fuel Consumption Detail ({year_label})", expanded=False):
            raw_table = _build_raw_data_summary(df, start_date, end_date)
            if raw_table is not None:
                st.dataframe(raw_table, hide_index=True, width="stretch")
            else:
                st.info(f"No actual data for {year_label}")

    with st.expander("Emissions Data Table", expanded=False):
        _full = 'Scope3_Total' in projection.columns
        _columns = ['FY', 'Phase', 'ROM_Mt', 'Scope1', 'Scope2']
        _columns += (['Scope3_Total', 'Total_WithScope3'] if _full
                     else ['Scope3', 'Total'])

        display_df = projection[_columns].copy()
        display_df['ROM_Mt'] = display_df['ROM_Mt'].apply(lambda x: f"{x:.2f}")
        for _col in display_df.columns:
            if _col in ('FY', 'Phase', 'ROM_Mt'):
                continue
            display_df[_col] = display_df[_col].apply(lambda x: f"{x:,.0f}")

        display_df = display_df.rename(columns={
            'Scope3_Total': 'Scope3',
            'Total_WithScope3': 'Total',
        })

        st.dataframe(display_df, hide_index=True, width="stretch", height=400)

    if df is not None:
        with st.expander(f"\U0001f4e5 Monthly Emission Detail ({year_label})", expanded=False):
            detail_table = _build_monthly_detail(df, start_date, end_date)
            if detail_table is not None:
                st.dataframe(detail_table, hide_index=True, width="stretch", height=400)
            else:
                st.info(f"No emissions data for {year_label}")