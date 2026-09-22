"""
LoaderLom.py
Reads Data/LOM.yaml, the shared milestone reference distributed with the
PrepData outputs.

Last updated: 2026-09-02

LOM.yaml is written by hand when a new life of mine revision lands and is
read by every downstream program, so one set of dates governs PrepData, the
forecast engine and this model.  Nothing here derives a date; the file is the
authority and the constants in Config.py are the fallback used only when the
file is absent or a key is missing.

Structure read:
    plan.name / plan.source / plan.source_dated   plan identity, for display
    facility.*                                    facility identity
    milestones.actuals_from                       start of the record
    milestones.actuals_to                         last closed month
    milestones.forecast_from                      first forecast month
    milestones.grid_connection                    site generation ceases
    milestones.end_of_mining                      last ore mined
    milestones.end_of_processing                  last ore milled
    milestones.end_of_rehabilitation              reporting horizon
    lom_totals.*                                  headline plan figures
    plant.*                                       plant limits

A milestone is returned as a datetime at the start of the day stated.  The
YAML carries end dates as the last day of the period, which is what the phase
labelling in Config.get_phase_name() compares against, so no adjustment is
applied here.
"""

import os
from datetime import datetime, date

try:
    import yaml
except ModuleNotFoundError as exc:                # pragma: no cover
    raise ModuleNotFoundError(
        "PyYAML is required to read the YAML configuration.  Install it into "
        "the environment running the app:  pip install PyYAML  "
        "(it is listed in requirements.txt)."
    ) from exc

import Paths
# ReferenceLifeOfMine.yaml in PrepData, or the LOM.yaml copy in Data where
# PrepData is not beside this repository.  See PREPDATA_SOURCES in Paths.
DEFAULT_LOM_PATH = Paths.source('lom')

# Milestone keys this model consumes.  A key absent from the file falls back
# to the Config.py constant of the same meaning.
MILESTONE_KEYS = (
    'actuals_from',
    'actuals_to',
    'forecast_from',
    'grid_connection',
    'end_of_mining',
    'end_of_processing',
    'end_of_rehabilitation',
)


def _to_datetime(value):
    """Coerce a YAML date, datetime or ISO string to datetime.  None passes through."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for pattern in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
    raise ValueError(f'LOM.yaml: cannot read {value!r} as a date')


class LomReference:
    """Parsed LOM.yaml.  Attribute access with a documented fallback."""

    def __init__(self, raw=None, path=None, error=None):
        self.raw = raw or {}
        self.path = path
        self.error = error
        self.available = raw is not None

        self.plan = self.raw.get('plan', {}) or {}
        self.facility = self.raw.get('facility', {}) or {}
        self.lom_totals = self.raw.get('lom_totals', {}) or {}
        self.plant = self.raw.get('plant', {}) or {}
        self.units = self.raw.get('units', {}) or {}

        milestones = self.raw.get('milestones', {}) or {}
        self.milestones = {k: _to_datetime(milestones.get(k)) for k in MILESTONE_KEYS}

    # -- milestones ---------------------------------------------------
    def milestone(self, key, fallback=None):
        """Return a milestone date, or the fallback where the file does not carry it."""
        value = self.milestones.get(key)
        return value if value is not None else fallback

    # -- provenance ---------------------------------------------------
    @property
    def plan_name(self):
        return self.plan.get('name', 'unknown')

    @property
    def plan_source(self):
        return self.plan.get('source', '')

    @property
    def plan_dated(self):
        return _to_datetime(self.plan.get('source_dated'))

    def provenance(self):
        """One line naming the plan revision the dates come from."""
        if not self.available:
            return f'LOM.yaml not read ({self.error}).  Config.py constants in use.'
        dated = self.plan_dated
        stamp = f", dated {dated:%d %b %Y}" if dated else ''
        return f'{self.plan_name}{stamp} ({os.path.basename(self.path or "LOM.yaml")})'

    def as_table(self):
        """Milestones as a list of (label, date) for display."""
        labels = {
            'actuals_from': 'Actuals from',
            'actuals_to': 'Actuals to',
            'forecast_from': 'Forecast from',
            'grid_connection': 'Grid connection',
            'end_of_mining': 'End of mining',
            'end_of_processing': 'End of processing',
            'end_of_rehabilitation': 'End of rehabilitation',
        }
        return [(labels[k], self.milestones.get(k)) for k in MILESTONE_KEYS]


def load_lom(path=None):
    """Read LOM.yaml.  A missing or unreadable file returns an empty reference.

    The model must still start when the file is absent, so failure is recorded
    on the returned object rather than raised.  Config.py then keeps its own
    constants and the About panel reports which set is in force.
    """
    path = path or DEFAULT_LOM_PATH
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            raw = yaml.safe_load(handle) or {}
        return LomReference(raw=raw, path=path)
    except FileNotFoundError:
        return LomReference(path=path, error='file not found')
    except yaml.YAMLError as exc:
        return LomReference(path=path, error=f'invalid YAML: {exc}')


# Module-level singleton.  Read once at import; the file is 2 kB.
LOM = load_lom()
