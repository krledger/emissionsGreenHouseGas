"""What a file would do to the model, decided before it does it.

An import is not a file copy.  Four hundred lines arrive every month, most of
them ordinary, a few of them new, and a handful of them quietly restating a
month that has already been reported.  The last group is the dangerous one:
nothing about a changed number looks different from an unchanged one, and by
the time it is noticed it is in a disclosure.

So every row is placed in exactly one bucket, and the bucket decides what the
screen does with it:

    new         no row like it in the model.  Import it.
    unchanged   already there, identical.  Nothing to do.
    restated    already there, and different.  A period already reported is
                moving, so somebody says yes to it by name.
    absent      in the model for a month this file covers, and not in the
                file.  Either it stopped or it was dropped.
    rejected    cannot be imported at all.  A blank activity or a quantity
                that is not a number has no sensible interpretation.
    questioned  can be imported, and should not be without a look.  A
                negative quantity, a fifty fold jump, a unit that changed.

Rejected and questioned are deliberately different.  A rejected row has no
meaning; a questioned row has one and it may be wrong.  Refusing them both
teaches people to click past the warnings, and accepting them both is how a
fifty fold spike reaches a published figure.

Every finding names the row, the column and what is wrong with it in words a
person can act on.  "Invalid" is not a finding.
"""

import numpy as np
import pandas as pd

import LoaderLookups as Lookups
from Config import (IMPORT_SPIKE_MULTIPLE, IMPORT_SPIKE_MINIMUM,
                    IMPORT_RESTATE_TOLERANCE)

# What makes a row the same row between one file and the next.  Verified
# unique across the whole operations history: thirteen thousand rows, no
# collisions.  Quantity and Value are deliberately not in it, because a
# changed quantity is the same row with a different number, which is exactly
# what a restatement is.
IDENTITY = ('Date', 'Activity', 'SubActivity', 'Description', 'Department',
            'CostCentre', 'UOM', 'Identifier')

# Columns a row cannot be imported without.
MANDATORY = ('Date', 'Activity', 'SubActivity', 'UOM', 'Quantity')

BUCKETS = ('rejected', 'questioned', 'restated', 'absent', 'new', 'unchanged')


def _text(series):
    return series.fillna('').astype(str).str.strip()


def row_key(frame):
    """The identity of every row, as one string."""
    parts = [_text(frame[column]) if column in frame.columns
             else pd.Series([''] * len(frame), index=frame.index)
             for column in IDENTITY]
    return parts[0].str.cat(parts[1:], sep='|')


def _numeric(series):
    """Quantities as numbers, keeping what could not be read.

    A thousands separator is the commonest fault in a file typed by a person
    and the commonest thing silently dropped by a parser, so it is named
    rather than coerced.
    """
    text = _text(series)
    cleaned = text.str.replace(',', '', regex=False)
    value = pd.to_numeric(cleaned, errors='coerce')
    unreadable = value.isna() & text.ne('')
    had_separator = unreadable | (text.str.contains(',', regex=False)
                                  & value.notna())
    return value, unreadable, had_separator


