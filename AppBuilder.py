"""Emissions Data Builder.

A separate application, not a reporting tab.  The reporting application reads
what this one publishes.

The division of labour is the point.  PrepData prepares operational data every
consumer needs.  This Builder owns the emissions question: which factor
applies, what a capital good is, what the assumptions are, and when a figure
becomes the published one.  The reporting application then filters,
aggregates and presents a dataset that somebody decided to publish, rather
than one that changes whenever an input file moves underneath it.

Run it beside the reporting application:

    streamlit run AppBuilder.py --server.port 8502
"""

import io
import os
from datetime import datetime

import pandas as pd
import streamlit as st

import CalcGhgCategoryStatus as Status
import CalcProduction as Production
import CalcImport as Import
import LoaderImport as Importer
import ConfigEdit
import ExportEmissionsTable as Publisher
import LoaderCapital
import LoaderFactorTable as FactorTable
import LoaderItems as Items
import LoaderLookups as Lookups
from CalcEmissionsTable import build_emissions_table, reconcile
from CalcPrecompute import precompute_all
from Config import (CREDIT_START_DATE, DECLINE_RATE_PHASE2,
                    DEFAULT_ACTUALS_TO_DATE, DEFAULT_END_MINING_DATE,
                    DEFAULT_END_PROCESSING_DATE,
                    DEFAULT_END_REHABILITATION_DATE, DEFAULT_START_DATE,
                    FSEI_ELEC, FSEI_ROM, MILESTONE_SOURCE)
from LoaderData import load_all_data, load_smc_transactions
from LoaderReference import CONFIG_PATH, load_reference

st.set_page_config(page_title='Emissions Data Builder', layout='wide',
                   page_icon='⚙️')

from Paths import DATA_DIR
SMC_PATH = os.path.join(DATA_DIR, 'SmcTransactions.csv')

TRACKED_INPUTS = [
    os.path.join(DATA_DIR, name) for name in (
        'OperationsMetricsActual.csv', 'OperationsMetricsBudget.csv',
        'NgaFactors.csv', 'ReferenceFx.csv', 'LOM.yaml')
] + [CONFIG_PATH, LoaderCapital.REGISTER_PATH,
     FactorTable.FACTORS_PATH, Items.ITEMS_PATH, Lookups.LOOKUPS_PATH]


# ---------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------
# Cached so a page change does not rebuild the inventory.  The cache is
# cleared explicitly when an assumption or a register changes, because that
# is exactly when the answer should change and not before.

@st.cache_data(show_spinner='Loading operational data...')
def _load(passphrase=None):
    return load_all_data(passphrase=passphrase)


@st.cache_resource(show_spinner='Calculating inventory...')
def _precompute(_df, token):
    return precompute_all(
        _df, fsei_rom=FSEI_ROM, fsei_elec=FSEI_ELEC,
        start_date=DEFAULT_START_DATE,
        end_date=DEFAULT_END_REHABILITATION_DATE,
        end_mining_date=DEFAULT_END_MINING_DATE,
        end_processing_date=DEFAULT_END_PROCESSING_DATE,
        end_rehabilitation_date=DEFAULT_END_REHABILITATION_DATE,
        credit_start_date=CREDIT_START_DATE,
        decline_rate_phase2=DECLINE_RATE_PHASE2)


def _stamp():
    """Fingerprint of the emissions-owned inputs."""
    parts = []
    for path in (CONFIG_PATH, LoaderCapital.REGISTER_PATH,
                 FactorTable.FACTORS_PATH, Items.ITEMS_PATH,
                 Lookups.LOOKUPS_PATH):
        parts.append(str(os.path.getmtime(path))
                     if os.path.exists(path) else '-')
    return '|'.join(parts)


# The build is held against a token, not against the inputs.  An edit does
# not silently move the figures somebody is reading: it marks the build stale
# and says so, and the build changes when Rebuild is pressed and at no other
# time.  Half a minute of projection is not something to spend on a
# keystroke, and a figure that changes underneath a reader is worse than an
# old one that says it is old.

def _token():
    return st.session_state.get('build_token', 0)


def _stale():
    """Whether the inputs have moved since the build on screen was made."""
    built = st.session_state.get('built_stamp')
    return built is not None and built != _stamp()


def _rebuild():
    """Mark the build stale.  Called wherever an input is saved.

    It does not rebuild.  The saved figure is on disk and will be picked up
    by the next build; until then the screen keeps showing the build it was
    showing, and the sidebar says so.
    """
    for key in ('pending_ok', 'pending_outstanding', 'pending_assumptions',
                'confirm_publish'):
        st.session_state.pop(key, None)


def _force_rebuild():
    """Rebuild now.  The only thing that changes what is on screen."""
    _load.clear()
    _precompute.clear()
    _build.clear()
    _published.clear()
    st.session_state['build_token'] = _token() + 1
    st.session_state['built_stamp'] = _stamp()
    # The baseline is not touched.  A rebuild is how an edit reaches the
    # figures, so it is the thing this session's comparison is measuring.
    for key in ('pending_ok', 'pending_outstanding', 'pending_assumptions',
                'confirm_publish'):
        st.session_state.pop(key, None)


@st.cache_data(show_spinner='Reading the published build...')
def _published(stamp):
    """What is on the record.  A file read, not a projection."""
    return Publisher.load_published()


def _published_stamp():
    path = Publisher.FAST_PATH if os.path.exists(Publisher.FAST_PATH) \
        else Publisher.TABLE_PATH
    return str(os.path.getmtime(path)) if os.path.exists(path) else '-'


# The table was being rebuilt on every page change.  Loading and projecting
# were already cached, so the eight hundred thousand row build was the whole
# of the wait, paid again for every click that only wanted to group what it
# had already produced.  Cached against the build token, so it is computed
# once and every page after that reads it.
@st.cache_resource(show_spinner='Building the inventory...')
def _build(_precomputed, token):
    return build_emissions_table(_precomputed, _precomputed.ghg_df)


def _summarise(table):
    """The build in a few hundred rows, for comparing one against another.

    Held instead of the build itself, because the question a comparison
    answers is by year and by scope and the eight hundred thousand lines
    underneath it are not part of the answer.
    """
    rows = table[table['RowKind'] == 'Emission']
    return (rows.groupby(['CalendarYear', 'Dataset', 'GHGScope',
                          'Scope3Category'], observed=True, dropna=False)
            ['Emissions_tCO2e'].sum().reset_index())


@st.cache_data(show_spinner='Reading that build...')
def _baseline_summary(build_id):
    """An earlier build, reduced to what a comparison needs."""
    frame = (Publisher.load_published() if not build_id
             else Publisher.load_archived(build_id))
    return _summarise(frame)


def _inventory():
    """The build on screen.  Made once, then read by every page."""
    token = _token()
    frame = _load()
    precomputed = _precompute(frame, token)
    table = _build(precomputed, token)
    # Recorded at the first build of a session, so a later edit can be
    # compared against it and reported as stale rather than applied.
    st.session_state.setdefault('built_stamp', _stamp())
    # The build this session opened on.  Everything after it is this
    # session's doing, which is a different question from what has
    # accumulated since the last publication.
    if 'session_baseline' not in st.session_state:
        st.session_state['session_baseline'] = _summarise(table)
        st.session_state['session_opened'] = datetime.now()
    return frame, precomputed, table


def _options(series):
    """Filter choices from a column: the values present, as text, sorted.

    Blanks are not choices, and a column read back from a file can hold a
    null beside its strings, which sorts against them and raises.  One
    helper, so every filter on every page behaves the same way.
    """
    if series is None or len(series) == 0:
        return []
    values = {str(value).strip() for value in series.dropna().unique()}
    return sorted(value for value in values if value)



# ---------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------

