"""Capital goods register, owned by Emissions.

Category 2 is the emissions of making the plant the Company buys, recognised
in full in the year it is acquired.  Which acquisitions qualify is an
emissions judgement, not an operational one: a rental is an expensed service
and belongs in Category 1, and only an owned or finance leased acquisition
produces a Category 2 event at all.

That judgement is why this register exists and why it is maintained here
rather than inferred from a project tracker.  A project system records what
the business decided to spend; it does not record whether the thing bought is
a capital good for greenhouse gas purposes, when it was commissioned, or
whether the Company took title.  Inferring those is how a category ends up
either double counted or silently nil.

A capital item is entered once and lives through two states:

    Forecast    expected, with an expected commissioning date and an
                expected value.  Contributes to the forecast inventory.
    Actual      commissioned or acquired, with the date and value that
                actually applied.  Contributes to the recorded inventory
                and supersedes its own forecast.

The item keeps one CapitalID across that transition, so the forecast and the
actual are the same item and never both counted.
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

__all__ = [
    'REGISTER_PATH', 'COLUMNS', 'STATUSES', 'TENURES', 'TENURE_HELP',
    'factor_classes', 'apply_factor_classes',
    'load_register', 'save_register', 'blank_item', 'next_capital_id',
    'resolve_register', 'register_issues', 'to_scope3_register',
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPE3_DIR = os.path.join(BASE_DIR, 'Scope3')
REGISTER_PATH = os.path.join(SCOPE3_DIR, 'CapitalGoodsRegister.csv')

STATUSES = ('Forecast', 'Actual', 'Cancelled')

COLUMNS = [
    'CapitalID',            # stable across the forecast to actual transition
    'AssetDescription',
    'AssetClass',           # the register's own class, e.g. Excavator
    'FactorClass',          # the factor table class it maps to
    'Department', 'CostCentre',
    'Status',               # Forecast, Actual or Cancelled
    'Tenure',               # Owned, Finance lease, Rental
    'ExpectedCommissionDate',
    'ActualCommissionDate',
    'ForecastValueAUD',
    'ActualValueAUD',
    'Factor', 'FactorSource',
    'RecognitionBasis',     # what the emission is recognised against
    'DataQuality',
    'AddedBy', 'AddedAt', 'UpdatedAt',
    'Notes',
]

# What produces a Category 2 event.  An acquisition does: the Company takes
# the asset and the emissions of making it belong to the year it is acquired.
# A rental does not: it is a service bought over time, and its emissions are
# the supplier's, reaching the Company as Category 1 in the periods it is
# used.  A finance lease sits with acquisitions because it transfers the risks
# and rewards of ownership in substance, whatever the paper says.
CAPITALISING_TENURES = ('Owned', 'Finance lease')

# The wording users choose from, so the distinction is made at the point of
# entry rather than left to be inferred from a one-word label.
TENURES = ('Owned', 'Finance lease', 'Rental')
TENURE_HELP = {
    'Owned': 'Purchased outright.  Category 2 in the year of commissioning.',
    'Finance lease': 'Long term lease transferring the risks and rewards of '
                     'ownership.  Category 2, same as a purchase.',
    'Rental': 'Operating lease or hire.  Not Category 2: a service, and its '
              'emissions reach the Company through Category 1.',
}


def factor_classes(reference):
    """Asset class to factor class and intensity, for entry by selection.

    A person entering a capital item knows what the asset is.  They do not
    know its emission factor, and should not be asked to: the class is the
    choice, and the factor follows from it.
    """
    settings = (getattr(reference, 'config', {}) or {}).get('category_2') or {}
    mapping = settings.get('asset_class_map') or {}
    intensity = reference.capital_intensity() if reference is not None else {}
    return {
        asset: {'factor_class': factor_class,
                'factor': intensity.get(factor_class)}
        for asset, factor_class in sorted(mapping.items())
    }


def apply_factor_classes(register, reference):
    """Fill the factor class and factor from the asset class on every row.

    Derived rather than entered, so the register cannot carry a factor that
    disagrees with the class beside it.
    """
    lookup = factor_classes(reference)
    if register is None or register.empty:
        return register
    frame = register.copy()
    resolved = frame['AssetClass'].astype(str).map(lookup)
    frame['FactorClass'] = resolved.map(
        lambda item: item['factor_class'] if isinstance(item, dict) else '')
    frame['Factor'] = resolved.map(
        lambda item: item['factor'] if isinstance(item, dict) else None)
    frame['FactorSource'] = frame['FactorClass'].map(
        lambda name: f'EPA SCEF, {name}, banded to AUD' if name else '')
    return frame


def blank_item(capital_id=''):
    """An empty register row, so the UI and the loader agree on the shape."""
    row = {column: '' for column in COLUMNS}
    row.update({
        'CapitalID': capital_id,
        'Status': 'Forecast',
        'Tenure': 'Owned',
        'ForecastValueAUD': 0.0,
        'ActualValueAUD': 0.0,
        'RecognitionBasis': 'Capitalised value, recognised on commissioning',
        'DataQuality': 'Entered from acquisition record',
        'AddedAt': datetime.now().strftime('%Y-%m-%d'),
    })
    return row


def next_capital_id(register):
    """The next identifier in sequence, stable and human readable."""
    if register is None or register.empty:
        return 'CAP0001'
    numbers = (register['CapitalID'].astype(str)
               .str.extract(r'(\d+)', expand=False).dropna().astype(int))
    return f'CAP{(numbers.max() + 1) if len(numbers) else 1:04d}'


def load_register(path=None):
    """The register as written, with types settled and nothing inferred."""
    path = path or REGISTER_PATH
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_csv(path)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ''
    for column in ('ForecastValueAUD', 'ActualValueAUD', 'Factor'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    for column in ('ExpectedCommissionDate', 'ActualCommissionDate'):
        frame[column] = pd.to_datetime(frame[column], errors='coerce')
    frame['Status'] = frame['Status'].astype(str).str.strip().str.title()
    return frame[COLUMNS]


def save_register(register, path=None):
    """Write the register back, stamping when each row was last touched."""
    path = path or REGISTER_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame = pd.DataFrame(register).reindex(columns=COLUMNS)
    frame['UpdatedAt'] = datetime.now().strftime('%Y-%m-%d')
    frame.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------
# RESOLUTION
# ---------------------------------------------------------------------

def resolve_register(register, actuals_to=None):
    """Decide, per item, which figures the inventory should use.

    An item that has been commissioned uses its actual date and value; one
    that has not uses its expected date and value.  It is never both, because
    it is one item with one identifier, and that is the whole reason the
    identifier is stable.

    Args:
        register:   the register as loaded.
        actuals_to: last recorded month.  An item commissioned after it is
                    still an actual item; the date decides which period it
                    lands in, not whether it counts.

    Returns:
        The register with RecognisedDate, RecognisedValueAUD, RecognisedBasis
        and Counts added.  Counts is False where the item contributes nothing
        and Notes says why.
    """
    if register is None or register.empty:
        out = pd.DataFrame(columns=COLUMNS + [
            'RecognisedDate', 'RecognisedValueAUD', 'RecognisedBasis',
            'Counts', 'Issue'])
        return out

    # Settle types here rather than assuming the caller loaded the file.
    # A blank date read as a string is not a date, and a register built in
    # memory by the user interface has not been through load_register.
    frame = pd.DataFrame(register).copy()
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ''
    for column in ('ForecastValueAUD', 'ActualValueAUD', 'Factor'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    for column in ('ExpectedCommissionDate', 'ActualCommissionDate'):
        frame[column] = pd.to_datetime(frame[column], errors='coerce')

    is_actual = frame['Status'].astype(str).str.strip().str.title().eq('Actual')
    is_cancelled = frame['Status'].astype(str).str.strip()\
        .str.title().eq('Cancelled')

    frame['RecognisedDate'] = frame['ExpectedCommissionDate'].where(
        ~is_actual, frame['ActualCommissionDate'])
    frame['RecognisedValueAUD'] = frame['ForecastValueAUD'].where(
        ~is_actual, frame['ActualValueAUD'])
    frame['RecognisedBasis'] = pd.Series('Forecast', index=frame.index).where(
        ~is_actual, 'Actual')

    capitalises = frame['Tenure'].astype(str).isin(CAPITALISING_TENURES)
    has_date = frame['RecognisedDate'].notna()
    has_value = frame['RecognisedValueAUD'].fillna(0.0) > 0

    frame['Counts'] = capitalises & has_date & has_value & ~is_cancelled

    # Why an item does not count, in the order a reviewer would ask.  Never
    # invent a commissioning date to make an item countable: an item missing
    # one is outstanding, and saying so is the point.
    issue = pd.Series('', index=frame.index)
    issue = issue.mask(is_cancelled, 'Cancelled')
    issue = issue.mask(~is_cancelled & ~capitalises,
                       'Rental, an expensed service in Category 1')
    issue = issue.mask(~is_cancelled & capitalises & ~has_date,
                       'Outstanding: no commissioning date')
    issue = issue.mask(~is_cancelled & capitalises & has_date & ~has_value,
                       'Outstanding: no value')
    frame['Issue'] = issue
    return frame


def register_issues(register):
    """Outstanding items, in the shape the build log records them."""
    resolved = resolve_register(register)
    if resolved.empty:
        return pd.DataFrame(columns=['Category', 'Item', 'Detail', 'Severity'])
    gaps = resolved[resolved['Issue'].str.startswith('Outstanding')]
    return pd.DataFrame([{
        'Category': 2,
        'Item': f"{row['CapitalID']} {row['AssetDescription']}".strip(),
        'Detail': row['Issue'],
        'Severity': 'Warning',
    } for _, row in gaps.iterrows()])


def to_scope3_register(register):
    """The register in the shape the Category 2 calculation already reads.

    The calculation is not rewritten to suit a new file.  The register is
    presented in the columns it already expects, so the methodology stays
    exactly where it was proven and only the source of the data moves.
    """
    resolved = resolve_register(register)
    if resolved.empty:
        return pd.DataFrame(columns=['Unit', 'Category', 'Department', 'Make',
                                     'Model', 'Model_Year', 'Tenure',
                                     'Market_Value_AUD', 'Cat2_Applies'])
    counting = resolved[resolved['Counts']]
    return pd.DataFrame({
        'Unit': counting['CapitalID'].astype(str).values,
        'Category': counting['AssetClass'].astype(str).values,
        'Department': counting['Department'].astype(str).values,
        'Make': counting['AssetDescription'].astype(str).values,
        'Model': counting['FactorClass'].astype(str).values,
        # The calculation recognises the acquisition in the year of the date
        # it resolved to, forecast or actual alike.
        'Model_Year': pd.to_datetime(counting['RecognisedDate']).dt.year.values,
        'Tenure': counting['Tenure'].astype(str).values,
        'Market_Value_AUD': counting['RecognisedValueAUD'].values,
        'Cat2_Applies': 'Yes',
    })
