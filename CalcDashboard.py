"""
CalcDashboard.py
Aggregations behind the GHG dashboard.

Last updated: 2026-09-02

Display only reads.  Every figure the GHG view shows is produced here and
arrives as a frame or a small record; the view formats and plots and derives
nothing.  CalcGhg.py is untouched: it builds the GHG Protocol frame, and this
module reads the result.

What the dashboard needs, and why each is here rather than in the view:

    headline()          the four scope cards, each against the same period a
                        year earlier, so a movement is stated rather than left
                        to the reader
    monthly_by_scope()  the month by month stack with the prior year total
                        beside it
    intensity()         the two intensity series and their movement
    breakdown()         department and cost centre, with the scope split and
                        each line's share of the period
"""

import numpy as np
import pandas as pd

from CalcUnits import TONNES_PER_MEGATONNE, KG_PER_TONNE
from CalcNga import dedupe_actual_over_budget as _dedupe
from Config import (DEFAULT_ACTUALS_TO_DATE, DEFAULT_FORECAST_FROM_DATE,
                    DEFAULT_GRID_CONNECTION_DATE,
                    DEFAULT_END_MINING_DATE, DEFAULT_END_PROCESSING_DATE,
                    DEFAULT_END_REHABILITATION_DATE,
                    MATERIALITY_THRESHOLD, CHART_MINIMUM_SHARE)

SCOPE_COLUMNS = ('Scope1', 'Scope2', 'Scope3')

# Scope 3 on the GHG view is the whole of Scope 3.  Where the frame carries
# the categories other than 3 they are added; where it does not, the column is
# Category 3 alone and the view says so.
SCOPE3_TOTAL = 'Scope3_Total'


def _year_number(label):
    """2026 from 'FY2026', 'CY2026' or a bare 2026."""
    digits = ''.join(character for character in str(label) if character.isdigit())
    return int(digits) if digits else None


def _prefix(label):
    """'CY' from 'CY2026'."""
    text = str(label)
    return ''.join(character for character in text if not character.isdigit())


def _scope3(row, columns):
    """The whole of Scope 3 for a row, whichever columns the frame carries."""
    if SCOPE3_TOTAL in columns:
        return float(row[SCOPE3_TOTAL])
    return float(row.get('Scope3', 0.0))


def _movement(current, prior):
    """Percentage movement, and None where there is nothing to compare with."""
    if prior is None or prior == 0 or not np.isfinite(prior):
        return None
    return (current - prior) / prior * 100.0


# ---------------------------------------------------------------------
# HEADLINE
# ---------------------------------------------------------------------

def headline(annual, period_label):
    """The four scope cards for one period, against the same period a year on.

    Returns a dict of records keyed 'Total', 'Scope 1', 'Scope 2', 'Scope 3',
    each carrying value, prior, movement and share of the total.  Returns None
    where the period is not in the frame.

    Movement is stated as the change against the prior period.  A fall in
    emissions is a negative movement and the view colours it accordingly; the
    sign is not flipped here, because a figure that reads one way in the data
    and another on the screen is how a chart lies.
    """
    if annual is None or annual.empty:
        return None

    label_column = 'FY' if 'FY' in annual.columns else 'Year'
    labels = annual[label_column].astype(str)

    row = annual[labels == str(period_label)]
    if row.empty:
        return None
    row = row.iloc[0]

    year = _year_number(period_label)
    prior_label = f'{_prefix(period_label)}{year - 1}' if year else None
    prior_rows = annual[labels == str(prior_label)] if prior_label else annual.iloc[0:0]
    prior = prior_rows.iloc[0] if not prior_rows.empty else None

    columns = set(annual.columns)
    values = {
        'Scope 1': float(row.get('Scope1', 0.0)),
        'Scope 2': float(row.get('Scope2', 0.0)),
        'Scope 3': _scope3(row, columns),
    }
    values['Total'] = sum(values.values())

    if prior is not None:
        priors = {
            'Scope 1': float(prior.get('Scope1', 0.0)),
            'Scope 2': float(prior.get('Scope2', 0.0)),
            'Scope 3': _scope3(prior, columns),
        }
        priors['Total'] = sum(priors.values())
    else:
        priors = {name: None for name in values}

    total = values['Total']
    return {
        name: {
            'value': values[name],
            'prior': priors[name],
            'prior_label': prior_label if prior is not None else None,
            'movement': _movement(values[name], priors[name]),
            'share': (values[name] / total * 100.0) if total else 0.0,
        }
        for name in ('Total', 'Scope 1', 'Scope 2', 'Scope 3')
    }


