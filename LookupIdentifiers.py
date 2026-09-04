"""
LookupIdentifiers.py
Mapping from new CSV schema (Activity/SubActivity) to legacy columns
Last updated: 2026-03-25

The OperationsMetrics CSVs were restructured to remove embedded NGA/GRI
references.  This lookup restores the derived columns needed by downstream
code:

    NGAFuel     — NGA factor key for CalcNga.py
    CommonName  — Normalised grouping key for GRI 14 export
    RowType     — Classification: fuel, electricity, production, consumption, revenue

Mapping is keyed on (Activity, SubActivity).  Where a SubActivity appears
under multiple Activities with different semantics (unlikely but guarded),
the Activity provides disambiguation.

Two layers, checked in order:

    IDENTIFIER_LOOKUP   an exact (Activity, SubActivity) pair.  Every line
                        that carries an emission factor, a production measure
                        or a named consumable is registered here by hand.

    ACTIVITY_FALLBACK   an Activity whose SubActivity list is open, so it is
                        classified at the Activity level and the SubActivity
                        is carried through as the common name.  Stores and
                        Headcount are the two: the 2026-08 inventory change
                        raised the item register from 150 items to 8,113 and
                        put 138 stores product groups into the physicals, none
                        of which carries an emission factor and each of which
                        is a Category 1 purchased good identified by its
                        product group rather than by name.

An Activity in neither layer is reported, as before.

Electricity sub-types:
    Grid Power, Residential, Warehouse, Water Delivery → Grid electricity
    Site Power → Site electricity (no NGAFuel — diesel already counted as fuel)
"""

import pandas as pd


# =====================================================================
# MASTER LOOKUP TABLE
# =====================================================================
# Each entry: (Activity, SubActivity) → dict of derived columns.
#
# NGAFuel: Must match a key in CalcNga.build_year_factor_map().
#          Empty string means no emission factor applies (production,
#          consumable, or electricity already accounted via fuel).
#
# CommonName: Grouping key used by ExportGri14.py _get_production_metric()
#             and _get_gri_consumable().  Case-sensitive match.
#
# UOM: The reporting unit the line is expected to carry.  A consumer that
#      sums a quantity or applies a factor per unit must check it: a line
#      holding two units cannot be summed, and a factor applied against the
#      wrong unit is out by orders of magnitude.  None marks a pair that
#      deliberately carries more than one measure, so no single unit applies
#      and the pair must be summed within a unit or not at all.
#
# RowType: Classification for filtering:
#     fuel         — combustible fuel with NGA emission factor
#     electricity  — purchased or generated electricity
#     production   — physical output (ore, gold, throughput)
#     consumption  — reagent, wear item, industrial gas
#     revenue      — financial / sold product metric

