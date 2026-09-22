"""
CalcUnits.py
The one place units are defined and converted.

Last updated: 2026-09-02

Every conversion in this model comes from here.  Nothing else divides by a
thousand, multiplies by 31.1034768, or decides that a litre is a thousandth of
a kilolitre.  A factor applied against the wrong unit is out by orders of
magnitude and reads as a plausible number, so the arithmetic is defined once,
in one table, and used everywhere.

How it works
------------
Each unit is declared once, as a dimension and a multiple of that dimension's
base unit.  A conversion is then derived, never listed:

    factor(a, b) = size of a / size of b

Deriving it has two consequences worth stating.  A conversion and its inverse
can never disagree, because both come from the same two numbers.  And a
conversion between units of different dimensions cannot be written down at
all, so litres cannot be turned into kilograms by a typo.

Base units, chosen so every declared multiple is exact:

    mass        kilogram
    volume      litre
    length      metre
    energy      megajoule
    count       one

Spelling
--------
Every metric unit is written in its abbreviated form: kg not kilogram, t not
Tonne, m not Meter, and L, kL, m3, g, km, kWh likewise.  One spelling per
unit, matching the upstream pipeline, so a quantity always groups with the
rest of its own line.  A count is not a metric unit and keeps its own word:
Each, Box, Roll, Pair, Kit, Set.

The same unit occasionally still arrives under more than one spelling.
SYNONYMS maps a spelling to the abbreviated form.  A synonym is a spelling
and never a conversion: both sides are the same unit, so nothing is scaled.
Anything that needs scaling is a conversion and belongs in UNITS.
"""

import pandas as pd

__all__ = [
    'UnitError', 'UNITS', 'SYNONYMS',
    'canonical', 'dimension', 'known', 'compatible',
    'factor', 'convert', 'scale_for', 'conversion_pairs',
    'KG_PER_TONNE', 'GRAMS_PER_KILOGRAM', 'LITRES_PER_KILOLITRE',
    'TROY_OUNCE_KG', 'GRAMS_PER_TROY_OUNCE', 'KWH_PER_MWH',
    'GJ_PER_KWH', 'MJ_PER_GJ', 'KG_PER_TONNE_CO2E',
    'TONNES_PER_MEGATONNE', 'TONNES_PER_KILOTONNE',
]


class UnitError(ValueError):
    """A unit is unknown, or the two units measure different things."""


# ---------------------------------------------------------------------
# UNIT TABLE
# ---------------------------------------------------------------------
# unit: (dimension, size in that dimension's base unit)
#
# Every entry is an exact definition or a defined constant.  Nothing here is
# an assumption, an average or a site specific factor: those are emission
# factors and belong in the factor files.

UNITS = {
    # -- mass, base kilogram ------------------------------------------
    'kg':  ('mass', 1.0),
    't':   ('mass', 1000.0),
    'g':   ('mass', 0.001),
    'mg':  ('mass', 0.000001),
    'kt':  ('mass', 1_000_000.0),
    'Mt':  ('mass', 1_000_000_000.0),
    # Troy ounce, the gold measure.  Exactly 31.1034768 grams by definition.
    'oz':  ('mass', 0.0311034768),

    # -- volume, base litre -------------------------------------------
    'L':   ('volume', 1.0),
    'mL':  ('volume', 0.001),
    'kL':  ('volume', 1000.0),
    'ML':  ('volume', 1_000_000.0),
    # A cubic metre is a kilolitre.  Both spellings are in use on site.
    'm3':  ('volume', 1000.0),

    # -- length, base metre -------------------------------------------
    'm':   ('length', 1.0),
    'mm':  ('length', 0.001),
    'cm':  ('length', 0.01),
    'km':  ('length', 1000.0),

    # -- energy, base megajoule ---------------------------------------
    # A kilowatt hour is 3.6 megajoules, so a kilowatt hour is 0.0036
    # gigajoules, which is the constant the energy content calculation uses.
    'MJ':  ('energy', 1.0),
    'GJ':  ('energy', 1000.0),
    'TJ':  ('energy', 1_000_000.0),
    'kWh': ('energy', 3.6),
    'MWh': ('energy', 3600.0),
    'GWh': ('energy', 3_600_000.0),
}


