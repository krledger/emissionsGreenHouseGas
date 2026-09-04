"""
LoaderReference.py
Reads the Scope 3 inputs distributed by PrepData.

Last updated: 2026-09-02

Nothing here calculates, and nothing here is a value.  This model holds no
Scope 3 factor and no Scope 3 parameter of its own: both files below are
produced by PrepData, distributed alongside the physicals and requested by
Data/PrepData.txt, exactly as LOM.yaml and ReferenceFx.csv are.  One register
governs every consumer, so a factor cannot be corrected in one program and
left stale in another.

    Data/Scope3Factors.csv      the factor table.  One flat file carrying
                                every Scope 3 factor with its unit, dollar
                                year, source and reference, built by
                                PrepData/BuildScope3Factors.py from the
                                registers in PrepData/Scope3/, exactly as
                                NgaFactors.csv is built from the National
                                Greenhouse Account workbooks
    Data/ReferenceInputs.yaml      assessment parameters and the exclusion
                                register: the roster, the travel pattern, the
                                waste streams, the currency basis and the
                                projection rule

    Data/ReferenceFx.csv        quarterly AUD/USD from PrepData

The capital goods register and the supplier spend classification are named in
the parameter file and read from Data/ where PrepData has distributed them.  A
register that is absent is reported; nothing falls back to a value held here

Factor strings
--------------
The registers carry a factor and its unit in one field, for example
"0.974 kg/USD" or "2.12 t/t".  parse_factor() splits them so the number and
the unit stay together and neither is guessed.  "In-code (NGA)" is not a
number; it marks a group whose emissions are computed from NGA factors in
CalcNga.py and must not be charged again on spend.
"""

import os
import re
from datetime import datetime

import pandas as pd
try:
    import yaml
except ModuleNotFoundError as exc:                # pragma: no cover
    raise ModuleNotFoundError(
        "PyYAML is required to read the YAML configuration.  Install it into "
        "the environment running the app:  pip install PyYAML  "
        "(it is listed in requirements.txt)."
    ) from exc

from Paths import ROOT as BASE_DIR
DATA_DIR = os.path.join(BASE_DIR, 'Data')

# Scope 3 methodology is owned here, not upstream.  PrepData prepares the
# physicals and the transactions every consumer needs; what counts as a
# purchased good, which factor applies to it and what a capital item is for
# greenhouse gas purposes are questions only this program asks, so the
# configuration and the registers behind them live in this folder.
#
# Data/ is still searched second, so a file distributed by an older PrepData
# run keeps working while the move settles.
REFERENCE_DIR = os.path.join(BASE_DIR, 'Reference')
CONFIG_PATH = os.path.join(REFERENCE_DIR, 'ReferenceInputs.yaml')


def reference_path(name):
    """A reference register, in the folder the reference registers live in.

    One place, and no fallback.  The fallback this replaced preferred the
    reference folder and quietly accepted a copy under Data, which meant two
    copies of the same register could drift apart with nothing to say which
    one the model was reading.  A missing register is now a missing file,
    which is a question somebody answers rather than a wrong number nobody
    sees.
    """
    return os.path.join(REFERENCE_DIR, name)


def prepdata_path(name):
    """An input PrepData supplies, which lands in Data.

    The exchange rate table is not a register somebody maintains here; it
    arrives with the operational data and belongs beside it.  Naming the two
    folders separately is what stops one file being looked for in both.
    """
    return os.path.join(DATA_DIR, name)

# Marks a product group computed from NGA factors elsewhere in the model.
IN_CODE_MARKER = 'In-code'

_FACTOR_RE = re.compile(r'^\s*([0-9]*\.?[0-9]+)\s*(.*)$')


