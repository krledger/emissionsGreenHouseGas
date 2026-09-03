"""
BuildScope3Factors.py
=====================
Builds the Scope 3 inputs PrepData distributes.

Writes two files into Data/, which downstream programs request through their
own prepData.txt:

    Scope3Factors.csv   one flat factor table, every Scope 3 factor with its
                        unit, dollar year, source and reference
    Scope3Inputs.yaml   the assessment parameters: the roster, the travel
                        pattern, the waste streams, the currency basis, the
                        projection rule and the exclusion register

Source registers live in Scope3/ and are maintained by hand:

    ProductGroups.csv           master product group register
    EpaNaicsFactorMapping.csv   the NAICS class behind each spend factor
    Cat2FactorMap.csv           capital goods intensity per asset class
    Cat2ProjectScreen.csv       approved capital projects
    Cat2RegisterReview.csv      asset register review
    ApSpendClassification.csv   supplier level spend
    Scope3Inputs.yaml           assessment parameters

No downstream program holds a Scope 3 factor or parameter of its own.  Every
value comes from here, so one register governs every consumer and a factor
cannot be corrected in one program and left stale in another.

PURPOSE:
    Scope 3 factors arrive from several places: a product group register, an
    EPA NAICS mapping, a capital goods intensity table and the treatment,
    travel and vehicle factors stated in the parameter file.  The model should
    read one file, not five, for the same reason it reads NgaFactors.csv
    rather than five National Greenhouse Account workbooks.

    This utility parses those sources once and writes a single, flat,
    version controllable artefact carrying every factor with its unit, its
    dollar year, its source and the reference behind it.

USAGE:
    python BuildScope3Factors.py                  # writes both files into Data/
    python BuildScope3Factors.py --check          # rebuild and report differences only

OUTPUT:
    Data/Scope3Factors.csv with columns:
        Category        GHG Protocol category number
        Basis           spend, physical, capital, treatment, travel, vehicle,
                        refining, or excluded
        Key             the value the model matches on
        Key_Type        what Key is: ProductGroup, AssetClass, CommonName,
                        WasteStream, TravelLeg, CommuteLeg or Product
        Description     plain description of the item
        Factor          the number
        Factor_Unit     its unit, stated in full
        Quantity_UOM    the unit the quantity must be in, for physical factors
        Factor_Year     the dollar year for a spend factor; blank otherwise
        Factor_Source   the publication the factor comes from
        Source_Ref      the specific table, commodity class or entry
        NAICS_Code      EPA commodity class, where the factor is an EPA factor
        NAICS_Title     its title
        Match_Key       an alternative match value, where Key is not what the
                        physicals carry
        Excluded        Y where the item is charged elsewhere in the model
        Exclude_Reason  why
        Notes           anything an assurer needs beside the number

    A blank cell means the column does not apply to that row, never that the
    value is unknown.  An unknown value is not written at all.
"""

import argparse
import os
import re
import sys

import pandas as pd

# The department vocabulary belongs with the registers, and Emissions owns
# both.  The chart of accounts is still PrepData's, because a division is
# operational data every consumer shares; what is emissions-owned is the
# knowledge that a register writes the site's shorthand for three of them.
# One vocabulary, held in Config, so this builder and the model that reads its
# output cannot settle on different names for the same department.
from Config import DEPARTMENT_ALIASES, canonical_department  # noqa: F401


def account_divisions(accounts_df):
    """Every division the chart of accounts carries."""
    if accounts_df is None or 'division' not in accounts_df.columns:
        return set()
    return {str(v).strip() for v in accounts_df['division'].dropna()}
try:
    import yaml
except ModuleNotFoundError as exc:                # pragma: no cover
    raise ModuleNotFoundError(
        "PyYAML is required to read the YAML configuration.  Install it into "
        "the environment running the app:  pip install PyYAML  "
        "(it is listed in requirements.txt)."
    ) from exc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPE3_DIR = os.path.join(BASE_DIR, 'Scope3')
# Outputs land beside the registers they are built from.  Emissions owns
# both, so there is nothing to distribute and nowhere else for them to go.
DATA_DIR = SCOPE3_DIR
CONFIG_PATH = os.path.join(SCOPE3_DIR, 'Scope3Inputs.yaml')
OUTPUT_PATH = os.path.join(DATA_DIR, 'Scope3Factors.csv')
INPUTS_OUTPUT_PATH = os.path.join(DATA_DIR, 'Scope3Inputs.yaml')