# Spelling variants.  Key is the spelling as it may arrive, lower cased;
# value is the spelling this model works in.  Both sides are the same unit.
SYNONYMS = {
    'kilogram': 'kg', 'kilograms': 'kg', 'kilo': 'kg', 'kilos': 'kg', 'kgs': 'kg',
    'tonne': 't', 'tonnes': 't', 'ton': 't', 'tons': 't', 'metric tonne': 't',
    'gram': 'g', 'grams': 'g', 'gm': 'g',
    'litre': 'L', 'litres': 'L', 'liter': 'L', 'liters': 'L', 'lt': 'L', 'l': 'L',
    'kilolitre': 'kL', 'kilolitres': 'kL', 'kiloliter': 'kL', 'kl': 'kL',
    'megalitre': 'ML', 'megalitres': 'ML',
    'cubic metre': 'm3', 'cubic meter': 'm3', 'cubic metres': 'm3', 'cum': 'm3',
    'metre': 'm', 'metres': 'm', 'meter': 'm', 'meters': 'm', 'lineal metre': 'm',
    'kilometre': 'km', 'kilometres': 'km', 'kilometer': 'km',
    'millimetre': 'mm', 'millimetres': 'mm',
    'kilowatt hour': 'kWh', 'kilowatt hours': 'kWh', 'kwh': 'kWh',
    'megawatt hour': 'MWh', 'megawatt hours': 'MWh', 'mwh': 'MWh',
    'gigajoule': 'GJ', 'gigajoules': 'GJ', 'gj': 'GJ',
    'ounce': 'oz', 'ounces': 'oz', 'troy ounce': 'oz', 'troy ounces': 'oz',
    # Hours.  A driver of productivity, never converted, so it is a spelling
    # only and carries no entry in UNITS.  PrepData writes 'h'.
    'hrs': 'h', 'hr': 'h', 'hour': 'h', 'hours': 'h',
    # Case only, so a unit written in the wrong case is not read as another.
    'kg': 'kg', 't': 't', 'g': 'g', 'm': 'm', 'm3': 'm3', 'km': 'km',
    'oz': 'oz', 'mj': 'MJ', 'tj': 'TJ', 'gwh': 'GWh', 'ml': 'mL',
}


# ---------------------------------------------------------------------
# NAMED CONSTANTS
# ---------------------------------------------------------------------
# Derived from the table above so a constant and a conversion can never
# disagree.  Use these where a formula reads better with a name than with a
# call, never as a second definition.

KG_PER_TONNE = UNITS['t'][1] / UNITS['kg'][1]                 # 1000
GRAMS_PER_KILOGRAM = UNITS['kg'][1] / UNITS['g'][1]           # 1000
LITRES_PER_KILOLITRE = UNITS['kL'][1] / UNITS['L'][1]         # 1000
TROY_OUNCE_KG = UNITS['oz'][1] / UNITS['kg'][1]               # 0.0311034768
GRAMS_PER_TROY_OUNCE = UNITS['oz'][1] / UNITS['g'][1]         # 31.1034768
KWH_PER_MWH = UNITS['MWh'][1] / UNITS['kWh'][1]               # 1000
GJ_PER_KWH = UNITS['kWh'][1] / UNITS['GJ'][1]                 # 0.0036
MJ_PER_GJ = UNITS['GJ'][1] / UNITS['MJ'][1]                   # 1000

# Emission factors are published in kilograms of carbon dioxide equivalent and
# reported in tonnes.  Same conversion, named for what it is at the point of
# use, so the emissions arithmetic does not carry a bare 1000.
KG_PER_TONNE_CO2E = KG_PER_TONNE

