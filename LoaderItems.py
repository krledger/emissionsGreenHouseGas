"""The Items table: what uses a factor.

Scope3Factors.csv held two things at once.  Four hundred rows are seventy
factors carried against three hundred and eighty eight product groups, and
reading them as a list of factors makes one figure look like dozens of
duplicates.  The factors moved to Factors.csv; what is left here is the
mapping, which is a different question with a different owner.

An item points at a factor identity and never at a release.  The release is
resolved against the year of the row being priced, so importing a later
edition of a publication changes no item.

Two columns rather than an assignment table.  FactorKey_Imported is what the
item arrived pointing at and belongs to whichever import wrote it.
FactorKey_Assigned is where a person pointed it, and wins.  Keeping both on
one row means the distributed position is never lost and an import can
replace its own column without touching the judgement beside it.
"""

import os
from datetime import datetime

import pandas as pd

import LoaderFactorTable as Factors
import LoaderLookups as Lookups

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPE3_DIR = os.path.join(BASE_DIR, 'Scope3')
ITEMS_PATH = os.path.join(SCOPE3_DIR, 'Items.csv')

COLUMNS = ['ItemID', 'Category', 'Key', 'Description', 'Basis',
           'Quantity_UOM', 'Match_Key', 'FactorKey_Imported',
           'FactorKey_Assigned', 'AssignedReason', 'AssignedBy', 'AssignedAt',
           'Excluded', 'Exclude_Reason', 'CountedAgainst', 'Import', 'Notes']


def load(path=None):
    path = path or ITEMS_PATH
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_csv(path)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ''
    frame['Excluded'] = (frame['Excluded'].astype(str).str.lower()
                         .isin(['true', '1', 'yes', 'y']))
    frame['Category'] = pd.to_numeric(frame['Category'], errors='coerce')
    for column in COLUMNS:
        if column not in ('Excluded', 'Category'):
            frame[column] = frame[column].fillna('').astype(str)
    # The factor actually in force: what somebody chose, else what arrived.
    frame['FactorKey'] = frame['FactorKey_Assigned'].where(
        frame['FactorKey_Assigned'].str.strip() != '',
        frame['FactorKey_Imported'])
    frame['IsAssigned'] = frame['FactorKey_Assigned'].str.strip() != ''
    return frame[COLUMNS + ['FactorKey', 'IsAssigned']]


def save(frame, path=None):
    path = path or ITEMS_PATH
    out = frame.copy()
    for column in COLUMNS:
        if column not in out.columns:
            out[column] = ''
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.writing'
    out[COLUMNS].to_csv(temporary, index=False, encoding='utf-8')
    os.replace(temporary, path)


def assign(items, item_ids, factor_key, reason, author='', factors=None,
           lookups=None):
    """Point items at a different factor.

    Refused where the factor does not measure what the item is recorded in.
    A factor per tonne cannot price a line in dollars, and the check is here
    rather than in a screen so it holds however the assignment is made.
    """
    if not str(factor_key).strip():
        raise ValueError('An assignment has to name a factor.')
    if not str(reason).strip():
        raise ValueError('An assignment has to carry a reason.')

    factors = Factors.load() if factors is None else factors
    target = factors[factors['FactorKey'] == factor_key]
    if target.empty:
        raise ValueError('No factor with that identity.')
    factor_unit = target.iloc[0]['Unit']

    lookups = Lookups.load() if lookups is None else lookups
    out = items.copy()
    stamp = datetime.now().isoformat(timespec='seconds')
    changed = []
    for item_id in item_ids:
        position = out.index[out['ItemID'] == item_id]
        if len(position) == 0:
            continue
        current = out.loc[position[0]]
        # An item is measured by the factor it already carries; where it
        # carries none, by its own quantity unit.
        held = factors[factors['FactorKey'] == current['FactorKey']]
        item_unit = (held.iloc[0]['Unit'] if not held.empty
                     else current['Quantity_UOM'])
        if item_unit and not Lookups.compatible(factor_unit, item_unit,
                                                lookups):
            raise ValueError(
                f"{item_id} is priced in {item_unit} and that factor is in "
                f"{factor_unit}.  They do not measure the same thing.")
        out.loc[position, 'FactorKey_Assigned'] = factor_key
        out.loc[position, 'AssignedReason'] = str(reason).strip()
        out.loc[position, 'AssignedBy'] = author or os.environ.get(
            'USER', 'unknown')
        out.loc[position, 'AssignedAt'] = stamp
        changed.append({'Path': f'{item_id}.FactorKey',
                        'From': current['FactorKey'], 'To': factor_key})
    return out, changed