# Registers a consumer reads at run time rather than through the factor
# table: the capital goods register carries an asset's tenure and capitalised
# value, and the supplier spend classification is the coverage test against
# accounts payable.  Both are distributed as written.
DISTRIBUTED_REGISTERS = (
    'Cat2RegisterReview.csv',
    'Cat2ProjectScreen.csv',
    'ApSpendClassification.csv',
)

COLUMNS = [
    'Category', 'Basis', 'Key', 'Key_Type', 'Description',
    'Factor', 'Factor_Unit', 'Quantity_UOM', 'Factor_Year',
    'Factor_Source', 'Source_Ref', 'NAICS_Code', 'NAICS_Title',
    'Match_Key', 'Excluded', 'Exclude_Reason', 'Notes',
]

_FACTOR_RE = re.compile(r'^\s*([0-9]*\.?[0-9]+)\s*(.*)$')
_IN_CODE = 'in-code'


def _distribute_register(source, destination, name):
    """Copy a register out, in the department vocabulary of the accounts.

    A register is kept by hand and uses the site's shorthand for a few
    departments; the physicals carry the division as the chart of accounts
    writes it.  A consumer that groups the two together sees one department
    under two names, so the shorthand is resolved here, once, on the way out.
    Anything that matches neither a division nor an alias is reported and
    written through unchanged, because a silent guess is how a department
    goes missing.
    """
    import shutil
    frame = None
    try:
        frame = pd.read_csv(source)
    except Exception as exc:                      # pragma: no cover - defensive
        print(f'  {name}: could not read for department check ({exc})')

    column = None
    if frame is not None:
        column = next((c for c in frame.columns
                       if c.strip().lower() == 'department'), None)

    if column is None:
        shutil.copy2(source, destination)
        print(f'  copied {name}')
        return

    accounts = _load_accounts()
    divisions = account_divisions(accounts)
    original = frame[column].astype(str).str.strip()
    frame[column] = original.map(canonical_department)

    changed = {}
    for was, now in zip(original, frame[column]):
        if was != now:
            changed[was] = now
    unknown = sorted({
        value for value in frame[column].unique()
        if divisions and value and value.lower() != 'nan'
        and value not in divisions
    })

    frame.to_csv(destination, index=False)
    note = ''
    if changed:
        note = ('; ' + ', '.join(f'{was} to {now}'
                                 for was, now in sorted(changed.items())))
    print(f'  copied {name}{note}')
    for value in unknown:
        print(f'  {name}: department "{value}" is not a division in the '
              f'chart of accounts and has no alias')


def _load_accounts():
    """Chart of accounts, or None where it is not beside this script."""
    path = os.path.join(BASE_DIR, 'Data', 'ReferenceAccounts.csv')
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:                             # pragma: no cover - defensive
        return None


