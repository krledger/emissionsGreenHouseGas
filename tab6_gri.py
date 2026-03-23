"""
tab6_gri.py
GRI 14 Mining Sector Reporting tab
Last updated: 2026-03-23

ARCHITECTURE:
    Display only.  Receives PrecomputedData, raw_df, display_year
    and year_type from app.py.
    Calls export_gri14.py for data extraction and coverage reporting.
    Shows GRI 14.1 climate disclosures, GRI consumables and coverage
    status for the selected reporting year.
"""

import streamlit as st
import pandas as pd
from export_gri14 import (
    build_gri14_export,
    build_coverage_report,
    coverage_summary_counts,
    GRI14_QUANTITATIVE_MAP,
)


def render_gri_tab(df, precomputed, display_year, year_type):
    """Render the GRI 14 Mining Sector Reporting tab.

    Args:
        df: Raw DataFrame from load_all_data()
        precomputed: PrecomputedData from calc_precompute
        display_year: Selected year (int) from sidebar
        year_type: 'FY' or 'CY' from sidebar
    """
    year_prefix = 'CY' if year_type == 'CY' else 'FY'
    year_label = f"{year_prefix}{display_year}"

    st.subheader("GRI 14 Mining Sector Disclosure")
    st.caption(f"Reporting year: {year_label}")

    # Build export for selected year only
    gri_df = build_gri14_export(
        precomputed, raw_df=df, reporting_fys=[display_year]
    )

    if gri_df.empty:
        st.warning(f"No GRI data available for {year_label}.")
        return

    # Filter to rows with values
    has_value = gri_df[gri_df['Value'].notna()].copy()

    # === Coverage Summary ===
    with st.expander("Coverage Summary", expanded=True):
        _render_coverage_summary()

    # === Climate Disclosures (14.1) ===
    with st.expander(f"14.1 Climate Change Disclosures ({year_label})", expanded=False):
        climate = has_value[~has_value['Section'].isin(
            ['Reagents and consumables', 'Wear items']
        )]
        if not climate.empty:
            display_df = climate[['Section', 'GRI_Reference', 'Description',
                                  'Unit', 'Value']].copy()
            display_df['Value'] = display_df.apply(_format_value, axis=1)
            display_df = display_df.rename(columns={'Value': year_label})
            st.dataframe(display_df, hide_index=True, width="stretch", height=600)
            csv_climate = climate.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Climate Disclosures (CSV)",
                data=csv_climate,
                file_name=f"gri14_climate_{year_label}.csv",
                mime="text/csv",
                key="gri14_climate_dl",
            )
        else:
            st.info(f"No climate disclosure data for {year_label}.")

    # === GRI Consumables ===
    with st.expander(f"Reagents and Consumables ({year_label})", expanded=False):
        consumables = has_value[has_value['Section'].isin(
            ['Reagents and consumables', 'Wear items']
        )]
        if not consumables.empty:
            display_c = consumables[['Section', 'Description', 'Unit',
                                     'Value']].copy()
            display_c['Value'] = display_c.apply(_format_value, axis=1)
            display_c = display_c.rename(columns={'Value': year_label})
            st.dataframe(display_c, hide_index=True, width="stretch")
            csv_cons = consumables.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Consumables (CSV)",
                data=csv_cons,
                file_name=f"gri14_consumables_{year_label}.csv",
                mime="text/csv",
                key="gri14_cons_dl",
            )
        else:
            st.info(
                "No consumable data available.  "
                "Run prep_data.py with INV03 source files to populate."
            )

    # === Full Data Table ===
    with st.expander(f"Full Disclosure Data ({year_label})", expanded=False):
        display_full = gri_df[['Section', 'GRI_Reference', 'Description',
                                'Unit', 'Value', 'Methodology_Note']].copy()
        display_full['Value'] = display_full.apply(_format_value, axis=1)
        display_full = display_full.rename(columns={'Value': year_label})
        display_full = display_full.sort_values(['Section', 'Description'])
        st.dataframe(display_full, hide_index=True, width="stretch", height=400)
        csv_full = gri_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Full Disclosure (CSV)",
            data=csv_full,
            file_name=f"gri14_disclosure_{year_label}.csv",
            mime="text/csv",
            key="gri14_full_dl",
        )


def _format_value(row):
    """Format a disclosure value for display."""
    val = row['Value']
    if pd.isna(val):
        return None
    if isinstance(val, float):
        if val == 0.0:
            return 0
        elif abs(val) < 0.01:
            return round(val, 6)
        elif abs(val) < 1:
            return round(val, 4)
        elif abs(val) < 100:
            return round(val, 2)
        else:
            return round(val, 0)
    return val


def _render_coverage_summary():
    """Show coverage summary by GRI 14 topic."""
    counts = coverage_summary_counts()

    rows = []
    total_auto = 0
    total_collect = 0
    total_na = 0
    for topic, c in counts.items():
        a = c['auto']
        co = c['collectible']
        na = c['not_available']
        total = a + co + na
        rows.append({
            'Topic': topic,
            'Auto': a,
            'Collectible': co,
            'N/A': na,
            'Total': total,
            'Coverage': f"{a/total*100:.0f}%" if total > 0 else "0%",
        })
        total_auto += a
        total_collect += co
        total_na += na

    grand_total = total_auto + total_collect + total_na
    rows.append({
        'Topic': 'TOTAL',
        'Auto': total_auto,
        'Collectible': total_collect,
        'N/A': total_na,
        'Total': grand_total,
        'Coverage': f"{total_auto/grand_total*100:.0f}%" if grand_total > 0 else "0%",
    })

    summary_df = pd.DataFrame(rows)
    st.dataframe(summary_df, hide_index=True, width="stretch")

    st.caption(
        "Auto = populated from emissions model and inventory data.  "
        "Collectible = data exists in other systems (NPI, water balance, waste register).  "
        "N/A = not applicable to Ravenswood."
    )