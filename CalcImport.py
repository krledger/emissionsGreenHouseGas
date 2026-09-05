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

import LoaderImport
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

# What a source system calls a movement that is not consumption.  A negative
# declared as one of these is not a question: it is a stock movement doing
# exactly what it says.  Matched loosely because every system words it
# differently and none of them will change to suit this model.
ADJUSTMENT_WORDS = (r'adjust|return|reversal|credit|cycle\s*count|'
                    r'stocktake|write[\s-]?(off|back)|correction')


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
    # A monthly file may carry no day at all.  Aug-2026 is a perfectly clear
    # month and refusing it because it is not 1/8/2026 would be pedantry.
    dates, how = LoaderImport.read_dates(work['Date'])
    note(dates.isna(), 'Date', 'rejected',
         'The date cannot be read.  A day, as 1/8/2026, or a month, as '
         'Aug-2026, are both understood.')
    work['_date'] = dates
    work['_date_read_as'] = how
    # Stored the way the operations file stores it, so a month with no day
    # becomes the first of that month like every row already there.
    written = dates.dt.strftime('%-d/%-m/%Y')
    work['Date'] = written.where(dates.notna(), work['Date'])

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

    # Which system a row came from.  Three feed this model and a fourth
    # would be a pipeline change nobody mentioned, not a row to wave through.
    if 'Source' in work.columns and live is not None \
            and 'Source' in live.columns:
        systems = set(_text(live['Source']))
        stated = _text(work['Source'])
        note(stated.eq(''), 'Source', 'questioned',
             'No source system, so there is nothing to trace this row back '
             'to.')
        note(stated.ne('') & ~stated.isin(systems), 'Source', 'questioned',
             'Not one of the systems this model reads (%s).  Either a new '
             'feed or a spelling.' % ', '.join(sorted(systems)))

    # A row whose description says it is a total.  Two quite different
    # things wear that word.  INV03 uses "Total Other" for a residual
    # bucket: whatever in a sub-activity was not itemised, carrying its own
    # OTHER| identifier and its own quantity.  A spreadsheet uses it for a
    # sum of the rows above, and importing that alongside those rows counts
    # everything twice.
    #
    # They are told apart by arithmetic rather than by the word.  If the
    # total equals the sum of its neighbours it is the second kind.
    aggregate = _text(work['Description']).str.contains(
        'total', case=False, na=False)

    if aggregate.any():
        grouping = ['Date', 'Activity', 'SubActivity', 'CostCentre', 'UOM']
        held = [column for column in grouping if column in work.columns]
        if held:
            parts = (work[~aggregate].groupby(held)['_quantity']
                     .agg(['sum', 'size']))
            for position in work.index[aggregate]:
                key = tuple(work.at[position, column] for column in held)
                if key not in parts.index:
                    continue
                beside, how_many = parts.loc[key, 'sum'], parts.loc[key, 'size']
                stated = quantity[position]
                if not beside or pd.isna(stated) or how_many < 2:
                    continue
                if abs(stated - beside) <= abs(beside) * 0.02:
                    findings.append({
                        'Line': int(work.at[position, '_row']),
                        'Column': 'Quantity', 'Severity': 'questioned',
                        'Finding': 'This row says Total and its quantity '
                                   'equals the sum of the %d other rows '
                                   'beside it (%s).  If it is a spreadsheet '
                                   'total, importing it counts them all '
                                   'twice.' % (how_many, f'{beside:,.6g}'),
                        'Value': f'{stated:,.6g}',
                        '_key': work.at[position, '_key'],
                    })

    # Fuel in a bucket is priced without anybody being able to say what was
    # burned.  Right where the sub-activity is right, and untraceable either
    # way, which is worth knowing rather than discovering during an audit.
    burned = aggregate & _text(work['Activity']).eq('Combustion')
    note(burned, 'Description', 'questioned',
         'An aggregate line, and it is fuel, so it is priced without saying '
         'what was burned.  Nothing here can check it against an invoice.')

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

        # Every negative in the operations history comes from INV03 and most
        # are Stores, with the value negative alongside the quantity: a stock
        # return or a cycle count, which is ordinary and nets out in the
        # month.  Saying so means the reader knows what they are confirming.
        values = pd.to_numeric(work.get('Value'), errors='coerce') \
            if 'Value' in work.columns else pd.Series(index=work.index,
                                                      dtype=float)
        # A negative quantity is not questioned.  PrepData has already
        # settled it: ImportInventory keeps only Component Used and Stock
        # Adjustment, reads INV03's sign convention from the data, and nets
        # returns off rather than taking abs().  What reaches here is a month
        # whose returns to store exceeded its issues, which is an inventory
        # movement and not a fault.
        #
        # The one case left is a row that contradicts itself.  A return
        # credits the value along with the quantity, so a negative quantity
        # beside a value that is not negative is one or the other being
        # wrong, and nothing upstream has resolved which.
        declared = (_text(work['TransactionType'])
                    if 'TransactionType' in work.columns
                    else pd.Series('', index=work.index))
        adjustment = declared.str.contains(
            ADJUSTMENT_WORDS, case=False, na=False, regex=True)
        note(negative & ~values.lt(0) & values.notna() & ~adjustment,
             'Quantity', 'questioned',
             'A negative quantity, and the value beside it is not negative.  '
             'A return credits both, so one of the two is wrong.')
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

    # -- the same line more than once in one file ------------------------
    # Two different problems wear the same shape.  Where the repeats agree on
    # the quantity it is a duplicate and importing them all counts the line
    # more than once.  Where they disagree the file is contradicting itself,
    # and nothing here can say which figure is meant, which is the worse of
    # the two and was being described in the words of the milder one.
    twice = work['_key'].duplicated(keep=False) & work['_key'].ne('')
    for key, group in work[twice].groupby('_key'):
        ordered = group.sort_values('_row')
        first = int(ordered.iloc[0]['_row'])
        others = [int(v) for v in ordered['_row'][1:]]
        values = [str(v).strip() for v in ordered['Quantity']]
        agree = len(set(values)) == 1

        for position in ordered.index:
            line = int(work.at[position, '_row'])
            if agree:
                if line == first:
                    what = ('Repeated on line%s %s of this file.  This is the '
                            'first of them and the one that imports; the '
                            'others are left out.'
                            % ('' if len(others) == 1 else 's',
                               ', '.join(str(v) for v in others)))
                else:
                    what = ('The same line as line %d, same quantity.  '
                            'Importing both would count it twice.' % first)
            else:
                shown = ' and '.join(
                    '%s on line %d' % (value, int(row))
                    for value, row in zip(values, ordered['_row']))
                what = ('This file gives this one line two different '
                        'quantities: %s.  Nothing here can say which is '
                        'meant.' % shown)
            findings.append({
                'Line': line,
                'Column': 'Quantity' if not agree else 'Description',
                'Severity': 'questioned',
                'Finding': what,
                'Value': str(work.at[position, 'Quantity'])[:60],
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

    # What the comparison against the model concluded, before any finding
    # rewrites it below.  The suppression at the end needs this and not the
    # rewritten value: an unchanged row carrying an old negative becomes
    # 'questioned' in the loop below and then no longer looks unchanged to
    # the thing meant to leave it alone.
    work['Standing'] = work['Verdict']

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
        settled_rows = set(work.loc[work['Standing'] == 'unchanged', '_row'])
        found = found[~((found['Line'].isin(settled_rows))
                        & (found['Severity'] == 'questioned'))]
        found = found.reset_index(drop=True)

        work['Verdict'] = work['Standing']
        order = {'rejected': 0, 'questioned': 1, 'restated': 2}
        if not found.empty:
            ranked = (found[found['Severity'].isin(order)]
                      .assign(_rank=lambda f: f['Severity'].map(order))
                      .sort_values('_rank').groupby('Line').first())
            for line, row in ranked.iterrows():
                position = work.index[work['_row'] == line]
                if len(position):
                    work.loc[position, 'Verdict'] = row['Severity']

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

    # One short line for the table to show in a column.  The panel lists
    # every finding in full, so running them together here only produced a
    # sentence that got cut off in the middle.
    work['Issue'] = work['_row'].map(
        found.sort_values('Severity').groupby('Line')['Finding'].first()
    ).fillna('')
    work['Issues'] = work['_row'].map(
        found.groupby('Line').size()).fillna(0).astype(int)

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