def page_verify(precomputed, table):
    st.subheader('Verify')
    st.caption('Whether this build is safe to publish: that it holds together, that the physicals agree with the plan, and what has moved since the last publication.')

    published = Publisher.load_build_log()
    actuals_to = (DEFAULT_ACTUALS_TO_DATE.strftime('%d %b %Y')
                  if DEFAULT_ACTUALS_TO_DATE else 'not stated')
    emissions = table[table['RowKind'] == 'Emission']
    recorded = emissions[~emissions['IsForecast']]['Emissions_tCO2e'].sum()
    forecast = emissions[emissions['IsForecast']]['Emissions_tCO2e'].sum()

    columns = st.columns(4)
    columns[0].metric('Recorded to', actuals_to)
    columns[1].metric('Forecast to',
                      table['Date'].max().strftime('%b %Y'))
    columns[2].metric('Recorded emissions', f'{recorded:,.0f} t')
    columns[3].metric('Forecast emissions', f'{forecast:,.0f} t')

    st.caption(f'Milestones: {MILESTONE_SOURCE}')

    left, right = st.columns(2)
    with left:
        st.markdown('**This build**')
        summary = (emissions.groupby(['GHGScope', 'Dataset'], observed=True)
                   ['Emissions_tCO2e'].sum().unstack(fill_value=0.0)
                   .round(0))
        st.dataframe(summary.style.format('{:,.0f}'), width='stretch')
    with right:
        st.markdown('**Published build**')
        if published:
            # A log written by an earlier version may not carry every field.
            # A status panel that raises is worse than one that says it does
            # not know, so every line is built from what is there.
            rows = (published.get('Rows') or {}).get('published')
            total = (published.get('Totals_tCO2e') or {}).get('total')
            lines = [
                f"Build ID     {published.get('BuildID', '-')}",
                f"Built        {str(published.get('BuiltAt', ''))[:16]}",
                f"Recorded to  {published.get('ActualsTo', '-')}",
                f"Rows         {rows:,}" if rows is not None
                else "Rows         not recorded",
                f"Total        {total:,.0f} tCO2-e" if total is not None
                else "Total        not recorded",
                f"Outstanding  {published.get('Outstanding', 0)}",
            ]
            st.code('\n'.join(lines), language='text')
        else:
            st.info('Nothing published yet.  Build and publish below.')

    st.divider()
    st.markdown('**The physicals, against the life of mine plan**')
    st.caption('Emissions are a function of physicals, so a physical that is '
               'wrong gives an emissions figure that is wrong and still looks '
               'reasonable.  What catches that is the plan.')

    checks = Production.plan_checks(precomputed.ghg_df)
    disagreeing = checks[checks['Verdict'] == 'disagrees']
    drifting = checks[checks['Verdict'] == 'drifting']
    if disagreeing.empty and drifting.empty:
        st.success(f'{len(checks)} physical checks, all agree with '
                   f'{checks["Plan"].iloc[0]}.')
    elif disagreeing.empty:
        st.warning(f'{len(drifting)} of {len(checks)} physical checks are '
                   f'drifting from the plan.  Worth a look before publishing.')
    else:
        st.error(f'{len(disagreeing)} of {len(checks)} physical checks '
                 f'disagree with the plan.')

    shown = checks.copy()
    shown['Drift'] = shown['Drift'].apply(
        lambda value: '' if value is None or pd.isna(value)
        else f'{value:+.1%}')
    shown['Measured'] = shown['Measured'].apply(
        lambda value: '' if value is None or pd.isna(value)
        else f'{value:,.3g}')
    shown['Planned'] = shown['Planned'].apply(
        lambda value: '' if value is None or pd.isna(value)
        else f'{value:,.3g}')
    st.dataframe(
        shown[['Check', 'Measured', 'Planned', 'Unit', 'Drift', 'Verdict',
               'Means']],
        hide_index=True, width='stretch',
        column_config={
            'Check': st.column_config.TextColumn('Check', width='medium'),
            'Measured': st.column_config.TextColumn('This build',
                                                    width='small'),
            'Planned': st.column_config.TextColumn('Plan', width='small'),
            'Unit': st.column_config.TextColumn('Unit', width='small'),
            'Drift': st.column_config.TextColumn('Apart', width='small'),
            'Verdict': st.column_config.TextColumn('Verdict', width='small'),
            'Means': st.column_config.TextColumn('What it means',
                                                 width='large'),
        })
    st.caption(f'Plan: {checks["Plan"].iloc[0]}.  Tolerances are in '
               'Data/Assumptions.yaml.')

    with st.expander('The measures year by year', expanded=False):
        grade = Production.head_grade(precomputed.ghg_df)
        recovery = Production.recovery(precomputed.ghg_df)
        intensity = Production.intensity(precomputed.ghg_df)
        yearly = pd.DataFrame({
            'Head grade g/t': grade.round(3),
            'Recovery %': recovery.round(1),
            'Scope 1 kg per t ROM': intensity.round(2),
        })
        yearly.index.name = 'Year'
        st.dataframe(yearly, width='stretch')
        st.caption('An annual recovery is poured over contained in the same '
                   'year, and those are not the same gold: ore waits on a '
                   'stockpile and a pour lands after the mill run that made '
                   'it.  Read the cumulative figure above for the recovery '
                   'and read this column for how well the two series line up.')

    with st.expander('Activity streams', expanded=False):
        st.dataframe(Production.continuity(precomputed.ghg_df),
                     hide_index=True, width='stretch')
        st.caption('A stream that stops part way through the mine life takes '
                   'its emissions with it, and the total reads as an '
                   'abatement nobody achieved.')

    st.divider()
    st.markdown('**Reconciliation against the calculation engines**')
    st.caption('The table is a projection of what the engines computed.  '
               'A difference here is a fault in the projection, not a '
               'finding about emissions.')
    checks = pd.concat(
        [reconcile(table, precomputed, 'CY').assign(Basis='CY'),
         reconcile(table, precomputed, 'FY').assign(Basis='FY')])
    failures = checks[~checks['Within']]
    if failures.empty:
        st.success(f'{len(checks)} year and scope checks, all reconcile.')
    else:
        st.error(f'{len(failures)} of {len(checks)} checks do not '
                 f'reconcile.  Do not publish.')
        st.dataframe(failures, hide_index=True, width='stretch')

    with st.expander('Inputs in this build', expanded=False):
        rows = []
        for path in TRACKED_INPUTS:
            exists = os.path.exists(path)
            rows.append({
                'File': os.path.basename(path),
                'Present': exists,
                'Size': f'{os.path.getsize(path):,}' if exists else '',
                'Modified': (datetime.fromtimestamp(os.path.getmtime(path))
                             .strftime('%d %b %Y %H:%M') if exists else ''),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')


# ---------------------------------------------------------------------
# EXPLORE
# ---------------------------------------------------------------------

def page_explore(table):
    st.subheader('Inventory')
    st.caption('Every scope and every physical measure, monthly.  Filter to '
               'the question, then read the buckets or take the rows.')

    emissions_only = table[table['RowKind'] == 'Emission']
    # Every filter carries a key.  Without one Streamlit rebuilds the widget
    # from its default on any rerun the page did not ask for - a cache clear,
    # a slow rebuild - and a selection the user made comes back changed.  The
    # key is what makes the choice survive the rerun.
    #
    # In the sidebar rather than across the top, because the filters are read
    # against the result and a control that scrolls away with the page is a
    # control the reader has to go looking for.
    side = st.sidebar
    side.divider()
    side.markdown('**Filter the inventory**')

    years = sorted(int(y) for y in table['CalendarYear'].dropna().unique())
    earliest, latest = (years[0], years[-1]) if years else (0, 0)
    span = side.columns(2)
    first = span[0].number_input('From year', min_value=earliest,
                                 max_value=latest, value=earliest, step=1,
                                 key='inv_year_from')
    last = span[1].number_input('To year', min_value=earliest,
                                max_value=latest, value=latest, step=1,
                                key='inv_year_to')
    basis = side.multiselect('Basis', ['Actual', 'Forecast'],
                             default=['Actual', 'Forecast'], key='inv_basis')
    scopes = side.multiselect(
        'Scope', _options(emissions_only['GHGScope']),
        default=_options(emissions_only['GHGScope']), key='inv_scope')
    departments = side.multiselect(
        'Department', _options(table['Department']), key='inv_dept')
    categories = side.multiselect(
        'Scope 3 category',
        sorted(int(c) for c in
               emissions_only['Scope3Category'].dropna().unique()),
        key='inv_cat')
    frameworks = side.selectbox('Framework',
                                ['All', 'NGER', 'Safeguard', 'GRI'],
                                key='inv_framework')

    # Which publication priced a figure is an audit question asked often
    # enough to deserve a control rather than a download and a spreadsheet.
    if 'FactorSet' in emissions_only.columns:
        sets = side.multiselect(
            'Factor set', _options(emissions_only['FactorSet']), key='inv_set')
        derivations = side.multiselect(
            'Factor basis',
            _options(emissions_only.get('FactorDerivation',
                                        pd.Series(dtype=str))),
            key='inv_derivation')
        pool = emissions_only
        if sets:
            pool = pool[pool['FactorSet'].isin(sets)]
        sources = side.multiselect(
            'Factor source', _options(pool['FactorSource']),
            key='inv_source')
    else:
        sets, sources, derivations = [], [], []

    if first > last:
        first, last = last, first

    rows = table[(table['CalendarYear'] >= first)
                 & (table['CalendarYear'] <= last)]
    rows = rows[rows['Dataset'].isin(basis)]
    if departments:
        rows = rows[rows['Department'].isin(departments)]
    if categories:
        rows = rows[rows['Scope3Category'].isin(categories)]
    if frameworks == 'NGER':
        rows = rows[rows['NGERApplicable']]
    elif frameworks == 'Safeguard':
        rows = rows[rows['SafeguardApplicable']]
    elif frameworks == 'GRI':
        rows = rows[rows['GRIApplicable']]

    picked = rows[(rows['RowKind'] == 'Emission')
                  & rows['GHGScope'].isin(scopes)]
    # A factor filter is an emissions question.  Physical measures carry no
    # factor, so they are left alone rather than filtered to nothing.
    if sets:
        picked = picked[picked['FactorSet'].isin(sets)]
    if derivations:
        picked = picked[picked['FactorDerivation'].isin(derivations)]
    if sources:
        picked = picked[picked['FactorSource'].isin(sources)]
    physicals = rows[rows['RowKind'] == 'Physical']

    summary = st.columns(4)
    summary[0].metric('Emissions', f"{picked['Emissions_tCO2e'].sum():,.0f} t")
    summary[1].metric('Energy', f"{picked['Energy_GJ'].sum():,.0f} GJ")
    summary[2].metric('Spend', f"${picked['SpendAUD'].sum():,.0f}")
    summary[3].metric('Rows', f'{len(picked):,}')

    st.markdown('**Monthly, by scope**')
    monthly = (picked.pivot_table(index='Date', columns='GHGScope',
                                  values='Emissions_tCO2e', aggfunc='sum',
                                  observed=True).fillna(0.0).sort_index())
    if not monthly.empty:
        st.bar_chart(monthly, height=280)

    left, right = st.columns(2)
    with left:
        st.markdown('**By calendar year**')
        yearly = (picked.groupby(['CalendarYear', 'GHGScope'], observed=True)
                  ['Emissions_tCO2e'].sum().unstack(fill_value=0.0))
        yearly['Total'] = yearly.sum(axis=1)
        st.dataframe(yearly.style.format('{:,.0f}'), width='stretch',
                     height=300)
    with right:
        st.markdown('**Physical measures**')
        if physicals.empty:
            st.caption('No physical measures in this filter.')
        else:
            measures = (physicals.groupby(['SubActivity', 'UOM'],
                                          observed=True)['Quantity']
                        .sum().reset_index()
                        .sort_values('Quantity', ascending=False))
            st.dataframe(
                measures, hide_index=True, width='stretch', height=300,
                column_config={'Quantity': st.column_config.NumberColumn(
                    'Quantity', format='%,.0f')})

    # Most recent first, because the question asked of a row list is almost
    # always about the latest month rather than the first one.
    display = picked.sort_values('Date', ascending=False).copy()
    if not display.empty:
        display['Date'] = pd.to_datetime(display['Date']).dt.date
    display = display.drop(
        columns=[column for column in ('CalendarYear', 'FinancialYear')
                 if column in display.columns])

    with st.expander(f'Rows ({len(display):,})', expanded=False):
        st.dataframe(
            display.head(2000), hide_index=True, width='stretch', height=400,
            column_config={
                'Date': st.column_config.DateColumn(format='YYYY-MM-DD'),
                'Quantity': st.column_config.NumberColumn(format='%,.3f'),
                'SpendAUD': st.column_config.NumberColumn(format='%,.0f'),
                'Emissions_tCO2e': st.column_config.NumberColumn(
                    format='%,.2f'),
                'Energy_GJ': st.column_config.NumberColumn(format='%,.0f'),
            })
        st.caption(f'Showing the most recent {min(len(display), 2000):,} of '
                   f'{len(display):,} rows.  The download carries all of '
                   f'them.')
        buffer = io.StringIO()
        display.to_csv(buffer, index=False)
        st.download_button('Download this selection',
                           data=buffer.getvalue().encode('utf-8'),
                           file_name='EmissionsSelection.csv',
                           mime='text/csv')


# ---------------------------------------------------------------------
# SCOPE 3
# ---------------------------------------------------------------------

BADGE = {'Calculated': '🟢', 'Estimated': '🟡', 'Outstanding': '🔴',
         'Excluded': '⚪', 'Not applicable': '⚪'}


# ---------------------------------------------------------------------
# SCOPE 1 AND 2
# ---------------------------------------------------------------------
# The Scope 3 page answers "does this category carry a position".  The same
# question is worth asking of combustion and electricity, where the failure
# is quieter: an activity that never resolved to a factor produces nothing
# and reads as nil rather than as missing.

def page_scope12(precomputed, table):
    st.subheader('Scope 1 and Scope 2')
    st.caption('Every source that burns fuel, buys electricity or reacts.  A '
               'source without a factor is shown as outstanding rather than '
               'left out, because an activity that produced nothing and an '
               'activity that was never priced look identical in a total.')

    rows = table[(table['RowKind'] == 'Emission')
                 & table['GHGScope'].isin(['Scope 1', 'Scope 2'])].copy()
    if rows.empty:
        st.info('No Scope 1 or Scope 2 rows in this build.')
        return

    # Activity carrying a fuel or a common name that produced no emission at
    # all.  This is the gap the totals cannot show.  It comes from the
    # engine, so a published build cannot answer it and says so rather than
    # reporting nil.
    ghg = precomputed.ghg_df
    unpriced = pd.DataFrame()
    if ghg is not None and not ghg.empty:
        quantity = ghg['Quantity'].fillna(0.0)
        produced = (ghg['Scope1_tCO2e'].fillna(0.0).abs()
                    + ghg['Scope2_tCO2e'].fillna(0.0).abs())
        named = ghg['NGAFuel'].astype(str).str.strip() != ''
        unpriced = ghg[named & (quantity != 0.0) & (produced == 0.0)]

    totals = rows.groupby('GHGScope', observed=True)['Emissions_tCO2e'].sum()
    columns = st.columns(4)
    columns[0].metric('Scope 1', f"{totals.get('Scope 1', 0.0):,.0f} t")
    columns[1].metric('Scope 2', f"{totals.get('Scope 2', 0.0):,.0f} t")
    columns[2].metric('Sources', f"{rows['EmissionSource'].nunique():,}")
    columns[3].metric('Activity not priced', f'{len(unpriced):,}')

    # Actual and forecast side by side, because a source that stops part way
    # through the plan should be visible as a source that stops.  Split
    # inside the same grouping rather than merged back, so a source priced
    # two ways cannot repeat its recorded tonnes against each factor.
    rows['_actual'] = rows['Emissions_tCO2e'].where(
        rows['Dataset'] == 'Actual', 0.0)
    rows['_forecast'] = rows['Emissions_tCO2e'].where(
        rows['Dataset'] == 'Forecast', 0.0)

    grouped = rows.groupby(['GHGScope', 'EmissionSource', 'UOM', 'FactorSet',
                            'FactorSource'], observed=True, dropna=False)
    summary = grouped.agg(
        Quantity=('Quantity', 'sum'),
        Emissions=('Emissions_tCO2e', 'sum'),
        Actual=('_actual', 'sum'),
        Forecast=('_forecast', 'sum'),
        Energy=('Energy_GJ', 'sum'),
        Factor=('EmissionFactor', 'last'),
        FactorUOM=('FactorUOM', 'last'),
        Regulated=('FactorRegulated', 'last'),
        Derivation=('FactorDerivation', 'last'),
        Lines=('Emissions_tCO2e', 'size')).reset_index()

    # A published factor on metered activity is a calculated figure,
    # whoever published it.  Explosives are the case that matters: the tonnes
    # are weighed and the factor is the Australian Greenhouse Office's, so the
    # figure is calculated even though the source sits outside NGER.  An
    # estimate is a factor derived here or attributed to nothing.
    derivation = summary.get('Derivation',
                             pd.Series('', index=summary.index)).astype(str)
    summary['Status'] = derivation.map(
        lambda basis: 'Calculated' if basis == 'Published' else 'Estimated')
    summary['Share'] = (summary['Emissions']
                        / max(summary['Emissions'].sum(), 1.0) * 100.0)
    summary = summary.sort_values('Emissions', ascending=False)
    shown = summary.copy()
    shown['Status'] = shown['Status'].map(lambda s: f'{BADGE[s]} {s}')

    st.dataframe(
        shown[['GHGScope', 'EmissionSource', 'Status', 'Quantity', 'UOM',
               'Factor', 'FactorUOM', 'FactorSet', 'Derivation',
               'Emissions', 'Actual', 'Forecast', 'Share', 'Energy',
               'Lines']],
        hide_index=True, width='stretch', height=520,
        column_config={
            'GHGScope': st.column_config.TextColumn('Scope', width='small'),
            'EmissionSource': st.column_config.TextColumn(
                'Source', width='medium'),
            'Quantity': st.column_config.NumberColumn(format='%,.0f'),
            'Factor': st.column_config.NumberColumn(format='%.4g'),
            'FactorUOM': st.column_config.TextColumn('Factor unit'),
            'FactorSet': st.column_config.TextColumn('Publication'),
            'Emissions': st.column_config.NumberColumn(
                'Total t CO2-e', format='%,.0f'),
            'Actual': st.column_config.NumberColumn(
                'Actual t', format='%,.0f'),
            'Forecast': st.column_config.NumberColumn(
                'Forecast t', format='%,.0f'),
            'Share': st.column_config.NumberColumn('Share %', format='%.1f'),
            'Energy': st.column_config.NumberColumn('GJ', format='%,.0f'),
            'Lines': st.column_config.NumberColumn(format='%,d'),
        })

    left, right = st.columns(2)
    with left:
        st.markdown('**By department**')
        by_department = (rows.groupby(['Department', 'GHGScope'],
                                      observed=True)['Emissions_tCO2e']
                         .sum().unstack(fill_value=0.0))
        by_department['Total'] = by_department.sum(axis=1)
        st.dataframe(
            by_department.sort_values('Total', ascending=False)
            .style.format('{:,.0f}'), width='stretch', height=300)
    with right:
        st.markdown('**Framework coverage**')
        coverage = pd.DataFrame({
            'Framework': ['NGER', 'Safeguard Mechanism', 'GRI'],
            'tCO2e': [
                rows.loc[rows['NGERApplicable'], 'Emissions_tCO2e'].sum(),
                rows.loc[rows['SafeguardApplicable'], 'Emissions_tCO2e'].sum(),
                rows.loc[rows['GRIApplicable'], 'Emissions_tCO2e'].sum()],
        })
        coverage['Of total %'] = (coverage['tCO2e']
                                  / max(rows['Emissions_tCO2e'].sum(), 1.0)
                                  * 100.0)
        st.dataframe(
            coverage, hide_index=True, width='stretch', height=300,
            column_config={
                'tCO2e': st.column_config.NumberColumn(format='%,.0f'),
                'Of total %': st.column_config.NumberColumn(format='%.1f')})
        st.caption('Explosives are a real Scope 1 source and are reported, '
                   'but they carry no NGA combustion factor and sit outside '
                   'NGER and the Safeguard Mechanism.  That is why the three '
                   'figures differ.')

    with st.expander(f'Activity not priced ({len(unpriced):,} lines)',
                     expanded=False):
        if unpriced.empty:
            st.success('Every named fuel resolved to a factor.')
        else:
            st.caption('These lines name a fuel but produced no emission.  '
                       'Either the fuel does not resolve to a factor or the '
                       'quantity is recorded in a unit the factor does not '
                       'price.')
            gaps = (unpriced.groupby(['NGAFuel', 'UOM'], observed=True)
                    .agg(Lines=('Quantity', 'size'),
                         Quantity=('Quantity', 'sum'))
                    .reset_index().sort_values('Quantity', ascending=False))
            st.dataframe(
                gaps, hide_index=True, width='stretch',
                column_config={
                    'NGAFuel': st.column_config.TextColumn('Fuel'),
                    'Quantity': st.column_config.NumberColumn(format='%,.1f'),
                    'Lines': st.column_config.NumberColumn(format='%,d')})



def page_scope3(precomputed, reference):
    st.subheader('Scope 3, all fifteen categories')
    st.caption('Every category carries a position.  A category without a '
               'figure says whether it is excluded, not applicable, or '
               'outstanding, because the three are different.')

    status = Status.category_status(precomputed.scope3, reference)
    counts = status['Status'].value_counts()
    columns = st.columns(5)
    for index, name in enumerate(Status.CATEGORY_STATUSES):
        columns[index].metric(f'{BADGE[name]} {name}', int(counts.get(name, 0)))

    shown = status.copy()
    shown['Status'] = shown['Status'].map(lambda s: f'{BADGE[s]} {s}')
    st.dataframe(
        shown[['Category', 'Name', 'Status', 'tCO2e', 'ActualBasis',
               'ForecastBasis', 'OpenItems', 'Reason']],
        hide_index=True, width='stretch', height=580,
        column_config={'tCO2e': st.column_config.NumberColumn(
            'tCO2-e', format='%.0f')})

    st.divider()
    picked = st.selectbox('Category detail',
                          status['Category'].tolist(),
                          format_func=lambda c: (
                              f"{c}  {status.loc[status['Category'] == c, 'Name'].iloc[0]}"))
    record = status[status['Category'] == picked].iloc[0]
    left, right = st.columns([2, 3])
    with left:
        st.markdown(f"**Status** {BADGE[record['Status']]} {record['Status']}")
        st.markdown(f"**Actual basis** {record['ActualBasis'] or '—'}")
        st.markdown(f"**Forecast basis** {record['ForecastBasis'] or '—'}")
        st.markdown(f"**Method** {record['Method'] or '—'}")
        if record['Reason']:
            st.info(record['Reason'])
    with right:
        detail = getattr(precomputed.scope3, 'detail', None)
        if detail is not None and not detail.empty:
            rows = detail[pd.to_numeric(detail['Category'],
                                        errors='coerce') == picked]
            if rows.empty:
                st.caption('No lines for this category.')
            else:
                yearly = (rows.groupby('Year', observed=True)['tCO2e']
                          .sum().round(1))
                st.markdown('**By year**')
                st.dataframe(yearly, width='stretch', height=240)
                st.caption(
                    f"{len(rows):,} lines · factor sources: "
                    f"{rows['FactorSource'].nunique()}")


# ---------------------------------------------------------------------
# MAINTENANCE
# ---------------------------------------------------------------------
# Assumptions, capital items and credits are all maintained the same way:
# edit the grid, save, and the change is recorded.  One pattern rather than
# three, because a person who learns one screen has learned all of them.

HISTORY_PATH = os.path.join(os.path.dirname(LoaderCapital.REGISTER_PATH),
                            'ChangeHistory.csv')


def _maintain(frame, key, column_config=None, disabled=None, height=420,
              allow_rows=True):
    """The common editor.  Returns the edited frame and what changed."""
    edited = st.data_editor(
        frame, hide_index=True, width='stretch', height=height,
        num_rows='dynamic' if allow_rows else 'fixed',
        column_config=column_config or {}, disabled=disabled or [],
        key=key)
    return edited


def _diff_rows(before, after, identity):
    """Cell level differences between two frames, keyed on an identity column.

    Returned as history records, so what is written to the log is the same
    shape whatever screen produced it.
    """
    records = []
    if identity not in before.columns or identity not in after.columns:
        return records
    old = before.set_index(identity, drop=False)
    new = after.set_index(identity, drop=False)
    for key in new.index:
        if key not in old.index:
            records.append({'Path': f'{identity}={key}', 'From': '',
                            'To': 'added'})
            continue
        for column in new.columns:
            if column not in old.columns:
                continue
            was, now = old.loc[key, column], new.loc[key, column]
            if pd.isna(was) and pd.isna(now):
                continue
            if str(was) == str(now):
                continue
            records.append({'Path': f'{identity}={key}.{column}',
                            'From': '' if pd.isna(was) else str(was),
                            'To': '' if pd.isna(now) else str(now)})
    for key in old.index:
        if key not in new.index:
            records.append({'Path': f'{identity}={key}', 'From': 'present',
                            'To': 'removed'})
    return records


def _record(records, source, note=''):
    """Write history records against the screen that produced them."""
    if not records:
        return
    stamped = []
    for record in records:
        stamped.append({
            'ChangedAt': datetime.now().isoformat(timespec='seconds'),
            'ChangedBy': os.environ.get('USER', 'unknown'),
            'File': source, 'Path': record.get('Path', ''),
            'From': record.get('From', ''), 'To': record.get('To', ''),
            'Note': note,
        })
    ConfigEdit.append_history(HISTORY_PATH, stamped)


# ---------------------------------------------------------------------
# ASSUMPTIONS
# ---------------------------------------------------------------------

def page_assumptions(reference):
    st.subheader('Assumptions')
    st.caption('An assumption a user maintains belongs in the configuration '
               f'file, not in code.  Editing here changes the line in '
               f'{os.path.basename(CONFIG_PATH)} and leaves the rest of the '
               'file, including the comments explaining each figure, exactly '
               'as it was.')
    st.caption('The source is editable and should be filled in whenever a '
               'figure is.  Both standards require the source of an emission '
               'factor to be disclosed, so a number without one is only half '
               'entered.')

    rows = Status.assumption_rows(reference.config)
    if rows.empty:
        st.error('No assumptions found in the configuration.  If the file '
                 'looks empty, restore it from `Data/ReferenceInputs.yaml` or '
                 'from the archive under `Data/Published/`.')
        return

    shown = rows[['Category', 'Group', 'Parameter', 'Value', 'Unit', 'Source']]
    edited = _maintain(
        shown, key='assumption_editor', allow_rows=False,
        disabled=['Category', 'Group', 'Parameter', 'Unit'],
        column_config={
            'Value': st.column_config.NumberColumn(
                'Value', format='%.4f',
                help='The figure in force.  Blank means not supplied.'),
            'Source': st.column_config.TextColumn(
                'Source', width='large',
                help='Publication, table and year.  A factor a reader '
                     'cannot look up is a factor they cannot check.'),
        })

    value_changed = edited['Value'].fillna(-1).ne(shown['Value'].fillna(-1))
    source_changed = (edited['Source'].fillna('').astype(str)
                      .ne(shown['Source'].fillna('').astype(str)))
    changed = value_changed | source_changed

    unsourced = edited[edited['Value'].notna()
                       & edited['Source'].fillna('').astype(str).eq('')]
    if not unsourced.empty:
        st.warning(
            f'{len(unsourced)} figure(s) carry no source: '
            + ', '.join(f'category {int(r.Category)} {r.Parameter}'
                        for r in unsourced.itertuples()))

    if changed.any():
        st.info(f'{int(changed.sum())} assumption(s) edited and not yet '
                'saved.')
    if st.button('Save assumptions', type='primary',
                 disabled=not changed.any()):
        edits = []
        for position in edited.index[changed]:
            path = [p for p in rows.loc[position, 'Path'].split('.') if p != '']
            if value_changed.loc[position]:
                edits.append((path, edited.loc[position, 'Value']))
            if source_changed.loc[position]:
                edits.append((path[:-1] + ['factor_source'],
                              str(edited.loc[position, 'Source'])))
        try:
            records = ConfigEdit.set_values(
                CONFIG_PATH, edits, history_path=HISTORY_PATH)
        except ConfigEdit.HistoryError as problem:
            # Nothing was written, and saying so is the whole point.
            st.error(f'{problem}')
            return
        _rebuild()
        st.success(f'{len(records)} value(s) saved.  Preview the change '
                   'before publishing it.')
        st.rerun()


# ---------------------------------------------------------------------
# CAPITAL GOODS
# ---------------------------------------------------------------------

def page_capital(reference):
    st.subheader('Capital goods register')
    st.caption('An item is entered once and keeps one identifier through two '
               'states.  It contributes to the forecast while it is expected, '
               'and to the record once it is commissioned.  It is never both.')

    register = LoaderCapital.apply_factor_classes(
        LoaderCapital.load_register(), reference)
    resolved = LoaderCapital.resolve_register(register)
    classes = LoaderCapital.factor_classes(reference)

    columns = st.columns(4)
    columns[0].metric('Items', f'{len(register):,}')
    columns[1].metric('Counting', f"{int(resolved['Counts'].sum()):,}"
                      if not resolved.empty else '0')
    columns[2].metric('Outstanding',
                      f"{int(resolved['Issue'].str.startswith('Outstanding').sum()):,}"
                      if not resolved.empty else '0')
    columns[3].metric(
        'Recognised value',
        f"${resolved.loc[resolved['Counts'], 'RecognisedValueAUD'].sum():,.0f}"
        if not resolved.empty else '$0')

    st.caption(
        'Tenure decides whether an item produces a Category 2 event at all.  '
        + '  '.join(f'**{name}** {note}'
                    for name, note in LoaderCapital.TENURE_HELP.items()))

    st.caption('Choose the asset class and the factor follows from it.  The '
               'factor class and the factor are derived, not entered, so the '
               'register cannot carry a factor that disagrees with the class '
               'beside it.')

    # Only the fields a person can answer are editable.  Add a row at the
    # foot of the grid; the identifier is issued on save.
    editable = register[[
        'CapitalID', 'AssetDescription', 'AssetClass', 'Department',
        'CostCentre', 'Tenure', 'Status', 'ExpectedCommissionDate',
        'ActualCommissionDate', 'ForecastValueAUD', 'ActualValueAUD',
        'FactorClass', 'Factor', 'Notes']].copy()

    edited = _maintain(
        editable, key='capital_editor', height=420,
        disabled=['CapitalID', 'FactorClass', 'Factor'],
        column_config={
            'CapitalID': st.column_config.TextColumn('ID', width='small'),
            'AssetClass': st.column_config.SelectboxColumn(
                'Asset class', options=sorted(classes), required=True,
                help='The factor follows from this.'),
            'Tenure': st.column_config.SelectboxColumn(
                'Tenure', options=list(LoaderCapital.TENURES)),
            'Status': st.column_config.SelectboxColumn(
                'Status', options=list(LoaderCapital.STATUSES)),
            'ExpectedCommissionDate': st.column_config.DateColumn('Expected'),
            'ActualCommissionDate': st.column_config.DateColumn('Actual'),
            'ForecastValueAUD': st.column_config.NumberColumn(
                'Forecast AUD', format='%,.0f'),
            'ActualValueAUD': st.column_config.NumberColumn(
                'Actual AUD', format='%,.0f'),
            'FactorClass': st.column_config.TextColumn(
                'Factor class', width='medium'),
            'Factor': st.column_config.NumberColumn(
                'Factor', format='%.1f',
                help='t CO2-e per $1M AUD, from the class.'),
        })

    if st.button('Save register', type='primary'):
        saving = edited.copy()
        # Issue an identifier to anything added in the grid.
        for position in saving.index[saving['CapitalID'].fillna('').eq('')]:
            saving.loc[position, 'CapitalID'] = \
                LoaderCapital.next_capital_id(saving)
        merged = LoaderCapital.load_register().set_index('CapitalID')
        saving = saving.set_index('CapitalID')
        for column in saving.columns:
            merged.loc[saving.index.intersection(merged.index), column] = \
                saving.loc[saving.index.intersection(merged.index), column]
        added = saving.loc[saving.index.difference(merged.index)]
        merged = pd.concat([merged, added])
        merged = LoaderCapital.apply_factor_classes(
            merged.reset_index(), reference)
        _record(_diff_rows(register, merged, 'CapitalID'),
                'CapitalGoodsRegister.csv')
        LoaderCapital.save_register(merged)
        _rebuild()
        st.success('Saved.  Press Rebuild to bring it into the figures.')
        st.rerun()

    if not resolved.empty:
        excluded = resolved[~resolved['Counts']]
        if not excluded.empty:
            with st.expander(f'Not counting ({len(excluded)})',
                             expanded=False):
                st.caption('Every item is kept, whether or not it counts, so '
                           'the determination is visible rather than implied '
                           'by an absence.')
                st.dataframe(
                    excluded[['CapitalID', 'AssetDescription', 'Tenure',
                              'Status', 'Issue']],
                    hide_index=True, width='stretch')


# ---------------------------------------------------------------------
# CREDITS
# ---------------------------------------------------------------------

CREDIT_TYPES = ('Issuance', 'Surrender', 'Sale', 'Purchase', 'Correction')
LEAVES_HOLDING = ('Surrender', 'Sale')


def page_credits():
    st.subheader('Safeguard Mechanism credits')
    st.caption('Issuance, surrender, sale and purchase.  These are registry '
               'transactions, not model outputs: they are what happened to '
               'the credit position, and the model is read against them '
               'rather than the other way round.')

    if os.path.exists(SMC_PATH):
        ledger = pd.read_csv(SMC_PATH)
    else:
        ledger = pd.DataFrame(columns=['Date', 'Type', 'Quantity',
                                       'Unit_Price', 'Total_Value',
                                       'Reference', 'Applies_To_FY', 'Notes'])

    # A date read from a csv arrives as text, and a date column that a person
    # is meant to edit has to be a date.  Parsed on the way in and written
    # back as a plain date, so the file stays readable by anything.
    ledger['Date'] = pd.to_datetime(ledger.get('Date'), errors='coerce',
                                    dayfirst=True)
    for column in ('Quantity', 'Unit_Price', 'Total_Value'):
        if column in ledger.columns:
            ledger[column] = pd.to_numeric(ledger[column], errors='coerce')
    for column in ('Type', 'Reference', 'Applies_To_FY', 'Notes'):
        if column in ledger.columns:
            ledger[column] = ledger[column].fillna('').astype(str)

    quantity = pd.to_numeric(ledger.get('Quantity'), errors='coerce').fillna(0)
    kind = ledger.get('Type', pd.Series(dtype=str)).astype(str)
    columns = st.columns(4)
    columns[0].metric('Issued', f"{quantity[kind.eq('Issuance')].sum():,.0f}")
    columns[1].metric('Surrendered',
                      f"{-quantity[kind.eq('Surrender')].sum():,.0f}")
    columns[2].metric('Sold', f"{-quantity[kind.eq('Sale')].sum():,.0f}")
    columns[3].metric('Holding', f'{quantity.sum():,.0f}')

    st.caption('A surrender or a sale leaves the holding and is stored '
               'negative, so the running sum is the holding the registry '
               'should agree with.  The sign is applied on save; enter the '
               'number of units either way.')

    edited = _maintain(
        ledger, key='credit_editor', height=360,
        column_config={
            'Date': st.column_config.DateColumn('Date'),
            'Type': st.column_config.SelectboxColumn(
                'Type', options=list(CREDIT_TYPES)),
            'Quantity': st.column_config.NumberColumn(
                'Units', format='%,.0f'),
            'Unit_Price': st.column_config.NumberColumn(
                'Unit price AUD', format='%.2f'),
            'Total_Value': st.column_config.NumberColumn(
                'Value AUD', format='%,.0f'),
        })

    if st.button('Save transactions', type='primary'):
        saving = edited.copy()
        # Direction is a property of the transaction, not of what somebody
        # happened to type.
        leaving = saving['Type'].astype(str).isin(LEAVES_HOLDING)
        units = pd.to_numeric(saving['Quantity'], errors='coerce')
        saving['Quantity'] = units.abs().where(~leaving, -units.abs())
        saving['Date'] = pd.to_datetime(saving['Date'],
                                        errors='coerce').dt.date
        _record(_diff_rows(ledger.assign(_row=ledger.index.astype(str)),
                           saving.assign(_row=saving.index.astype(str)),
                           '_row'), 'SmcTransactions.csv')
        saving.to_csv(SMC_PATH, index=False)
        _rebuild()
        st.success('Saved.')
        st.rerun()


# ---------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------

def page_history():
    st.subheader('Change history')
    st.caption('Every edit made through this application: what changed, from '
               'what to what, by whom and when.  A published figure that '
               'moved should be explainable, and this is where the '
               'explanation lives.')

    history = ConfigEdit.read_history(HISTORY_PATH)
    if history.empty:
        st.info('No changes recorded yet.')
        return

    controls = st.columns(3)
    files = controls[0].multiselect('File', _options(history['File']))
    term = controls[1].text_input('Search', placeholder='A path or a value')
    limit = controls[2].number_input('Show', min_value=20, max_value=5000,
                                     value=200, step=20)

    rows = history
    if files:
        rows = rows[rows['File'].isin(files)]
    if term:
        joined = rows.astype(str).agg(' '.join, axis=1).str.lower()
        rows = rows[joined.str.contains(term.lower(), na=False)]

    st.caption(f'{len(rows):,} of {len(history):,} changes')
    st.dataframe(rows.head(int(limit)), hide_index=True, width='stretch',
                 height=460)
    st.download_button(
        'Download the full history',
        data=history.to_csv(index=False).encode('utf-8'),
        file_name='ChangeHistory.csv', mime='text/csv')


# ---------------------------------------------------------------------
# PREVIEW AND PUBLISH
# ---------------------------------------------------------------------

def page_changes(reference):
    st.subheader('Changes')
    st.caption('What this session has done, and what publishing would write.  '
               'Reading this page changes nothing.')

    # This page always builds.  Comparing the current inputs against the
    # published figures is the whole question it answers, so it cannot be
    # asked from the published file alone and does not wait to be told.
    _, precomputed, table = _inventory()

    checks = pd.concat([reconcile(table, precomputed, 'CY'),
                        reconcile(table, precomputed, 'FY')])
    failures = checks[~checks['Within']]

    status = Status.category_status(precomputed.scope3, reference)
    outstanding = pd.DataFrame(
        getattr(precomputed.scope3, 'outstanding', None) or [])
    capital_issues = LoaderCapital.register_issues(LoaderCapital.load_register())
    if not capital_issues.empty:
        outstanding = pd.concat([outstanding, capital_issues],
                                ignore_index=True)
    # Held for the sidebar, so publishing writes exactly what was reviewed
    # here rather than gathering it again afterwards.
    st.session_state['pending_outstanding'] = outstanding
    st.session_state['pending_assumptions'] = Status.assumption_rows(
        reference.config)
    st.session_state['pending_ok'] = bool(failures.empty)

    columns = st.columns(3)
    columns[0].metric('Reconciliation',
                      'Pass' if failures.empty else f'{len(failures)} failed')
    columns[1].metric('Outstanding items', len(outstanding))
    columns[2].metric('Categories without a figure',
                      int((status['Status'] == 'Outstanding').sum()))

    if not failures.empty:
        st.error('The table does not reconcile to the engines.  Publishing '
                 'is blocked.')
        st.dataframe(failures, hide_index=True, width='stretch')
        return

    current = _summarise(table)
    baseline, name = _pick_baseline()
    if baseline is None:
        st.info('Nothing published yet, so there is nothing to compare '
                'against.')
        return

    moved = _movement(baseline, current, name, 'This build')
    total = moved.loc[moved['CalendarYear'] == 'Total', 'Change']
    if float(total.iloc[0] if len(total) else 0.0) == 0.0:
        st.success(f'Nothing has moved against {name.lower()}.')
    left, right = st.columns([2, 3])
    with left:
        st.caption('By scope and basis')
        st.dataframe(_headline(baseline, current, name, 'This build'),
                     hide_index=True, width='stretch', height=300,
                     column_config={
                         name: st.column_config.NumberColumn(format='%,.0f'),
                         'This build': st.column_config.NumberColumn(
                             format='%,.0f'),
                         'Change': st.column_config.NumberColumn(
                             format='%,.0f')})
    with right:
        st.caption('By year, and in total')
        st.dataframe(moved, hide_index=True, width='stretch', height=300,
                     column_config=_movement_columns(name, 'This build'))

    comparison = Publisher.compare_builds(table)
    with st.expander('Largest moves by year and scope', expanded=False):
        st.dataframe(comparison['movers'], hide_index=True, width='stretch')
    with st.expander('Scope 3 by category', expanded=False):
        st.dataframe(comparison['category'], hide_index=True, width='stretch')
    with st.expander(f'Outstanding items ({len(outstanding)})',
                     expanded=False):
        if outstanding.empty:
            st.success('Nothing outstanding.')
        else:
            st.caption('These are known gaps.  Missing data is surfaced here '
                       'rather than being reported as nil.')
            st.dataframe(outstanding, hide_index=True, width='stretch')


def _pick_baseline():
    """Choose what this build is being compared against.

    The published build by default, because that is what publishing writes.
    The build this session opened on answers a different question - what have
    I done today - and an earlier published build answers a third, which is
    what changed between two disclosures.
    """
    log = Publisher.load_build_log() or {}
    current_id = log.get('BuildID', '')
    archive = Publisher.archived_builds()

    # This session first, because the question in front of somebody is
    # almost always what have I just done.  What has accumulated since the
    # last publication is the second question and the one publishing answers.
    options = []
    folders = {}
    if st.session_state.get('session_baseline') is not None:
        options.append('When this session opened')
    options.append('Published build')
    for position, row in archive.iterrows():
        # The one at the top is the build now published, and it is already
        # the default option.
        if position == 0 and row['BuildID'] == current_id:
            continue
        label = f"Published {row['PublishedAt']}  ({row['BuildID']})"
        folders[label] = row['Folder']
        options.append(label)

    chosen = st.selectbox('Compare against', options, key='changes_baseline',
                          help='Every published build is archived whole, so '
                               'any of them can be the comparison.')
    if chosen == 'When this session opened':
        opened = st.session_state.get('session_opened')
        when = opened.strftime('%d %b %H:%M') if opened else 'this session'
        st.caption(f'Against the build this session opened on, at {when}.  '
                   f'An edit appears here once Rebuild has brought it in.')
        return st.session_state.get('session_baseline'), 'Opened'
    if chosen == 'Published build':
        st.caption(f'Against the published build, {current_id or "none"}.  '
                   f'This is what publishing would write.')
        return _baseline_summary(''), 'Published'
    folder = folders.get(chosen, '')
    st.caption(f'Against the build published on {chosen.split("  ")[0][10:]}.  '
               f'Publishing still writes the difference against the current '
               f'published build.')
    return _baseline_summary(folder), 'Earlier'


def _movement_columns(before, after):
    return {
        'CalendarYear': st.column_config.TextColumn('Year'),
        before: st.column_config.NumberColumn(format='%,.0f'),
        after: st.column_config.NumberColumn(format='%,.0f'),
        'Change': st.column_config.NumberColumn(format='%,.0f'),
        'ChangePct': st.column_config.NumberColumn('Change %', format='%.2f'),
    }


def _headline(before, after, before_name, after_name):
    """Two summaries against each other, by basis and scope."""
    def fold(frame, name):
        if frame is None or frame.empty:
            return pd.Series(dtype='float64', name=name)
        return frame.groupby(['Dataset', 'GHGScope'], observed=True)[
            'Emissions_tCO2e'].sum().rename(name)

    joined = pd.concat([fold(before, before_name), fold(after, after_name)],
                       axis=1).fillna(0.0).reset_index()
    joined['Change'] = joined[after_name] - joined[before_name]
    return joined


def _movement(before, after, before_name='Published', after_name='Preview'):
    """Two summaries against each other, by year and in total."""
    def fold(frame, name):
        if frame is None or frame.empty:
            return pd.Series(dtype='float64', name=name)
        return frame.groupby('CalendarYear', observed=True)[
            'Emissions_tCO2e'].sum().rename(name)

    joined = pd.concat([fold(before, before_name), fold(after, after_name)],
                       axis=1).fillna(0.0).reset_index()
    joined['CalendarYear'] = joined['CalendarYear'].astype(int).astype(str)
    total = pd.DataFrame({'CalendarYear': ['Total'],
                          before_name: [joined[before_name].sum()],
                          after_name: [joined[after_name].sum()]})
    joined = pd.concat([joined, total], ignore_index=True)
    joined['Change'] = joined[after_name] - joined[before_name]
    joined['ChangePct'] = (joined['Change']
                           / joined[before_name].replace(0.0, pd.NA) * 100.0)
    return joined


# ---------------------------------------------------------------------
# FACTORS
# ---------------------------------------------------------------------
# Who published a factor decides who may change it.  A National Greenhouse
# Account or US EPA factor is a regulated input and is shown as it was
# published; a factor this company derived or selected is a judgement, and a
# judgement is maintained by the person who has to defend it.

# Named for what each holds, and on one principle.  "Maintained here" and
# "Used as published" were not opposites - one said who maintains a factor,
# the other said how it is used - and splitting the published factors by
# which file they sit in made a distinction out of an implementation detail.
#
# All factors is where you find one.  The rest are the three places a number
# comes from: set here, the National Greenhouse Accounts, or the spend based
# database.  Overrides is the fifth because it is a different act.

FACTOR_STATUS = {
    'Published': 'Used as its publisher issued it.',
    'Internal': 'Converted, banded or chosen here.',
    'Needs a source': 'Carries a number and names no publication.',
    'Override': 'A published factor superseded by a company assumption.',
    'Excluded': 'Not priced in this category.  The reason says where it is.',
}


# ---------------------------------------------------------------------
# FACTORS, ITEMS AND LOOKUPS
# ---------------------------------------------------------------------
# Three tables, three tabs, and one rule running through them.
#
# A factor is Class, Source, Name, Region and Unit.  A release is a version
# of that identity; an item points at the identity and never at a release, so
# a later edition of a publication changes no item and restates no year
# already reported.
#
# Class decides who may change a factor.  Internal is this company's and is
# editable here; NGA and Spend-based are used as published and are shown but
# locked, because a regulated figure edited in a screen is a figure nobody
# can trace back to its publication.

FACTOR_VIEW = ['FactorID', 'Class', 'Source', 'Name', 'Release', 'Region',
               'Unit', 'Scope1', 'Scope2', 'Scope3', 'Obsolete', 'Reason']

FACTOR_CONFIG = {
    'FactorID': st.column_config.TextColumn('ID', width='small'),
    'Class': st.column_config.TextColumn('Class', width='small'),
    'Source': st.column_config.TextColumn('Source', width='medium'),
    'Name': st.column_config.TextColumn('Name', width='large'),
    'Release': st.column_config.TextColumn('Release', width='small'),
    'Region': st.column_config.TextColumn('Region', width='small'),
    'Unit': st.column_config.TextColumn('Unit', width='medium'),
    'Scope1': st.column_config.NumberColumn('Scope 1', format='%.6g'),
    'Scope2': st.column_config.NumberColumn('Scope 2', format='%.6g'),
    'Scope3': st.column_config.NumberColumn('Scope 3', format='%.6g'),
    'Obsolete': st.column_config.CheckboxColumn('Obsolete', width='small'),
    'Reason': st.column_config.TextColumn('Reason', width='large'),
}

ITEM_VIEW = ['ItemID', 'Category', 'Key', 'Description', 'Basis',
             'Quantity_UOM', 'Source', 'Name', 'Unit', 'Scope3',
             'IsAssigned']

ITEM_CONFIG = {
    'ItemID': st.column_config.TextColumn('Item', width='medium'),
    'Category': st.column_config.NumberColumn('Cat', width='small'),
    'Key': st.column_config.TextColumn('Group', width='small'),
    'Description': st.column_config.TextColumn('Description', width='large'),
    'Basis': st.column_config.TextColumn('Basis', width='small'),
    'Quantity_UOM': st.column_config.TextColumn('UOM', width='small'),
    'Source': st.column_config.TextColumn('Factor source', width='medium'),
    'Name': st.column_config.TextColumn('Factor', width='large'),
    'Unit': st.column_config.TextColumn('Unit', width='medium'),
    'Scope3': st.column_config.NumberColumn('Value', format='%.6g'),
    'IsAssigned': st.column_config.CheckboxColumn('Pointed', width='small'),
}

LOOKUP_CONFIG = {
    'ListName': st.column_config.TextColumn('List', width='small'),
    'Code': st.column_config.TextColumn('Code', width='medium'),
    'Label': st.column_config.TextColumn('Label', width='large'),
    'Dimension': st.column_config.TextColumn('Dimension', width='small'),
    'EmissionScale': st.column_config.NumberColumn('Emission scale',
                                                   format='%.6g'),
    'QuantityScale': st.column_config.NumberColumn('Quantity scale',
                                                   format='%.6g'),
    'SortOrder': st.column_config.NumberColumn('Order', format='%d'),
    'Active': st.column_config.CheckboxColumn('Active', width='small'),
    'Notes': st.column_config.TextColumn('Notes', width='large'),
}


def _rows_selected(frame, key):
    """Which rows the reader highlighted.

    Streamlit returns the selection on the widget's session state, as an
    object on some versions and a mapping on others, so it is read either way
    rather than assuming one.
    """
    state = st.session_state.get(key)
    if state is None:
        return []
    selection = getattr(state, 'selection', None)
    if selection is None and isinstance(state, dict):
        selection = state.get('selection')
    rows = getattr(selection, 'rows', None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get('rows')
    return [row for row in (rows or []) if 0 <= row < len(frame)]


def page_factors():
    st.subheader('Factors')
    st.caption('A factor is where it came from, what it is called, where it '
               'was published for and what it measures.  An item points at '
               'that identity; which release applies is resolved against the '
               'year being priced, so a new edition changes no item.')

    factors = FactorTable.load()
    items = Items.load()
    lookups = Lookups.load()
    if factors.empty:
        st.error('Factors.csv is empty.  Import a factor set before editing.')
        return

    identities = factors['FactorKey'].nunique()
    unsourced = FactorTable.unsourced(factors)
    orphans = Items.orphans(items, factors)
    columns = st.columns(5)
    columns[0].metric('Factors', f'{identities:,}')
    columns[1].metric('Releases', f'{len(factors):,}')
    columns[2].metric('Items', f'{len(items):,}')
    columns[3].metric('Pointed elsewhere',
                      f"{int(items['IsAssigned'].sum()):,}")
    columns[4].metric('Needing a source', f'{len(unsourced):,}')

    if not unsourced.empty:
        names = ', '.join(unsourced['Name'].astype(str).head(3))
        st.warning(f'{len(unsourced)} factor(s) name no publication: {names}.  '
                   'Source is mandatory, and a description does not satisfy '
                   'it.')
    if not orphans.empty:
        st.error(f'{len(orphans)} item(s) point at a factor that is no longer '
                 'in the table.  Those items are unpriced.')

    factor_tab, item_tab, lookup_tab = st.tabs(
        [f'Factors ({identities})', f'Items ({len(items)})',
         f'Lookups ({lookups["ListName"].nunique()} lists)'])

    with factor_tab:
        _factors_tab(factors, items, lookups)
    with item_tab:
        _items_tab(items, factors, lookups)
    with lookup_tab:
        _lookups_tab(lookups)


def _factors_tab(factors, items, lookups):
    controls = st.columns([2, 2, 2, 4])
    classes = controls[0].multiselect(
        'Class', Lookups.values('Class', lookups), key='ft_class')
    sources = controls[1].multiselect(
        'Source', sorted(factors['Source'].unique()), key='ft_source')
    releases = controls[2].multiselect(
        'Release', sorted(factors['Release'].astype(str).unique()),
        key='ft_release')
    term = controls[3].text_input('Search', key='ft_term',
                                  placeholder='diesel, steel, electricity')

    shown = factors
    if classes:
        shown = shown[shown['Class'].isin(classes)]
    if sources:
        shown = shown[shown['Source'].isin(sources)]
    if releases:
        shown = shown[shown['Release'].astype(str).isin(releases)]
    if term:
        haystack = (shown['Name'].astype(str) + ' ' + shown['Source'] + ' '
                    + shown['Region'] + ' ' + shown['Unit'])
        shown = shown[haystack.str.contains(term, case=False, na=False,
                                            regex=False)]

    editable = FactorTable.editable(shown)
    st.caption(f'{len(shown):,} of {len(factors):,} releases.  '
               f'{int(editable.sum())} stand on our own research and may be '
               'edited here.  The rest are published figures, or derived from '
               'one by a published conversion, and are used as published: we '
               'set neither the factor, nor the price index, nor the rate.')

    st.markdown('**Used as published**')
    fixed = shown[~editable]
    st.dataframe(fixed[FACTOR_VIEW], hide_index=True, width='stretch',
                 height=280, column_config=FACTOR_CONFIG,
                 key='published_factors', on_select='rerun',
                 selection_mode='single-row')
    _where_used(fixed, 'published_factors', items, factors)

    st.markdown('**Maintained here**')
    own = shown[editable]
    if own.empty:
        st.caption('Nothing in this filter is ours to edit.')
    else:
        edited = _maintain(
            own[FACTOR_VIEW], key='internal_factors', height=260,
            allow_rows=False, column_config=FACTOR_CONFIG,
            disabled=['FactorID', 'Class', 'Source', 'Release'])
        if st.button('Save factors', type='primary', key='factor_save'):
            _save_factors(own[FACTOR_VIEW], edited)

    _add_factor(factors, lookups)


def _where_used(frame, widget_key, items, factors):
    """The items a highlighted factor prices.

    Selecting a factor and seeing what moves if it changes is the whole
    question a person comes to this screen with.
    """
    picked = _rows_selected(frame, widget_key)
    if not picked:
        return
    row = frame.iloc[picked[0]]
    used = items[items['FactorKey'] == row['FactorKey']]
    st.caption(f"{row['Source']} | {row['Name']} prices {len(used)} item(s).")
    if not used.empty:
        view = Items.with_factors(used, factors)
        st.dataframe(view[ITEM_VIEW], hide_index=True, width='stretch',
                     height=200, column_config=ITEM_CONFIG)


def _save_factors(before, edited):
    """Write the edited Internal rows back into the whole table.

    The identity is rebuilt from the fields, because a rename is a new
    identity and the items pointing at the old one have to be moved with it
    or they lose their factor.
    """
    whole = FactorTable.load()
    changes = _diff_rows(before, edited, 'FactorID')
    if not changes:
        st.info('Nothing changed.')
        return
    indexed = whole.set_index('FactorID')
    saving = edited.set_index('FactorID')
    was = dict(zip(whole['FactorID'], whole['FactorKey']))
    for column in saving.columns:
        indexed.loc[saving.index, column] = saving[column]
    restored = indexed.reset_index()
    restored['FactorKey'] = [
        FactorTable.factor_key(row['Class'], row['Source'], row['Name'],
                               row['Region'], row['Unit'])
        for _, row in restored.iterrows()]
    restored.loc[restored['FactorID'].isin(saving.index), 'UpdatedAt'] = (
        datetime.now().isoformat(timespec='seconds'))
    FactorTable.save(restored)

    moved = {was[fid]: key for fid, key
             in zip(restored['FactorID'], restored['FactorKey'])
             if fid in was and was[fid] != key}
    if moved:
        items = Items.load()
        for column in ('FactorKey_Imported', 'FactorKey_Assigned'):
            items[column] = items[column].replace(moved)
        Items.save(items)
        st.caption(f'{len(moved)} identity change(s) carried through to the '
                   'items pointing at them.')
    _record(changes, 'Factors.csv')
    _rebuild()
    st.success('Saved.  Press Rebuild to bring it into the figures.')
    st.rerun()


def _add_factor(factors, lookups):
    """Add an Internal factor.

    Only Internal.  A published factor arrives by import and carries the
    publication's own identity; typing one in by hand produces a figure that
    looks published and is not.
    """
    with st.expander('Add a factor'):
        st.caption('Only our own research is added here: a figure this '
                   'company derived and stands behind, resting on no '
                   'authoritative source.  A published factor arrives by '
                   'import carrying its publication\'s own identity, and a '
                   'conversion of one is still that publication\'s.  It '
                   'still needs a source, because a number without one '
                   'cannot be disclosed.')
        with st.form('add_factor'):
            top = st.columns(3)
            source = top[0].text_input(
                'Source', placeholder='worldsteel 2023, AusLCI V48')
            name = top[1].text_input('Name',
                                     placeholder='Grinding media, steel')
            release = top[2].text_input('Release', placeholder='2023, V48')
            middle = st.columns(4)
            effective = middle[0].number_input(
                'Effective from', min_value=2000, max_value=2100,
                value=datetime.now().year, step=1, format='%d')
            region = middle[1].selectbox(
                'Region', Lookups.values('Region', lookups))
            unit = middle[2].selectbox('Unit', Lookups.values('Unit', lookups))
            scopes = st.columns(3)
            scope1 = scopes[0].text_input('Scope 1', placeholder='blank if none')
            scope2 = scopes[1].text_input('Scope 2', placeholder='blank if none')
            scope3 = scopes[2].text_input('Scope 3', placeholder='blank if none')
            reason = st.text_area(
                'Reason',
                placeholder='Why this factor exists and what it is based on.')
            submitted = st.form_submit_button('Add factor', type='primary')
        if not submitted:
            return
        problems = []
        if not source.strip():
            problems.append('Source is mandatory.')
        if not name.strip():
            problems.append('Name is mandatory.')
        if not reason.strip():
            problems.append('A reason is mandatory.')
        values = {}
        for label, raw in (('Scope1', scope1), ('Scope2', scope2),
                           ('Scope3', scope3)):
            text = str(raw).strip()
            if not text:
                values[label] = ''
                continue
            try:
                values[label] = float(text)
            except ValueError:
                problems.append(f'{label} is not a number.')
        if not any(str(v) != '' for v in values.values()):
            problems.append('At least one scope needs a value.')
        key = FactorTable.factor_key(FactorTable.CLASS_INTERNAL,
                                     source.strip(), name.strip(), region,
                                     unit)
        clash = factors[(factors['FactorKey'] == key)
                        & (factors['Release'].astype(str) == release.strip())]
        if not clash.empty:
            problems.append('That factor and release already exist.')
        if problems:
            for problem in problems:
                st.error(problem)
            return

        whole = FactorTable.load()
        row = {column: '' for column in FactorTable.COLUMNS}
        row.update({
            'FactorID': FactorTable.next_id(whole),
            'FactorKey': key,
            'Class': FactorTable.CLASS_INTERNAL,
            'Source': source.strip(),
            'DisplaySource': f'{source.strip()}, {name.strip()}',
            'Name': name.strip(),
            'Release': release.strip(),
            'EffectiveFrom': int(effective),
            'Region': region,
            'Unit': unit,
            'Obsolete': False,
            'Reason': reason.strip(),
            'Import': 'Entered here',
            'AddedBy': os.environ.get('USER', 'unknown'),
            'AddedAt': datetime.now().isoformat(timespec='seconds'),
        })
        row.update(values)
        FactorTable.save(pd.concat([whole, pd.DataFrame([row])],
                                   ignore_index=True))
        _record([{'Path': f"{row['FactorID']}.Factor", 'From': '',
                  'To': f"{source.strip()} | {name.strip()}"}],
                'Factors.csv', note=reason.strip())
        _rebuild()
        st.success(f"Added {row['FactorID']}.  Point items at it under Items.")
        st.rerun()


def _items_tab(items, factors, lookups):
    st.caption('An item carries no value of its own.  It points at a factor, '
               'and where the one you want does not exist it is added under '
               'Factors first.  That is what keeps every figure traceable to '
               'something published.')
    controls = st.columns([2, 2, 4])
    bases = controls[0].multiselect('Basis', Lookups.values('Basis', lookups),
                                    key='it_basis')
    categories = controls[1].multiselect(
        'Category',
        sorted(int(c) for c in items['Category'].dropna().unique()),
        key='it_cat')
    term = controls[2].text_input('Search', key='it_term',
                                  placeholder='grinding, pump, steel')

    view = Items.with_factors(items, factors)
    if bases:
        view = view[view['Basis'].isin(bases)]
    if categories:
        view = view[view['Category'].isin(categories)]
    if term:
        haystack = (view['Description'].astype(str) + ' '
                    + view['Key'].astype(str) + ' '
                    + view['Name'].fillna('').astype(str))
        view = view[haystack.str.contains(term, case=False, na=False,
                                          regex=False)]
    view = view.reset_index(drop=True)

    st.caption(f'{len(view):,} of {len(items):,} items.')
    st.dataframe(view[ITEM_VIEW], hide_index=True, width='stretch',
                 height=320, key='item_table', on_select='rerun',
                 selection_mode='multi-row', column_config=ITEM_CONFIG)

    picked = list(view.iloc[_rows_selected(view, 'item_table')]['ItemID'])
    with st.expander(f'Point {len(picked)} selected item(s) at another factor',
                     expanded=bool(picked)):
        if not picked:
            st.caption('Select one or more items above.')
            return
        # Only factors measuring what these items are measured in.  The rule
        # is enforced on save as well; this is so the wrong one is never
        # offered in the first place.
        units = {unit for unit
                 in view[view['ItemID'].isin(picked)]['Unit'].dropna()
                 if str(unit).strip()}
        pool = (factors[~factors['Obsolete']]
                .sort_values('EffectiveFrom').groupby('FactorKey').tail(1))
        if len(units) == 1:
            unit = next(iter(units))
            pool = pool[[Lookups.compatible(held, unit, lookups)
                         for held in pool['Unit']]]
            st.caption(f'Showing the {len(pool)} factor(s) measured in '
                       f'something compatible with {unit}.')
        labels = {f"{row['Source']}  |  {row['Name']}  |  {row['Region']}  |  "
                  f"{row['Unit']}": row['FactorKey']
                  for _, row in pool.iterrows()}
        with st.form('assign_items'):
            chosen = st.selectbox('Point them at', sorted(labels))
            reason = st.text_area('Reason',
                                  placeholder='Why these items take a '
                                              'different factor.')
            go, undo = st.columns(2)
            assign = go.form_submit_button('Assign', type='primary')
            clear = undo.form_submit_button('Return to distributed')
        if assign:
            try:
                updated, changes = Items.assign(
                    items, picked, labels.get(chosen, ''), reason,
                    factors=factors, lookups=lookups)
            except ValueError as exc:
                st.error(str(exc))
                return
            Items.save(updated)
            _record(changes, 'Items.csv', note=reason)
            _rebuild()
            st.success(f'{len(picked)} item(s) assigned.  Press Rebuild.')
            st.rerun()
        if clear:
            updated, changes = Items.clear_assignment(items, picked)
            Items.save(updated)
            _record(changes, 'Items.csv', note='Returned to distributed.')
            _rebuild()
            st.success('Returned to the distributed factor.  Press Rebuild.')
            st.rerun()


def _lookups_tab(lookups):
    st.caption('Every list the model chooses from.  A list held in code '
               'cannot be added to without a release; these change whenever a '
               'publication does, which is a different rhythm.')
    chosen = st.selectbox('List', sorted(lookups['ListName'].unique()),
                          key='lk_list')
    rows = lookups[lookups['ListName'] == chosen].reset_index(drop=True)
    if chosen == 'Unit':
        st.caption('Emission scale converts the numerator to kg CO2-e and '
                   'quantity scale converts the denominator to the base of '
                   'its dimension.  Together they decide whether a factor may '
                   'price an item, and by how much to convert it.')
    edited = _maintain(rows, key='lookup_editor', height=380, allow_rows=True,
                       disabled=['ListName'], column_config=LOOKUP_CONFIG)
    if st.button('Save list', type='primary', key='lookup_save'):
        saving = edited.copy()
        saving['ListName'] = chosen
        changes = _diff_rows(rows, saving, 'Code')
        if not changes:
            st.info('Nothing changed.')
            return
        whole = pd.concat([lookups[lookups['ListName'] != chosen], saving],
                          ignore_index=True)
        Lookups.save(whole)
        _record(changes, 'Lookups.csv')
        _rebuild()
        st.success('Saved.  Press Rebuild to bring it into the figures.')
        st.rerun()




# ---------------------------------------------------------------------
# IMPORT
# ---------------------------------------------------------------------
# One table.  Every row of the file, checked against what the model holds,
# with the cell at fault coloured and clickable.  Nothing is written until
# the button at the bottom, and the button says what it will do.

OVERWRITE_CHOICES = {
    'No, stop': 'Nothing is imported while a reported month would move.  '
                'The safest, and why it is first.',
    'Ignore them': 'New rows are imported, reported months are left as they '
                   'are.  Right when the model is correct and the file is '
                   'not.',
    'Overwrite them': 'Reported months take the file\'s values.  Right when '
                      'you know why the source changed.',
    'Row by row': 'Tick the ones to overwrite.',
}

VERDICT_MARK = {'rejected': '✕', 'questioned': '⚠', 'restated': '↻',
                'new': '✓', 'unchanged': '·'}

# The cell at fault, and a lighter wash across the rest of its row so the eye
# finds the row first and the cell second.
CELL_TINT = {'rejected': 'background-color: #F1948A; color: #4A1109',
             'questioned': 'background-color: #F7DC6F; color: #4A3B00',
             'restated': 'background-color: #A9CCE3; color: #0E2A3E'}
ROW_TINT = {'rejected': 'background-color: #FDEDEC',
            'questioned': 'background-color: #FEF9E7',
            'restated': 'background-color: #EAF2F8'}

IMPORT_FIELDS = ['Date', 'Activity', 'SubActivity', 'Description',
                 'Department', 'CostCentre', 'UOM', 'Quantity',
                 'ProductGroup', 'Value', 'Source', 'TransactionType']

SHOWN = ['Line', 'Verdict', 'What is wrong', 'Held now'] + IMPORT_FIELDS


def _live_operations():
    """The operations file as it stands, read as text so nothing is coerced."""
    path = os.path.join(DATA_DIR, 'OperationsMetricsActual.csv')
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str)


def _corrections():
    return st.session_state.setdefault('import_corrections', {})


def page_import():
    st.subheader('Import')
    st.caption('Every row of the file, against what the model already holds.  '
               'Click a coloured cell to fix it.  Nothing is written until '
               'the button at the bottom.')

    top = st.columns([3, 1])
    uploaded = top[0].file_uploader(
        'Operations file, csv or Excel', type=['csv', 'xlsx', 'xlsm'],
        key='import_file', label_visibility='collapsed')
    top[1].download_button(
        'Blank template', Importer.template().to_csv(index=False),
        file_name='OperationsImportTemplate.csv', mime='text/csv',
        width='stretch')

    if uploaded is None:
        st.info('Choose a file.  It is read and checked here; nothing is '
                'written until you say so.')
        st.session_state.pop('import_corrections', None)
        return

    try:
        frame, sheets, sheet = Importer.read(uploaded)
    except ValueError as exc:
        st.error(str(exc))
        return

    # -- the columns, only when they need attention --------------------
    proposed, spare = Importer.propose(frame.columns)
    missing = proposed[proposed['Required'] & proposed['Column in file'].eq('')]
    guessed = proposed[proposed['Matched by'].str.contains('guess')]
    mapping = proposed
    if not missing.empty or not guessed.empty:
        with st.expander('Columns need a look', expanded=True):
            if not missing.empty:
                st.error('Nothing matched %s, and a row cannot be read '
                         'without it.' % ', '.join(missing['Field']))
            mapping = st.data_editor(
                proposed, hide_index=True, width='stretch', num_rows='fixed',
                key='import_mapping',
                disabled=['Field', 'Required', 'Matched by', 'What it is for'],
                column_config={'Column in file':
                               st.column_config.SelectboxColumn(
                                   'Column in file',
                                   options=[''] + list(frame.columns))})
    else:
        st.caption('%s: %d rows.  All columns matched by name.%s'
                   % (uploaded.name, len(frame),
                      '  Not used: %s.' % ', '.join(spare) if spare else ''))

    try:
        staged = Importer.apply_mapping(frame, mapping)
    except ValueError as exc:
        st.error(str(exc))
        return

    # Corrections are applied before the check, so the table recolours the
    # moment one is made rather than at some later confirmation step.
    fixes = _corrections()
    for (line, column), value in fixes.items():
        if column in staged.columns and 0 <= line - 2 < len(staged):
            staged.iat[line - 2, staged.columns.get_loc(column)] = value

    live = _live_operations()
    work, found, absent = Import.validate(staged, live)
    counts = work['Verdict'].value_counts()
    stopped = Import.blocking(work)
    restated = work[work['Verdict'] == 'restated']

    # -- what kind of file is this --------------------------------------
    # Asked before the rows, because a file can pass every row check and
    # still be last month's sent again, or half a month, or four thousand
    # rows where eleven hundred was normal.
    about = Import.file_checks(work, live)
    if not about.empty:
        for _, item in about[about['Severity'] == 'rejected'].iterrows():
            st.error('%s.  %s' % (item['Check'], item['Detail']))
        asked = about[about['Severity'] == 'questioned']
        if not asked.empty:
            st.warning('\n\n'.join(
                '**%s.**  %s' % (item['Check'], item['Detail'])
                for _, item in asked.iterrows()))
        stated = about[about['Severity'] == 'note']
        for _, item in stated.iterrows():
            st.caption('%s: %s' % (item['Check'], item['Detail']))

    tiles = st.columns(6)
    for tile, bucket in zip(tiles, Import.BUCKETS):
        number = len(absent) if bucket == 'absent' else int(counts.get(bucket, 0))
        tile.metric(bucket.title(), f'{number:,}')

    if fixes:
        st.caption('%d correction(s) applied on this screen.  They are not in '
                   'the file, and not written anywhere, until you import.'
                   % len(fixes))
    if stopped:
        st.error('%d row(s) cannot be imported.  Click a red cell to fix it, '
                 'or leave them and they are left out.' % stopped)
    elif not restated.empty:
        st.warning('%d row(s) would change a month already reported.'
                   % len(restated))
    else:
        st.success('Every row reads cleanly and nothing already reported '
                   'would move.')

    # -- the one table --------------------------------------------------
    choices = ['Needs attention', 'All rows', 'Already reported', 'New',
               'Unchanged']
    which = st.radio('Show', choices, horizontal=True, key='import_show',
                     label_visibility='collapsed')
    if which == 'Needs attention':
        rows = work[work['Verdict'].isin(['rejected', 'questioned'])]
    elif which == 'Already reported':
        rows = restated
    elif which == 'New':
        rows = work[work['Verdict'] == 'new']
    elif which == 'Unchanged':
        rows = work[work['Verdict'] == 'unchanged']
    else:
        rows = work

    capped = rows.head(500).reset_index(drop=True)
    if capped.empty:
        st.caption('No rows in this view.')
        selection = None
    else:
        view = capped[['_row', 'Verdict', 'Issue'] + IMPORT_FIELDS].copy()
        view.insert(3, 'Held now', capped['Was'].values)
        view = view.rename(columns={'_row': 'Line', 'Issue': 'What is wrong'})
        view['Verdict'] = view['Verdict'].map(VERDICT_MARK)

        # Which cell is at fault, per row, from the findings themselves.
        at_fault = {}
        if not found.empty:
            for _, finding in found.iterrows():
                at_fault.setdefault(int(finding['Line']), []).append(
                    (finding['Column'], finding['Severity']))

        verdicts = dict(zip(capped['_row'], capped['Verdict']))

        def paint(frame):
            styles = pd.DataFrame('', index=frame.index, columns=frame.columns)
            for position, line in enumerate(view['Line']):
                verdict = verdicts.get(line, '')
                wash = ROW_TINT.get(verdict, '')
                if wash:
                    styles.iloc[position] = wash
                for column, severity in at_fault.get(int(line), []):
                    if column in styles.columns:
                        styles.iloc[position,
                                    styles.columns.get_loc(column)] = \
                            CELL_TINT.get(severity, '')
            return styles

        selection = st.dataframe(
            view.style.apply(paint, axis=None), hide_index=True,
            width='stretch', height=420, key='import_table',
            on_select='rerun', selection_mode=['multi-row', 'single-cell'],
            column_config={
                'Line': st.column_config.NumberColumn('Line', width='small',
                                                      format='%d'),
                'Verdict': st.column_config.TextColumn('', width='small'),
                'What is wrong': st.column_config.TextColumn(
                    'What is wrong', width='large',
                    help='The first finding.  Select the row to read every '
                         'finding against it in full.'),
                'Held now': st.column_config.NumberColumn(
                    'Held now', format='%.6g', width='small',
                    help='What the model holds for this row today.'),
                'Quantity': st.column_config.TextColumn('In this file',
                                                        width='small'),
            })
        if len(rows) > 500:
            st.caption('Showing the first 500 of %d.' % len(rows))

        _fix_panel(selection, view, capped, found)

    if not absent.empty:
        with st.expander('%d row(s) the model holds and this file does not'
                         % len(absent)):
            st.caption('Left alone.  An import never deletes: a file that '
                       'arrived short is far commoner than a line that '
                       'genuinely stopped, and only one of those two '
                       'mistakes can be undone.')
            st.dataframe(absent[['Date', 'SubActivity', 'Description',
                                 'CostCentre', 'Quantity']].head(100),
                         hide_index=True, width='stretch', height=200)

    # -- the reported months, and writing it ---------------------------
    policy = 'No, stop'
    if not restated.empty:
        policy = st.radio(
            'If the file changes a month already reported',
            list(OVERWRITE_CHOICES), horizontal=True, key='import_policy',
            captions=list(OVERWRITE_CHOICES.values()))
        if policy == 'Row by row':
            side = restated[['_row', 'Date', 'SubActivity', 'Description']].copy()
            side['Held now'] = restated['Was'].values
            side['In this file'] = restated['_quantity'].values
            side['Overwrite'] = False
            decided = st.data_editor(
                side, hide_index=True, width='stretch', num_rows='fixed',
                key='import_decide',
                disabled=[c for c in side.columns if c != 'Overwrite'],
                column_config={
                    '_row': st.column_config.NumberColumn('Line', format='%d'),
                    'Held now': st.column_config.NumberColumn(
                        'Held now', format='%.6g'),
                    'In this file': st.column_config.NumberColumn(
                        'In this file', format='%.6g')})
            st.session_state['import_decisions'] = decided

    will_add = int(counts.get('new', 0))
    if policy == 'Overwrite them':
        will_change = len(restated)
    elif policy == 'Row by row':
        decided = st.session_state.get('import_decisions')
        will_change = (int(decided['Overwrite'].sum())
                       if decided is not None and 'Overwrite' in decided else 0)
    else:
        will_change = 0

    stop = policy == 'No, stop' and not restated.empty
    st.divider()
    if stop:
        st.error('%d row(s) would change a reported month and the choice is '
                 'to stop.  Choose what to do with them above.' % len(restated))
    else:
        st.caption('%d new row(s) added, %d reported row(s) overwritten, '
                   '%d left out as unreadable.  Nothing is deleted.'
                   % (will_add, will_change, stopped))

    confirm = st.checkbox('I have looked at the rows above',
                          key='import_confirm')
    if st.button('Import', type='primary', disabled=stop or not confirm,
                 key='import_apply'):
        added, changed = _apply_import(work, policy, uploaded.name)
        st.session_state.pop('import_corrections', None)
        st.success('%d row(s) added, %d overwritten.  Press Rebuild to bring '
                   'it into the figures.' % (added, changed))
        _rebuild()


def _fix_panel(selection, view, capped, found):
    """The selected row, whole, with everything known against it.

    One panel for both ways in.  A clicked cell says which field to point at;
    a selected row says nothing more than which row.  Either way the whole
    line is shown, because the fault named in one column is often corrected
    in another and nobody can tell which without the rest of the row.
    """
    state = getattr(selection, 'selection', None) or {}
    cells = list(getattr(state, 'cells', None) or state.get('cells') or [])
    picked = list(getattr(state, 'rows', None) or state.get('rows') or [])
    fixes = _corrections()

    position, pointed = None, None
    if cells:
        position, pointed = cells[0][0], cells[0][1]
    elif len(picked) == 1:
        position = picked[0]

    if position is not None:
        _row_form(position, pointed, view, capped, found, fixes)
        return

    if picked:
        _bulk_form(picked, view, fixes)
        return

    st.caption('Select a row, or click any cell in it, to see the whole line '
               'and everything known against it.')


def _row_form(position, pointed, view, capped, found, fixes):
    """One line: what is wrong with it, what the model holds, every field."""
    line = int(view.at[position, 'Line'])
    verdict = str(capped.iloc[position]['Verdict'])

    against = found[found['Line'] == line] if not found.empty else found
    if len(against):
        for _, finding in against.iterrows():
            speak = {'rejected': st.error, 'questioned': st.warning,
                     'restated': st.info}.get(finding['Severity'], st.info)
            speak('**%s**  %s' % (finding['Column'], finding['Finding']))
    else:
        st.success('Nothing is wrong with this row.  It is %s.' % verdict)

    held = view.at[position, 'Held now']
    if pd.notna(held):
        st.caption('The model holds %s for this row today, and this file says '
                   '%s.' % (f'{held:,.6g}', view.at[position, 'Quantity']))
    if pointed and pointed in IMPORT_FIELDS:
        st.caption('You clicked %s.  The whole row is below, because the '
                   'column at fault is not always the column to change.'
                   % pointed)

    with st.form('fix_row_%d' % line):
        st.markdown('**Line %d**' % line)
        entered = {}
        for block in range(0, len(IMPORT_FIELDS), 3):
            columns = st.columns(3)
            for slot, column in zip(columns, IMPORT_FIELDS[block:block + 3]):
                entered[column] = slot.text_input(
                    column, value=str(view.at[position, column]),
                    key='row_%d_%s' % (line, column))
        left, right = st.columns(2)
        if left.form_submit_button('Apply to this row', type='primary'):
            for column, value in entered.items():
                if value != str(view.at[position, column]):
                    fixes[(line, column)] = value
            st.rerun()
        if right.form_submit_button('Undo corrections on this row'):
            for column in IMPORT_FIELDS:
                fixes.pop((line, column), None)
            st.rerun()


def _bulk_form(picked, view, fixes):
    """One field, the same value, across every selected row."""
    lines = [int(view.at[position, 'Line']) for position in picked]
    with st.form('fix_rows'):
        st.markdown('**%d rows selected**' % len(lines))
        st.caption('Set one field to the same value on all of them.  Select a '
                   'single row instead to see that line in full.')
        column = st.selectbox('Field', IMPORT_FIELDS, key='bulk_field')
        replacement = st.text_input('Value for all of them', key='bulk_value')
        left, right = st.columns(2)
        if left.form_submit_button('Apply to all', type='primary'):
            for line in lines:
                fixes[(line, column)] = replacement
            st.rerun()
        if right.form_submit_button('Undo on these rows'):
            for line in lines:
                fixes.pop((line, column), None)
            st.rerun()


def _fields_at_fault(trouble):
    """The field names a finding sentence refers to, best effort."""
    return [(field, True) for field in IMPORT_FIELDS
            if field.lower() in str(trouble).lower()]


def _apply_import(work, policy, filename):
    """Write the accepted rows into the operations file.

    An import never deletes.  A row the model holds and the file does not is
    left where it is, because a file that arrived short is far commoner than
    a line that genuinely stopped, and one of those two mistakes can be
    undone.
    """
    path = os.path.join(DATA_DIR, 'OperationsMetricsActual.csv')
    live = _live_operations()
    columns = list(live.columns) if not live.empty else IMPORT_FIELDS

    adding = work[work['Verdict'] == 'new']
    changed = 0

    if policy == 'Overwrite them':
        overwrite = work[work['Verdict'] == 'restated']
    elif policy == 'Row by row':
        decided = st.session_state.get('import_decisions')
        keep = (set(decided.loc[decided['Overwrite'], '_row'])
                if decided is not None and 'Overwrite' in decided else set())
        overwrite = work[work['_row'].isin(keep)]
    else:
        overwrite = work.iloc[0:0]

    if not overwrite.empty:
        live = live.copy()
        live['_key'] = Import.row_key(live)
        replacing = dict(zip(overwrite['_key'], overwrite['Quantity']))
        touched = live['_key'].isin(replacing)
        live.loc[touched, 'Quantity'] = live.loc[touched, '_key'].map(replacing)
        changed = int(touched.sum())
        live = live.drop(columns=['_key'])

    if not adding.empty:
        fresh = adding.copy()
        for column in columns:
            if column not in fresh.columns:
                fresh[column] = ''
        live = pd.concat([live, fresh[columns]], ignore_index=True)

    temporary = path + '.writing'
    live.to_csv(temporary, index=False, encoding='utf-8')
    os.replace(temporary, path)

    _record([{'Path': 'OperationsMetricsActual.csv',
              'From': '%d rows' % (len(live) - len(adding)),
              'To': '%d rows' % len(live)}],
            'OperationsMetricsActual.csv',
            note='Imported %s: %d added, %d overwritten, "%s".'
                 % (filename, len(adding), changed, policy))
    return len(adding), changed

# ---------------------------------------------------------------------
# DIRECTOR
# ---------------------------------------------------------------------

PAGES = ('Verify', 'Import', 'Inventory', 'Scope 1 and 2', 'Scope 3',
         'Factors',
         'Assumptions', 'Capital goods', 'Credits', 'Changes', 'History')

# Pages that read figures and nothing else.  These run off the published
# file, which is a read rather than a projection.
FIGURE_PAGES = ('Verify', 'Inventory', 'Scope 1 and 2', 'Scope 3', 'Changes')


def _build_controls():
    """Rebuild, and publish.  Two buttons, and they do different things."""
    side = st.sidebar
    side.divider()
    side.caption(Publisher.published_summary())

    if _stale():
        side.warning('An input has changed since this build was made.  '
                     'Rebuild to see it.')

    if side.button('Rebuild', width='stretch',
                   type='primary' if _stale() else 'secondary',
                   help='Rebuild from the current assumptions, capital '
                        'items, factors and overrides.  Nothing is '
                        'written.'):
        _force_rebuild()
        st.rerun()

    # Publishing is offered once the Changes page has been read and the
    # build reconciled.  There is no way to publish a build nobody has
    # looked at, and an edit made afterwards withdraws the permission.
    ready = st.session_state.get('pending_ok') is True
    if side.button('Publish', type='primary', width='stretch',
                   disabled=not ready,
                   help='Write this build to the published figures.'
                        if ready else
                        'Open Changes first.  Publishing is offered once the '
                        'build has been reviewed there and reconciles.'):
        st.session_state['confirm_publish'] = True

    if st.session_state.get('confirm_publish'):
        with side.form('publish_form'):
            st.markdown('**Publish this build?**')
            st.caption('The reporting application will read these figures '
                       'from now on.  The previous build is archived and can '
                       'be restored.')
            notes = st.text_input('Publication note',
                                  placeholder='What changed, and why.')
            go, stop = st.columns(2)
            confirmed = go.form_submit_button('Yes, publish',
                                              type='primary')
            cancelled = stop.form_submit_button('Cancel')
        if cancelled:
            st.session_state.pop('confirm_publish', None)
            st.rerun()
        if confirmed:
            _do_publish(notes)


def _do_publish(notes):
    _, precomputed, table = _inventory()
    log = Publisher.publish(
        table,
        outstanding=st.session_state.get('pending_outstanding'),
        assumptions=st.session_state.get('pending_assumptions'),
        inputs=TRACKED_INPUTS,
        actuals_to=DEFAULT_ACTUALS_TO_DATE,
        forecast_to=table['Date'].max(), notes=notes)
    st.session_state.pop('confirm_publish', None)
    st.session_state.pop('pending_ok', None)
    # What was just written is the new starting point, so the next thing
    # this session shows is what happened after the publication.
    st.session_state['session_baseline'] = _summarise(table)
    st.session_state['session_opened'] = datetime.now()
    _published.clear()
    st.sidebar.success(f"Published build {log['BuildID']}.")
    st.rerun()


def main():
    st.sidebar.title('Emissions Data Builder')
    st.sidebar.caption('Builds the inventory.  The reporting application '
                       'reads what is published here.')
    page = st.sidebar.radio('Section', PAGES, label_visibility='collapsed')
    _build_controls()

    # Pages that touch no inventory load nothing, so entering a capital item
    # or a credit transaction does not wait on a projection.
    if page == 'Credits':
        page_credits()
        return
    if page == 'History':
        page_history()
        return
    if page == 'Factors':
        page_factors()
        return

    reference = load_reference()
    if page == 'Capital goods':
        page_capital(reference)
        return
    if page == 'Assumptions':
        page_assumptions(reference)
        return

    _, precomputed, table = _inventory()
    if page == 'Import':
        page_import()
    elif page == 'Verify':
        page_verify(precomputed, table)
    elif page == 'Inventory':
        page_explore(table)
    elif page == 'Scope 1 and 2':
        page_scope12(precomputed, table)
    elif page == 'Scope 3':
        page_scope3(precomputed, reference)
    elif page == 'Changes':
        page_changes(reference)


if __name__ == '__main__':
    main()