# ---------------------------------------------------------------------
# MONTHLY BY SCOPE
# ---------------------------------------------------------------------

def _period_bounds(period_label):
    """First and last month of a reporting period, from its label."""
    year = _year_number(period_label)
    if year is None:
        return None, None
    if _prefix(period_label).upper() == 'FY':
        return (pd.Timestamp(year=year - 1, month=7, day=1),
                pd.Timestamp(year=year, month=6, day=1))
    return (pd.Timestamp(year=year, month=1, day=1),
            pd.Timestamp(year=year, month=12, day=1))


def monthly_by_scope(monthly, period_label, scope3_monthly=None):
    """Month by month emissions by scope, with the prior year total beside it.

    Args:
        monthly:        the monthly projection frame
        period_label:   'CY2026' or 'FY2026'
        scope3_monthly: optional Series of the Scope 3 categories other than
                        3, indexed by month, added to the Scope 3 column

    Returns a frame with one row per month of the period:
        Month, MonthLabel, Scope1, Scope2, Scope3, Total, PriorTotal
    """
    columns = ['Month', 'MonthLabel', 'Scope1', 'Scope2', 'Scope3',
               'Total', 'PriorTotal']
    if monthly is None or monthly.empty:
        return pd.DataFrame(columns=columns)

    start, end = _period_bounds(period_label)
    if start is None:
        return pd.DataFrame(columns=columns)

    def _window(first, last):
        rows = monthly[(monthly['Date'] >= first) & (monthly['Date'] <= last)].copy()
        if rows.empty:
            return rows
        rows = rows[['Date', 'Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']]
        rows.columns = ['Date', 'Scope1', 'Scope2', 'Scope3']
        if scope3_monthly is not None:
            extra = rows['Date'].map(scope3_monthly).fillna(0.0)
            rows['Scope3'] = rows['Scope3'] + extra.values
        rows['Total'] = rows[['Scope1', 'Scope2', 'Scope3']].sum(axis=1)
        return rows

    current = _window(start, end)
    if current.empty:
        return pd.DataFrame(columns=columns)

    prior = _window(start - pd.DateOffset(years=1), end - pd.DateOffset(years=1))

    # The prior year is matched month position by month position, so July
    # sits against July on a financial year and January against January on a
    # calendar year.  Matching on the date itself would leave the line blank
    # in a period the record does not reach.
    current = current.reset_index(drop=True)
    prior_total = (prior['Total'].reset_index(drop=True)
                   if not prior.empty else pd.Series(dtype=float))
    current['PriorTotal'] = prior_total.reindex(range(len(current))).values

    current['Month'] = current['Date']
    current['MonthLabel'] = current['Date'].dt.strftime('%b')
    return current[columns]


def scope3_monthly_other(scope3_result):
    """Monthly total of the Scope 3 categories other than 3, indexed by month.

    Returns None where the result is absent, so the caller charts Category 3
    alone and the view says so.
    """
    if scope3_result is None or scope3_result.detail.empty:
        return None
    detail = scope3_result.detail
    other = detail[detail['Category'] != 3]
    if other.empty:
        return None
    return other.groupby('Date')['tCO2e'].sum()


# ---------------------------------------------------------------------
# INTENSITY
# ---------------------------------------------------------------------

