"""
tab4_nger.py
NGER Factors Tab - Display emission factors by year
Last updated: 2026-01-07 15:00 AEST
"""

import streamlit as st
import pandas as pd
from nga_loader import NGAFactorsByYear


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
    st.dataframe(elec_df, width="stretch", hide_index=True)

    # Show trends
    scope2_2021 = float(elec_df.iloc[0]['Scope 2 (kg CO₂-e/kWh)'])
    scope2_2025 = float(elec_df.iloc[4]['Scope 2 (kg CO₂-e/kWh)'])
    scope2_change = ((scope2_2025 - scope2_2021) / scope2_2021) * 100

    scope3_2021 = float(elec_df.iloc[0]['Scope 3 (kg CO₂-e/kWh)'])
    scope3_2025 = float(elec_df.iloc[4]['Scope 3 (kg CO₂-e/kWh)'])
    scope3_change = ((scope3_2025 - scope3_2021) / scope3_2021) * 100

    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "Scope 2 Change (2021→2025)",
            f"{scope2_change:.1f}%",
            delta=f"{scope2_change:.1f}%",
            delta_color="inverse"
        )
    with col2:
        st.metric(
            "Scope 3 Change (2021→2025)",
            f"{scope3_change:.1f}%",
            delta=f"{scope3_change:.1f}%",
            delta_color="inverse"
        )

    st.caption("Source: NGA Table 1 (2022-2025), Table 6 (2021) | Grid emissions decreasing as renewable generation increases")

    # Diesel Factors by Year
    st.markdown("### ⛽ Diesel Emission Factors")
    st.markdown("**All diesel combustion uses**")

    # Create comprehensive diesel table with all parameters
    diesel_data = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        factors = nga_all_years.get_factors_for_year(year, 'QLD')
        diesel = factors['diesel']
        diesel_data.append({
            'Year': year,
            'Energy Content (GJ/kL)': f"{diesel['energy_content_gj_per_kl']:.1f}",
            'Stationary S1 (kg CO₂-e/kL)': f"{diesel['scope1_kg_co2e_per_kl_stationary']:.2f}",
            'Stationary S1 (t CO₂-e/kL)': f"{diesel['scope1_t_co2e_per_kl_stationary']:.5f}",
            'Electricity Gen S1 (t CO₂-e/kL)': f"{diesel['scope1_t_co2e_per_kl_electricity']:.5f}",
            'Transport S1 (t CO₂-e/kL)': f"{diesel['scope1_t_co2e_per_kl_transport']:.5f}",
            'Scope 3 (t CO₂-e/kL)': f"{diesel['scope3_t_co2e_per_kl']:.5f}"
        })

    diesel_df = pd.DataFrame(diesel_data)
    st.dataframe(diesel_df, width="stretch", hide_index=True)

    st.caption("Source: NGA 'Energy - Scope 1' and 'Energy - Scope 3' sheets (2022-2025), Table 3 (2021) | All diesel factors constant across years")

    # Purpose-specific factors table
    st.markdown("### 🔧 Diesel Factors by Purpose (All Years)")

    purpose_data = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        factors = nga_all_years.get_factors_for_year(year, 'QLD')
        diesel_purpose = factors['diesel_by_purpose']
        purpose_data.append({
            'Year': year,
            'Electricity Gen S1': f"{diesel_purpose['electricity']['scope1']:.5f}",
            'Stationary S1': f"{diesel_purpose['stationary']['scope1']:.5f}",
            'Transport S1': f"{diesel_purpose['transport']['scope1']:.5f}",
            'Electricity Gen S3': f"{diesel_purpose['electricity']['scope3']:.5f}",
            'Stationary S3': f"{diesel_purpose['stationary']['scope3']:.5f}",
            'Transport S3': f"{diesel_purpose['transport']['scope3']:.5f}"
        })

    purpose_df = pd.DataFrame(purpose_data)
    st.dataframe(purpose_df, width="stretch", hide_index=True)

    st.caption("All values in t CO₂-e/kL | Used for cost centre mapping: Electricity = Supplemental Power, Stationary = Mining/Processing, Transport = Light Vehicles")

    # Processing Chemicals
    st.markdown("### 🧪 Processing Chemicals & Reagents")
    st.markdown("**Gold leach processing and auxiliary fuels**")

    # Create chemicals table for all years
    chemical_data = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        # LPG factors from Table 8 in NGA (constant across years)
        lpg_s1 = 1.55742  # t CO2-e/kL
        lpg_s3 = 0.51914  # t CO2-e/kL

        chemical_data.append({
            'Year': year,
            'LPG S1 (t CO₂-e/kL)': f"{lpg_s1:.5f}",
            'LPG S3 (t CO₂-e/kL)': f"{lpg_s3:.5f}",
            'Limestone/Lime (t CO₂/t)': '0.44000',
            'Soda Ash (t CO₂-e/t)': '0.41500'
        })

    chemical_df = pd.DataFrame(chemical_data)
    st.dataframe(chemical_df, width="stretch", hide_index=True)

    st.caption("LPG Source: NGA Table 8 (Energy - Scope 1 & 3) | Limestone: NGA Table 12 (Calcination) | Soda Ash: NGA Table 14")
    st.caption("⚠️ All chemical factors are CONSTANT across years (2021-2025)")

    # Explanatory note on chemicals
    with st.expander("ℹ️ Chemical Usage Notes", expanded=False):
        st.markdown("""
        **LPG (Liquefied Petroleum Gas):**
        - Used for heating and auxiliary processes
        - Scope 1: Direct combustion emissions (1.55742 t CO₂-e/kL)
        - Scope 3: Production and transport emissions (0.51914 t CO₂-e/kL)
        
        **Limestone/Lime (Calcium Carbonate):**
        - Used for pH control in processing
        - Emissions from calcination process (heating limestone)
        - Factor: 0.44 t CO₂ per tonne of limestone consumed
        - Only applies if calcination occurs onsite
        
        **Soda Ash (Sodium Carbonate):**
        - Used for pH adjustment
        - Factor: 0.415 t CO₂-e per tonne consumed
        - Emissions from consumption/dissolution
        
        **Sodium Cyanide (NaCN):**
        - Primary leach reagent for gold extraction
        - ⚠️ **Not in NGA factors** - no direct GHG emissions from use in leaching
        - Emissions occur during cyanide production (Scope 3 supply chain)
        - Would require supplier-specific emission factors for Scope 3 accounting
        - Typical industry value: ~3-5 t CO₂-e per tonne of NaCN produced
        
        **Other Process Chemicals:**
        - Hydrochloric acid (HCl), caustic soda (NaOH), flocculants: Not in NGA factors
        - Would require supplier emission factors for Scope 3 accounting
        """)

    # Explosives
    st.markdown("### 💥 Explosives (Blasting)")
    st.markdown("**ANFO, emulsions, and other blasting agents**")

    st.warning("""
    **⚠️ Explosives Emission Factors NOT in NGA Files**
    
    The National Greenhouse Accounts (NGA) factors do NOT include emission factors for mining explosives.
    Explosives emissions must be calculated using NGER (Measurement) Determination 2008 methodology.
    """)

    # Explosives information table
    explosives_info = pd.DataFrame([
        ['ANFO (Ammonium Nitrate/Fuel Oil)', 'Method 1 or 2', 'NGER Determination', 'Fuel oil component as diesel'],
        ['Emulsion Explosives', 'Method 1 or 2', 'NGER Determination', 'Composition-based calculation'],
        ['Heavy ANFO', 'Method 1 or 2', 'NGER Determination', 'Combined methodology'],
        ['Detonating Cord', 'Method 1 or 2', 'NGER Determination', 'Minor source']
    ], columns=['Explosive Type', 'Calculation Method', 'Source', 'Notes'])

    st.dataframe(explosives_info, width="stretch", hide_index=True)

    with st.expander("📖 Explosives Emission Calculation Guidance", expanded=False):
        st.markdown("""
        **NGER Measurement Determination Methods:**
        
        Explosives emissions are calculated using **NGER (Measurement) Determination 2008**, not NGA factors.
        Two methods are available:
        
        **Method 1 - Fuel Oil Component:**
        ```
        Emissions = Fuel Oil Mass (kg) × Diesel Emission Factor (kg CO₂-e/kg)
        ```
        - Only accounts for fuel oil combustion in ANFO
        - Uses standard diesel emission factor: ~3.15 kg CO₂-e/kg fuel oil
        - Simplest approach but incomplete
        
        **Method 2 - Stoichiometric Calculation:**
        ```
        Based on complete detonation reaction:
        3NH₄NO₃ + CH₂ → 3N₂ + 7H₂O + CO₂
        ```
        - Accounts for both fuel oil and ammonium nitrate decomposition
        - More accurate but requires detailed composition data
        - Typical ANFO (94/6 blend): ~0.17-0.20 kg CO₂-e per kg explosive
        
        **Typical Emission Factors (Industry Values):**
        
        | Explosive Type | Scope 1 Emission Factor | Notes |
        |----------------|-------------------------|-------|
        | ANFO (94/6) | 0.17-0.20 kg CO₂-e/kg | 94% AN, 6% FO |
        | Heavy ANFO | 0.15-0.18 kg CO₂-e/kg | Contains emulsion |
        | Emulsion | 0.12-0.15 kg CO₂-e/kg | No fuel oil |
        | Bulk Emulsion | 0.10-0.13 kg CO₂-e/kg | Sensitized onsite |
        
        **For Ravenswood Gold:**
        
        1. **Track Monthly Consumption:**
           - ANFO tonnage used
           - Emulsion tonnage used
           - Fuel oil component percentage
        
        2. **Calculate Emissions:**
           - Option A: Use Method 1 (fuel oil only) - conservative estimate
           - Option B: Use Method 2 (full stoichiometry) - accurate but complex
           - Option C: Use industry benchmark (0.17 kg CO₂-e/kg ANFO)
        
        3. **Report in NGER:**
           - Include in Scope 1 emissions
           - Report under "Use of explosives" category
           - Document calculation methodology
        
        **Diesel Component vs Full Emissions:**
        
        - **Current system:** Blasting mapped to 'explosives' with zero factor
        - **Recommendation:** Map to diesel factor (fuel oil component only)
        - **Better approach:** Calculate full explosive emissions using Method 2
        - **Best practice:** Obtain supplier emission factors for specific products
        
        **Data Requirements:**
        
        - Monthly explosives consumption by type (kg or tonnes)
        - Composition breakdown (% ammonium nitrate, % fuel oil, % emulsion)
        - Supplier product specifications
        - Blasting records from mining operations
        
        **References:**
        - NGER (Measurement) Determination 2008 - Section 2.23
        - Clean Energy Regulator guidance on explosives
        - Australian Explosives Industry and Safety Group (AEISG) guidelines
        """)

    # Critical note about year-specific factors
    st.markdown("---")
    st.info("""
    **⚠️ CRITICAL: Use Year-Specific Factors**
    
    - **Electricity factors CHANGE by year** - using wrong year significantly misrepresents emissions
    - **Diesel factors are CONSTANT** - same values apply to all years (2021-2025)
    - FY2021 emissions must use 2021 electricity factors (Scope 2: 0.77 kg CO₂-e/kWh)
    - FY2025 emissions must use 2025 electricity factors (Scope 2: 0.67 kg CO₂-e/kWh)
    - NGER submissions require factors from the reporting year
    - Safeguard baseline calculations must use consistent year factors
    """)