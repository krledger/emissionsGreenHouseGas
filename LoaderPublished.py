"""
LoaderPublished.py
==================
The published inventory, as the reporting application reads it.

The Builder computes the inventory and publishes it.  This reads what was
published and hands it to the views in the shape they already take, so the
reporting application computes no emissions of its own.  Two programs
calculating the same inventory from the same sources is two answers waiting
to differ: a factor changed in one, a source file re-run after the other
last read it, a cache an hour old.  What is on the screen here is the build
somebody reviewed and published, and a figure that has not been published is
not on the screen.

What is read:
    Data/Reporting/*.parquet    the frames the views draw
    Data/Reporting/Scope3State.json   the parts of the Scope 3 result that
                                      are not frames
    Data/EmissionsBuildLog.json       which build this is

What is still loaded here rather than published:
    the NGA factor register, which is a reference table the Builder owns and
    this application reads for the factors behind a figure, and the credit
    ledger, which is a record of transactions rather than a result.  Neither
    is a calculation, so neither can disagree.

Last updated: 2026-09-12
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pandas as pd

from CalcPrecompute import PrecomputedData
from ExportEmissionsTable import (BUILD_LOG_PATH, REPORTING_DIR,
                                  REPORTING_FRAMES, REPORTING_SCOPE3,
                                  SCOPE3_STATE)
from LoaderData import load_smc_transactions
from LoaderNga import NGAFactorsByYear
from CalcNga import build_year_factor_map
from CalcGhg import build_ghg_factor_map

__all__ = ['PublishedScope3', 'published_at', 'is_published', 'load_published_build']


@dataclass
class PublishedScope3:
    """The Scope 3 result as it was published.

    The same fields the view reads from the computed result, read back from
    the pack.  Nothing is recalculated: the categories, the detail and the
    open items are the published ones.
    """

    detail: pd.DataFrame
    annual_fy: pd.DataFrame
    annual_cy: pd.DataFrame
    rates: pd.DataFrame
    outstanding: List[Dict[str, Any]]
    exclusions: pd.DataFrame
    coverage: Dict[str, Any]
    notes: Dict[str, str] = field(default_factory=dict)
    reference: Any = None

    def category_total(self, category, year=None, year_type='FY'):
        """Total tCO2-e for one category, optionally for one year."""
        frame = self.detail
        if frame is None or frame.empty:
            return 0.0
        mask = frame['Category'] == category
        if year is not None:
            column = 'FY' if year_type == 'FY' else 'Year'
            mask &= frame[column] == year
        return float(frame.loc[mask, 'tCO2e'].sum())


def _path(name):
    """Where one frame of the pack is, in whichever form it was written."""
    for suffix in ('.parquet', '.csv.gz'):
        path = os.path.join(REPORTING_DIR, name + suffix)
        if os.path.exists(path):
            return path
    return os.path.join(REPORTING_DIR, name + '.parquet')


def is_published():
    """Whether a build has been published for this application to read."""
    return (os.path.exists(_path('Ghg'))
            and os.path.exists(_path('Monthly')))


def published_at():
    """The build on the record: its identifier and when it was published."""
    if not os.path.exists(BUILD_LOG_PATH):
        return {}
    try:
        with open(BUILD_LOG_PATH, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _frame(name, dates=()):
    """One published frame, or an empty one where it was not written."""
    path = _path(name)
    if not os.path.exists(path):
        return pd.DataFrame()
    frame = (pd.read_parquet(path) if path.endswith('.parquet')
             else pd.read_csv(path, low_memory=False))
    for column in dates:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors='coerce')
    return frame


def _scope3(state):
    """The published Scope 3 result."""
    return PublishedScope3(
        detail=_frame('Scope3Detail', dates=('Date',)),
        annual_fy=_frame('Scope3AnnualFY'),
        annual_cy=_frame('Scope3AnnualCY'),
        rates=_frame('Scope3Rates'),
        outstanding=list(state.get('outstanding') or []),
        exclusions=_frame('Scope3Exclusions'),
        coverage=dict(state.get('coverage') or {}),
        notes=dict(state.get('notes') or {}),
    )


def load_published_build():
    """The published build, in the shape the views take.

    Returns (ghg_df, PrecomputedData).  The frame and every frame on the
    object are the published ones; nothing here recomputes an emission.

    Raises FileNotFoundError where nothing has been published, because a
    reporting application with no published build has nothing to report and
    saying so is better than showing a figure nobody approved.
    """
    if not is_published():
        raise FileNotFoundError(
            'No published build.  The Emissions Data Builder publishes the '
            'inventory this application reports; run it and press Publish.')

    frames = {name: _frame(name, dates=('Date',))
              for name in REPORTING_FRAMES}
    ghg_df = frames['Ghg']

    state = {}
    state_path = os.path.join(REPORTING_DIR, SCOPE3_STATE)
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding='utf-8') as handle:
                state = json.load(handle)
        except (OSError, ValueError):
            state = {}

    # The factor register and the credit ledger: read, not computed.  The
    # register is what every factor on the published table was taken from,
    # and the views show it beside a figure to say where the figure came
    # from; the ledger is the record of credits issued and sold.
    nga_by_year = NGAFactorsByYear()
    years = sorted(int(y) for y in ghg_df['FY'].dropna().unique()) \
        if 'FY' in ghg_df.columns else []
    year_factor_map = build_year_factor_map(nga_by_year, years)

    precomputed = PrecomputedData(
        monthly=frames['Monthly'],
        annual_fy=frames['AnnualFY'],
        annual_cy=frames['AnnualCY'],
        year_factor_map=year_factor_map,
        safeguard_source=frames['SafeguardSource'],
        safeguard_ore=frames['SafeguardOre'],
        safeguard_electricity=frames['SafeguardElectricity'],
        smc_transactions=load_smc_transactions(),
        nga_by_year=nga_by_year,
        ghg_df=ghg_df,
        ghg_annual_fy=frames['GhgAnnualFY'],
        ghg_annual_cy=frames['GhgAnnualCY'],
        ghg_monthly=frames['GhgMonthly'],
        ghg_factor_map=build_ghg_factor_map(nga_by_year, years),
        gri_annual=frames['GriAnnual'],
        gri_source=frames['GriSource'],
        scope3=_scope3(state),
    )
    return ghg_df, precomputed