def parse_factor(text):
    """Split "0.974 kg/USD" into (0.974, 'kg/USD').

    Returns (None, marker) where the field marks an in-code calculation, and
    (None, None) where the field is blank.  Never guesses a unit.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None, None
    text = str(text).strip()
    if not text or text.lower() == 'nan':
        return None, None
    if IN_CODE_MARKER.lower() in text.lower():
        return None, text
    match = _FACTOR_RE.match(text)
    if not match:
        return None, text
    return float(match.group(1)), match.group(2).strip() or None


def _read_csv(relative, locate=None, **kwargs):
    """Read a register from the folder that owns it."""
    path = (locate or reference_path)(relative)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, **kwargs)


class FxTable:
    """Quarterly AUD/USD, with a month taking its quarter's rate."""

    def __init__(self, frame=None):
        self.available = frame is not None and not frame.empty
        self.frame = frame if self.available else pd.DataFrame()
        self._by_quarter = {}
        if self.available:
            work = self.frame.copy()
            work['quarter_end'] = pd.to_datetime(work['quarter_end'])
            work['period'] = work['quarter_end'].dt.to_period('Q')
            self._by_quarter = dict(zip(work['period'], work['rate_audusd']))
            self._basis = dict(zip(work['period'], work.get('basis', '')))
            self._first = work['quarter_end'].min()
            self._last = work['quarter_end'].max()
            self._first_rate = work.sort_values('quarter_end')['rate_audusd'].iloc[0]
            self._last_rate = work.sort_values('quarter_end')['rate_audusd'].iloc[-1]

    def rate(self, date):
        """AUD/USD for the quarter containing date.

        Outside the published range the nearest published rate applies, which
        is the same treatment ReferenceFx.csv already gives its own forward
        years: held flat at the last actual.
        """
        if not self.available:
            return None
        period = pd.Timestamp(date).to_period('Q')
        if period in self._by_quarter:
            return float(self._by_quarter[period])
        if pd.Timestamp(date) < self._first:
            return float(self._first_rate)
        return float(self._last_rate)

    def basis(self, date):
        """Whether the quarter's rate is an actual or an assumption."""
        if not self.available:
            return None
        period = pd.Timestamp(date).to_period('Q')
        return self._basis.get(period)

    def actual_to(self):
        """Last quarter carrying an actual rate."""
        if not self.available or 'basis' not in self.frame.columns:
            return None
        actual = self.frame[self.frame['basis'].astype(str) == 'actual']
        if actual.empty:
            return None
        return pd.to_datetime(actual['quarter_end']).max()