def intensity(monthly, period_label, scope3_monthly=None):
    """The two intensity series for a period, with their movement.

    Per ounce of gold sold and per tonne of run of mine ore, on the whole
    inventory.  A month with no denominator carries no ratio rather than a
    spike, and the headline is the period total over the period denominator,
    not the mean of the monthly ratios: the two differ whenever production
    varies, and only the first is the intensity of the period.

    Returns a dict with 'gold' and 'rom', each carrying series, headline,
    prior and movement.
    """
    empty = {'series': pd.DataFrame(columns=['Month', 'MonthLabel', 'Value']),
             'headline': None, 'prior': None, 'movement': None, 'unit': ''}
    if monthly is None or monthly.empty:
        return {'gold': dict(empty), 'rom': dict(empty)}

    start, end = _period_bounds(period_label)
    if start is None:
        return {'gold': dict(empty), 'rom': dict(empty)}

    def _totals(first, last):
        rows = monthly[(monthly['Date'] >= first) & (monthly['Date'] <= last)].copy()
        if rows.empty:
            return None
        emissions = rows[['Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e']].sum(axis=1)
        if scope3_monthly is not None:
            emissions = emissions + rows['Date'].map(scope3_monthly).fillna(0.0).values
        rows = rows.assign(_emissions=emissions)
        return rows

    current = _totals(start, end)
    if current is None:
        return {'gold': dict(empty), 'rom': dict(empty)}
    prior = _totals(start - pd.DateOffset(years=1), end - pd.DateOffset(years=1))

    def _build(denominator_column, scale, unit, places):
        series = current[['Date', '_emissions', denominator_column]].copy()
        series['Value'] = np.where(
            series[denominator_column] > 0,
            series['_emissions'] / series[denominator_column] * scale,
            np.nan)
        out = pd.DataFrame({
            'Month': series['Date'],
            'MonthLabel': series['Date'].dt.strftime('%b'),
            'Value': series['Value'],
        })

        def _period_ratio(frame):
            if frame is None:
                return None
            denominator = float(frame[denominator_column].sum())
            if denominator <= 0:
                return None
            return float(frame['_emissions'].sum()) / denominator * scale

        head = _period_ratio(current)
        was = _period_ratio(prior)
        return {'series': out, 'headline': head, 'prior': was,
                'movement': _movement(head, was) if head is not None else None,
                'unit': unit, 'places': places}

    return {
        # Tonnes per ounce reads at two decimals; kilograms per tonne of ore
        # is the readable scale for the ore series.
        'gold': _build('Gold_oz', 1.0, 't CO2-e/oz Au', 2),
        'rom': _build('ROM_t', 1000.0, 'kg CO2-e/t ROM', 1),
    }


# ---------------------------------------------------------------------
# DEPARTMENT AND COST CENTRE
# ---------------------------------------------------------------------

def dedupe_actual_over_budget(frame):
    """Drop budget rows superseded by an actual on the same month and line.

    The same rule the projection uses.  Without it a period that is part
    recorded and part forecast is counted twice on one view and once on
    another, and the breakdown stops adding to the headline.
    """
    return _dedupe(frame)


def _period_mask(frame, period_label):
    start, end = _period_bounds(period_label)
    if start is None:
        return pd.Series(True, index=frame.index)
    return (frame['Date'] >= start) & (frame['Date'] <= end)


def breakdown(df, period_label, dataset=None, departments=None,
              scopes=None, scope3_rows=None):
    """Emissions by department and cost centre for one period.

    Args:
        df:            the transaction frame from load_all_data()
        period_label:  'CY2026' or 'FY2026'
        dataset:       'Actual', 'Budget', or None for both
        departments:   iterable to keep, or None for all
        scopes:        iterable of 'Scope 1', 'Scope 2', 'Scope 3', or None
        scope3_rows:   optional Scope 3 detail, so the categories other than 3
                       reach the breakdown

    Returns (departments, cost_centres), two frames each carrying Department,
    CostCentre where it applies, Scope1, Scope2, Scope3, Total and Share.
    Sorted largest first, which is the order a reader wants: the lines that
    carry the result, then the tail.
    """
    columns = ['Department', 'CostCentre', 'Scope1', 'Scope2', 'Scope3',
               'Total', 'Share']
    if df is None or df.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=columns)

    rows = dedupe_actual_over_budget(df[_period_mask(df, period_label)])
    if departments:
        rows = rows[rows['Department'].astype(str).isin(list(departments))]
    if rows.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=columns)

    work = pd.DataFrame({
        # A row with no department is named for what it is rather than left
        # as the string 'nan', which reads as a fault in the model.
        'Department': rows['Department'].astype(str).replace(
            {'nan': 'Unallocated', '': 'Unallocated', 'None': 'Unallocated'}),
        'CostCentre': rows['CostCentre'].astype(str).replace(
            {'nan': '', 'None': ''}),
        'Scope1': rows['Scope1_tCO2e'].astype(float),
        'Scope2': rows['Scope2_tCO2e'].astype(float),
        'Scope3': rows['Scope3_tCO2e'].astype(float),
    })

    # The Scope 3 categories other than 3 are computed on their own frame and
    # carry the department and cost centre of the line they came from, so they
    # join the breakdown rather than sitting outside it.
    if scope3_rows is not None and not scope3_rows.empty:
        extra = scope3_rows[scope3_rows['Category'] != 3]
        extra = extra[_period_mask(extra, period_label)]
        if not extra.empty and 'Department' in extra.columns:
            addition = pd.DataFrame({
                'Department': extra['Department'].astype(str).replace(
                    {'nan': 'Unallocated', '': 'Unallocated',
                     'None': 'Unallocated'}),
                'CostCentre': extra['CostCentre'].astype(str).replace(
                    {'nan': '', 'None': ''}),
                'Scope1': 0.0, 'Scope2': 0.0,
                'Scope3': extra['tCO2e'].astype(float),
            })
            if departments:
                addition = addition[addition['Department'].isin(list(departments))]
            work = pd.concat([work, addition], ignore_index=True)

    if scopes:
        keep = set(scopes)
        for name, column in (('Scope 1', 'Scope1'), ('Scope 2', 'Scope2'),
                             ('Scope 3', 'Scope3')):
            if name not in keep:
                work[column] = 0.0

    def _shape(frame, keys):
        grouped = frame.groupby(keys, observed=True)[
            ['Scope1', 'Scope2', 'Scope3']].sum().reset_index()
        grouped['Total'] = grouped[['Scope1', 'Scope2', 'Scope3']].sum(axis=1)
        # The share is of the whole period total.  Lines below the chart
        # minimum are then left off: they are clutter on a chart, and the
        # total they belong to is unchanged by not drawing them.
        grand = float(grouped['Total'].sum())
        grouped['Share'] = grouped['Total'] / grand * 100.0 if grand else 0.0
        grouped = grouped[grouped['Share'].abs() >= CHART_MINIMUM_SHARE * 100.0]
        if 'CostCentre' not in grouped.columns:
            grouped['CostCentre'] = ''
        return grouped[columns].sort_values('Total', ascending=False).reset_index(drop=True)

    return _shape(work, ['Department']), _shape(work, ['Department', 'CostCentre'])


