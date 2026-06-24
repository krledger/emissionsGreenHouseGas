"""
calc_ghg.py
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

import pandas as pd
from config import GHG_EXPLOSIVES_EF_T_CO2_PER_T


def build_ghg_frame(nger_df):
    """Build a GHG Protocol DataFrame from the NGER frame.

    Takes the clean NGER DataFrame and adds Scope 1 emissions for
    GHG-only items (currently: explosives).  Returns a new DataFrame;
    the input is not modified.

    Args:
        nger_df: DataFrame from loader_data / calc_emissions pipeline.
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
    # Identify explosives rows by CommonName (set by lookup_identifiers.py).
    # These have NGAFuel = '' and Scope1_tCO2e = 0 in the NGER frame.
    # Under GHG Protocol, detonation emissions are Scope 1.
    expl_mask = (
        (ghg_df['CommonName'].astype(str) == 'Explosives')
        & (ghg_df['Quantity'].abs() > 0)
    )

    if expl_mask.any():
        # Factor: 0.17 t CO₂ per tonne ANFO (AGO / Dept of Climate Change)
        # Source data UOM is tonnes.  If UOM changes, adjust here.
        # tCO2-e = Quantity (t) * 0.17 (t CO₂/t ANFO)
        ghg_df.loc[expl_mask, 'Scope1_tCO2e'] = (
            ghg_df.loc[expl_mask, 'Quantity'] * GHG_EXPLOSIVES_EF_T_CO2_PER_T
        )
        # Set a pseudo NGAFuel so tab1 summary includes these rows
        ghg_df.loc[expl_mask, 'NGAFuel'] = 'Explosives (GHG only)'
        ghg_df.loc[expl_mask, 'GHG_Source'] = 'AGO 0.17 t CO₂/t ANFO'

    return ghg_df
