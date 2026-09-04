"""Step I: a factor is editable only where the number is our own research.

Class was doing two jobs badly.  It named a publication family and it decided
who could edit, and the two answers disagreed on the capital goods bands: EPA
factors converted to Australian dollars per million, filed as Internal
because the conversion was done here.

Applying a published conversion to a published number does not make the
result ours.  The EPA sets the intensity, the Bureau of Labor Statistics sets
the price index and the Reserve Bank sets the rate.  Nobody here chooses any
of them, so nobody here can defend typing a different answer, and the field
should not accept one.

The rule, applied everywhere and not only to EPA:

    NGA           National Greenhouse Accounts          locked
    Spend-based   US EPA supply chain factors, and      locked
                  anything derived from them by a
                  published conversion
    Industry      a published factor from an industry   locked
                  body: worldsteel, AusLCI, AGO.  One
                  figure or a hundred, the test is the
                  same: we did not set it
    Internal      our own research, standing on no      editable
                  authoritative source

Three factors are Internal, out of a hundred and sixty nine.  That is the
honest count of how much of this model is our own judgement, and it lines up
exactly with the three the page already warns carry no publication.

What stays ours either way is which factor an item uses.  That is an
assignment, it lives on the item, and none of this touches it.
"""
import ast
import os
import sys

BASE = os.path.expanduser('~/mnt/EmissionsGreenHouseGas')
sys.path.insert(0, BASE)
os.chdir(BASE)

import pandas as pd

# ---------------------------------------------------------------------
# 1: the vocabulary
# ---------------------------------------------------------------------

CONFIG_WAS = b"""CLASS_INTERNAL = 'Internal'"""
CONFIG_NOW = b"""# Class says which publication governs a factor, and that decides whether it
# may be edited.  A factor derived from a publication by a published
# conversion is still that publication's: we choose neither the factor, nor
# the price index, nor the exchange rate, so there is nothing here to defend
# a different value with.  Only our own research is ours to change.
CLASS_INTERNAL = 'Internal'
CLASS_INDUSTRY = 'Industry'"""

path = 'Config.py'
source = open(path, 'rb').read()
if CONFIG_NOW not in source:
    assert CONFIG_WAS in source
    source = source.replace(CONFIG_WAS, CONFIG_NOW, 1)
    source = source.replace(
        b"FACTOR_CLASSES = (CLASS_INTERNAL, CLASS_NGA, CLASS_SPEND)",
        b"FACTOR_CLASSES = (CLASS_NGA, CLASS_SPEND, CLASS_INDUSTRY,\n"
        b"                  CLASS_INTERNAL)\n\n"
        b"# The only class a person may edit.  Everything else is used as\n"
        b"# published, and shown greyed rather than hidden, because a locked\n"
        b"# figure somebody can still read is what makes the lock credible.\n"
        b"EDITABLE_CLASSES = (CLASS_INTERNAL,)", 1)
    ast.parse(source.decode('utf-8'))
    with open(path + '.writing', 'wb') as handle:
        handle.write(source)
    os.replace(path + '.writing', path)
    print('Config: Industry added, EDITABLE_CLASSES declared')

path = 'LoaderFactorTable.py'
source = open(path, 'rb').read()
if b'CLASS_INDUSTRY' not in source:
    source = source.replace(
        b"from Config import (CLASS_INTERNAL, CLASS_NGA, CLASS_SPEND, FACTOR_CLASSES)",
        b"from Config import (CLASS_INTERNAL, CLASS_NGA, CLASS_SPEND,\n"
        b"                    CLASS_INDUSTRY, FACTOR_CLASSES,\n"
        b"                    EDITABLE_CLASSES)", 1)
    ADDITION = b'''

def editable(frame):
    """Which rows a person may change.

    One rule, in one place, so a screen cannot decide differently from a
    saver.  A factor is editable where the number is this company's own
    research and stands on no authoritative source, and nowhere else.
    """
    return frame['Class'].isin(EDITABLE_CLASSES)
'''
    source = source.rstrip() + b'\n' + ADDITION
    ast.parse(source.decode('utf-8'))
    with open(path + '.writing', 'wb') as handle:
        handle.write(source)
    os.replace(path + '.writing', path)
    print('LoaderFactorTable: editable() added')

