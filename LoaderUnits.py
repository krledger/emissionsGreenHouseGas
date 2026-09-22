"""LoaderUnits.py

Units, read from the registers PrepData keeps, and applied to the lines that
arrive in a unit their emission factor cannot take.

PrepData owns the unit model: ReferenceUnits.csv says what each unit is and
how it may be spelt, and ReferenceConversions.csv says what one of an item
holds.  PrepData applies both before it writes its outputs.  A line still
arrives here in a count when nobody has yet said what one of that item holds,
which is how a new pack size shows up: a 1000 kg grease hopper, a 1000 L IBC.

This module does two things with that.

    extend_spellings()   adds PrepData's spellings to the ones CalcUnits
                         knows, so a unit PrepData writes is never unknown
                         here.  A spelling is only ever added; the exact
                         definitions in CalcUnits are not replaced.

    resolve_counts()     carries a counted line into the unit its mapping
                         declares, where something says what one holds.  The
                         register is asked first, by item number.  Failing
                         that, the item description, where it states the
                         size: PrepData's own register uses the same basis,
                         recorded as "the description says what is in it".
                         A mass taken as a volume uses units.mass_as_volume
                         in ReferenceInputs.yaml.

Every line carried is marked with how, so Verify can show it and a person can
put the conversion into the PrepData register where it belongs.  A line that
cannot be carried is left as it is, and CalcNga reports it as a unit gap.

Last updated: 2026-09-11
"""

import os
import re

import pandas as pd

import CalcUnits
import Paths
from LookupIdentifiers import expected_uom

# Marks a line this module carried, and the multiplier it used.
BASIS_COLUMN = 'UnitBasis'
FACTOR_COLUMN = 'UnitFactor'
FROM_COLUMN = 'UnitFrom'

BASIS_REGISTER = 'PrepData register'
BASIS_DESCRIPTION = 'Item description'

# A size written into a description: a number, then a unit.  Only units that
# measure something are read; a millimetre, a size letter or an hour rating
# is not what a pack holds.
_SIZE = re.compile(
    r'(?<![\w.])(\d+(?:\.\d+)?)\s*'
    r'(KGS?|KILOS?|GMS?|G|LTRS?|LT|LITRES?|LITERS?|L|ML|CC|M3)(?![A-Z0-9])',
    re.IGNORECASE)

# The spelling in a description, to the unit this model works in.
_SIZE_UNITS = {
    'kg': 'kg', 'kgs': 'kg', 'kilo': 'kg', 'kilos': 'kg',
    'g': 'g', 'gm': 'g', 'gms': 'g',
    'l': 'L', 'lt': 'L', 'ltr': 'L', 'ltrs': 'L', 'litre': 'L',
    'litres': 'L', 'liter': 'L', 'liters': 'L',
    'ml': 'mL', 'cc': 'mL',
    'm3': 'm3',
}


# ---------------------------------------------------------------------
# REGISTERS
# ---------------------------------------------------------------------

def _prepdata_register(name):
    """One of PrepData's reference files, or None where it is not there."""
    path = os.path.join(Paths.PREPDATA_DIR, 'Reference', name)
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path, dtype=str).fillna('')
    except Exception:                               # pragma: no cover
        return None


def extend_spellings():
    """Add PrepData's unit spellings to the ones CalcUnits recognises.

    Returns the number of spellings added.  Only spellings of a unit this
    model already knows, or of a count or an hour, are taken, and only where
    CalcUnits does not already say something about that spelling.
    """
    units = _prepdata_register('ReferenceUnits.csv')
    if units is None or 'Unit' not in units.columns:
        return 0
    added = 0
    for _, row in units.iterrows():
        unit = str(row.get('Unit', '')).strip()
        if not unit:
            continue
        target = CalcUnits.canonical(unit)
        if target not in CalcUnits.UNITS and target not in ('h', 'Each'):
            continue
        for spelling in str(row.get('Spellings', '')).split(';'):
            key = spelling.strip().lower()
            if key and key not in CalcUnits.SYNONYMS:
                CalcUnits.SYNONYMS[key] = target
                added += 1
    return added


def _register_conversions():
    """Item number to (unit, multiplier) from ReferenceConversions.csv."""
    frame = _prepdata_register('ReferenceConversions.csv')
    if frame is None or 'ItemCode' not in frame.columns:
        return {}
    out = {}
    for _, row in frame.iterrows():
        code = str(row.get('ItemCode', '')).strip()
        unit = CalcUnits.canonical(str(row.get('ReportingUOM', '')).strip())
        try:
            factor = float(row.get('Factor', ''))
        except (TypeError, ValueError):
            continue
        if code and unit in CalcUnits.UNITS and factor > 0:
            out[code] = (unit, factor)
    return out


# ---------------------------------------------------------------------
# RESOLUTION
# ---------------------------------------------------------------------