def _split_factor(text):
    """Split "0.974 kg/USD" into (0.974, 'kg/USD').  In-code marks return None."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None, None
    text = str(text).strip()
    if not text or text.lower() == 'nan':
        return None, None
    if _IN_CODE in text.lower():
        return None, text
    match = _FACTOR_RE.match(text)
    if not match:
        return None, text
    return float(match.group(1)), match.group(2).strip() or None


def _read(name, folder=SCOPE3_DIR):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        print(f'  missing: {path}')
        return pd.DataFrame()
    return pd.read_csv(path)


def _config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def _naics_lookup(mapping):
    """Product group name to (code, title), from the EPA mapping register."""
    if mapping.empty:
        return {}
    lookup = {}
    for _, row in mapping.iterrows():
        key = str(row.get('Product_Group', '')).strip().lower()
        if key:
            lookup[key] = (row.get('NAICS_Code'), row.get('NAICS_Title'))
    return lookup


def build_rows():
    """Every factor the model needs, as a list of dicts."""
    config = _config()
    product_groups = _read('ProductGroups.csv')
    epa_mapping = _read('EpaNaicsFactorMapping.csv')
    capital = _read('Cat2FactorMap.csv')

    naics = _naics_lookup(epa_mapping)
    rows = []

    # -- Category 1 and 4, product group factors ----------------------
    settings_1 = config.get('category_1', {}) or {}
    excluded = settings_1.get('excluded_groups', {}) or {}
    physical = settings_1.get('physical_unit_factors', {}) or {}
    excluded_4 = (config.get('category_4', {}) or {}).get('excluded_groups', {}) or {}

    for _, row in product_groups.iterrows():
        code = str(row.get('Code', '')).strip()
        if not code:
            continue
        description = str(row.get('Description', '')).strip()
        code_naics, title_naics = naics.get(description.lower(), (None, None))

        # Category 1, spend.
        value, unit = _split_factor(row.get('S3_tCO2e'))
        in_code = unit is not None and _IN_CODE in str(unit).lower()
        is_excluded = code in excluded or in_code
        reason = excluded.get(code)
        if reason is None and in_code:
            reason = 'Computed from NGA factors in CalcEmissions.py'

        if value is not None or is_excluded:
            rows.append({
                'Category': 1,
                'Basis': 'excluded' if is_excluded else 'spend',
                'Key': code,
                'Key_Type': 'ProductGroup',
                'Description': description,
                'Factor': value,
                'Factor_Unit': None if is_excluded else unit,
                'Factor_Year': None if is_excluded else 2022,
                'Factor_Source': row.get('S3_Source'),
                'NAICS_Code': code_naics,
                'NAICS_Title': title_naics,
                'Excluded': 'Y' if is_excluded else 'N',
                'Exclude_Reason': reason,
            })

        # Category 4, the margin component of the same factor.
        # An excluded group is written even without a margin factor, so the
        # exclusion is recorded rather than reading as a gap in the register.
        margin, margin_unit = _split_factor(row.get('Cat4_Transport_tCO2e'))
        excluded_here = code in excluded_4 or is_excluded
        if margin is not None or excluded_here:
            rows.append({
                'Category': 4,
                'Basis': 'excluded' if excluded_here else 'spend',
                'Key': code,
                'Key_Type': 'ProductGroup',
                'Description': description,
                'Factor': margin,
                'Factor_Unit': margin_unit,
                'Factor_Year': 2022,
                'Factor_Source': row.get('Cat4_Transport_Source'),
                'NAICS_Code': code_naics,
                'NAICS_Title': title_naics,
                'Excluded': 'Y' if excluded_here else 'N',
                'Exclude_Reason': excluded_4.get(code) or (
                    'Inbound freight is inside the Category 3 well to tank '
                    'coefficient.' if excluded_here else None),
            })

    # -- Category 1, physical unit overrides --------------------------
    # These take precedence over the spend factor for the same group.
    for code, spec in physical.items():
        rows.append({
            'Category': 1,
            'Basis': 'physical',
            'Key': code,
            'Key_Type': 'ProductGroup',
            'Description': spec.get('description', code),
            'Factor': spec.get('factor'),
            'Factor_Unit': spec.get('unit'),
            'Quantity_UOM': spec.get('quantity_uom'),
            'Factor_Source': spec.get('source'),
            'Match_Key': spec.get('match_common_name'),
            'Excluded': 'N',
            'Notes': ' '.join(str(spec.get('note', '')).split()) or None,
        })

    # -- Category 2, capital goods intensity by asset class -----------
    use_margins = bool((config.get('category_2', {}) or {})
                       .get('use_margin_inclusive_factor', False))
    column = ('tCO2e_per_1M_AUD_with_margins' if use_margins
              else 'tCO2e_per_1M_AUD')
    for _, row in capital.iterrows():
        rows.append({
            'Category': 2,
            'Basis': 'capital',
            'Key': row.get('Asset_Class'),
            'Key_Type': 'AssetClass',
            'Description': row.get('NAICS_Title'),
            'Factor': row.get(column),
            'Factor_Unit': 't CO2-e per $1M AUD',
            'Factor_Year': 2022,
            'Factor_Source': 'US EPA SCEF v1.3, band calibrated to AUD',
            'Source_Ref': ('with margins' if use_margins else 'without margins'),
            'NAICS_Code': row.get('NAICS_Code'),
            'NAICS_Title': row.get('NAICS_Title'),
            'Excluded': 'N',
        })

    # -- Category 5, waste treatment ----------------------------------
    for stream in (config.get('category_5', {}) or {}).get('streams', []) or []:
        rows.append({
            'Category': 5,
            'Basis': 'treatment',
            'Key': stream.get('name'),
            'Key_Type': 'WasteStream',
            'Description': stream.get('name'),
            'Factor': stream.get('factor_tco2e_per_t'),
            'Factor_Unit': 't CO2-e per t',
            'Quantity_UOM': 't',
            'Factor_Source': stream.get('factor_source'),
            'Excluded': 'N',
        })

    # -- Category 6, travel -------------------------------------------
    for leg in (config.get('category_6', {}) or {}).get('air_legs', []) or []:
        rows.append({
            'Category': 6,
            'Basis': 'travel',
            'Key': leg.get('name'),
            'Key_Type': 'TravelLeg',
            'Description': f"Air sector, {leg.get('name')}",
            'Factor': leg.get('factor_kgco2e_per_pkm'),
            'Factor_Unit': 'kg CO2-e per passenger km',
            'Quantity_UOM': 'passenger km',
            'Factor_Source': leg.get('factor_source'),
            'Excluded': 'N',
        })
    for leg in (config.get('category_6', {}) or {}).get('road_legs', []) or []:
        rows.append({
            'Category': 6,
            'Basis': 'travel',
            'Key': leg.get('name'),
            'Key_Type': 'TravelLeg',
            'Description': f"Road leg, {leg.get('name')}",
            'Factor': leg.get('factor_kgco2e_per_km'),
            'Factor_Unit': 'kg CO2-e per km',
            'Quantity_UOM': 'km',
            'Factor_Source': leg.get('factor_source'),
            'Excluded': 'N',
        })

    # -- Category 7, commuting ----------------------------------------
    roster = (config.get('category_7', {}) or {}).get('roster', {}) or {}
    if roster.get('factor_kgco2e_per_km') is not None:
        rows.append({
            'Category': 7,
            'Basis': 'vehicle',
            'Key': 'Commuting passenger vehicle',
            'Key_Type': 'CommuteLeg',
            'Description': 'Passenger vehicle, diesel and petrol blend',
            'Factor': roster.get('factor_kgco2e_per_km'),
            'Factor_Unit': 'kg CO2-e per km',
            'Quantity_UOM': 'km',
            'Factor_Source': roster.get('factor_source'),
            'Excluded': 'N',
        })

    # -- Category 10, refining ----------------------------------------
    settings_10 = config.get('category_10', {}) or {}
    if settings_10.get('refining_intensity_kgco2e_per_kg_au') is not None:
        rows.append({
            'Category': 10,
            'Basis': 'refining',
            'Key': 'Gold refining',
            'Key_Type': 'Product',
            'Description': 'Refining of dore into investment grade gold',
            'Factor': settings_10.get('refining_intensity_kgco2e_per_kg_au'),
            'Factor_Unit': 'kg CO2-e per kg Au',
            'Quantity_UOM': 'kg Au',
            'Factor_Source': settings_10.get('factor_source'),
            'Excluded': 'N',
        })

    return rows


def build_table():
    """The factor table, ordered and with every column present."""
    frame = pd.DataFrame(build_rows())
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[COLUMNS]
    return frame.sort_values(['Category', 'Basis', 'Key']).reset_index(drop=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Build Data/Scope3Factors.csv from the source registers.')
    parser.add_argument('--check', action='store_true',
                        help='rebuild and report differences without writing')
    parser.add_argument('--output', default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    print('Building the Scope 3 factor table')
    table = build_table()
    print(f'  {len(table):,} factors')
    for category, count in table.groupby('Category').size().items():
        print(f'    category {category}: {count:,}')

    if args.check:
        if not os.path.exists(args.output):
            print(f'  {args.output} does not exist yet')
            return 1
        existing = pd.read_csv(args.output)
        same = existing.shape == table.shape and existing.fillna('').astype(str) \
            .equals(table.fillna('').astype(str))
        print('  unchanged' if same else '  DIFFERS from the file on disk')
        return 0 if same else 1

    table.to_csv(args.output, index=False)
    print(f'  written to {args.output}')

    # The parameter file and the two registers a consumer reads at run time
    # are distributed as they are written.  Copying them into Data/ puts every
    # Scope 3 input in the folder downstream programs read, beside LOM.yaml
    # and ReferenceFx.csv.
    # The configuration is already where consumers read it.  There was a
    # copy step here when the file had to travel from PrepData to Emissions;
    # it does not travel any more.
    import shutil
    if os.path.abspath(CONFIG_PATH) != os.path.abspath(INPUTS_OUTPUT_PATH):
        shutil.copy2(CONFIG_PATH, INPUTS_OUTPUT_PATH)
    print(f'  copied to {INPUTS_OUTPUT_PATH}')
    # No distribution step: the registers are already in this folder.
    return 0


if __name__ == '__main__':
    sys.exit(main())