IDENTIFIER_LOOKUP = {
    # ---- FUELS (Scope 1 emission factor applies) ----
    ('Combustion', 'Diesel'): {
        'NGAFuel': 'Diesel oil',
        'CommonName': 'Diesel',
        'RowType': 'fuel',
        'UOM': 'kL',
    },
    ('Combustion', 'LPG'): {
        'NGAFuel': 'Liquefied petroleum gas (LPG)',
        'CommonName': 'LPG',
        'RowType': 'fuel',
        'UOM': 'kL',
    },
    ('Combustion', 'Acetylene'): {
        'NGAFuel': 'Gaseous fossil fuels other than those mentioned in the items above',
        'CommonName': 'Acetylene',
        'RowType': 'fuel',
        'UOM': 'm3',
    },
    ('Combustion', 'Lubricants'): {
        'NGAFuel': 'Petroleum based oils (other than petroleum based oil used as fuel)',
        'CommonName': 'Lubricants',
        'RowType': 'fuel',
        'UOM': 'kL',
    },
    ('Combustion', 'Greases'): {
        'NGAFuel': 'Petroleum based greases',
        'CommonName': 'Greases',
        'RowType': 'fuel',
        'UOM': 'L',
    },
    # ---- INDUSTRIAL GASES (no NGA emission factor) ----
    ('Combustion', 'Oxygen'): {
        'NGAFuel': '',
        'CommonName': 'Liquid oxygen',
        'RowType': 'consumption',
        'UOM': 'm3',
    },
    ('Combustion', 'Nitrogen'): {
        'NGAFuel': '',
        'CommonName': 'Nitrogen',
        'RowType': 'consumption',
        'UOM': 'm3',
    },
    ('Combustion', 'Welding Gas'): {
        'NGAFuel': '',
        'CommonName': 'Welding gas',
        'RowType': 'consumption',
        'UOM': 'm3',
    },
    # ---- ELECTRICITY ----
    ('Electricity', 'Grid Power'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
        'UOM': 'kWh',
    },
    ('Electricity', 'Residential'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
        'UOM': 'kWh',
    },
    ('Electricity', 'Warehouse'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
        'UOM': 'kWh',
    },
    ('Electricity', 'Water Delivery'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
        'UOM': 'kWh',
    },
    ('Electricity', 'Site Power'): {
        'NGAFuel': '',
        'CommonName': 'Site electricity',
        'RowType': 'electricity',
        'UOM': 'kWh',
    },
    ('Electricity', 'Sewage Treatment'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
        'UOM': 'kWh',
    },
    # ---- BLASTING ----
    ('Blasting', 'Explosives'): {
        'NGAFuel': '',
        'CommonName': 'Explosives',
        'RowType': 'consumption',
        'UOM': 't',
    },
    # Blasted volume in BCM.  A production measure, not a consumable, and not
    # a second reading of explosives tonnes.
    ('Blasting', 'Broken Stock'): {
        'NGAFuel': '',
        'CommonName': 'Blasted volume',
        'RowType': 'production',
        'UOM': 'BCM',
    },
    # ---- REAGENTS ----
    ('Reagent', 'Cyanide'): {
        'NGAFuel': '',
        'CommonName': 'Cyanide',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Lime'): {
        'NGAFuel': '',
        'CommonName': 'Lime',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Caustic Soda'): {
        'NGAFuel': '',
        'CommonName': 'Caustic soda',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Acid'): {
        'NGAFuel': '',
        'CommonName': 'Hydrochloric acid',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Flocculant'): {
        'NGAFuel': '',
        'CommonName': 'Flocculant',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Soda Ash'): {
        'NGAFuel': '',
        'CommonName': 'Soda ash',
        'RowType': 'consumption',
        'UOM': 'kg',
    },
    ('Reagent', 'Carbon'): {
        'NGAFuel': '',
        'CommonName': 'Activated carbon',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Leach Aid'): {
        'NGAFuel': '',
        'CommonName': 'Leach aid',
        'RowType': 'consumption',
        'UOM': 'kg',
    },
    ('Reagent', 'Antiscalant'): {
        'NGAFuel': '',
        'CommonName': 'Antiscalant',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Reagent', 'Dust Suppressant'): {
        'NGAFuel': '',
        'CommonName': 'Dust suppressant',
        'RowType': 'consumption',
        'UOM': 'kL',
    },
    ('Reagent', 'Degreaser'): {
        'NGAFuel': '',
        'CommonName': 'Degreaser',
        'RowType': 'consumption',
        'UOM': 'kL',
    },
    ('Reagent', 'Sodium Chlorite'): {
        'NGAFuel': '',
        'CommonName': 'Sodium chlorite',
        'RowType': 'consumption',
        'UOM': 'kg',
    },
    ('Reagent', 'Sodium Hypochlorite'): {
        'NGAFuel': '',
        'CommonName': 'Sodium hypochlorite',
        'RowType': 'consumption',
        'UOM': 'L',
    },
    ('Reagent', 'Sewage Treatment'): {
        'NGAFuel': '',
        'CommonName': 'Sewage treatment',
        'RowType': 'consumption',
        'UOM': 'kg',
    },
    # ---- WEAR ITEMS ----
    ('Wear Item', 'Grinding Media'): {
        'NGAFuel': '',
        'CommonName': 'Grinding media',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Wear Item', 'Grinding'): {
        'NGAFuel': '',
        'CommonName': 'Grinding media',
        'RowType': 'consumption',
        'UOM': 't',
    },
    ('Wear Item', 'Tyres'): {
        'NGAFuel': '',
        'CommonName': 'Tyres',
        'RowType': 'consumption',
        'UOM': 'Each',
    },
    # ---- MINING / PRODUCTION ----
    ('Mining', 'Ore ROM'): {
        'NGAFuel': '',
        'CommonName': 'ROM ore',
        'RowType': 'production',
        'UOM': 't',
    },
    ('Mining', 'Ore Mined'): {
        'NGAFuel': '',
        'CommonName': 'Ore mined',
        'RowType': 'production',
        'UOM': 'BCM',
    },
    ('Mining', 'Ore Waste'): {
        'NGAFuel': '',
        'CommonName': 'Waste',
        'RowType': 'production',
        'UOM': None,
    },
    ('Mining', 'Ore Milled'): {
        'NGAFuel': '',
        'CommonName': 'Ore milled',
        'RowType': 'production',
        'UOM': 't',
    },
    ('Mining', 'Ore Gold'): {
        'NGAFuel': '',
        'CommonName': 'Contained gold',
        'RowType': 'production',
        'UOM': 'g',
    },
    ('Mining', 'Drilling'): {
        'NGAFuel': '',
        'CommonName': 'Drilling',
        'RowType': 'production',
        'UOM': 'm',
    },
    ('Mining', 'Rehandle'): {
        'NGAFuel': '',
        'CommonName': 'Rehandle',
        'RowType': 'production',
        'UOM': 't',
    },
    # Current name for the same measure.  'Rehandle' is retained above so a
    # file written before the rename still maps.
    ('Mining', 'Ore Rehandle'): {
        'NGAFuel': '',
        'CommonName': 'Rehandle',
        'RowType': 'production',
        'UOM': 't',
    },
    ('Mining', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
        'UOM': None,
    },
    # ---- CRUSHING / BENEFICIATION ----
    ('Crushing', 'Ore Crushed'): {
        'NGAFuel': '',
        'CommonName': 'Ore crushed',
        'RowType': 'production',
        'UOM': 't',
    },
    ('Crushing', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
        'UOM': 'hrs',
    },
    ('Crushing - Beneficiation', 'Ore Crushed'): {
        'NGAFuel': '',
        'CommonName': 'Ore crushed',
        'RowType': 'production',
        'UOM': 'dmt',
    },
    ('Crushing - Beneficiation', 'Ore Gold'): {
        'NGAFuel': '',
        'CommonName': 'Contained gold',
        'RowType': 'production',
        'UOM': 'g',
    },
    # ---- MILLING ----
    ('Milling', 'Ore Milled'): {
        'NGAFuel': '',
        'CommonName': 'Ore milled',
        'RowType': 'total',
        'UOM': 't',
    },
    ('Milling', 'Ore Gold'): {
        'NGAFuel': '',
        'CommonName': 'Contained gold',
        'RowType': 'production',
        'UOM': 'g',
    },
    ('Milling', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
        'UOM': None,
    },
    # ---- DREDGING ----
    ('Dredging', 'Ore Dredge'): {
        'NGAFuel': '',
        'CommonName': 'Ore dredge',
        'RowType': 'production',
        'UOM': 't',
    },
    ('Dredging', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
        'UOM': 'hrs',
    },
    # ---- REVENUE ----
    ('Revenue', 'Gold Recovered'): {
        'NGAFuel': '',
        'CommonName': 'Gold recovered',
        'RowType': 'production',
        'UOM': 'oz',
    },
    ('Revenue', 'Gold Sold'): {
        'NGAFuel': '',
        'CommonName': 'Gold sold',
        'RowType': 'revenue',
        'UOM': 'oz',
    },
    ('Revenue', 'Gold Poured'): {
        'NGAFuel': '',
        'CommonName': 'Gold poured',
        'RowType': 'production',
        'UOM': 'oz',
    },
    ('Revenue', 'Gold Leach Tails'): {
        'NGAFuel': '',
        'CommonName': 'Gold leach tails',
        'RowType': 'production',
        'UOM': 'g',
    },
    ('Revenue', 'Gold Scats'): {
        'NGAFuel': '',
        'CommonName': 'Gold scats',
        'RowType': 'production',
        'UOM': 'g',
    },
}