class Reference:
    """Everything CalcGhgCategories.py needs, read once."""

    def __init__(self, config, factors, product_groups, epa_naics, exceptions,
                 capital_factors, capital_projects, capital_register,
                 supplier_spend, fx, errors):
        self.config = config
        self.factors = factors
        self.product_groups = product_groups
        self.epa_naics = epa_naics
        self.exceptions = exceptions
        self.capital_factors = capital_factors
        self.capital_projects = capital_projects
        self.capital_register = capital_register
        self.supplier_spend = supplier_spend
        self.fx = fx
        self.errors = errors

    # -- the factor table --------------------------------------------
    @property
    def has_factor_table(self):
        return self.factors is not None and not self.factors.empty

    def _table_rows(self, category, bases):
        """Rows of the factor table for one category and one set of bases."""
        if not self.has_factor_table:
            return None
        rows = self.factors[
            (self.factors['Category'] == category)
            & (self.factors['Basis'].astype(str).isin(bases))
        ]
        return rows if not rows.empty else None

    def _group_factors_from_table(self, category):
        """Product group factors for one category, from Scope3Factors.csv.

        A group carrying a physical unit factor takes it in preference to its
        spend factor, per the method: the highest priority physical unit
        source wins.
        """
        rows = self._table_rows(category, ('spend', 'physical', 'excluded'))
        if rows is None:
            return None

        rows = rows[rows['Key_Type'].astype(str) == 'ProductGroup']
        if rows.empty:
            return None

        # physical beats spend beats excluded for the same key.
        priority = {'physical': 0, 'spend': 1, 'excluded': 2}
        rows = rows.assign(
            _rank=rows['Basis'].astype(str).map(priority).fillna(9)
        ).sort_values('_rank')
        rows = rows.drop_duplicates(subset=['Key'], keep='first')

        built = pd.DataFrame({
            'Code': rows['Key'].astype(str).str.strip(),
            'Description': rows['Description'],
            'Factor': pd.to_numeric(rows['Factor'], errors='coerce'),
            'FactorUnit': rows['Factor_Unit'],
            'QuantityUOM': rows['Quantity_UOM'],
            'FactorSource': rows['Factor_Source'],
            'Basis': rows['Basis'].astype(str),
            'MatchKey': rows['Match_Key'],
            'Excluded': rows['Excluded'].astype(str).str.upper().eq('Y'),
            'ExcludeReason': rows['Exclude_Reason'],
        })
        return built.set_index('Code')

    def factor_for(self, category, key, default=None):
        """One factor by category and key.  The default is used where absent."""
        if not self.has_factor_table:
            return default
        rows = self.factors[
            (self.factors['Category'] == category)
            & (self.factors['Key'].astype(str) == str(key))
        ]
        if rows.empty:
            return default
        value = pd.to_numeric(rows['Factor'], errors='coerce').dropna()
        return float(value.iloc[0]) if not value.empty else default

    def capital_intensity(self):
        """Asset class to tonnes CO2-e per million dollars of capitalised value."""
        rows = self._table_rows(2, ('capital',))
        if rows is None:
            # Fall back to the register the table is built from.
            frame = self.capital_factors
            if frame.empty:
                return {}
            column = ('tCO2e_per_1M_AUD_with_margins'
                      if (self.config.get('category_2', {}) or {})
                      .get('use_margin_inclusive_factor', False)
                      else 'tCO2e_per_1M_AUD')
            return dict(zip(frame['Asset_Class'], frame[column]))
        values = pd.to_numeric(rows['Factor'], errors='coerce')
        return {str(k): float(v) for k, v in zip(rows['Key'], values)
                if pd.notna(v)}

    # -- product group factors ---------------------------------------
    def category_1_factors(self):
        """Product group to Category 1 factor.

        Returns a DataFrame indexed on Code with:
            Factor          number in the unit stated, or NaN
            FactorUnit      'kg/USD', or the physical unit where overridden
            FactorSource    the register's own source text
            Basis           'spend', 'physical' or 'in-code'
            Excluded        True where the group is charged elsewhere
            ExcludeReason   why
        """
        from_table = self._group_factors_from_table(1)
        if from_table is not None:
            return from_table

        excluded = self.config.get('category_1', {}).get('excluded_groups', {}) or {}
        physical = self.config.get('category_1', {}).get('physical_unit_factors', {}) or {}

        rows = []
        for _, row in self.product_groups.iterrows():
            code = str(row['Code']).strip()
            value, unit = parse_factor(row.get('S3_tCO2e'))
            source = row.get('S3_Source')

            if code in physical:
                # A physical unit factor takes precedence over spend, per the
                # method: highest priority physical-unit source wins.
                override = physical[code]
                rows.append({
                    'Code': code,
                    'Description': row.get('Description'),
                    'Factor': float(override['factor']),
                    'FactorUnit': override.get('unit'),
                    'QuantityUOM': override.get('quantity_uom'),
                    'FactorSource': override.get('source'),
                    'Basis': 'physical',
                    'Excluded': code in excluded,
                    'ExcludeReason': excluded.get(code),
                })
                continue

            basis = 'spend' if value is not None else (
                'in-code' if unit and IN_CODE_MARKER.lower() in str(unit).lower() else 'none'
            )
            rows.append({
                'Code': code,
                'Description': row.get('Description'),
                'Factor': value,
                'FactorUnit': unit,
                'QuantityUOM': None,
                'FactorSource': source,
                'Basis': basis,
                'Excluded': code in excluded or basis == 'in-code',
                'ExcludeReason': excluded.get(
                    code,
                    'Computed from NGA factors in CalcNga.py'
                    if basis == 'in-code' else None),
            })

        return pd.DataFrame(rows).set_index('Code')

    def category_4_factors(self):
        """Product group to Category 4 margin factor, same shape as above."""
        from_table = self._group_factors_from_table(4)
        if from_table is not None:
            return from_table

        excluded = self.config.get('category_4', {}).get('excluded_groups', {}) or {}

        rows = []
        for _, row in self.product_groups.iterrows():
            code = str(row['Code']).strip()
            value, unit = parse_factor(row.get('Cat4_Transport_tCO2e'))
            rows.append({
                'Code': code,
                'Description': row.get('Description'),
                'Factor': value,
                'FactorUnit': unit,
                'FactorSource': row.get('Cat4_Transport_Source'),
                'Basis': 'spend' if value is not None else 'none',
                'Excluded': code in excluded,
                'ExcludeReason': excluded.get(code),
            })
        return pd.DataFrame(rows).set_index('Code')

    # -- currency ----------------------------------------------------
    def usd_rate(self, date):
        """AUD to USD of the factor dollar year, for one month.

        Two steps, both stated in ConfigScope3.yaml: the AUD/USD rate for the
        quarter, then the deflator restating the spend year's dollars into the
        factor's dollar year.
        """
        currency = self.config.get('currency', {}) or {}
        mode = currency.get('mode', 'reference_fx')
        deflator = float(currency.get('deflator_2022_to_spend_year', 1.0) or 1.0)

        if mode == 'fixed':
            return float(currency.get('fixed_rate_audusd')) * deflator

        rate = self.fx.rate(date)
        if rate is None:
            # No table.  Fall back to the stated fixed rate rather than
            # silently producing nil emissions on every spend line.
            rate = float(currency.get('fixed_rate_audusd'))
        return rate * deflator

    def currency_note(self):
        """One line describing the conversion in force."""
        currency = self.config.get('currency', {}) or {}
        mode = currency.get('mode', 'reference_fx')
        deflator = float(currency.get('deflator_2022_to_spend_year', 1.0) or 1.0)
        year = currency.get('factor_dollar_year', 2022)
        if mode == 'fixed':
            base = f"fixed AUD/USD {currency.get('fixed_rate_audusd')}"
        else:
            actual_to = self.fx.actual_to()
            stamp = f", actual to {actual_to:%b %Y}" if actual_to is not None else ''
            base = f'quarterly AUD/USD from ReferenceFx.csv{stamp}'
        tail = 'no deflator applied' if deflator == 1.0 else f'deflator {deflator:.4f}'
        return f'{base}; factors in USD{year}; {tail}'