def mass_as_volume():
    """Subactivity to litres per kilogram, from units.mass_as_volume."""
    from LoaderReference import load_settings
    out = {}
    for entry in ((load_settings().get('units', {}) or {})
                  .get('mass_as_volume') or []):
        try:
            out[str(entry.get('name'))] = float(entry.get('litres_per_kg'))
        except (TypeError, ValueError):
            continue
    return out


def _carry(unit, factor, declared, subactivity):
    """Multiplier from one of the item in `unit` to the declared unit.

    None where the two measure different things.  A mass is taken as a
    volume only for the subactivities units.mass_as_volume names, at the
    litres per kilogram it gives.
    """
    if CalcUnits.compatible(unit, declared):
        return factor * CalcUnits.factor(unit, declared)
    litres_per_kg = mass_as_volume().get(subactivity)
    if (litres_per_kg and CalcUnits.dimension(unit) == 'mass'
            and CalcUnits.dimension(declared) == 'volume'):
        in_kg = factor * CalcUnits.factor(unit, 'kg')
        return in_kg * litres_per_kg * CalcUnits.factor('L', declared)
    return None


def size_in_description(description, declared, subactivity=''):
    """The first size a description states that can reach the declared unit.

    Returns (multiplier, text matched) or (None, '').  "200L 250KG" against
    kilograms reads the 250 kg; against litres it reads the 200 L.
    """
    for number, spelt in _SIZE.findall(str(description or '')):
        unit = _SIZE_UNITS.get(spelt.lower())
        if unit is None:
            continue
        value = float(number)
        if value <= 0:
            continue
        multiplier = _carry(unit, value, declared, subactivity)
        if multiplier is not None:
            return multiplier, f'{number} {unit}'
    return None, ''


def resolve_counts(df):
    """Carry lines in a unit their mapping cannot take into the one it can.

    Works on the raw frame, before aggregation, where each row still carries
    its item number and description.  Adds BASIS_COLUMN, FACTOR_COLUMN and
    FROM_COLUMN; they are blank on every row not carried.
    """
    df[BASIS_COLUMN] = ''
    df[FACTOR_COLUMN] = float('nan')
    df[FROM_COLUMN] = ''

    pairs = df[['Activity', 'SubActivity', 'UOM']].astype(str) \
        .drop_duplicates()
    candidates = []
    for activity, subactivity, unit in pairs.itertuples(index=False):
        declared = expected_uom(activity, subactivity)
        if not declared or unit == declared:
            continue
        try:
            CalcUnits.factor(unit, declared)
            continue                     # converts already, nothing to do
        except CalcUnits.UnitError:
            candidates.append((activity, subactivity, unit, declared))
    if not candidates:
        return df

    register = _register_conversions()
    carried = 0
    for activity, subactivity, unit, declared in candidates:
        mask = ((df['Activity'].astype(str) == activity)
                & (df['SubActivity'].astype(str) == subactivity)
                & (df['UOM'].astype(str) == unit))
        items = df.loc[mask, ['Identifier', 'Description']].astype(str) \
            .drop_duplicates()
        for identifier, description in items.itertuples(index=False):
            multiplier, basis, said = None, '', ''
            code = identifier.split('.')[0].strip()
            if code in register:
                reg_unit, reg_factor = register[code]
                multiplier = _carry(reg_unit, reg_factor, declared, subactivity)
                if multiplier is not None:
                    basis, said = BASIS_REGISTER, f'{reg_factor:g} {reg_unit}'
            if multiplier is None:
                multiplier, said = size_in_description(
                    description, declared, subactivity)
                basis = BASIS_DESCRIPTION if multiplier is not None else ''
            if multiplier is None:
                continue
            at = mask & (df['Identifier'].astype(str) == identifier) \
                & (df['Description'].astype(str) == description)
            df.loc[at, 'Quantity'] = df.loc[at, 'Quantity'] * multiplier
            df.loc[at, 'UOM'] = declared
            df.loc[at, BASIS_COLUMN] = basis
            df.loc[at, FACTOR_COLUMN] = multiplier
            df.loc[at, FROM_COLUMN] = f'{unit}, one holds {said}'
            carried += int(at.sum())
    if carried:
        print(f'Units: {carried:,} counted rows carried into their declared '
              f'unit from the PrepData register or the item description')
    return df


def conversions_applied(frame):
    """The lines resolve_counts() carried, one row per item.

    Returns: DataSet, Activity, SubActivity, Identifier, Description, From,
    UOM, Multiplier, Basis, Rows, Quantity
    """
    columns = ['DataSet', 'Activity', 'SubActivity', 'Identifier',
               'Description', 'From', 'UOM', 'Multiplier', 'Basis', 'Rows',
               'Quantity']
    if frame is None or BASIS_COLUMN not in frame.columns:
        return pd.DataFrame(columns=columns)
    marked = frame[frame[BASIS_COLUMN].astype(str) != '']
    if marked.empty:
        return pd.DataFrame(columns=columns)
    keys = ['DataSet', 'Activity', 'SubActivity', 'Identifier', 'Description',
            FROM_COLUMN, 'UOM', FACTOR_COLUMN, BASIS_COLUMN]
    work = marked.copy()
    for column in keys:
        if column != FACTOR_COLUMN:
            work[column] = work[column].astype(str)
    out = work.groupby(keys, dropna=False).agg(
        Rows=('Quantity', 'size'), Quantity=('Quantity', 'sum')).reset_index()
    out = out.rename(columns={FROM_COLUMN: 'From', FACTOR_COLUMN: 'Multiplier',
                              BASIS_COLUMN: 'Basis'})
    return out.sort_values(['DataSet', 'SubActivity', 'Description'])[columns] \
        .reset_index(drop=True)