def filter_options(df):
    """The values the global filters offer, from the data itself."""
    if df is None or df.empty:
        return {'departments': [], 'datasets': []}
    return {
        'departments': sorted(d for d in df['Department'].astype(str).unique() if d),
        'datasets': sorted(df['DataSet'].astype(str).unique()),
    }


# ---------------------------------------------------------------------
# PAYLOAD
# ---------------------------------------------------------------------
# The dashboard renders as one page rather than a stack of framework widgets,
# so it needs its figures as plain data.  Everything below is JSON ready:
# numbers, strings and lists, nothing that has to be formatted by the caller.

def _clean(value, places=1):
    """A finite float rounded, or None."""
    if value is None:
        return None
    value = float(value)
    if not np.isfinite(value):
        return None
    return round(value, places)


def dashboard_payload(df, precomputed, annual, period_label,
                      departments=None, scopes=None):
    """Everything the GHG dashboard draws, as plain data.

    Args:
        df:            the transaction frame
        precomputed:   PrecomputedData, for the monthly projection and Scope 3
        annual:        the annual GHG frame for the basis in force
        period_label:  'CY2026'
        departments:   iterable to keep, or None
        scopes:        iterable of scope names to keep, or None

    Returns a dict with keys: period, cards, months, series, prior,
    intensity, tree, note.
    """
    scope3_monthly = scope3_monthly_other(getattr(precomputed, 'scope3', None))
    scope3_rows = (precomputed.scope3.detail
                   if getattr(precomputed, 'scope3', None) is not None else None)

    cards = headline(annual, period_label) or {}
    # The GHG monthly projection, never the NGER one: the monthly series and
    # the intensities must carry the same Scope 1 as the cards beside them,
    # which includes explosives.
    ghg_monthly = precomputed.ghg_monthly
    trend = monthly_by_scope(ghg_monthly, period_label, scope3_monthly)
    measures = intensity(ghg_monthly, period_label, scope3_monthly)
    department_totals, centre_totals = breakdown(
        df, period_label, departments=departments,
        scopes=scopes, scope3_rows=scope3_rows)

    def _card(name):
        record = cards.get(name)
        if record is None:
            return {'value': None, 'movement': None, 'prior_label': None,
                    'share': None}
        return {
            'value': _clean(record['value'], 0),
            'movement': _clean(record['movement'], 1),
            'prior_label': record['prior_label'],
            'share': _clean(record['share'], 0),
        }

    def _measure(key):
        record = measures[key]
        series = record['series']
        return {
            'headline': _clean(record['headline'], record.get('places', 2)),
            'prior': _clean(record['prior'], record.get('places', 2)),
            'movement': _clean(record['movement'], 1),
            'unit': record['unit'],
            'places': record.get('places', 2),
            'values': [None if pd.isna(v) else round(float(v), 4)
                       for v in series['Value']] if not series.empty else [],
            'labels': list(series['MonthLabel']) if not series.empty else [],
        }

    # The tree is one flat list, each row carrying its depth, so the view
    # renders it without knowing the shape of the data.
    grand = float(department_totals['Total'].sum()) if not department_totals.empty else 0.0
    largest = float(department_totals['Total'].max()) if not department_totals.empty else 0.0
    tree = []
    for index, row in department_totals.iterrows():
        name = row['Department']
        # A department with nothing against it adds a line and no reading, so
        # it is left off the breakdown entirely.
        if not (float(row['Total'] or 0.0) > 0):
            continue
        children = centre_totals[
            (centre_totals['Department'] == name)
            & (centre_totals['Total'].astype(float) > 0)]
        tree.append({
            'key': f'g{index}',
            'depth': 0,
            'label': name,
            'scope1': _clean(row['Scope1'], 0),
            'scope2': _clean(row['Scope2'], 0),
            'scope3': _clean(row['Scope3'], 0),
            'total': _clean(row['Total'], 0),
            'share': _clean(row['Share'], 1),
            'children': int(len(children)),
        })
        for _, child in children.iterrows():
            tree.append({
                'key': f'g{index}',
                'depth': 1,
                'label': child['CostCentre'] or 'Unallocated',
                'scope1': _clean(child['Scope1'], 0),
                'scope2': _clean(child['Scope2'], 0),
                'scope3': _clean(child['Scope3'], 0),
                'total': _clean(child['Total'], 0),
                'share': _clean(child['Share'], 1),
                'children': 0,
            })

    sources = by_source(df, period_label, departments=departments,
                        scopes=scopes, scope3_rows=scope3_rows)
    centres = cost_centre_ranked(df, period_label, departments=departments,
                                 scopes=scopes, scope3_rows=scope3_rows)

    # Life of mine.  Unfiltered by period on purpose: the point of the view is
    # the whole plan, and a year filter would leave one bar standing.
    years = annual_by_scope(annual, actuals_to=DEFAULT_ACTUALS_TO_DATE)
    lifecycle = lifecycle_by_scope(annual, actuals_to=DEFAULT_ACTUALS_TO_DATE)
    marks = milestone_marks(years, [
        ('Grid connection', DEFAULT_GRID_CONNECTION_DATE),
        ('End of mining', DEFAULT_END_MINING_DATE),
        ('End of processing', DEFAULT_END_PROCESSING_DATE),
        ('End of rehabilitation', DEFAULT_END_REHABILITATION_DATE),
    ])

    return {
        'period': period_label,
        'years': [
            {'label': r['label'], 'year': r['year'], 'phase': r['phase'],
             'basis': r['basis'],
             'scope1': _clean(r['scope1'], 0), 'scope2': _clean(r['scope2'], 0),
             'scope3': _clean(r['scope3'], 0), 'total': _clean(r['total'], 0),
             'rom_mt': _clean(r['rom_mt'], 2), 'gold_oz': _clean(r['gold_oz'], 0)}
            for r in years
        ],
        'bands': phase_bands(years),
        # Where the record stops and the forecast starts, on the year axis.
        'forecast_from': (milestone_marks(
            years, [('Forecast from', DEFAULT_FORECAST_FROM_DATE)]) or [None])[0],
        'intensity_years': [
            {'label': r['label'], 'year': r['year'], 'basis': r['basis'],
             'gold': _clean(r['gold'], 3), 'rom': _clean(r['rom'], 2)}
            for r in intensity_by_year(
                annual,
                actuals_to=DEFAULT_ACTUALS_TO_DATE,
                last_mining=DEFAULT_END_MINING_DATE,
                last_processing=DEFAULT_END_PROCESSING_DATE)
        ],
        'marks': marks,
        'lifecycle': [
            {'label': r['label'], 'years': r['years'],
             'scope1': _clean(r['scope1'], 0), 'scope2': _clean(r['scope2'], 0),
             'scope3': _clean(r['scope3'], 0), 'total': _clean(r['total'], 0)}
            for r in lifecycle
        ],
        'cards': {name: _card(name) for name in
                  ('Total', 'Scope 1', 'Scope 2', 'Scope 3')},
        'sources': [
            {'label': str(row['Label']),
             'total': _clean(row['Total'], 0),
             'share': _clean(row['Share'], 1)}
            for _, row in sources.iterrows()
        ],
        'departments': [
            {'label': str(row['Department']),
             'scope1': _clean(row['Scope1'], 0),
             'scope2': _clean(row['Scope2'], 0),
             'scope3': _clean(row['Scope3'], 0),
             'total': _clean(row['Total'], 0),
             'share': _clean(row['Share'], 1)}
            for _, row in department_totals.head(8).iterrows()
        ],
        'cost_centres': [
            {'label': str(row['CostCentre']) or 'Unallocated',
             'department': str(row['Department']),
             'total': _clean(row['Total'], 0),
             'share': _clean(row['Share'], 1),
             'movement': _clean(row['Movement'], 1)}
            for _, row in centres.iterrows()
        ],
        'months': list(trend['MonthLabel']) if not trend.empty else [],
        'series': {
            'scope1': [round(float(v), 1) for v in trend['Scope1']] if not trend.empty else [],
            'scope2': [round(float(v), 1) for v in trend['Scope2']] if not trend.empty else [],
            'scope3': [round(float(v), 1) for v in trend['Scope3']] if not trend.empty else [],
        },
        'prior': ([None if pd.isna(v) else round(float(v), 1)
                   for v in trend['PriorTotal']] if not trend.empty else []),
        'intensity': {'gold': _measure('gold'), 'rom': _measure('rom')},
        'tree': tree,
        'tree_scale': _clean(largest, 0) or 1.0,
        'tree_total': _clean(grand, 0),
    }