def validate(staged, live=None, lookups=None):
    """Place every row, and say why.

    Returns the staged frame with the verdict on it, and a findings frame of
    one row per problem: which row, which column, how bad, and what to do.
    """
    lookups = Lookups.load() if lookups is None else lookups
    work = staged.copy().reset_index(drop=True)
    work['_row'] = work.index + 2          # the line number in the file
    work['_key'] = row_key(work)

    findings = []

    def note(mask, column, severity, what):
        for position in work.index[mask]:
            findings.append({
                'Line': int(work.at[position, '_row']),
                'Column': column,
                'Severity': severity,
                'Finding': what,
                'Value': str(work.at[position, column])[:60]
                         if column in work.columns else '',
                '_key': work.at[position, '_key'],
            })

    # -- can it be read at all -----------------------------------------
    dates = pd.to_datetime(work['Date'], dayfirst=True, errors='coerce')
    note(dates.isna(), 'Date', 'rejected',
         'The date cannot be read.  Dates in this file are day first, as '
         '1/8/2026.')
    work['_date'] = dates

    for column in MANDATORY:
        if column in ('Date', 'Quantity'):
            continue
        note(_text(work[column]).eq(''), column, 'rejected',
             '%s is blank, and a row cannot be priced without it.' % column)

    quantity, unreadable, separator = _numeric(work['Quantity'])
    work['_quantity'] = quantity
    note(unreadable, 'Quantity', 'rejected',
         'The quantity is not a number.')
    # It parses, so refusing it helps nobody, but 1,240 is one thousand two
    # hundred in one convention and one point two four in another, and the
    # file does not say which it means.
    note(separator & ~unreadable, 'Quantity', 'questioned',
         'Written with a thousands separator, so it has been read as a '
         'number and the file does not say which convention it used.')
    note(quantity.isna() & ~unreadable, 'Quantity', 'rejected',
         'The quantity is blank.')

    # -- is every value one the model knows -----------------------------
    if live is not None and not live.empty:
        for column, plural in (('Activity', 'activities'),
                               ('SubActivity', 'sub-activities'),
                               ('Department', 'departments'),
                               ('CostCentre', 'cost centres')):
            if column not in live.columns:
                continue
            known = set(_text(live[column]))
            unknown = ~_text(work[column]).isin(known) & _text(work[column]).ne('')
            severity = 'rejected' if column == 'Activity' else 'questioned'
            note(unknown, column, severity,
                 'Not one of the %s the model has seen before.  Either it is '
                 'new and needs setting up, or it is a spelling.' % plural)

    # A cost centre is not needed to price a row, but it is needed to put
    # the result anywhere, so a blank one is a question rather than a refusal.
    note(_text(work['CostCentre']).eq(''), 'CostCentre', 'questioned',
         'No cost centre, so this emission has nowhere to sit in the '
         'departmental view.')

    units = set(Lookups.values('Unit', lookups, active_only=False))
    if live is not None and 'UOM' in live.columns:
        units |= set(_text(live['UOM']))
    unknown_unit = ~_text(work['UOM']).isin(units) & _text(work['UOM']).ne('')
    note(unknown_unit, 'UOM', 'rejected',
         'Not a unit the model knows, so nothing can convert it.')

    # -- is it sensible -------------------------------------------------
    # Held until the line's own history is known, below.  A negative is
    # ordinary on a line that has always had them and is news on one that
    # never has, and only the second is worth anybody's attention.
    negative = quantity < 0

    # A jump against the same line's own history, which is a fairer test than
    # a jump against everything: a drum of reagent and a month of diesel are
    # not comparable and never were.
    if live is not None and not live.empty and 'Quantity' in live.columns:
        history = live.copy()
        history['_k'] = (_text(history['SubActivity']) + '|'
                         + _text(history['Description']) + '|'
                         + _text(history['CostCentre']))
        typical = (pd.to_numeric(history['Quantity'], errors='coerce')
                   .groupby(history['_k']).median())
        work['_k'] = (_text(work['SubActivity']) + '|'
                      + _text(work['Description']) + '|'
                      + _text(work['CostCentre']))
        usual = work['_k'].map(typical)

        # A negative on a line that has carried one before is a credit note
        # and needs no comment.  On a line that never has, it is either a new
        # kind of transaction or a sign error.
        ever_negative = (pd.to_numeric(history['Quantity'], errors='coerce')
                         .groupby(history['_k']).min().lt(0))
        work['_k2'] = work['_k']
        first_negative = negative & ~work['_k'].map(ever_negative).fillna(False)
        note(first_negative, 'Quantity', 'questioned',
             'A negative quantity on a line that has never carried one.  A '
             'credit note is fine and a sign error is not, and they look the '
             'same from here.')
        spike = (quantity.abs() > usual.abs() * IMPORT_SPIKE_MULTIPLE) & \
                (quantity.abs() > IMPORT_SPIKE_MINIMUM) & usual.notna() & \
                (usual.abs() > 0)
        for position in work.index[spike]:
            findings.append({
                'Line': int(work.at[position, '_row']),
                'Column': 'Quantity', 'Severity': 'questioned',
                'Finding': 'About %.0f times what this line usually carries '
                           '(%s).  A spike, a unit change, or a real month.'
                           % (abs(quantity[position] / usual[position]),
                              f'{usual[position]:,.4g}'),
                'Value': f'{quantity[position]:,.4g}',
                '_key': work.at[position, '_key'],
            })

        # A unit that changed on a line the model already carries.  The
        # quantity moves by a factor of a thousand and means the same thing,
        # which is the failure a total will not show.
        # Only lines that have used exactly one unit, ever.  A consumable
        # bought by the Each, the Roll and the Packet is all three, and
        # telling somebody so every month is how a warning stops being read.
        units_used = (history.assign(_u=_text(history['UOM']))
                      .groupby('_k')['_u'].nunique())
        held = (history.assign(_u=_text(history['UOM']))
                .groupby('_k')['_u'].first())
        settled = work['_k'].map(units_used).eq(1)
        was = work['_k'].map(held)
        changed = (settled & was.notna() & was.ne('')
                   & _text(work['UOM']).ne(was))
        for position in work.index[changed]:
            findings.append({
                'Line': int(work.at[position, '_row']),
                'Column': 'UOM', 'Severity': 'questioned',
                'Finding': 'This line has always been recorded in %s and this '
                           'file says %s.'
                           % (was[position], work.at[position, 'UOM']),
                'Value': str(work.at[position, 'UOM']),
                '_key': work.at[position, '_key'],
            })

    # -- can it be priced ------------------------------------------------
    # A product group is what points a row at a factor.  One the register
    # does not carry leaves the row counted in the physicals and absent from
    # the emissions, which is the quietest way to understate a total.
    if 'ProductGroup' in work.columns and live is not None \
            and 'ProductGroup' in live.columns:
        groups = set(_text(live['ProductGroup']))
        stated = _text(work['ProductGroup'])
        note(stated.ne('') & ~stated.isin(groups), 'ProductGroup',
             'questioned',
             'Not a product group the register carries, so no factor prices '
             'this row and it will count as physicals only.')

    # -- the same line twice in one file --------------------------------
    twice = work['_key'].duplicated(keep=False) & work['_key'].ne('')
    for key, group in work[twice].groupby('_key'):
        lines = ', '.join(str(int(v)) for v in group['_row'])
        for position in group.index:
            findings.append({
                'Line': int(work.at[position, '_row']),
                'Column': 'Description', 'Severity': 'questioned',
                'Finding': 'The same line appears on lines %s of this file.  '
                           'Importing both counts it twice.' % lines,
                'Value': str(work.at[position, 'Description'])[:60],
                '_key': key,
            })

    # -- against what the model already holds ---------------------------
    work['Verdict'] = 'new'
    work['Was'] = np.nan

    if live is not None and not live.empty:
        reference = live.copy()
        reference['_key'] = row_key(reference)
        reference['_q'] = pd.to_numeric(reference['Quantity'], errors='coerce')
        previous = reference.groupby('_key')['_q'].first()

        seen = work['_key'].isin(previous.index)
        work.loc[seen, 'Was'] = work.loc[seen, '_key'].map(previous)

        moved = seen & work['Was'].notna() & quantity.notna() & (
            (work['Was'] - quantity).abs()
            > work['Was'].abs() * IMPORT_RESTATE_TOLERANCE)
        work.loc[seen & ~moved, 'Verdict'] = 'unchanged'
        work.loc[moved, 'Verdict'] = 'restated'

        for position in work.index[moved]:
            before, after = work.at[position, 'Was'], quantity[position]
            findings.append({
                'Line': int(work.at[position, '_row']),
                'Column': 'Quantity', 'Severity': 'restated',
                'Finding': 'This row is already in the model at %s and this '
                           'file says %s, a change of %+.1f per cent in a '
                           'period already reported.'
                           % (f'{before:,.4g}', f'{after:,.4g}',
                              (after - before) / before * 100.0
                              if before else float('nan')),
                'Value': f'{after:,.4g}',
                '_key': work.at[position, '_key'],
            })

    # -- rows the model holds for these months, missing from the file ---
    absent = pd.DataFrame()
    if live is not None and not live.empty and work['_date'].notna().any():
        covered = set(work['_date'].dropna().dt.to_period('M').astype(str))
        reference = live.copy()
        reference['_d'] = pd.to_datetime(reference['Date'], dayfirst=True,
                                         errors='coerce')
        reference['_key'] = row_key(reference)
        in_scope = reference[
            reference['_d'].dt.to_period('M').astype(str).isin(covered)]
        gone = in_scope[~in_scope['_key'].isin(set(work['_key']))]
        if not gone.empty:
            absent = gone.copy()
            for _, row in gone.iterrows():
                findings.append({
                    'Line': 0, 'Column': 'Description', 'Severity': 'absent',
                    'Finding': 'The model holds this row for %s and this file '
                               'does not.  Either it stopped or it was '
                               'dropped on the way here.'
                               % str(row['Date']),
                    'Value': str(row['Description'])[:60],
                    '_key': row['_key'],
                })

    # -- the verdict per row, worst finding wins ------------------------
    found = pd.DataFrame(findings) if findings else pd.DataFrame(
        columns=['Line', 'Column', 'Severity', 'Finding', 'Value', '_key'])
    if not found.empty:
        order = {'rejected': 0, 'questioned': 1, 'restated': 2}
        by_line = (found[found['Severity'].isin(order)]
                   .assign(_rank=lambda f: f['Severity'].map(order))
                   .sort_values('_rank').groupby('Line').first())
        for line, row in by_line.iterrows():
            position = work.index[work['_row'] == line]
            if len(position):
                work.loc[position, 'Verdict'] = row['Severity']

    # A row the model already holds, unchanged, has been through this once
    # and was accepted.  Raising it again every month buries the rows that
    # are genuinely arriving.  Rejections still stand: a row that cannot be
    # read cannot be waved through on the grounds of being familiar.
    if not found.empty:
        settled_rows = set(work.loc[work['Verdict'] == 'unchanged', '_row'])
        found = found[~((found['Line'].isin(settled_rows))
                        & (found['Severity'] == 'questioned'))]
        found = found.reset_index(drop=True)

    work['Findings'] = work['_row'].map(
        found.groupby('Line').size()).fillna(0).astype(int)
    # Which cell to click.  The worst finding decides, and where a row has
    # several in different columns they are named together, because sending
    # somebody to one cell when two are wrong wastes the trip.
    if not found.empty:
        by_row = found.groupby('Line')['Column'].apply(
            lambda values: ', '.join(dict.fromkeys(values)))
        work['Field'] = work['_row'].map(by_row).fillna('')
    else:
        work['Field'] = ''

    work['Issue'] = work['_row'].map(
        found.sort_values('Severity').groupby('Line')['Finding']
        .apply(lambda values: '  '.join(values))).fillna('')

    return work, found, absent


def summary(work, absent=None):
    """One line per bucket: what this file would do."""
    counts = work['Verdict'].value_counts().to_dict()
    if absent is not None and not absent.empty:
        counts['absent'] = len(absent)
    rows = [{'Bucket': bucket, 'Rows': int(counts.get(bucket, 0)),
             'Means': MEANING[bucket]} for bucket in BUCKETS]
    return pd.DataFrame(rows)


MEANING = {
    'rejected': 'Cannot be imported.  There is no sensible reading of the row.',
    'questioned': 'Can be imported, and should not be without a look.',
    'restated': 'A period already reported would move.',
    'absent': 'Held by the model for these months, and not in this file.',
    'new': 'Not in the model.  This is the ordinary case.',
    'unchanged': 'Already in the model, identical.  Nothing happens.',
}


def blocking(work):
    """Whether anything stops the import outright."""
    return int((work['Verdict'] == 'rejected').sum())
