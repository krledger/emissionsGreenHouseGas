"""
CalcGhg.py
GHG Protocol overlay for emissions not reportable under NGER.

Last updated: 2026-05-19

Purpose:
    The NGER DataFrame (used by Safeguard / Tab 2, Carbon Tax / Tab 3)
    excludes certain emission sources that ARE reportable under the
    GHG Protocol.  This module builds a GHG-adjusted copy of the data
    by adding those sources back in.

    Currently covers:
        - Explosives (ANFO) detonation → Scope 1

    The NGER frame is never modified.  Tab 1 (GHG) receives the overlay;
    all other tabs continue to use the clean NGER frame.

Emission factor source:
    AGO / Dept of Climate Change: 0.17 t CO₂ per tonne ANFO
    (Pending confirmation against current NGA Factors publication)

References:
    - CER: Reporting blended fuels, other fuel mixes, bitumen and
      explosives guideline (July 2025) s2.7 — NOT reportable under NGER
    - Balmoral South Iron Ore Project GHG Assessment (Kewan Bond, 2008)
      — precedent for Scope 1 treatment under AGO methods
    - GHG Protocol Corporate Accounting and Reporting Standard (WRI/WBCSD)
"""

import logging

import pandas as pd

from Config import GHG_EXPLOSIVES_EF_T_CO2_PER_T
from LookupIdentifiers import expected_uom

logger = logging.getLogger(__name__)

# The factor is tonnes of carbon dioxide per tonne of explosive, so the line
# must be in tonnes.  The unit is read from the identifier lookup rather than
# assumed here, so one declaration governs the factor and every consumer.
EXPLOSIVES_UOM = expected_uom('Blasting', 'Explosives')


def build_ghg_frame(nger_df):
    """Build a GHG Protocol DataFrame from the NGER frame.

    Takes the clean NGER DataFrame and adds Scope 1 emissions for
    GHG-only items (currently: explosives).  Returns a new DataFrame;
    the input is not modified.

    Args:
        nger_df: DataFrame from LoaderData / CalcNga pipeline.
                 Must contain columns: CommonName, Quantity, Scope1_tCO2e,
                 NGAFuel, UOM.

    Returns:
        DataFrame with same shape as nger_df but Scope1_tCO2e adjusted
        for GHG-only items.  A new column 'GHG_Source' marks rows where
        GHG-specific emissions were added (for audit trail).
    """
    ghg_df = nger_df.copy()

    # Convert Categorical columns to object so new values can be assigned
    for col in ('NGAFuel', 'GHG_Source'):
        if col in ghg_df.columns and hasattr(ghg_df[col], 'cat'):
            ghg_df[col] = ghg_df[col].astype(object)

    # Flag column for audit — default empty string
    ghg_df['GHG_Source'] = ''

    # ── Explosives (ANFO) ──────────────────────────────────────────────
    # Identify explosives rows by CommonName (set by LookupIdentifiers.py).
    # These have NGAFuel = '' and Scope1_tCO2e = 0 in the NGER frame.
    # Under GHG Protocol, detonation emissions are Scope 1.
    named = (ghg_df['CommonName'].astype(str) == 'Explosives')
    expl_mask = named & (ghg_df['Quantity'].abs() > 0)

    # The factor is per tonne, so only the tonnes line takes it.  A row
    # carrying the name in another unit is a different thing: stores carries
    # rock rivets by the box under the same subactivity name.  Charging it
    # would add boxes to tonnes.
    if EXPLOSIVES_UOM and 'UOM' in ghg_df.columns:
        wrong_unit = expl_mask & (ghg_df['UOM'].astype(str) != EXPLOSIVES_UOM)
        if wrong_unit.any():
            for unit, count in ghg_df.loc[wrong_unit, 'UOM'].astype(str) \
                    .value_counts().items():
                logger.warning(
                    f"Explosives: {count} rows are in '{unit}' and the factor "
                    f"is per '{EXPLOSIVES_UOM}'.  Excluded from the GHG "
                    f"overlay."
                )
        expl_mask = expl_mask & (ghg_df['UOM'].astype(str) == EXPLOSIVES_UOM)

    if expl_mask.any():
        # The loader stores the emission columns float32 to save memory.  The
        # product below is float64 on some numpy versions, and pandas will
        # not write one into the other.  Widen first rather than depend on
        # which promotion rules the installed numpy uses.
        ghg_df['Scope1_tCO2e'] = ghg_df['Scope1_tCO2e'].astype('float64')
        # Factor: 0.17 t CO₂ per tonne ANFO (AGO / Dept of Climate Change)
        # tCO2-e = Quantity (t) * 0.17 (t CO₂/t ANFO)
        ghg_df.loc[expl_mask, 'Scope1_tCO2e'] = (
            ghg_df.loc[expl_mask, 'Quantity'] * GHG_EXPLOSIVES_EF_T_CO2_PER_T
        )
        # Name the source for what it is.  Where it discloses is not part of
        # what it is called: explosives are Scope 1 under the GHG Protocol
        # and outside NGER and the Safeguard Mechanism, and that is carried
        # by GHG_Source here and by the applicability flags on the canonical
        # table, not by decorating the name.
        ghg_df.loc[expl_mask, 'NGAFuel'] = 'Explosives'
        ghg_df.loc[expl_mask, 'GHG_Source'] = 'AGO 0.17 t CO₂/t ANFO'

    # Converted last, after the explosives overlay has written its values in.
    # A category cannot take a value it does not already hold, so narrowing
    # the column before the last write to it turns a working assignment into
    # an error.
    for _column in ('NGAFuel', 'GHG_Source'):
        if _column in ghg_df.columns and ghg_df[_column].dtype == object:
            ghg_df[_column] = ghg_df[_column].astype('category')

    return ghg_df