# ---------------------------------------------------------------------
# LIFE OF MINE
# ---------------------------------------------------------------------
# The month is the wrong grain for a mine that runs to 2049.  These two
# aggregations put the whole plan on one axis: every year of it, and the
# same emissions collected into the phases the plan is built around.

PHASE_ORDER = ('Mining', 'Processing', 'Rehabilitation', 'Closed')


def _scope_columns(frame):
    """Scope columns to read, preferring the Scope 3 inclusive totals."""
    scope3 = ('Scope3_Total' if 'Scope3_Total' in frame.columns
              else 'Scope3' if 'Scope3' in frame.columns else None)
    return 'Scope1', 'Scope2', scope3


def annual_by_scope(annual, actuals_to=None):
    """Every year of the projection, stacked by scope.

    Each year carries the phase it sits in and whether it is recorded or
    forecast, so the view can shade the plan behind the bars.
    """
    if annual is None or annual.empty:
        return []

    label_column = 'FY' if 'FY' in annual.columns else 'Year'
    s1, s2, s3 = _scope_columns(annual)
    cutoff = pd.Timestamp(actuals_to) if actuals_to is not None else None

    rows = []
    for _, row in annual.iterrows():
        label = str(row[label_column])
        year = _year_number(label)
        date = row['Date'] if 'Date' in annual.columns else None
        if cutoff is None or date is None:
            basis = 'Recorded'
        elif pd.Timestamp(date) > cutoff:
            basis = 'Forecast'
        else:
            # A year the record does not cover in full is part recorded.
            year_end = pd.Timestamp(date) + pd.offsets.DateOffset(years=1) \
                - pd.Timedelta(days=1)
            basis = 'Recorded' if year_end <= cutoff else 'Part recorded'
        scope3 = float(row.get(s3, 0.0) or 0.0) if s3 else 0.0
        rows.append({
            'label': label,
            'year': year,
            'phase': str(row.get('Phase', '') or ''),
            'basis': basis,
            'scope1': float(row.get(s1, 0.0) or 0.0),
            'scope2': float(row.get(s2, 0.0) or 0.0),
            'scope3': scope3,
            'rom_mt': float(row.get('ROM_Mt', 0.0) or 0.0),
            'gold_oz': float(row.get('Gold_oz', 0.0) or 0.0),
        })
    for record in rows:
        record['total'] = (record['scope1'] + record['scope2']
                           + record['scope3'])
    # A year carrying nothing is a gap in the plan, not a reading of nil, so
    # it is dropped rather than drawn as an empty slot on the axis.
    return [record for record in rows if record['total'] > 0]