# =====================================================================
# ACTIVITY-LEVEL FALLBACK
# =====================================================================
# An Activity whose SubActivity list is open, classified at the Activity
# level.  CommonName is taken from the SubActivity so the line keeps its own
# identity for grouping and display.
#
# Neither carries an NGA emission factor.  Stores lines are Category 1
# purchased goods, priced rather than measured, and are assessed on spend by
# product group in CalcGhgCategories.py.  Headcount is a driver, in FTE, and produces
# no emission of its own; it is the basis for the Category 7 commuting
# estimate.

ACTIVITY_FALLBACK = {
    'Stores': {
        'NGAFuel': '',
        'RowType': 'stores',
    },
    'Headcount': {
        'NGAFuel': '',
        'RowType': 'headcount',
    },
}

# A fallback common name is the subactivity, and a stores subactivity can
# carry the same name as a mapped line while meaning something else in a
# different unit.  Stores/Explosives is rock rivets in boxes, not the
# explosive loaded into a hole in tonnes; Stores/Lubricants is tins and cans,
# not bulk oil in kilolitres.  Left alone the two would group together and sum
# across units, so a colliding name is qualified.

FALLBACK_NAME_SUFFIX = ' (stores)'

_MAPPED_COMMON_NAMES = {
    entry['CommonName'] for entry in IDENTIFIER_LOOKUP.values()
    if entry.get('CommonName')
}