# Display scales for the physicals.  Ore is reported in megatonnes on a chart
# and tonnes on a table; both come from the same table so they cannot drift.
TONNES_PER_MEGATONNE = UNITS['Mt'][1] / UNITS['t'][1]         # 1,000,000
TONNES_PER_KILOTONNE = UNITS['kt'][1] / UNITS['t'][1]         # 1000


# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------

def canonical(uom):
    """The spelling this model works in.  Unmapped values pass through.

    A unit that is not a known spelling is returned trimmed and unchanged:
    this collapses duplicate spellings, it does not police the unit list.  A
    count such as Each, Kit or Roll is not a unit of measure and is returned
    as given.
    """
    if uom is None:
        return uom
    text = str(uom).strip()
    if not text:
        return text
    return SYNONYMS.get(text.lower(), text)


def known(uom):
    """True where the unit can be converted."""
    return canonical(uom) in UNITS


def dimension(uom):
    """What the unit measures, or None where it is not a unit of measure."""
    entry = UNITS.get(canonical(uom))
    return entry[0] if entry else None


def compatible(from_uom, to_uom):
    """True where the two measure the same thing."""
    left, right = dimension(from_uom), dimension(to_uom)
    return left is not None and left == right


def factor(from_uom, to_uom):
    """Multiply a quantity in from_uom by this to express it in to_uom.

    Raises UnitError where either unit is unknown or the two measure
    different things.  Both are errors that produce a plausible looking
    number, so neither may pass silently.
    """
    source, target = canonical(from_uom), canonical(to_uom)
    if source == target:
        return 1.0
    # A count is not a unit of measure and has no conversion, but Each and
    # each are the same count.  Compare case insensitively before deciding a
    # unit is unknown, so a disclosure written in lower case still matches the
    # data.
    if source.lower() == target.lower():
        return 1.0
    if source not in UNITS:
        raise UnitError(
            f"Unknown unit '{from_uom}'.  Add it to UNITS in CalcUnits.py, or "
            f"correct the source data.")
    if target not in UNITS:
        raise UnitError(
            f"Unknown unit '{to_uom}'.  Add it to UNITS in CalcUnits.py.")
    if UNITS[source][0] != UNITS[target][0]:
        raise UnitError(
            f"Cannot convert '{from_uom}' to '{to_uom}': "
            f"{UNITS[source][0]} is not {UNITS[target][0]}.")
    return UNITS[source][1] / UNITS[target][1]


def convert(quantity, from_uom, to_uom):
    """A quantity expressed in another unit.  Works on a number or a Series."""
    return quantity * factor(from_uom, to_uom)


def scale_for(uoms, to_uom, on_error='raise'):
    """A multiplier per row, carrying each row's unit to to_uom.

    Args:
        uoms:     Series of unit values, one per row
        to_uom:   the unit the factor or the total is expressed in
        on_error: 'raise' stops on a unit that cannot be converted;
                  'zero' scales it to nil and returns it in the report

    Returns:
        (scale, unconvertible) where scale is a float Series aligned to uoms
        and unconvertible maps a unit to the number of rows carrying it.
    """
    values = pd.Series(uoms).astype(str)
    scale = pd.Series(1.0, index=values.index)
    unconvertible = {}

    for unit in values.unique():
        try:
            multiplier = factor(unit, to_uom)
        except UnitError:
            if on_error == 'raise':
                raise
            unconvertible[unit] = int((values == unit).sum())
            multiplier = 0.0
        scale.loc[values.index[values == unit]] = multiplier

    return scale, unconvertible


def conversion_pairs():
    """Every convertible pair as {(from, to): multiplier}.

    Derived from UNITS, so it cannot disagree with factor().  Provided for
    code and reports that want the conversions as a table; the calculation
    path calls factor() and never reads this.
    """
    pairs = {}
    for source, (source_dim, source_size) in UNITS.items():
        for target, (target_dim, target_size) in UNITS.items():
            if source_dim == target_dim:
                pairs[(source, target)] = source_size / target_size
    return pairs