def phase_bands(years):
    """Contiguous runs of one phase, as index spans into the year list.

    Returned as spans rather than a label per year so the view draws one
    shaded block per phase instead of a band behind every bar.
    """
    bands = []
    for index, record in enumerate(years):
        phase = record['phase']
        if not phase:
            continue
        if bands and bands[-1]['phase'] == phase:
            bands[-1]['end'] = index
            continue
        bands.append({'phase': phase, 'start': index, 'end': index})
    return bands


def milestone_marks(years, milestones):
    """Milestone dates placed on the year axis.

    A milestone outside the plotted range is dropped rather than pinned to
    an end, because a marker on the wrong year is worse than no marker.
    """
    if not years or not milestones:
        return []
    first = years[0]['year']
    last = years[-1]['year']
    marks = []
    for label, value in milestones:
        if value is None:
            continue
        stamp = pd.Timestamp(value)
        if first is None or last is None:
            continue
        if not (first <= stamp.year <= last):
            continue
        # Position is fractional: a milestone in July sits mid year.
        position = (stamp.year - first) + (stamp.month - 1) / 12.0
        marks.append({'label': label, 'position': position,
                      'date': stamp.strftime('%b %Y')})
    return marks


def intensity_by_year(annual, actuals_to=None, last_mining=None,
                      last_processing=None):
    """Both intensity measures across the plan, one point per year.

    Same basis as the headline cards: every scope over the denominator for
    the year, not the mean of the monthly ratios.  A year with no gold or no
    ore carries no ratio rather than a spike, so the line breaks where the
    plan stops producing instead of running along the axis.

    Mining winds down over its closing year: ore falls away while a full year
    of emissions continues, so that year returns a ratio which reads as a
    collapse in performance and is nothing of the kind.  The ore series
    therefore stops at the last full year of mining.

    Processing does not have the same problem, because gold keeps being poured
    from stockpile to the end.  The gold series runs to the end of processing,
    which is where the plan itself ends.
    """
    years = annual_by_scope(annual, actuals_to=actuals_to)
    mining_cut = pd.Timestamp(last_mining).year if last_mining else None
    processing_cut = (pd.Timestamp(last_processing).year
                      if last_processing else None)
    rows = []
    for record in years:
        year = record['year']
        rom_t = record['rom_mt'] * TONNES_PER_MEGATONNE
        gold_oz = record['gold_oz']
        rom_open = mining_cut is None or year is None or year < mining_cut
        gold_open = (processing_cut is None or year is None
                     or year <= processing_cut)
        rows.append({
            'label': record['label'],
            'year': year,
            'basis': record['basis'],
            # Tonnes per ounce, and kilograms per tonne of ore.
            'gold': (record['total'] / gold_oz)
                    if gold_oz > 0 and gold_open else None,
            'rom': (record['total'] / rom_t * KG_PER_TONNE)
                   if rom_t > 0 and rom_open else None,
        })
    return rows


