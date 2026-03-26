"""
lookup_identifiers.py
Mapping from new CSV schema (Activity/SubActivity) to legacy columns
Last updated: 2026-03-25

The operations_metrics CSVs were restructured to remove embedded NGA/GRI
references.  This lookup restores the derived columns needed by downstream
code:

    NGAFuel     — NGA factor key for calc_emissions.py
    CommonName  — Normalised grouping key for GRI 14 export
    RowType     — Classification: fuel, electricity, production, consumption, revenue

Mapping is keyed on (Activity, SubActivity).  Where a SubActivity appears
under multiple Activities with different semantics (unlikely but guarded),
the Activity provides disambiguation.

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
# NGAFuel: Must match a key in calc_emissions.build_year_factor_map().
#          Empty string means no emission factor applies (production,
#          consumable, or electricity already accounted via fuel).
#
# CommonName: Grouping key used by export_gri14.py _get_production_metric()
#             and _get_gri_consumable().  Case-sensitive match.
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
    },
    ('Combustion', 'LPG'): {
        'NGAFuel': 'Liquefied petroleum gas (LPG)',
        'CommonName': 'LPG',
        'RowType': 'fuel',
    },
    ('Combustion', 'Acetylene'): {
        'NGAFuel': 'Gaseous fossil fuels other than those mentioned in the items above',
        'CommonName': 'Acetylene',
        'RowType': 'fuel',
    },
    ('Combustion', 'Lubricants'): {
        'NGAFuel': 'Petroleum based oils (other than petroleum based oil used as fuel)',
        'CommonName': 'Lubricants',
        'RowType': 'fuel',
    },
    ('Combustion', 'Greases'): {
        'NGAFuel': 'Petroleum based greases',
        'CommonName': 'Greases',
        'RowType': 'fuel',
    },
    # ---- INDUSTRIAL GASES (no NGA emission factor) ----
    ('Combustion', 'Oxygen'): {
        'NGAFuel': '',
        'CommonName': 'Liquid oxygen',
        'RowType': 'consumption',
    },
    ('Combustion', 'Nitrogen'): {
        'NGAFuel': '',
        'CommonName': 'Nitrogen',
        'RowType': 'consumption',
    },
    ('Combustion', 'Welding Gas'): {
        'NGAFuel': '',
        'CommonName': 'Welding gas',
        'RowType': 'consumption',
    },
    # ---- ELECTRICITY ----
    ('Electricity', 'Grid Power'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
    },
    ('Electricity', 'Residential'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
    },
    ('Electricity', 'Warehouse'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
    },
    ('Electricity', 'Water Delivery'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
    },
    ('Electricity', 'Site Power'): {
        'NGAFuel': '',
        'CommonName': 'Site electricity',
        'RowType': 'electricity',
    },
    ('Electricity', 'Sewage Treatment'): {
        'NGAFuel': 'Grid electricity',
        'CommonName': 'Grid electricity',
        'RowType': 'electricity',
    },
    # ---- BLASTING ----
    ('Blasting', 'Explosives'): {
        'NGAFuel': '',
        'CommonName': 'Explosives',
        'RowType': 'consumption',
    },
    # ---- REAGENTS ----
    ('Reagent', 'Cyanide'): {
        'NGAFuel': '',
        'CommonName': 'Cyanide',
        'RowType': 'consumption',
    },
    ('Reagent', 'Lime'): {
        'NGAFuel': '',
        'CommonName': 'Lime',
        'RowType': 'consumption',
    },
    ('Reagent', 'Caustic Soda'): {
        'NGAFuel': '',
        'CommonName': 'Caustic soda',
        'RowType': 'consumption',
    },
    ('Reagent', 'Acid'): {
        'NGAFuel': '',
        'CommonName': 'Hydrochloric acid',
        'RowType': 'consumption',
    },
    ('Reagent', 'Flocculant'): {
        'NGAFuel': '',
        'CommonName': 'Flocculant',
        'RowType': 'consumption',
    },
    ('Reagent', 'Soda Ash'): {
        'NGAFuel': '',
        'CommonName': 'Soda ash',
        'RowType': 'consumption',
    },
    ('Reagent', 'Carbon'): {
        'NGAFuel': '',
        'CommonName': 'Activated carbon',
        'RowType': 'consumption',
    },
    ('Reagent', 'Leach Aid'): {
        'NGAFuel': '',
        'CommonName': 'Leach aid',
        'RowType': 'consumption',
    },
    ('Reagent', 'Antiscalant'): {
        'NGAFuel': '',
        'CommonName': 'Antiscalant',
        'RowType': 'consumption',
    },
    ('Reagent', 'Dust Suppressant'): {
        'NGAFuel': '',
        'CommonName': 'Dust suppressant',
        'RowType': 'consumption',
    },
    ('Reagent', 'Degreaser'): {
        'NGAFuel': '',
        'CommonName': 'Degreaser',
        'RowType': 'consumption',
    },
    ('Reagent', 'Sodium Chlorite'): {
        'NGAFuel': '',
        'CommonName': 'Sodium chlorite',
        'RowType': 'consumption',
    },
    ('Reagent', 'Sodium Hypochlorite'): {
        'NGAFuel': '',
        'CommonName': 'Sodium hypochlorite',
        'RowType': 'consumption',
    },
    ('Reagent', 'Sewage Treatment'): {
        'NGAFuel': '',
        'CommonName': 'Sewage treatment',
        'RowType': 'consumption',
    },
    # ---- WEAR ITEMS ----
    ('Wear Item', 'Grinding Media'): {
        'NGAFuel': '',
        'CommonName': 'Grinding media',
        'RowType': 'consumption',
    },
    ('Wear Item', 'Grinding'): {
        'NGAFuel': '',
        'CommonName': 'Grinding media',
        'RowType': 'consumption',
    },
    ('Wear Item', 'Tyres'): {
        'NGAFuel': '',
        'CommonName': 'Tyres',
        'RowType': 'consumption',
    },
    # ---- MINING / PRODUCTION ----
    ('Mining', 'Ore ROM'): {
        'NGAFuel': '',
        'CommonName': 'ROM ore',
        'RowType': 'production',
    },
    ('Mining', 'Ore Mined'): {
        'NGAFuel': '',
        'CommonName': 'Ore mined',
        'RowType': 'production',
    },
    ('Mining', 'Ore Waste'): {
        'NGAFuel': '',
        'CommonName': 'Waste',
        'RowType': 'production',
    },
    ('Mining', 'Ore Milled'): {
        'NGAFuel': '',
        'CommonName': 'Ore milled',
        'RowType': 'production',
    },
    ('Mining', 'Ore Gold'): {
        'NGAFuel': '',
        'CommonName': 'Contained gold',
        'RowType': 'production',
    },
    ('Mining', 'Drilling'): {
        'NGAFuel': '',
        'CommonName': 'Drilling',
        'RowType': 'production',
    },
    ('Mining', 'Rehandle'): {
        'NGAFuel': '',
        'CommonName': 'Rehandle',
        'RowType': 'production',
    },
    ('Mining', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
    },
    # ---- CRUSHING / BENEFICIATION ----
    ('Crushing', 'Ore Crushed'): {
        'NGAFuel': '',
        'CommonName': 'Ore crushed',
        'RowType': 'production',
    },
    ('Crushing', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
    },
    ('Crushing - Beneficiation', 'Ore Crushed'): {
        'NGAFuel': '',
        'CommonName': 'Ore crushed',
        'RowType': 'production',
    },
    ('Crushing - Beneficiation', 'Ore Gold'): {
        'NGAFuel': '',
        'CommonName': 'Contained gold',
        'RowType': 'production',
    },
    # ---- MILLING ----
    ('Milling', 'Ore Milled'): {
        'NGAFuel': '',
        'CommonName': 'Ore milled',
        'RowType': 'total',
    },
    ('Milling', 'Ore Gold'): {
        'NGAFuel': '',
        'CommonName': 'Contained gold',
        'RowType': 'production',
    },
    ('Milling', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
    },
    # ---- DREDGING ----
    ('Dredging', 'Ore Dredge'): {
        'NGAFuel': '',
        'CommonName': 'Ore dredge',
        'RowType': 'production',
    },
    ('Dredging', 'Productivity'): {
        'NGAFuel': '',
        'CommonName': 'Productivity',
        'RowType': 'production',
    },
    # ---- REVENUE ----
    ('Revenue', 'Gold Recovered'): {
        'NGAFuel': '',
        'CommonName': 'Gold recovered',
        'RowType': 'production',
    },
    ('Revenue', 'Gold Sold'): {
        'NGAFuel': '',
        'CommonName': 'Gold sold',
        'RowType': 'revenue',
    },
    ('Revenue', 'Gold Poured'): {
        'NGAFuel': '',
        'CommonName': 'Gold poured',
        'RowType': 'production',
    },
    ('Revenue', 'Gold Leach Tails'): {
        'NGAFuel': '',
        'CommonName': 'Gold leach tails',
        'RowType': 'production',
    },
    ('Revenue', 'Gold Scats'): {
        'NGAFuel': '',
        'CommonName': 'Gold scats',
        'RowType': 'production',
    },
}


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

    keys = list(zip(df['Activity'], df['SubActivity']))

    df['NGAFuel'] = [nga_map.get(k, '') for k in keys]
    df['CommonName'] = [cn_map.get(k, '') for k in keys]
    df['RowType'] = [rt_map.get(k, '') for k in keys]

    # Warn about unmapped combinations
    unique_keys = set(keys)
    unmapped = unique_keys - set(IDENTIFIER_LOOKUP.keys())
    if unmapped:
        for act, sub in sorted(unmapped):
            logger.warning(
                f"No lookup entry for Activity='{act}', SubActivity='{sub}'.  "
                f"NGAFuel/CommonName/RowType will be empty."
            )

    return df
