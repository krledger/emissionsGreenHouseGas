"""Lookups: every list the model chooses from, in one table.

A list held in code cannot be added to without a release.  Region, Unit and
the rest change when a publication changes, which is not the same rhythm as
the code, so they live in a file and the code reads them.

One table rather than eight small ones.  A list is identified by its name,
which means a new list costs a row rather than a file, and one screen
maintains all of them.

Unit carries three fields the others do not.

Dimension is what the factor measures, and it decides whether a factor may
price an item at all: a factor per tonne cannot price a line recorded in
dollars.  Spend is split by currency, so a factor per US dollar cannot price
Australian spend until it has been converted on import.  That is a rule
enforced by the data rather than remembered by a person.

A unit has two scales because it has two halves.  EmissionScale is the
numerator against a kilogram of CO2-e: "t CO2-e per t" and "kg CO2-e/t"
measure the same thing and differ by a thousand in the emission, not the
quantity.  QuantityScale is the denominator against the dimension's base
unit: a factor per kilolitre priced against litres differs by a thousand in
the quantity, not the emission.

One scale cannot express both, and getting it wrong is a factor of a
thousand that nothing else would catch.
"""

import os

import pandas as pd

from Paths import ROOT as BASE_DIR
REFERENCE_DIR = os.path.join(BASE_DIR, 'Reference')
LOOKUPS_PATH = os.path.join(REFERENCE_DIR, 'Lookups.csv')
PRICE_INDEX_PATH = os.path.join(REFERENCE_DIR, 'PriceIndex.csv')

COLUMNS = ['ListName', 'Code', 'Label', 'Dimension', 'EmissionScale',
           'QuantityScale', 'SortOrder', 'Active', 'Notes']

PRICE_COLUMNS = ['Year', 'Series', 'Index', 'Basis', 'Source']

# The lists the model reads.  Named here so a typo in a ListName is caught
# rather than quietly producing an empty list.
LISTS = ('Class', 'Region', 'Unit', 'Dimension', 'Basis', 'Category',
         'Status', 'Tenure', 'AssetClass', 'ImportType', 'Rule')


def load(path=None):
    """The whole table.  Inactive rows are kept and marked, never dropped."""
    path = path or LOOKUPS_PATH
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_csv(path)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ''
    frame['Active'] = (frame['Active'].astype(str).str.lower()
                       .isin(['true', '1', 'yes', 'y']))
    for column in ('EmissionScale', 'QuantityScale'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame['SortOrder'] = pd.to_numeric(frame['SortOrder'],
                                       errors='coerce').fillna(0)
    return frame[COLUMNS]


def save(frame, path=None):
    path = path or LOOKUPS_PATH
    out = frame.copy()
    for column in COLUMNS:
        if column not in out.columns:
            out[column] = ''
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.writing'
    out[COLUMNS].sort_values(['ListName', 'SortOrder', 'Code']).to_csv(
        temporary, index=False, encoding='utf-8')
    os.replace(temporary, path)


def values(list_name, frame=None, active_only=True):
    """The codes in one list, in order.  The Select behind a field."""
    frame = load() if frame is None else frame
    rows = frame[frame['ListName'] == list_name]
    if active_only:
        rows = rows[rows['Active']]
    return list(rows.sort_values(['SortOrder', 'Code'])['Code'])


def labels(list_name, frame=None):
    """Code to label, for showing a list without losing what it stores."""
    frame = load() if frame is None else frame
    rows = frame[frame['ListName'] == list_name]
    return dict(zip(rows['Code'], rows['Label'].where(
        rows['Label'].astype(str).str.strip() != '', rows['Code'])))


def unit_dimension(frame=None):
    """Unit to what it measures.  The test for whether a factor fits an item."""
    frame = load() if frame is None else frame
    rows = frame[frame['ListName'] == 'Unit']
    return dict(zip(rows['Code'], rows['Dimension']))


def unit_scale(frame=None):
    """Unit to (emission scale, quantity scale)."""
    frame = load() if frame is None else frame
    rows = frame[frame['ListName'] == 'Unit']
    return {code: (emission, quantity) for code, emission, quantity in zip(
        rows['Code'],
        pd.to_numeric(rows['EmissionScale'], errors='coerce'),
        pd.to_numeric(rows['QuantityScale'], errors='coerce'))}


def compatible(factor_unit, item_unit, frame=None):
    """Whether a factor measured one way may price an item measured another.

    Same dimension is the test, not the same name.  A factor per tonne and a
    quantity in kilograms agree about what is being measured and differ by a
    thousand, which is a conversion.  A factor per tonne and a quantity in
    dollars do not agree at all, which is not.
    """
    dimensions = unit_dimension(frame)
    left = dimensions.get(str(factor_unit))
    right = dimensions.get(str(item_unit))
    if not left or not right:
        return False
    return left == right


def conversion(factor_unit, item_unit, frame=None):
    """What to multiply a factor by so it is expressed in another unit.

    Both halves move.  A factor of 2.12 t CO2-e per t restated as kg CO2-e/t
    is 2120: the emission scales by a thousand and the quantity does not.  A
    factor per kilolitre restated per litre divides by a thousand: the
    quantity scales and the emission does not.

    Returns None where the two do not measure the same thing, which is a
    refusal rather than a number.
    """
    if not compatible(factor_unit, item_unit, frame):
        return None
    scale = unit_scale(frame)
    source = scale.get(str(factor_unit))
    target = scale.get(str(item_unit))
    if not source or not target:
        return None
    (emission_from, quantity_from) = source
    (emission_to, quantity_to) = target
    if any(pd.isna(v) or not v for v in
           (emission_from, quantity_from, emission_to, quantity_to)):
        return None
    return (emission_from / emission_to) * (quantity_to / quantity_from)


# ---------------------------------------------------------------------
# PRICE INDEX
# ---------------------------------------------------------------------
# Held beside the exchange rates and read the same way, because it answers
# the same shape of question: what a dollar was worth, in a stated year.

def load_price_index(path=None):
    path = path or PRICE_INDEX_PATH
    if not os.path.exists(path):
        return pd.DataFrame(columns=PRICE_COLUMNS)
    frame = pd.read_csv(path)
    for column in PRICE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ''
    frame['Year'] = pd.to_numeric(frame['Year'], errors='coerce')
    frame['Index'] = pd.to_numeric(frame['Index'], errors='coerce')
    return frame[PRICE_COLUMNS].dropna(subset=['Year'])


def price_index(year, series='US CPI-U', frame=None):
    """The index for one year, or None where it is not published.

    None rather than a guess: an import that cannot find its year should
    stop and say so, not deflate by something plausible.
    """
    frame = load_price_index() if frame is None else frame
    rows = frame[(frame['Series'] == series) & (frame['Year'] == int(year))]
    if rows.empty:
        return None
    value = rows['Index'].iloc[0]
    return None if pd.isna(value) else float(value)


def deflator(from_year, to_year, series='US CPI-U', frame=None):
    """How much more of a dollar it takes to buy the same thing.

    A factor published per 2022 dollar, applied to 2026 spend, is applied to
    dollars that buy less than the ones it was measured against.  This is the
    number that corrects that, and it is None where either year is missing.
    """
    frame = load_price_index() if frame is None else frame
    start = price_index(from_year, series, frame)
    end = price_index(to_year, series, frame)
    if start in (None, 0) or end is None:
        return None
    return end / start