def lifecycle_by_scope(annual, actuals_to=None):
    """Emissions collected into plan phases, plus the life of mine total.

    One bar per phase and one for the whole plan, each stacked by scope, so
    the reader can see where in the life of the mine the emissions sit.
    """
    years = annual_by_scope(annual, actuals_to=actuals_to)
    if not years:
        return []

    collected = {}
    for record in years:
        phase = record['phase'] or 'Unphased'
        bucket = collected.setdefault(
            phase, {'label': phase, 'scope1': 0.0, 'scope2': 0.0,
                    'scope3': 0.0, 'years': 0})
        for key in ('scope1', 'scope2', 'scope3'):
            bucket[key] += record[key]
        bucket['years'] += 1

    ordered = [collected[name] for name in PHASE_ORDER if name in collected]
    ordered += [collected[name] for name in sorted(collected)
                if name not in PHASE_ORDER]

    total = {'label': 'Life of mine', 'years': len(years),
             'scope1': sum(r['scope1'] for r in years),
             'scope2': sum(r['scope2'] for r in years),
             'scope3': sum(r['scope3'] for r in years)}
    ordered.append(total)

    for bucket in ordered:
        bucket['total'] = (bucket['scope1'] + bucket['scope2']
                           + bucket['scope3'])
    return [bucket for bucket in ordered if bucket['total'] > 0]


# ---------------------------------------------------------------------
# SOURCES AND RANKED COST CENTRES
# ---------------------------------------------------------------------

