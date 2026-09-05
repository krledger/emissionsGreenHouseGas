"""Read a file somebody has chosen, and work out what its columns mean.

Two jobs, both dull and both worth doing properly.  Reading a file that may
be a csv or a workbook, in whatever encoding the system that wrote it
favoured, and then deciding which of its columns is the quantity.

The mapping is a proposal, never a decision.  Every match is offered with the
reason it was made, and every one can be overridden, because a column matched
on a fuzzy name is a guess and a guess that cannot be corrected is worse than
no guess at all.
"""

import io
import os
import re

import pandas as pd

# The columns the operations file is expected to carry, and what each is for.
# Order is the order they are offered in.
EXPECTED = [
    ('Date', True, 'The month the quantity belongs to, day first.'),
    ('Activity', True, 'What was done: Combustion, Electricity, Reagent.'),
    ('SubActivity', True, 'What it was done with: Diesel, Grid Power.'),
    ('Description', False, 'The line as the source system writes it.'),
    ('Department', False, 'Who it belongs to.'),
    ('CostCentre', False, 'Where it sits in the departmental view.'),
    ('State', False, 'The grid the electricity came from.'),
    ('UOM', True, 'The unit the quantity is in.'),
    ('Quantity', True, 'How much.'),
    ('Source', False, 'The system it came from.'),
    ('Identifier', False, 'The source system reference.'),
    ('ProductGroup', False, 'What points the row at a factor.'),
    ('TransactionType', False,
     'What the source system calls this movement: an issue, a return, a '
     'cycle count adjustment.  Optional, and where it is present a negative '
     'stops being a question.'),
    ('Value', False, 'Spend in dollars, where the row carries any.'),
    ('Mass_kg', False, 'Mass, where the row carries any.'),
]

REQUIRED = tuple(name for name, required, _ in EXPECTED if required)

# Spellings that mean the same column.  Lower case, punctuation stripped.
SYNONYMS = {
    'date': 'Date', 'month': 'Date', 'period': 'Date', 'postingdate': 'Date',
    'activity': 'Activity', 'activitytype': 'Activity',
    'subactivity': 'SubActivity', 'subtype': 'SubActivity',
    'description': 'Description', 'material': 'Description',
    'materialdescription': 'Description', 'item': 'Description',
    'department': 'Department', 'dept': 'Department',
    'costcentre': 'CostCentre', 'costcenter': 'CostCentre', 'cc': 'CostCentre',
    'state': 'State',
    'uom': 'UOM', 'unit': 'UOM', 'unitofmeasure': 'UOM', 'units': 'UOM',
    'quantity': 'Quantity', 'qty': 'Quantity', 'volume': 'Quantity',
    'amount': 'Quantity',
    'source': 'Source', 'system': 'Source',
    'identifier': 'Identifier', 'id': 'Identifier', 'ref': 'Identifier',
    'materialnumber': 'Identifier',
    'productgroup': 'ProductGroup', 'group': 'ProductGroup',
    'transactiontype': 'TransactionType', 'trantype': 'TransactionType',
    'movementtype': 'TransactionType', 'txntype': 'TransactionType',
    'documenttype': 'TransactionType', 'postingtype': 'TransactionType',
    'value': 'Value', 'spend': 'Value', 'cost': 'Value', 'aud': 'Value',
    'masskg': 'Mass_kg', 'mass': 'Mass_kg', 'weight': 'Mass_kg',
}