# ---------------------------------------------------------------------
# CORRECTIONS
# ---------------------------------------------------------------------
# A figure recorded in one unit under the heading of another cannot be found
# from the heading, and no register can say so.  units.corrections in
# ReferenceInputs.yaml names each one a person has found, and this reads the
# rows it names in the unit they are really in.

CORRECTION_COLUMN = 'UnitCorrection'


def corrections():
    """The corrections in force, from units.corrections."""
    from LoaderReference import load_settings
    return [c for c in ((load_settings().get('units', {}) or {})
                        .get('corrections') or []) if isinstance(c, dict)]


def _typical_month(frame):
    """The median monthly total of the positive months, or None."""
    if frame.empty:
        return None
    monthly = frame.groupby('Date')['Quantity'].sum()
    monthly = monthly[monthly > 0]
    return float(monthly.median()) if len(monthly) else None


def apply_corrections(df):
    """Read the rows each correction names in the unit they are really in.

    Needs parsed dates and the DataSet column.  Adds CORRECTION_COLUMN,
    carrying the correction's name on every row it changed.  A correction
    whose rows are within guard_ratio of the stream's typical month outside
    them is not applied: the source has been put right, or was never wrong.
    """
    df[CORRECTION_COLUMN] = ''
    for rule in corrections():
        name = str(rule.get('name', 'unnamed correction'))
        stated = CalcUnits.canonical(str(rule.get('stated_unit', '')))
        actual = CalcUnits.canonical(str(rule.get('actual_unit', '')))
        try:
            multiplier = CalcUnits.factor(actual, stated)
            guard = float(rule.get('guard_ratio', 100))
        except (CalcUnits.UnitError, TypeError, ValueError) as problem:
            print(f'Correction {name}: not applied, {problem}')
            continue

        stream = ((df['Activity'].astype(str) == str(rule.get('activity')))
                  & (df['SubActivity'].astype(str)
                     == str(rule.get('subactivity')))
                  & (df['UOM'].astype(str) == stated))
        target = stream.copy()
        if rule.get('dataset'):
            target &= df['DataSet'].astype(str) == str(rule['dataset'])
        if rule.get('from'):
            target &= df['Date'] >= pd.Timestamp(rule['from'])
        if rule.get('to'):
            target &= df['Date'] <= pd.Timestamp(rule['to'])
        if not target.any():
            print(f'Correction {name}: no rows to correct')
            continue

        # What the stream looks like where nobody says it is wrong: the
        # recorded months outside this correction, not already corrected.
        baseline = (stream & ~target & (df['DataSet'].astype(str) == 'Actual')
                    & (df[CORRECTION_COLUMN] == ''))
        typical = _typical_month(df[baseline])
        named = _typical_month(df[target])
        if not typical or not named:
            print(f'Correction {name}: not applied, no months outside it to '
                  f'compare against')
            continue
        ratio = named / typical if multiplier < 1 else typical / named
        if ratio < guard:
            print(f'Correction {name}: not applied, the rows are {ratio:,.1f} '
                  f'times the typical month and the guard is {guard:g}')
            continue
        df.loc[target, 'Quantity'] = df.loc[target, 'Quantity'] * multiplier
        df.loc[target, CORRECTION_COLUMN] = name
        print(f'Correction {name}: {int(target.sum()):,} rows read as '
              f'{actual} ({ratio:,.0f} times the typical month)')
    return df


def corrections_status(frame):
    """Every correction in force, and whether this build applied it."""
    rows = []
    marked = (frame[CORRECTION_COLUMN].astype(str)
              if frame is not None and CORRECTION_COLUMN in frame.columns
              else pd.Series(dtype=str))
    for rule in corrections():
        name = str(rule.get('name', ''))
        hit = frame[marked == name] if len(marked) else frame.iloc[0:0]
        rows.append({
            'Correction': name,
            'Applied': 'Yes' if len(hit) else 'No',
            'Lines': int(len(hit)),
            'Quantity now': float(hit['Quantity'].sum()) if len(hit) else 0.0,
            'Stated': str(rule.get('stated_unit', '')),
            'Read as': str(rule.get('actual_unit', '')),
            'Rows named': f"{rule.get('dataset', 'all')} "
                          f"{rule.get('from', '')} to {rule.get('to', '')}"
                          .replace(' to ', ' to ' if rule.get('from') else '')
                          .strip(),
            'Why': str(rule.get('factor_source', '')),
        })
    return pd.DataFrame(rows)