# ---------------------------------------------------------------------
# 2: the Class lookup
# ---------------------------------------------------------------------

lookups = pd.read_csv('Reference/Lookups.csv')
wanted = [
    ('NGA', 'National Greenhouse Accounts', 1,
     'Published by the Department.  Used as published.'),
    ('Spend-based', 'Spend-based, US EPA', 2,
     'US EPA supply chain factors, and anything derived from them by a '
     'published conversion.  Used as published.'),
    ('Industry', 'Industry publication', 3,
     'A published factor from an industry body: worldsteel, AusLCI, AGO.  '
     'Used as published, whether it is one figure or a hundred.'),
    ('Internal', 'Our own research', 4,
     'A figure derived from our own research, standing on no authoritative '
     'source.  The only class that may be edited here.'),
]
rows = [{'ListName': 'Class', 'Code': code, 'Label': label, 'Dimension': '',
         'EmissionScale': '', 'QuantityScale': '', 'SortOrder': order,
         'Active': 'true', 'Notes': note}
        for code, label, order, note in wanted]
rebuilt = pd.concat([lookups[lookups['ListName'] != 'Class'],
                     pd.DataFrame(rows)], ignore_index=True)
rebuilt.to_csv('Reference/Lookups.csv.writing', index=False, encoding='utf-8')
os.replace('Reference/Lookups.csv.writing', 'Reference/Lookups.csv')
print('Lookups: Class is %s' % ', '.join(code for code, *_ in wanted))

# ---------------------------------------------------------------------
# 3: reclassify, and carry the items with them
# ---------------------------------------------------------------------
# Class is part of a factor's identity, so changing it changes the key every
# item points at.  Moving one without the other unprices four hundred items.

import LoaderFactorTable as F
import LoaderItems as I

BY_SOURCE = {
    'EPA SCEF': 'Spend-based',
    'EPA SCEF Margins': 'Spend-based',
    'worldsteel': 'Industry',
    'AusLCI': 'Industry',
    'AGO': 'Industry',
    'Company': 'Internal',
}

factors = F.load()
before = dict(zip(factors['FactorID'], factors['FactorKey']))

moving = factors['Class'] == 'Internal'
factors.loc[moving, 'Class'] = factors.loc[moving, 'Source'].map(BY_SOURCE)
unmapped = factors[factors['Class'].isna() | (factors['Class'] == '')]
if not unmapped.empty:
    raise SystemExit('no class for: %s' % sorted(set(unmapped['Source'])))

factors['FactorKey'] = [
    F.factor_key(row['Class'], row['Source'], row['Name'], row['Region'],
                 row['Unit'])
    for _, row in factors.iterrows()]

remap = {before[fid]: key for fid, key
         in zip(factors['FactorID'], factors['FactorKey'])
         if fid in before and before[fid] != key}

F.save(factors)
items = I.load()
for column in ('FactorKey_Imported', 'FactorKey_Assigned'):
    items[column] = items[column].replace(remap)
I.save(items)

print()
print('reclassified %d release(s); %d identities renamed and carried through '
      'to the items' % (int(moving.sum()), len(remap)))
print()
print(factors.groupby(['Class', 'Source'])
      .agg(identities=('FactorKey', 'nunique'),
           releases=('FactorID', 'size')).to_string())

check = I.load()
orphans = I.orphans(check, F.load())
print()
print('items %d, orphans after the move: %d' % (len(check), len(orphans)))
if not orphans.empty:
    print(orphans[['ItemID', 'FactorKey']].head(10).to_string(index=False))
print('editable factors: %d'
      % int(F.editable(F.load())['Class'].sum()
            if False else F.editable(F.load()).sum()))
