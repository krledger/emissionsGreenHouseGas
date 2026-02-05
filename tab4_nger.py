"""
tab4_nger.py
NGER Factors Tab - Display emission factors by year
Last updated: 2026-02-04 16:00 AEST
"""
# NOTE FOR CLAUDE: This file contains emojis. Use binary-safe editing (rb/wb) to prevent corruption.

import streamlit as st
import pandas as pd
from loader_nga import NGAFactorsByYear


def render_nger_tab():
    """Render the NGER Factors tab showing emission factors for all years"""

    st.subheader("NGER Emission Factors by Year (Queensland)")
    st.caption("National Greenhouse Accounts Factors 2021-2025")

    # Load all years of NGA factors
    nga_all_years = NGAFactorsByYear('.')

    # Electricity Factors by Year
    st.markdown("### 📊 Electricity Emission Factors")
    st.markdown("**Grid electricity consumption - Queensland**")

    # Create comprehensive electricity table
    elec_data = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        factors = nga_all_years.get_factors_for_year(year, 'QLD')
        elec = factors['electricity']['QLD']
        elec_data.append({
            'Year': year,
            'Scope 2 (kg CO₂-e/kWh)': f"{elec['scope2']:.2f}",
            'Scope 3 (kg CO₂-e/kWh)': f"{elec['scope3']:.2f}"
        })

    elec_df = pd.DataFrame(elec_data)
    st.dataframe(elec_df, width='stretch', hide_index=True)

    # Show trends
    scope2_2021 = float(elec_df.iloc[0]['Scope 2 (kg CO₂-e/kWh)'])
    scope2_2025 = float(elec_df.iloc[-1]['Scope 2 (kg CO₂-e/kWh)'])
    change_pct = ((scope2_2025 - scope2_2021) / scope2_2021) * 100

    st.caption(f"Grid decarbonization: {change_pct:+.1f}% change from 2021 to 2025")

    st.markdown("---")

    # Diesel Factors by Year
    st.markdown("### 📊 Diesel Fuel Emission Factors")
    st.markdown("**Diesel oil - Stationary combustion**")

    diesel_data = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        factors = nga_all_years.get_factors_for_year(year, 'QLD')
        diesel = factors['diesel']
        diesel_data.append({
            'Year': year,
            'Energy Content (GJ/kL)': f"{diesel.get('energy_content_gj_per_kl', 0):.2f}",
            'Scope 1 (kg CO₂-e/kL)': f"{diesel.get('scope1_kg_co2e_per_kl_stationary', 0):.2f}",
            'Scope 1 (t CO₂-e/kL)': f"{diesel.get('scope1_t_co2e_per_kl_stationary', 0):.4f}",
            'Scope 3 (t CO₂-e/kL)': f"{diesel.get('scope3_t_co2e_per_kl', 0):.4f}"
        })

    diesel_df = pd.DataFrame(diesel_data)
    st.dataframe(diesel_df, width='stretch', hide_index=True)

    st.caption("Use year-specific factors - diesel emission factors vary slightly each year")

    st.markdown("---")

    # Show factor comparison
    st.markdown("### 📊 Emission Factor Summary by Year")

    summary_data = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        factors = nga_all_years.get_factors_for_year(year, 'QLD')
        diesel = factors['diesel']
        elec = factors['electricity']['QLD']

        summary_data.append({
            'Year': year,
            'Diesel (t CO₂-e/kL)': f"{diesel.get('scope1_t_co2e_per_kl_stationary', 0):.4f}",
            'Electricity Scope 2 (kg CO₂-e/kWh)': f"{elec['scope2']:.3f}",
            'Electricity Scope 3 (kg CO₂-e/kWh)': f"{elec['scope3']:.3f}"
        })

    summary_df = pd.DataFrame(summary_data)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    st.markdown("---")

    # Key Notes Section
    with st.expander("NGER Factor Notes", expanded=False):
        st.markdown("""
        **Data Sources:**
        - National Greenhouse Accounts Factors (Commonwealth of Australia)
        - Published annually by Department of Climate Change, Energy, Environment and Water
        - Mandatory for NGER reporting under NGER Act 2007
        
        **Key Points:**
        
        **Use Year-Specific Factors**
        - Emission factors change each year
        - Always use factors corresponding to the reporting year
        - Historical data should use historical factors
        
        **Grid Decarbonization**
        - Queensland grid emission factors declining over time
        - Reflects increasing renewable energy penetration
        - Future projections should account for continued decline
        
        **Explosives Emission Factors**
        - NOT included in NGA factor files
        - See NGER Technical Guidelines for explosive emission factors
        - Typically minor compared to fuel combustion
        
        **References:**
        - NGER (Measurement) Determination 2008
        - NGER Technical Guidelines
        - National Greenhouse Accounts Factors 2021-2025
        - Clean Energy Regulator guidance materials
        """)

    st.markdown("---")

    # Technical Details
    with st.expander("Technical Details", expanded=False):
        st.markdown("""
        **Emission Factor Structure:**
        
        **Diesel Factors:**
        - Energy Content: ~38.6 GJ/kL
        - Scope 1 (Stationary): ~2,680 kg CO₂-e/kL (~2.68 t/kL)
        - Scope 3 (Extraction/Transport): ~0.67 t CO₂-e/kL
        - Total includes CO₂, CH₄, and N₂O emissions
        
        **Electricity Factors (Queensland):**
        - Scope 2: Direct generation emissions (~0.79 kg CO₂-e/kWh in 2021, declining)
        - Scope 3: Transmission and distribution losses (~0.08-0.15 kg CO₂-e/kWh)
        - Grid decarbonizing: Renewable energy increasing over time
        
        **Global Warming Potentials (100-year):**
        - CO₂: 1 (reference gas)
        - CH₄: 25 (methane)
        - N₂O: 298 (nitrous oxide)
        
        **Data Sources:**
        - nationalgreenhouseaccountfactors2021.xlsx
        - nationalgreenhouseaccountfactors2022.xlsx
        - nationalgreenhouseaccountfactors2023.xlsx
        - nationalgreenhouseaccountfactors2024.xlsx
        - nationalgreenhouseaccountfactors2025.xlsx
        
        **Loading:**
        - Factors loaded via loader_nga.py
        - Cached for performance
        - Validated on import
        
        **Usage in Calculations:**
        - Diesel: Volume (kL) × Factor (t CO₂-e/kL) = Emissions (t CO₂-e)
        - Electricity: Consumption (kWh) × Factor (kg CO₂-e/kWh) ÷ 1000 = Emissions (t CO₂-e)
        """)