def clear_assignment(items, item_ids):
    """Return items to the factor they were distributed with."""
    out = items.copy()
    changed = []
    for item_id in item_ids:
        position = out.index[out['ItemID'] == item_id]
        if len(position) == 0:
            continue
        was = out.loc[position[0], 'FactorKey_Assigned']
        if not str(was).strip():
            continue
        out.loc[position, ['FactorKey_Assigned', 'AssignedReason',
                           'AssignedBy', 'AssignedAt']] = ''
        changed.append({'Path': f'{item_id}.FactorKey', 'From': was,
                        'To': out.loc[position[0], 'FactorKey_Imported']})
    return out, changed


def with_factors(items=None, factors=None, year=None):
    """Items beside the factor in force, resolved for a year where given."""
    items = load() if items is None else items
    factors = Factors.load() if factors is None else factors
    if items.empty:
        return items
    if year is None:
        latest = (factors[~factors['Obsolete']]
                  .sort_values('EffectiveFrom')
                  .groupby('FactorKey').tail(1))
    else:
        resolved = Factors.resolve_map(factors, [int(year)])
        latest = pd.DataFrame([row for (key, _), row in resolved.items()])
    columns = ['FactorKey', 'Class', 'Source', 'Name', 'Release', 'Region',
               'Unit', 'Scope1', 'Scope2', 'Scope3']
    return items.merge(latest[columns], on='FactorKey', how='left')


def orphans(items=None, factors=None):
    """Items pointing at a factor identity that no longer exists."""
    items = load() if items is None else items
    factors = Factors.load() if factors is None else factors
    known = set(factors['FactorKey'])
    priced = items[items['FactorKey'].str.strip() != '']
    return priced[~priced['FactorKey'].isin(known)]


def summary(items=None):
    """How the items divide, which is the shape of the Scope 3 assessment."""
    items = load() if items is None else items
    if items.empty:
        return pd.DataFrame(columns=['Basis', 'Items', 'Factors', 'Assigned'])
    return (items.groupby('Basis')
            .agg(Items=('ItemID', 'size'),
                 Factors=('FactorKey', 'nunique'),
                 Assigned=('IsAssigned', 'sum')).reset_index())


def as_factor_table(items=None, factors=None, year=None):
    """The distributed factor table's shape, built from the two tables.

    Scope3Factors.csv is gone; this is what stood in its place.  Every
    consumer downstream reads a flat table of category, basis, key, factor
    and source, and rewriting all of them to read two tables would be a large
    change for no gain.  So the shape is served rather than stored, and the
    two tables are what is maintained.

    The year resolves which release applies.  Passing none takes the latest,
    which is what a screen wants; the build passes the year of the rows it is
    pricing, which is what an audit wants.
    """
    items = load() if items is None else items
    factors = Factors.load() if factors is None else factors
    if items.empty:
        return pd.DataFrame(columns=[
            'Category', 'Basis', 'Key', 'Key_Type', 'Description', 'Factor',
            'Factor_Unit', 'Quantity_UOM', 'Factor_Year', 'Factor_Source',
            'Match_Key', 'Excluded', 'Exclude_Reason', 'Notes'])

    live = factors[~factors['Obsolete']].sort_values('EffectiveFrom')
    if year is None:
        chosen = live.groupby('FactorKey').tail(1)
    else:
        applicable = live[live['EffectiveFrom'] <= int(year)]
        chosen = applicable.groupby('FactorKey').tail(1)
        # An identity with no edition that early keeps its earliest, so a row
        # in an early year is priced rather than silently dropped.
        missing = set(live['FactorKey']) - set(chosen['FactorKey'])
        if missing:
            earliest = live[live['FactorKey'].isin(missing)].groupby(
                'FactorKey').head(1)
            chosen = pd.concat([chosen, earliest], ignore_index=True)

    held = chosen[['FactorKey', 'DisplaySource', 'Unit', 'Release', 'Scope1',
                   'Scope2', 'Scope3']]
    joined = items.merge(held, on='FactorKey', how='left')

    # Scope 3 is what this table has always carried; the other two belong to
    # the fuels and reach the model by another road.
    return pd.DataFrame({
        'Category': joined['Category'],
        'Basis': joined['Basis'],
        'Key': joined['Key'],
        'Key_Type': 'ProductGroup',
        'Description': joined['Description'],
        'Factor': pd.to_numeric(joined['Scope3'], errors='coerce'),
        'Factor_Unit': joined['Unit'].fillna(''),
        'Quantity_UOM': joined['Quantity_UOM'],
        'Factor_Year': pd.to_numeric(joined['Release'], errors='coerce'),
        'Factor_Source': joined['DisplaySource'].fillna('').where(
            joined['DisplaySource'].fillna('') != '',
            joined['CountedAgainst']),
        'Match_Key': joined['Match_Key'],
        'Excluded': joined['Excluded'].map(lambda flag: 'Y' if flag else 'N'),
        'Exclude_Reason': joined['Exclude_Reason'],
        'Notes': joined['Notes'],
    })