def load_reference(config_path=None):
    """Read the parameter file and every register it names.

    A missing register is recorded on the returned object rather than raised,
    so the model still starts and the tab reports what is absent.
    """
    config_path = config_path or CONFIG_PATH
    errors = []

    try:
        with open(config_path, 'r', encoding='utf-8') as handle:
            config = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        config = {}
        errors.append(
            f'ReferenceInputs.yaml not found at {config_path}.  It is distributed '
            f'by PrepData; check Data/PrepData.txt requests it and rerun the '
            f'pipeline.')
    except yaml.YAMLError as exc:
        config = {}
        errors.append(f'ReferenceInputs.yaml is not valid YAML: {exc}')

    registers = (config.get('meta', {}) or {}).get('factor_registers', {}) or {}

    def read(key, default_relative):
        relative = registers.get(key, default_relative)
        frame = _read_csv(relative)
        if frame is None:
            errors.append(f'{key}: not found at {reference_path(relative)}')
            return pd.DataFrame()
        return frame

    # The factor table is the authority.  Its absence is reported and the
    # registers below then answer directly, so the model still runs on a
    # checkout where the table has not been built.
    # Served from Factors.csv and Items.csv rather than read from a file.
    # The two tables are what is maintained; this is the shape the categories
    # have always consumed, so serving it keeps one change to one place.
    try:
        import LoaderItems
        factors = LoaderItems.as_factor_table()
        if factors.empty:
            errors.append(
                'Factors.csv or Items.csv is empty, so no Scope 3 factor is '
                'held.  Import the factor table before building.')
    except Exception as exc:                        # pragma: no cover
        errors.append(f'The factor table could not be served: {exc}')
        factors = pd.DataFrame()

    # A published factor superseded by a company assumption.  Applied here,
    # at the one place the factor table is read, so every category picks the
    # override up and none of them has to know it happened.  The published
    # figure is not discarded; it is carried beside the one that replaced it.
    # An item pointed at a different factor is already resolved above, on
    # the item, so nothing is applied on top here.
    applied_overrides = pd.DataFrame()
    try:
        import LoaderItems
        assigned = LoaderItems.load()
        applied_overrides = assigned[assigned['IsAssigned']]
    except Exception as exc:                        # pragma: no cover
        errors.append(f'Item assignments could not be read: {exc}')

    # Registers read at run time.  The rest, the product group register, the
    # NAICS mapping, the exceptions and the capital factor map, are the
    # builder's inputs and live in PrepData; their content reaches this model
    # inside Scope3Factors.csv, so they are not read here and their absence is
    # not an error.
    capital_projects = read('capital_projects', 'Cat2ProjectScreen.csv')
    capital_register = read('capital_register', 'Cat2RegisterReview.csv')
    supplier_spend = read('supplier_spend', 'ApSpendClassification.csv')
    product_groups = pd.DataFrame()
    epa_naics = pd.DataFrame()
    exceptions = pd.DataFrame()
    capital_factors = pd.DataFrame()

    # The exchange rate table comes from PrepData with the operational data,
    # so it is read from Data and not from the reference folder.  Without it
    # every spend based factor is converted at whatever the fallback rate is,
    # which is a difference of tens of thousands of tonnes and no warning on
    # the face of the result.
    fx_relative = (config.get('meta', {}) or {}).get('reference_fx', 'ReferenceFx.csv')
    fx_frame = _read_csv(fx_relative, locate=prepdata_path)
    if fx_frame is None:
        errors.append(
            f'reference_fx: {fx_relative} was not found in Data.  Spend based '
            f'factors are converted at the fallback rate and the Scope 3 '
            f'total is not reliable.')
    fx = FxTable(fx_frame)

    reference = Reference(
        config=config,
        factors=factors,
        product_groups=product_groups,
        epa_naics=epa_naics,
        exceptions=exceptions,
        capital_factors=capital_factors,
        capital_projects=capital_projects,
        capital_register=capital_register,
        supplier_spend=supplier_spend,
        fx=fx,
        errors=errors,
    )
    # Carried on the reference so a screen can say which figures are not the
    # publication's without reading the register again.
    reference.overrides = applied_overrides
    return reference