def fallback_common_name(subactivity):
    """Common name for an activity-level line, qualified where it collides."""
    name = str(subactivity)
    if name in _MAPPED_COMMON_NAMES:
        return name + FALLBACK_NAME_SUFFIX
    return name


def expected_uom(activity, subactivity):
    """The reporting unit a mapped line is expected to carry.

    None where the pair carries more than one measure by design, and None for
    an activity-level line, whose unit varies by item.
    """
    entry = IDENTIFIER_LOOKUP.get((str(activity), str(subactivity)))
    return entry.get('UOM') if entry else None


# =====================================================================
# ENRICHMENT FUNCTION
# =====================================================================

def enrich_with_lookup(df):
    """Add NGAFuel, CommonName, RowType columns from Activity/SubActivity.

    Rows with no match get empty strings (not NaN) so downstream
    notna() / != '' filters behave consistently.

    Logs a warning for any (Activity, SubActivity) pairs not in the
    lookup table so new items are caught early.

    Args:
        df: DataFrame with Activity and SubActivity columns

    Returns:
        DataFrame with NGAFuel, CommonName, RowType columns added
    """
    import logging
    logger = logging.getLogger(__name__)

    # Build lookup Series for vectorised mapping
    nga_map = {k: v['NGAFuel'] for k, v in IDENTIFIER_LOOKUP.items()}
    cn_map = {k: v['CommonName'] for k, v in IDENTIFIER_LOOKUP.items()}
    rt_map = {k: v['RowType'] for k, v in IDENTIFIER_LOOKUP.items()}

    # The frame holds at most a few hundred distinct Activity/SubActivity
    # pairs however many rows it carries, so the classification is resolved
    # once per pair and then mapped back.  At projection scale this is the
    # difference between a fraction of a second and several minutes.
    pairs = df[['Activity', 'SubActivity']].drop_duplicates()
    keys = list(zip(pairs['Activity'], pairs['SubActivity']))

    resolved = {}
    for activity, subactivity in keys:
        entry = IDENTIFIER_LOOKUP.get((activity, subactivity))
        if entry is not None:
            resolved[(activity, subactivity)] = (
                entry['NGAFuel'], entry['CommonName'], entry['RowType'])
            continue

        fallback = ACTIVITY_FALLBACK.get(activity)
        if fallback is not None:
            # SubActivity becomes the common name so the line keeps its
            # identity without an entry per product group.
            resolved[(activity, subactivity)] = (
                fallback['NGAFuel'], fallback_common_name(subactivity),
                fallback['RowType'])
            continue

        resolved[(activity, subactivity)] = ('', '', '')

    row_keys = pd.MultiIndex.from_arrays(
        [df['Activity'], df['SubActivity']])
    lookup = pd.DataFrame(
        [resolved[k] for k in keys],
        index=pd.MultiIndex.from_tuples(keys),
        columns=['NGAFuel', 'CommonName', 'RowType'])
    mapped = lookup.reindex(row_keys)

    df['NGAFuel'] = mapped['NGAFuel'].to_numpy()
    df['CommonName'] = mapped['CommonName'].to_numpy()
    df['RowType'] = mapped['RowType'].to_numpy()

    # Report combinations that reached neither layer.  These carry no
    # classification at all, so anything material here is a gap in the table.
    unmapped = {
        (act, sub) for act, sub in set(keys)
        if (act, sub) not in IDENTIFIER_LOOKUP and act not in ACTIVITY_FALLBACK
    }
    if unmapped:
        for act, sub in sorted(unmapped):
            logger.warning(
                f"No lookup entry for Activity='{act}', SubActivity='{sub}'.  "
                f"NGAFuel/CommonName/RowType will be empty."
            )

    # Report a line whose unit is not the one its mapping declares.  A pair
    # declaring None carries more than one measure by design and is skipped.
    if 'UOM' in df.columns:
        # Only the distinct Activity/SubActivity/UOM combinations matter here,
        # so the check runs on those rather than walking every row.
        combos = df[['Activity', 'SubActivity', 'UOM']].astype(str).drop_duplicates()
        for (activity, subactivity), group in combos.groupby(
                ['Activity', 'SubActivity'], observed=True, dropna=False):
            declared = expected_uom(activity, subactivity)
            if not declared:
                continue
            found = sorted(set(group['UOM'].unique()) - {declared})
            if found:
                logger.warning(
                    f"UOM: Activity='{activity}', SubActivity='{subactivity}' "
                    f"is declared as '{declared}' but carries {found}.  Update "
                    f"the lookup or correct the source file."
                )

    return df