def _emissions_frame(df, period_label, dataset=None, departments=None,
                     scopes=None, scope3_rows=None):
    """Rows for a period with a single Total column, scope filter applied."""
    rows = dedupe_actual_over_budget(df[_period_mask(df, period_label)])
    if departments:
        rows = rows[rows['Department'].astype(str).isin(list(departments))]
    if rows.empty:
        return pd.DataFrame(columns=['Label', 'Department', 'CostCentre', 'Total'])

    keep = set(scopes) if scopes else {'Scope 1', 'Scope 2', 'Scope 3'}
    total = 0.0
    if 'Scope 1' in keep:
        total = total + rows['Scope1_tCO2e'].astype(float)
    if 'Scope 2' in keep:
        total = total + rows['Scope2_tCO2e'].astype(float)
    if 'Scope 3' in keep:
        total = total + rows['Scope3_tCO2e'].astype(float)

    work = pd.DataFrame({
        # A line with no common name is named by its activity, which is always
        # present, so nothing lands in an unlabelled bucket.
        'Label': rows['CommonName'].astype(str).where(
            rows['CommonName'].astype(str) != '', rows['Activity'].astype(str)),
        'Department': rows['Department'].astype(str),
        'CostCentre': rows['CostCentre'].astype(str),
        'Total': total if not isinstance(total, float) else 0.0,
    })

    if scope3_rows is not None and not scope3_rows.empty and 'Scope 3' in keep:
        extra = scope3_rows[scope3_rows['Category'] != 3]
        extra = extra[_period_mask(extra, period_label)]
        if not extra.empty:
            addition = pd.DataFrame({
                'Label': extra['CategoryName'].astype(str),
                'Department': extra['Department'].astype(str),
                'CostCentre': extra['CostCentre'].astype(str),
                'Total': extra['tCO2e'].astype(float),
            })
            if departments:
                addition = addition[addition['Department'].isin(list(departments))]
            work = pd.concat([work, addition], ignore_index=True)

    return work


def by_source(df, period_label, top=7, **kwargs):
    """The largest emission sources for a period, with a remainder.

    Named by common name, which is what the line is: diesel, grid electricity,
    explosives.  Everything below the cut becomes one Other row rather than a
    long tail nobody reads.
    """
    work = _emissions_frame(df, period_label, **kwargs)
    if work.empty:
        return pd.DataFrame(columns=['Label', 'Total', 'Share'])

    grouped = work.groupby('Label', observed=True)['Total'].sum().reset_index()
    grouped = grouped[grouped['Total'] > 0].sort_values('Total', ascending=False)
    if grouped.empty:
        return pd.DataFrame(columns=['Label', 'Total', 'Share'])

    head = grouped.head(top).copy()
    tail = grouped.iloc[top:]
    if not tail.empty:
        head = pd.concat([head, pd.DataFrame([{
            'Label': f'Other, {len(tail)} sources',
            'Total': float(tail['Total'].sum()),
        }])], ignore_index=True)

    grand = float(grouped['Total'].sum())
    head['Share'] = head['Total'] / grand * 100.0 if grand else 0.0
    return head.reset_index(drop=True)


def cost_centre_ranked(df, period_label, top=10, **kwargs):
    """The largest cost centres for a period, with movement on the prior year."""
    columns = ['CostCentre', 'Department', 'Total', 'Share', 'Movement']
    work = _emissions_frame(df, period_label, **kwargs)
    if work.empty:
        return pd.DataFrame(columns=columns)

    grouped = work.groupby(['CostCentre', 'Department'],
                           observed=True)['Total'].sum().reset_index()
    grouped = grouped[grouped['Total'] > 0].sort_values('Total', ascending=False)
    if grouped.empty:
        return pd.DataFrame(columns=columns)

    grand = float(grouped['Total'].sum())
    grouped['Share'] = grouped['Total'] / grand * 100.0 if grand else 0.0

    year = _year_number(period_label)
    prior_label = f'{_prefix(period_label)}{year - 1}' if year else None
    prior = (_emissions_frame(df, prior_label, **kwargs)
             if prior_label else pd.DataFrame())
    if not prior.empty:
        prior_totals = prior.groupby('CostCentre', observed=True)['Total'].sum()
        grouped['Prior'] = grouped['CostCentre'].map(prior_totals)
        prior_values = grouped['Prior'].fillna(0)
        material = prior_values > (grouped['Total'].abs()
                                   * MATERIALITY_THRESHOLD)
        grouped['Movement'] = np.where(
            material,
            (grouped['Total'] - prior_values) / prior_values.replace(0, np.nan) * 100.0,
            np.nan)
    else:
        grouped['Movement'] = np.nan

    return grouped.head(top)[columns].reset_index(drop=True)
