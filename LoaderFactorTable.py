"""The Factors table: every factor the model holds, in one shape.

A factor is Class, Source, Name, Region and Unit.  That is its identity, and
it is what an item points at.  A release is a version of that identity, and a
factor gains one every time its publication issues an edition: the National
Greenhouse Accounts have published five since 2022, so diesel oil is one
identity with five releases and not five different factors.

An item stores the identity and never a release.  The release is resolved at
build time against the year of the row being priced, which is why importing
the 2027 Accounts changes no item and no earlier year.  It is also why
EffectiveFrom exists separately from Release: the Accounts version themselves
by year, the US EPA by v1.3.0 and AusLCI by V48, so Release is the label a
person reads and EffectiveFrom is what the resolver reads.

Class says who governs a factor and decides who may change it.  Source says
who published it.  They are different questions: a capital band converted
from the EPA factors is Internal by governance and EPA by publication, and
losing either fact loses something an assessor asked for.
"""

import os

import pandas as pd

import LoaderLookups as Lookups
from Config import (CLASS_INTERNAL, CLASS_NGA, CLASS_SPEND,
                    CLASS_INDUSTRY, FACTOR_CLASSES,
                    EDITABLE_CLASSES)

from Paths import ROOT as BASE_DIR
REFERENCE_DIR = os.path.join(BASE_DIR, 'Reference')
FACTORS_PATH = os.path.join(REFERENCE_DIR, 'Factors.csv')

COLUMNS = ['FactorID', 'FactorKey', 'Class', 'Source', 'DisplaySource',
           'SourceCode',
           'Name', 'Release',
           'EffectiveFrom', 'Region', 'Unit', 'Scope1', 'Scope2', 'Scope3',
           'Obsolete', 'Reason', 'Import', 'SourceUnit', 'SourceFactor',
           'FactorDollarYear', 'SpendBasisYear', 'ConversionNote',
           'AddedBy', 'AddedAt', 'UpdatedAt', 'Notes']

SCOPES = ('Scope1', 'Scope2', 'Scope3')
NUMERIC = SCOPES + ('EffectiveFrom', 'SourceFactor', 'FactorDollarYear',
                    'SpendBasisYear')

# The fields that make a factor what it is.  Release is not among them: a new
# edition of the same publication is the same factor, later.
IDENTITY_FIELDS = ('Class', 'Source', 'Name', 'Region', 'Unit')


def factor_key(class_name, source, name, region, unit):
    return '|'.join([str(class_name), str(source), str(name), str(region),
                     str(unit)])


def load(path=None):
    """The whole table, typed."""
    path = path or FACTORS_PATH
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_csv(path)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ''
    for column in NUMERIC:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame['Obsolete'] = (frame['Obsolete'].astype(str).str.lower()
                         .isin(['true', '1', 'yes', 'y']))
    for column in COLUMNS:
        if column not in NUMERIC and column != 'Obsolete':
            frame[column] = frame[column].fillna('').astype(str)
    return frame[COLUMNS]


def save(frame, path=None):
    path = path or FACTORS_PATH
    out = frame.copy()
    for column in COLUMNS:
        if column not in out.columns:
            out[column] = ''
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.writing'
    out[COLUMNS].to_csv(temporary, index=False, encoding='utf-8')
    os.replace(temporary, path)


def next_id(frame):
    used = set()
    for value in frame.get('FactorID', pd.Series(dtype=str)).dropna():
        text = str(value)
        if text.startswith('F') and text[1:].isdigit():
            used.add(int(text[1:]))
    return 'F%04d' % ((max(used) + 1) if used else 1)


def identities(frame=None):
    """One row per factor identity, with the releases it has."""
    frame = load() if frame is None else frame
    if frame.empty:
        return frame
    live = frame[~frame['Obsolete']]
    return (live.groupby(['FactorKey'] + list(IDENTITY_FIELDS), dropna=False)
            .agg(Releases=('Release', 'nunique'),
                 Earliest=('EffectiveFrom', 'min'),
                 Latest=('EffectiveFrom', 'max')).reset_index())


def resolve(frame, factor_key_value, year):
    """The release of one factor that applies to a given year.

    The latest edition effective on or before the year, because a figure
    reported for 2024 was priced on what was published then and reissuing it
    against a later edition would restate a period already disclosed.  Where
    the year precedes every edition, the earliest is used: a factor has to
    price the row somehow, and the alternative is a gap nobody notices.
    """
    rows = frame[(frame['FactorKey'] == factor_key_value)
                 & (~frame['Obsolete'])]
    if rows.empty:
        return None
    applicable = rows[rows['EffectiveFrom'] <= int(year)]
    if applicable.empty:
        return rows.sort_values('EffectiveFrom').iloc[0]
    return applicable.sort_values('EffectiveFrom').iloc[-1]


def resolve_map(frame, years):
    """Every identity resolved for every year, in one pass.

    A build prices hundreds of thousands of rows over a few dozen years and a
    couple of hundred identities.  Resolving per row would run the lookup
    millions of times to answer a few thousand questions.
    """
    live = frame[~frame['Obsolete']].sort_values('EffectiveFrom')
    resolved = {}
    for key, rows in live.groupby('FactorKey'):
        effective = rows['EffectiveFrom'].to_numpy()
        for year in years:
            fits = effective <= int(year)
            position = fits.sum() - 1 if fits.any() else 0
            resolved[(key, int(year))] = rows.iloc[position]
    return resolved


def value_for(row, scope):
    """One scope's value off a resolved factor, or None where it has none."""
    if row is None:
        return None
    value = row.get(scope)
    return None if value is None or pd.isna(value) else float(value)


def unsourced(frame=None):
    """Factors whose source names no publication.

    Source is mandatory and a description does not satisfy it.  "Company
    screening factor" is a source, because this company stands behind it.
    "Recognised aviation factor" is not: recognised by whom, published where.
    """
    frame = load() if frame is None else frame
    if frame.empty:
        return frame
    named = frame['Source'].fillna('').astype(str).str.strip()
    own = frame['Reason'].astype(str).str.lower().str.contains(
        'company|assumption|stated here', na=False)
    return frame[named.eq('') | (named.eq('Company') & ~own)]


def summary(frame=None):
    """One line per class and source: how many, and how many identities."""
    frame = load() if frame is None else frame
    if frame.empty:
        return pd.DataFrame(columns=['Class', 'Source', 'Identities',
                                     'Releases'])
    return (frame.groupby(['Class', 'Source'])
            .agg(Identities=('FactorKey', 'nunique'),
                 Releases=('FactorID', 'size')).reset_index()
            .sort_values(['Class', 'Source']))


def editable(frame):
    """Which rows a person may change.

    One rule, in one place, so a screen cannot decide differently from a
    saver.  A factor is editable where the number is this company's own
    research and stands on no authoritative source, and nowhere else.
    """
    return frame['Class'].isin(EDITABLE_CLASSES)