def _flatten(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def read(uploaded, sheet=None):
    """A file as a frame of text, with nothing coerced yet.

    Everything is read as text on purpose.  Letting the parser decide that a
    column of identifiers is numeric drops the leading zeros, and letting it
    decide a quantity is text hides that it could not be read.  The checks
    decide, and they say so.
    """
    name = getattr(uploaded, 'name', str(uploaded))
    data = uploaded.read() if hasattr(uploaded, 'read') else open(
        uploaded, 'rb').read()

    if name.lower().endswith(('.xlsx', '.xlsm', '.xls')):
        book = pd.ExcelFile(io.BytesIO(data))
        chosen = sheet or book.sheet_names[0]
        frame = book.parse(chosen, dtype=str)
        return frame, book.sheet_names, chosen

    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            frame = pd.read_csv(io.BytesIO(data), dtype=str,
                                encoding=encoding)
            return frame, [], None
        except UnicodeDecodeError:
            continue
    raise ValueError(
        'The file is not readable as UTF-8, Windows-1252 or Latin-1.  Save '
        'it again as CSV UTF-8 and try once more.')


def propose(columns):
    """A mapping from the file's columns to the model's, with reasons.

    A proposal and not a decision.  Each match carries how it was made, so a
    person can see at a glance which ones were obvious and which were a
    guess.
    """
    available = list(columns)
    flattened = {_flatten(column): column for column in available}
    taken, rows = set(), []

    for field, required, purpose in EXPECTED:
        match, why = '', ''
        key = _flatten(field)
        if key in flattened and flattened[key] not in taken:
            match, why = flattened[key], 'the same name'
        else:
            for spelling, target in SYNONYMS.items():
                if target != field:
                    continue
                if spelling in flattened and flattened[spelling] not in taken:
                    match = flattened[spelling]
                    why = 'matched on "%s"' % match
                    break
        if not match:
            for flat, column in flattened.items():
                if column in taken:
                    continue
                if key and (key in flat or flat in key):
                    match, why = column, 'the names overlap, so this is a guess'
                    break
        if match:
            taken.add(match)
        rows.append({
            'Field': field,
            'Required': required,
            'Column in file': match,
            'Matched by': why or ('nothing matched' if required
                                  else 'not present, and not needed'),
            'What it is for': purpose,
        })

    spare = [column for column in available if column not in taken]
    return pd.DataFrame(rows), spare


def apply_mapping(frame, mapping):
    """The file's columns, renamed to the model's, with the rest dropped."""
    pairs = {row['Column in file']: row['Field']
             for _, row in mapping.iterrows()
             if str(row['Column in file']).strip()}
    missing = [row['Field'] for _, row in mapping.iterrows()
               if row['Required'] and not str(row['Column in file']).strip()]
    if missing:
        raise ValueError(
            'Nothing is mapped to %s, and a row cannot be read without %s.'
            % (', '.join(missing), 'it' if len(missing) == 1 else 'them'))
    staged = frame[list(pairs)].rename(columns=pairs).copy()
    for field, _, _ in EXPECTED:
        if field not in staged.columns:
            staged[field] = ''
    return staged[[field for field, _, _ in EXPECTED]]


def template():
    """An empty file in the shape the import expects, to hand out."""
    return pd.DataFrame(columns=[field for field, _, _ in EXPECTED])


# The shapes a month arrives in.  A monthly file has no day in it, so
# Aug-2026 is what the source means and 1/8/2026 is only how this model
# stores it.  Day first everywhere, because that is what the operations file
# uses and 3/8/2026 has to mean August.
MONTH_FORMATS = ('%b-%Y', '%b %Y', '%B-%Y', '%B %Y', '%Y-%m', '%m-%Y',
                 '%b-%y', '%Y%m')


def read_dates(series):
    """Dates as timestamps, whatever sensible shape they arrived in.

    Returns the parsed dates and the format that read them, so a screen can
    say how it understood the column rather than leaving somebody to guess
    whether 3/8 was March or August.
    """
    text = series.fillna('').astype(str).str.strip()
    parsed = pd.to_datetime(text, dayfirst=True, errors='coerce',
                            format='mixed')
    if parsed.notna().all():
        return parsed, 'day first'

    # Whichever month format reads the most of what is left wins, rather
    # than the first one that reads anything: a column of Aug-2026 should not
    # be claimed by a pattern that happens to match one row of it.
    best, best_read, best_name = parsed, parsed.notna().sum(), 'day first'
    for pattern in MONTH_FORMATS:
        attempt = pd.to_datetime(text, format=pattern, errors='coerce')
        read = attempt.notna().sum()
        if read > best_read:
            best, best_read, best_name = attempt, read, pattern
    if best_name == 'day first':
        return parsed, 'day first'
    return best.fillna(parsed), 'month only (%s)' % best_name


def as_model_dates(series):
    """A date column in the shape the operations file stores.

    A month with no day becomes the first of that month, which is what every
    row in the operations file already is.
    """
    parsed, how = read_dates(series)
    return parsed.dt.strftime('%-d/%-m/%Y').where(parsed.notna(), ''), how
