"""Publication of the canonical emissions table.

The reporting application reads what was published, not what the engines
happen to compute this session.  That is the point of the step: a figure in a
disclosure should change when somebody decides it changes, not because an
input file moved underneath it.

Publishing writes four files and an archive copy:

    EmissionsTable.csv.gz      the canonical table
    EmissionsBuildLog.json     what went into the build, and what it produced
    EmissionsOutstanding.csv   what is known to be missing
    EmissionsAssumptions.csv   every user-maintained assumption in force

Compressed because the table is the whole inventory at monthly grain and the
uncompressed file is a hundred megabytes.  Gzip is read natively by pandas and
by every spreadsheet worth the name, so this costs nothing and adds no
dependency.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime

import pandas as pd

from CalcEmissionsTable import COLUMNS, build_id_for

__all__ = [
    'TABLE_PATH', 'FAST_PATH', 'BUILD_LOG_PATH', 'OUTSTANDING_PATH',
    'ASSUMPTIONS_PATH', 'REPORTING_DIR', 'REPORTING_FRAMES', 'compact',
    'archived_builds', 'load_archived', 'aggregate_for_publication',
    'publish', 'write_reporting_pack', 'load_published', 'load_build_log',
    'compare_builds', 'published_summary',
]

from Paths import ROOT as BASE_DIR
DATA_DIR = os.path.join(BASE_DIR, 'Data')
ARCHIVE_DIR = os.path.join(DATA_DIR, 'Published')

TABLE_PATH = os.path.join(DATA_DIR, 'EmissionsTable.csv.gz')
# The same table again, columnar.  The gzipped csv is what gets distributed,
# because anything can open it; the parquet is what this application reads,
# because opening the csv costs six seconds and half a gigabyte of Python
# strings every time and the application opens it constantly.  They are
# written together and never separately, so the two cannot drift.
FAST_PATH = os.path.join(DATA_DIR, 'EmissionsTable.parquet')
BUILD_LOG_PATH = os.path.join(DATA_DIR, 'EmissionsBuildLog.json')
OUTSTANDING_PATH = os.path.join(DATA_DIR, 'EmissionsOutstanding.csv')
ASSUMPTIONS_PATH = os.path.join(DATA_DIR, 'EmissionsAssumptions.csv')

# The reporting pack: every frame the reporting application draws, written
# by the publication that produced them.  The application reads these and
# computes no inventory of its own, so the two cannot disagree: what is on
# the screen is what was published, and a figure that has not been published
# is not on the screen.
#
# The published table is the record of the inventory and stays the record.
# These are the same figures in the shapes the views were built around, kept
# beside it rather than derived again by a second program from the sources.
REPORTING_DIR = os.path.join(DATA_DIR, 'Reporting')

# Each frame, and the attribute of the build it comes from.  One list, so
# writing and reading cannot fall out of step with each other.
REPORTING_FRAMES = {
    'Ghg': 'ghg_df',
    'Monthly': 'monthly',
    'AnnualCY': 'annual_cy',
    'AnnualFY': 'annual_fy',
    'GhgAnnualCY': 'ghg_annual_cy',
    'GhgAnnualFY': 'ghg_annual_fy',
    'GhgMonthly': 'ghg_monthly',
    'GriAnnual': 'gri_annual',
    'GriSource': 'gri_source',
    'SafeguardSource': 'safeguard_source',
    'SafeguardOre': 'safeguard_ore',
    'SafeguardElectricity': 'safeguard_electricity',
}

# The Scope 3 result, in the parts it is made of.
REPORTING_SCOPE3 = {
    'Scope3Detail': 'detail',
    'Scope3AnnualCY': 'annual_cy',
    'Scope3AnnualFY': 'annual_fy',
    'Scope3Rates': 'rates',
    'Scope3Exclusions': 'exclusions',
}
SCOPE3_STATE = 'Scope3State.json'
REPORTING_LOG = 'ReportingPack.json'

# The grain the table is published at.  Everything that identifies where a
# figure came from, what factor produced it and which framework it counts
# towards is a key; only the measures are summed.  A transaction line is not
# preserved, because the transaction is in the physicals and the Scope 3
# detail and duplicating it here would treble the file for no new fact.
PUBLISH_KEYS = [
    'Date', 'FinancialYear', 'CalendarYear', 'Dataset', 'RowKind',
    'IsForecast', 'IsEstimated',
    'Activity', 'SubActivity', 'Department', 'CostCentre',
    'UOM', 'GHGScope', 'Scope3Category', 'Scope3CategoryName',
    'EmissionSource', 'EmissionFactor', 'FactorUOM', 'FactorSet',
    'FactorSource', 'FactorDerivation', 'FactorRegulated', 'FactorYear',
    'CalculationMethod',
    'ActivityDataSource', 'DateBasis', 'DataQuality', 'NGERApplicable',
    'SafeguardApplicable', 'GRIApplicable', 'BuildID',
]

MEASURES = ['Quantity', 'SpendAUD', 'Emissions_tCO2e', 'Energy_GJ']


def aggregate_for_publication(table):
    """Collapse the line table to the published grain.

    Every measure is preserved exactly; only the count of source lines is
    added, so a reader can see how many transactions sit behind a figure
    without carrying them.
    """
    if table is None or table.empty:
        return pd.DataFrame(columns=PUBLISH_KEYS + MEASURES + ['SourceLines'])
    grouped = table.groupby(PUBLISH_KEYS, observed=True, dropna=False).agg(
        Quantity=('Quantity', 'sum'),
        SpendAUD=('SpendAUD', 'sum'),
        Emissions_tCO2e=('Emissions_tCO2e', 'sum'),
        Energy_GJ=('Energy_GJ', 'sum'),
        SourceLines=('Emissions_tCO2e', 'size'),
    ).reset_index()
    return grouped.sort_values(['Date', 'GHGScope', 'Scope3Category',
                                'Department'], na_position='last') \
        .reset_index(drop=True)


def _fingerprint(path):
    """Size and modification time of an input, enough to spot a change."""
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return {'bytes': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(
                timespec='seconds')}


def _write_frame(frame, name):
    """One frame of the pack.  Nothing else writes these.

    Parquet where the environment has an engine, because the largest frame
    is seven hundred thousand rows and the application opens it on every
    start; a gzipped csv where it does not, so the pack is written either
    way and the reader takes whichever is there.
    """
    frame = pd.DataFrame() if frame is None else pd.DataFrame(frame)
    # A category of mixed types, and an index the reader does not want, are
    # the two things parquet refuses.  Both are the writer's to settle.
    frame = frame.reset_index(drop=True)
    for column in frame.columns:
        if str(frame[column].dtype) == 'category':
            frame[column] = frame[column].astype(object)
    path = os.path.join(REPORTING_DIR, name + '.parquet')
    plain = os.path.join(REPORTING_DIR, name + '.csv.gz')
    try:
        frame.to_parquet(path, index=False)
        if os.path.exists(plain):
            os.remove(plain)
        return path
    except Exception:
        frame.to_csv(plain, index=False, compression='gzip')
        if os.path.exists(path):
            os.remove(path)
        return plain


def write_reporting_pack(precomputed, build_id, built_at=None):
    """Write every frame the reporting application draws.

    Called by publish(), with the build that was published.  The application
    reads these instead of loading the sources and computing again, so it
    reports the published figures and nothing else.

    Returns the list of files written.
    """
    if precomputed is None:
        return []
    os.makedirs(REPORTING_DIR, exist_ok=True)
    written = []
    for name, attribute in REPORTING_FRAMES.items():
        written.append(_write_frame(getattr(precomputed, attribute, None),
                                    name))
    scope3 = getattr(precomputed, 'scope3', None)
    for name, attribute in REPORTING_SCOPE3.items():
        written.append(_write_frame(getattr(scope3, attribute, None), name))
    # What the Scope 3 result carries that is not a frame.
    state = {
        'outstanding': list(getattr(scope3, 'outstanding', None) or []),
        'coverage': dict(getattr(scope3, 'coverage', None) or {}),
        'notes': dict(getattr(scope3, 'notes', None) or {}),
    }
    with open(os.path.join(REPORTING_DIR, SCOPE3_STATE), 'w',
              encoding='utf-8') as handle:
        json.dump(state, handle, indent=2, default=str)
    with open(os.path.join(REPORTING_DIR, REPORTING_LOG), 'w',
              encoding='utf-8') as handle:
        json.dump({'BuildID': build_id,
                   'BuiltAt': (built_at or datetime.now()).isoformat(
                       timespec='seconds') if not isinstance(built_at, str)
                   else built_at,
                   'Frames': sorted(os.path.basename(p) for p in written)},
                  handle, indent=2, default=str)
    return written


def publish(table, outstanding=None, assumptions=None, inputs=None,
            actuals_to=None, forecast_to=None, notes='', archive=True,
            precomputed=None):
    """Write the reviewed table as the published inventory.

    Args:
        table:       the canonical line table.
        outstanding: DataFrame of known gaps, or None.
        assumptions: DataFrame of user-maintained assumptions in force.
        inputs:      paths whose size and date are recorded, so a later build
                     can be shown to have used the same inputs or not.
        actuals_to:  last recorded month.
        forecast_to: last forecast month.
        notes:       free text from whoever published it.
        archive:     keep a copy under the build identifier.
        precomputed: the build the table was made from.  Its frames are
                     written as the reporting pack, which is what the
                     reporting application reads.

    Returns:
        The build log that was written.
    """
    published = aggregate_for_publication(table)
    build_id = (str(table['BuildID'].iloc[0]) if len(table)
                else build_id_for('empty'))

    os.makedirs(DATA_DIR, exist_ok=True)
    published.to_csv(TABLE_PATH, index=False, compression='gzip')
    try:
        published.to_parquet(FAST_PATH, index=False)
    except Exception:
        # No parquet engine here.  The csv is the published artefact and the
        # parquet is a convenience, so its absence slows the application
        # down and changes nothing about what was published.
        if os.path.exists(FAST_PATH):
            os.remove(FAST_PATH)

    if outstanding is not None:
        pd.DataFrame(outstanding).to_csv(OUTSTANDING_PATH, index=False)
    if assumptions is not None:
        pd.DataFrame(assumptions).to_csv(ASSUMPTIONS_PATH, index=False)

    emissions = published[published['RowKind'] == 'Emission']
    by_scope = emissions.groupby('GHGScope', observed=True)[
        'Emissions_tCO2e'].sum().round(2).to_dict()
    by_basis = emissions.groupby('Dataset', observed=True)[
        'Emissions_tCO2e'].sum().round(2).to_dict()

    log = {
        'BuildID': build_id,
        'BuiltAt': datetime.now().isoformat(timespec='seconds'),
        'ActualsTo': str(actuals_to) if actuals_to is not None else None,
        'ForecastTo': str(forecast_to) if forecast_to is not None else None,
        'Rows': {'lines': int(len(table)), 'published': int(len(published))},
        'Totals_tCO2e': {'by_scope': by_scope, 'by_basis': by_basis,
                         'total': round(float(
                             emissions['Emissions_tCO2e'].sum()), 2)},
        'Outstanding': int(len(outstanding)) if outstanding is not None else 0,
        'Inputs': {os.path.basename(p): _fingerprint(p)
                   for p in (inputs or [])},
        'Notes': notes,
    }
    with open(BUILD_LOG_PATH, 'w', encoding='utf-8') as handle:
        json.dump(log, handle, indent=2, default=str)

    # The frames the reporting application draws, from the same build.
    write_reporting_pack(precomputed, build_id, log['BuiltAt'])

    if archive:
        # A published build is kept whole, so an earlier disclosure can be
        # reproduced rather than argued about.
        #
        # Named for when it was published, not for what it contains.  The
        # build identifier is derived from the inputs, so republishing
        # unchanged inputs produced the same name and quietly overwrote the
        # copy already there - which is exactly the history somebody would
        # come here for.  A publication is an event and gets its own folder.
        folder = os.path.join(ARCHIVE_DIR, f'{_archive_stamp()}_{build_id}')
        os.makedirs(folder, exist_ok=True)
        for path in (TABLE_PATH, FAST_PATH, BUILD_LOG_PATH,
                     OUTSTANDING_PATH, ASSUMPTIONS_PATH):
            if os.path.exists(path):
                shutil.copy2(path, os.path.join(folder,
                                                os.path.basename(path)))
    return log


def compact(frame):
    """Text columns as categories.

    Every text column in this table is a label from a short list; the widest
    holds 186 distinct values across three hundred thousand rows.  Held as
    Python strings they cost 484 MB and every grouping walks them one object
    at a time.  Held as categories they cost 34 MB and a grouping is an
    integer operation.  Nothing about the values changes.
    """
    if frame.empty:
        return frame
    for column in frame.columns:
        if frame[column].dtype == object:
            # A blank was published as a blank and has to read back as one.
            # read_csv turns an empty field into NaN, which then sorts
            # against the strings beside it and raises, and reads as "not
            # asked" where the table meant "nothing to say".  A physical row
            # carries no scope, and that is a statement, not a gap.
            frame[column] = frame[column].fillna('').astype('category')
    return frame


def load_published(path=None):
    """The published table, or an empty frame where nothing is published.

    Read from the columnar copy where one is there, because it is the same
    table and it opens in a fraction of a second.
    """
    if path is None and os.path.exists(FAST_PATH):
        try:
            return compact(pd.read_parquet(FAST_PATH))
        except Exception:
            pass
    explicit = path is not None
    path = path or TABLE_PATH
    if not os.path.exists(path):
        return pd.DataFrame(columns=PUBLISH_KEYS + MEASURES)
    frame = pd.read_csv(path, parse_dates=['Date'])
    for column in ('IsForecast', 'IsEstimated', 'NGERApplicable',
                   'SafeguardApplicable', 'GRIApplicable'):
        if column in frame.columns:
            frame[column] = frame[column].astype(str).str.lower().isin(
                ['true', '1', 'yes'])
    frame = compact(frame)
    # A build published before the columnar copy existed, or published from
    # an environment without a parquet engine.  Write it now rather than pay
    # the six second read on every start until the next publish.
    if not explicit and not os.path.exists(FAST_PATH):
        try:
            frame.to_parquet(FAST_PATH, index=False)
        except Exception:
            pass
    return frame


# Folders written before publications were dated carry the build
# identifier alone.  Both shapes are read; only the new shape is written.
_DATED_FOLDER = re.compile(r'^(\d{4}-\d{2}-\d{2}_\d{6})_(.+)$')


def _archive_stamp():
    return datetime.now().strftime('%Y-%m-%d_%H%M%S')


def _split_folder(name):
    """(published_at, build_id) from a folder name, in either shape."""
    match = _DATED_FOLDER.match(name)
    if not match:
        return '', name
    stamp, build_id = match.groups()
    return f'{stamp[:10]} {stamp[11:13]}:{stamp[13:15]}:{stamp[15:]}', build_id


def archived_builds():
    """Every published build still on disk, newest first.

    A build is archived whole under its own identifier, so an earlier
    disclosure can be reproduced rather than argued about.  The identifier is
    derived from the inputs, so republishing unchanged inputs replaces the
    archived copy rather than adding a second one that says the same thing.
    """
    if not os.path.isdir(ARCHIVE_DIR):
        return pd.DataFrame(columns=['BuildID', 'BuiltAt', 'Total_tCO2e',
                                     'Notes'])
    rows = []
    for name in sorted(os.listdir(ARCHIVE_DIR)):
        folder = os.path.join(ARCHIVE_DIR, name)
        table = os.path.join(folder, os.path.basename(TABLE_PATH))
        if not os.path.exists(table):
            continue
        published_at, build_id = _split_folder(name)
        log = {}
        log_path = os.path.join(folder, os.path.basename(BUILD_LOG_PATH))
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as handle:
                    log = json.load(handle) or {}
            except (ValueError, OSError):
                log = {}
        rows.append({
            'Folder': name,
            'BuildID': build_id,
            # An undated folder predates the change; its build log says when
            # the build was made, which is the closest thing it has.
            'PublishedAt': published_at or str(log.get('BuiltAt', ''))[:19]
                           .replace('T', ' '),
            'Total_tCO2e': (log.get('Totals_tCO2e') or {}).get('total'),
            'Notes': log.get('Notes', ''),
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values('PublishedAt', ascending=False).reset_index(
        drop=True)


def load_archived(folder_name):
    """One archived publication's table, read like the published one.

    Takes the folder name rather than the build identifier, because one
    build can have been published more than once and each publication is
    kept.
    """
    folder = os.path.join(ARCHIVE_DIR, str(folder_name))
    fast = os.path.join(folder, os.path.basename(FAST_PATH))
    if os.path.exists(fast):
        try:
            return compact(pd.read_parquet(fast))
        except Exception:
            pass
    table = os.path.join(folder, os.path.basename(TABLE_PATH))
    if not os.path.exists(table):
        return pd.DataFrame(columns=PUBLISH_KEYS + MEASURES)
    return load_published(path=table)


def load_build_log(path=None):
    """The build log, or None where nothing is published."""
    path = path or BUILD_LOG_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def published_summary():
    """One line describing what is currently published, for a status bar."""
    log = load_build_log()
    if not log:
        return 'No published build'
    total = log.get('Totals_tCO2e', {}).get('total', 0)
    return (f"Build {log.get('BuildID', '?')} "
            f"· {log.get('BuiltAt', '')[:16].replace('T', ' ')} "
            f"· {total:,.0f} tCO2-e")


# ---------------------------------------------------------------------
# PREVIEW AGAINST PUBLISHED
# ---------------------------------------------------------------------

def compare_builds(preview, published=None, basis='CY', top=12):
    """What changing an assumption would do, before it does it.

    Returns a dict of frames:
        headline   scope by basis, published against preview
        annual     year by year, actual and forecast separated
        category   Scope 3 by category
        movers     the largest absolute changes, by year and scope

    An empty published table is not an error; it is the first build, and
    everything reads as new.
    """
    published = load_published() if published is None else published
    year_column = 'CalendarYear' if basis == 'CY' else 'FinancialYear'

    def _emissions(frame):
        if frame is None or frame.empty:
            return pd.DataFrame(columns=[year_column, 'Dataset', 'GHGScope',
                                         'Scope3Category', 'Emissions_tCO2e'])
        rows = frame[frame['RowKind'] == 'Emission'] \
            if 'RowKind' in frame.columns else frame
        return rows

    now, new = _emissions(published), _emissions(preview)

    def _group(frame, keys):
        if frame.empty:
            return pd.Series(dtype='float64')
        return frame.groupby(keys, observed=True)['Emissions_tCO2e'].sum()

    def _side_by_side(keys, names):
        combined = pd.concat([
            _group(now, keys).rename('Published'),
            _group(new, keys).rename('Preview'),
        ], axis=1).fillna(0.0)
        combined['Change'] = combined['Preview'] - combined['Published']
        # Divide only where there is something to divide by.  Replacing the
        # zeros with a null would turn the column to object and take the
        # division with it.
        base = combined['Published'].where(combined['Published'] != 0.0)
        combined['ChangePct'] = combined['Change'] / base * 100.0
        out = combined.reset_index()
        out.columns = names + ['Published', 'Preview', 'Change', 'ChangePct']
        return out.round(2)

    headline = _side_by_side(['Dataset', 'GHGScope'], ['Dataset', 'Scope'])
    annual = _side_by_side([year_column, 'Dataset', 'GHGScope'],
                           ['Year', 'Dataset', 'Scope'])
    category = _side_by_side(['Scope3Category'], ['Scope3Category'])
    movers = annual.reindex(
        annual['Change'].abs().sort_values(ascending=False).index).head(top)

    return {'headline': headline, 'annual': annual,
            'category': category[category['Scope3Category'].notna()],
            'movers': movers.reset_index(drop=True)}
