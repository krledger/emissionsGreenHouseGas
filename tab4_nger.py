"""
tab4_nger.py
Model Reference & NGER Factors Tab
Last updated: 2026-02-12

Displays:
    Safeguard Mechanism formula and parameters (Section 11)
    Legislative compliance mapping
    ERC decline schedule and hybrid EI transition
    s58B opt-in eligibility rules
    NGA emission factors by year
    Data sources and references
"""
# NOTE FOR CLAUDE: This file contains emojis and special chars. Use binary-safe editing (rb/wb).

import streamlit as st
import pandas as pd
from config import (
    FSEI_ROM, FSEI_ELEC, SITE_GENERATION_RATIO,
    DEFAULT_INDUSTRY_EI_ROM, DEFAULT_INDUSTRY_EI_ELEC,
    BEST_PRACTICE_EI_ROM, BEST_PRACTICE_EI_ELEC,
    SAFEGUARD_MINIMUM_BASELINE, SAFEGUARD_THRESHOLD,
    DECLINE_RATE_PHASE1, DECLINE_RATE_PHASE2,
    DECLINE_PHASE1_START, DECLINE_PHASE1_END,
    DECLINE_PHASE2_START, DECLINE_PHASE2_END,
    TRANSITION_SCHEDULE, get_transition_proportion,
    S58B_EARLIEST_FY, S58B_LOOKBACK, S58B_MIN_COVERED,
)
from projections import calculate_erc_for_fy, calculate_hybrid_ei


def render_nger_tab(fsei_rom=FSEI_ROM, fsei_elec=FSEI_ELEC,
                    decline_rate_phase2=DECLINE_RATE_PHASE2):
    """Render the Model Reference & NGER Factors tab"""

    st.subheader("Model Reference")
    st.caption("Safeguard Mechanism calculation methodology, legislative compliance and emission factors")

    # =================================================================
    # SECTION 1: BASELINE FORMULA
    # =================================================================
    with st.expander("\u2696\ufe0f  Baseline Calculation \u2014 Section 11 Formula", expanded=True):

        st.markdown("#### Safeguard Mechanism Rule 2015, Part 3, Division 2, Subdivision A")

        st.markdown(
            '> **Section 11(1):** "The baseline emissions number for an existing '
            'facility (other than a landfill facility) for a financial year is '
            'the number worked out using the following formula"'
        )

        st.latex(
            r"\text{Baseline} = \text{ERC} \times "
            r"\sum_p \left[ "
            r"\left( h \cdot EI_p + (1 - h) \cdot EIF_p \right) "
            r"\times Q_p "
            r"\right] + BA"
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
**Formula terms (per s11(1)):**

| Symbol | Legislation | Description |
|--------|-------------|-------------|
| ERC | s31/s33 | Emissions Reduction Contribution |
| h | s13 | Transition proportion |
| EI | Schedule 1 | Default (industry-average) emissions intensity |
| EIF | s14\u2013s16 | Facility-specific EI (from approved EID) |
| Q | s11(1) | Production quantity (applies when EID specifies EIF) |
| Q\u2082 | s11(1) | = 0 when EID specifies EIF for that variable |
| BA | s11(1) | Borrowing Adjustment |
""")

        with col2:
            st.markdown("""
**Ravenswood application (2 production variables):**

| Component | Value | Source |
|-----------|-------|--------|
| PV 1: ROM metal ore | Q = tonnes mined | EID (CER Oct 2024) |
| PV 2: Electricity generation | Q = MWh on-site | EID (CER Oct 2024) |
| EI\u2082 \u00d7 Q\u2082 | = 0 | EID covers both PVs |
| BA (Borrowing) | 0 | Not used |
| Minimum baseline | 100,000 tCO\u2082-e/year | CER practice |
""")

        st.markdown(
            '> **Section 11(2):** "The number worked out using the formula in '
            'subsection (1) is to be rounded to the nearest whole number '
            '(rounding up if the first decimal place is 5 or more)."'
        )
        st.caption(
            "Implementation note: Python round() uses banker\u2019s rounding.  "
            "Max deviation from s11(2) is 1 tCO\u2082-e per year.  Negligible impact."
        )

        st.markdown("---")

        # Expanded formula for Ravenswood
        st.markdown("#### Applied Formula (Ravenswood)")
        st.markdown(
            "Since the EID specifies EIF for both production variables, "
            "the EI\u2082 \u00d7 Q\u2082 terms are zero (per s11(1) definition of Q\u2082(a): "
            '"if an emissions intensity determination applies\u2026 specifies a '
            'facility-specific emissions intensity number of the production '
            'variable \u2014 0").  The formula simplifies to:'
        )
        st.latex(
            r"\text{Baseline} = \text{ERC} \times "
            r"\left["
            r"\left( h \cdot 0.00859 + (1-h) \cdot 0.0177 \right) \times ROM_t"
            r" + "
            r"\left( h \cdot 0.539 + (1-h) \cdot 0.9081 \right) \times Site_{MWh}"
            r"\right]"
        )

        st.info(
            "**ERC is linear, not compound.**  "
            'Per DCCEEW: \u201cThe ERC is 0.951 in 2023\u201324, 0.902 in 2024\u201325, and so on.\u201d  \n'
            "Formula: ERC = 1 \u2212 (n \u00d7 0.049) where n = FY \u2212 2023.  "
            "This is confirmed by s31 which tabulates exact values (not a compounding formula)."
        )


    # =================================================================
    # SECTION 2: EMISSIONS INTENSITY PARAMETERS
    # =================================================================
    with st.expander("\U0001f3ed  Emissions Intensity Parameters", expanded=True):

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("##### Facility-Specific EI (EIF)")
            st.markdown("*From approved EID, CER October 2024*")
            st.markdown("*Per s14\u2013s16 of the Safeguard Rule*")
            ei_fsei = pd.DataFrame([
                {"Production Variable": "ROM metal ore",
                 "Value": f"{fsei_rom:.4f}",
                 "Unit": "tCO\u2082-e/t"},
                {"Production Variable": "Electricity generation",
                 "Value": f"{fsei_elec:.4f}",
                 "Unit": "tCO\u2082-e/MWh"},
            ])
            st.dataframe(ei_fsei, hide_index=True, width="stretch")

        with col2:
            st.markdown("##### Default EI (Industry Average)")
            st.markdown("*Safeguard Rule, Schedule 1*")
            st.markdown("*Confirmed by CER Oct 2024: existing facilities use Default EI*")
            ei_default = pd.DataFrame([
                {"Production Variable": "ROM metal ore",
                 "Value": f"{DEFAULT_INDUSTRY_EI_ROM:.5f}",
                 "Unit": "tCO\u2082-e/t"},
                {"Production Variable": "Electricity generation",
                 "Value": f"{DEFAULT_INDUSTRY_EI_ELEC:.3f}",
                 "Unit": "tCO\u2082-e/MWh"},
            ])
            st.dataframe(ei_default, hide_index=True, width="stretch")

        with col3:
            st.markdown("##### Best Practice EI")
            st.markdown("*Safeguard Rule, Schedule 1*")
            st.markdown("*Applies to new facilities/products only*")
            ei_bp = pd.DataFrame([
                {"Production Variable": "ROM metal ore",
                 "Value": f"{BEST_PRACTICE_EI_ROM:.5f}",
                 "Unit": "tCO\u2082-e/t"},
                {"Production Variable": "Electricity generation",
                 "Value": f"{BEST_PRACTICE_EI_ELEC:.3f}",
                 "Unit": "tCO\u2082-e/MWh"},
            ])
            st.dataframe(ei_bp, hide_index=True, width="stretch")

        st.caption(
            f"Site generation ratio: {SITE_GENERATION_RATIO:.6f} MWh/t ROM "
            f"({SITE_GENERATION_RATIO * 1000:.3f} kWh/t).  "
            "Post-grid connection (1 Jul 2027), site generation drops to 2% "
            "(backup/portable only).  Grid connection transfer is baked into the data file."
        )

        st.warning(
            "**EID Renewal Risk (s14\u2013s16):**  The EID must be renewed annually by 31 October.  "
            "If Ravenswood fails to renew, EIF = 0 for both production variables and the s11 "
            "formula falls back to EI\u2082 \u00d7 Q\u2082 terms using Best Practice EI values "
            "(ROM: 0.00247 vs FSEI: 0.0177; Elec: 0.236 vs FSEI: 0.9081).  "
            "This would reduce the baseline by ~85% overnight, destroying SMC generation capacity."
        )

    # =================================================================
    # SECTION 3: ERC + TRANSITION SCHEDULE
    # =================================================================
    with st.expander("\U0001f4c9  ERC Decline & Hybrid EI Transition Schedule", expanded=True):

        st.markdown(
            '> **Section 31:** "The default emissions reduction contribution for a '
            'financial year beginning on 1 July 2030 or a later 1 July is the '
            'greater of: (a) the default emissions reduction contribution for '
            'the previous financial year minus 0.03285; and (b) 0."'
        )
        st.markdown(
            '> **Section 33(1):** For a regular facility (not trade-exposed '
            'baseline-adjusted), "the emissions reduction contribution for the '
            'facility for the financial year is the default emissions reduction '
            'contribution for that financial year."'
        )
        st.caption(
            "Ravenswood is a regular facility per s33(1).  "
            "ERC = default ERC from the s31 table."
        )

        schedule_data = []
        for fy in range(2024, 2036):
            erc = calculate_erc_for_fy(fy, decline_rate_phase2)
            h = get_transition_proportion(fy)
            h_rom, h_elec = calculate_hybrid_ei(fy, fsei_rom, fsei_elec)

            schedule_data.append({
                "FY": f"{fy-1}-{fy}",
                "n": fy - 2023,
                "ERC": f"{erc:.3f}",
                "h (Default %)": f"{h*100:.0f}%",
                "1-h (FSEI %)": f"{(1-h)*100:.0f}%",
                "Hybrid EI ROM": f"{h_rom:.5f}",
                "Hybrid EI Elec": f"{h_elec:.4f}",
                "Phase": "Phase 1 (4.9%)" if fy <= DECLINE_PHASE1_END else f"Phase 2 ({decline_rate_phase2 * 100:.1f}%)",
            })

        schedule_df = pd.DataFrame(schedule_data)
        st.dataframe(schedule_df, hide_index=True, width="stretch")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
**ERC Decline (s31, s32 \u2014 linear):**
- Phase 1 (FY2024\u2013FY2030): 4.9% per year per s32 Items 1\u20137
- Phase 2 (FY2031+): {decline_rate_phase2 * 100:.3f}% per year per s32 Item 8
- Post-FY2050: Frozen at Phase 2 end value
- DCCEEW 2026\u201327 review will set Phase 2 rates
""")

        with col2:
            st.markdown("""
**Hybrid EI Transition (s13):**
- FY2024\u2013FY2027: +10% Default per year (Items 1\u20134)
- FY2028\u2013FY2030: +20% Default per year (Items 5\u20136, step-up)
- FY2030 onwards: h = 1.0 (100% Default EI, 0% FSEI) per Item 7
- Transition converges all facilities to industry average
""")

    # =================================================================
    # SECTION 4: BASELINE VALIDATION
    # =================================================================
    # SECTION 6: LEGISLATIVE COMPLIANCE SUMMARY
    # =================================================================
    with st.expander("\U0001f3db\ufe0f  Legislative Compliance Summary", expanded=True):

        st.markdown("#### Model Alignment with Legislation")
        st.markdown(
            "This table maps each model parameter to the authorising provision "
            "in the Safeguard Mechanism Rule 2015 (Compilation F2024C00846, "
            "registered 02/10/2024) and the NGER Regulations 2008 (F2025C01114)."
        )

        compliance_data = pd.DataFrame([
            {"Model Parameter": "Baseline formula",
             "Value": "ERC \u00d7 \u03a3[h\u00b7EI + (1\u2212h)\u00b7EIF] \u00d7 Q",
             "Provision": "s11(1)",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "Rounding",
             "Value": "Nearest whole number",
             "Provision": "s11(2)",
             "Status": "\u2705 \u00b11 tCO\u2082-e"},
            {"Model Parameter": "Transition proportion (h)",
             "Value": "0.1 \u2192 1.0 per schedule",
             "Provision": "s13 Table",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "Default ERC",
             "Value": "0.951 declining to 0.657",
             "Provision": "s31 Table",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "Phase 1 decline rate",
             "Value": "4.9% linear",
             "Provision": "s32 Items 1\u20137",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "Phase 2 decline rate",
             "Value": "3.285% linear",
             "Provision": "s32 Item 8",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "Regular facility ERC",
             "Value": "= Default ERC",
             "Provision": "s33(1)",
             "Status": "\u2705 Confirmed"},
            {"Model Parameter": "FSEI ROM",
             "Value": "0.0177 tCO\u2082-e/t",
             "Provision": "EID (s14\u2013s16)",
             "Status": "\u2705 CER Oct 2024"},
            {"Model Parameter": "FSEI Electricity",
             "Value": "0.9081 tCO\u2082-e/MWh",
             "Provision": "EID (s14\u2013s16)",
             "Status": "\u2705 CER Oct 2024"},
            {"Model Parameter": "Default EI ROM",
             "Value": "0.00859 tCO\u2082-e/t",
             "Provision": "Schedule 1",
             "Status": "\u2705 CER confirmed"},
            {"Model Parameter": "Default EI Electricity",
             "Value": "0.539 tCO\u2082-e/MWh",
             "Provision": "Schedule 1",
             "Status": "\u2705 CER confirmed"},
            {"Model Parameter": "Safeguard threshold",
             "Value": "100,000 tCO\u2082-e",
             "Provision": "NGER Act s22X",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "Minimum baseline floor",
             "Value": "100,000 tCO\u2082-e",
             "Provision": "CER practice",
             "Status": "\u2705 Applied"},
            {"Model Parameter": "s58B earliest FY",
             "Value": "FY2029",
             "Provision": "s58B(2)(a)",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "s58B lookback",
             "Value": "3 of prev 5 FYs",
             "Provision": "s58B(2)(b)",
             "Status": "\u2705 Exact"},
            {"Model Parameter": "SMC issuance",
             "Value": "Baseline \u2212 Scope 1",
             "Provision": "s22XB (NGER Act)",
             "Status": "\u2705 Verified"},
            {"Model Parameter": "SMC surrender restriction",
             "Value": "Covered facilities only",
             "Provision": "s22XN (NGER Act)",
             "Status": "\u2705 Applied"},
        ])
        st.dataframe(compliance_data, hide_index=True, width="stretch")

        st.markdown("---")
        st.markdown("#### Validation Results")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
**Cross-checks performed:**
- FY2024 baseline: **269,728** (exact match with CER/NGERS)
- FY2025 baseline: **214,665** (independently verified)
- FY2024 SMC: **132,501** (exact match with CER-issued credits, Jan 2025)
- FY2025 SMC: **70,687** (exact match with CER guidance)
""")

        with col2:
            st.markdown("""
**Key legislative interpretations confirmed by CER:**
- Existing facilities use Default EI (not Best Practice) in transition (Oct 2024)
- s58B opt-in confirmed as available where 3-of-5 lookback met (CER guidance)
- No time limits on SMC trading or sale (CER guidance)
- Surrender restricted to covered facilities per s22XN (CER guidance)
""")

        st.success(
            "All model parameters are traceable to specific provisions of the "
            "Safeguard Mechanism Rule 2015, NGER Act 2007 or CER-confirmed "
            "guidance.  Baseline calculations produce exact matches with both "
            "CER-issued SMCs (FY2024) and independent verification (FY2025)."
        )


    # =================================================================
    # =================================================================
    # SECTION 7: NGA EMISSION FACTORS
    # =================================================================
    with st.expander("NGA Emission Factors - All Fuels Used", expanded=False):

        st.markdown("#### National Greenhouse Accounts Factors")
        st.caption(
            "Factors applied per NGA year.  Years as columns, factors as rows.  "
            "Only fuels present in the Ravenswood emissions data are shown."
        )

        # Build comprehensive factor table from nga_factors.csv
        try:
            nga_df = pd.read_csv('nga_factors.csv')
        except FileNotFoundError:
            nga_df = pd.DataFrame()

        if len(nga_df) > 0:
            # Fuels used at Ravenswood (matching NGAFuel column in emissions data)
            used_fuels = [
                'Diesel oil',
                'Grid electricity',
                'Liquefied petroleum gas (LPG)',
                'Petroleum based greases',
                'Petroleum based oils (other than petroleum based oil used as fuel), e.g. lubricants',
                'Gaseous fossil fuels other than those mentioned in the items above',
            ]

            # Short display names
            fuel_short = {
                'Diesel oil': 'Diesel',
                'Grid electricity': 'Grid Electricity (QLD)',
                'Liquefied petroleum gas (LPG)': 'LPG',
                'Petroleum based greases': 'Petroleum Greases',
                'Petroleum based oils (other than petroleum based oil used as fuel), e.g. lubricants': 'Lubricating Oils',
                'Gaseous fossil fuels other than those mentioned in the items above': 'Gaseous Fossil Fuels (Acetylene)',
            }

            years = sorted(nga_df['NGA_Year'].unique())

            table_rows = []
            for fuel in used_fuels:
                fuel_data = nga_df[nga_df['Fuel_Name'] == fuel]
                if len(fuel_data) == 0:
                    continue

                short_name = fuel_short.get(fuel, fuel)

                # Filter to QLD for grid electricity (state-specific)
                if fuel == 'Grid electricity':
                    fuel_data = fuel_data[fuel_data['State'] == 'QLD']

                for scope in sorted(fuel_data['Scope'].unique()):
                    scope_data = fuel_data[fuel_data['Scope'] == scope]
                    unit = scope_data['EF_Unit'].iloc[0] if len(scope_data) > 0 else ''

                    row = {
                        'Fuel': short_name,
                        'Scope': int(scope),
                        'Unit': unit,
                    }
                    for year in years:
                        yr_data = scope_data[scope_data['NGA_Year'] == year]
                        if len(yr_data) > 0:
                            val = yr_data['EF_kgCO2e_per_unit'].iloc[0]
                            if abs(val) < 1:
                                row[str(year)] = f"{val:.5f}"
                            elif abs(val) < 10:
                                row[str(year)] = f"{val:.2f}"
                            else:
                                row[str(year)] = f"{val:,.2f}"
                        else:
                            row[str(year)] = '\u2014'

                    table_rows.append(row)

            if table_rows:
                factor_df = pd.DataFrame(table_rows)
                st.dataframe(factor_df, hide_index=True, width="stretch")

                st.caption(
                    "Grid electricity factors are state-specific (Queensland shown).  "
                    "Combustion fuels use national factors.  "
                    "Scope 1 = direct combustion.  Scope 2 = purchased electricity.  "
                    "Scope 3 = upstream/indirect."
                )
            else:
                st.warning("No matching fuel factors found in nga_factors.csv")
        else:
            st.warning("nga_factors.csv not found")

    # SECTION 8: REFERENCES
    # =================================================================
    with st.expander("\U0001f4da  References & Data Sources", expanded=False):

        st.markdown("""
**Primary legislation:**
- National Greenhouse and Energy Reporting Act 2007 (NGER Act)
  - s22XB (safeguard mechanism credit units \u2014 issuance)
  - s22XE (safeguard mechanism credit units \u2014 surrender)
  - s22XN (restriction on surrender by non-covered facilities)
  - s22XS (rule-making power for Safeguard Mechanism)
- National Greenhouse and Energy Reporting (Safeguard Mechanism) Rule 2015
  - Compilation F2024C00846, registered 02/10/2024
  - Part 3, Division 2, Subdivision A, s11 (baseline formula)
  - Part 3, Division 2, Subdivision B, s13 (transition proportion)
  - Part 3, Division 2, Subdivision C, s14\u2013s16 (emissions intensity determination)
  - Part 3, Division 5, Subdivision A, s31 (default ERC)
  - Part 3, Division 5, s32 (default decline rate)
  - Part 3, Division 5, Subdivision B, s33 (regular facility ERC)
  - Part 3A, s58B (eligible facility \u2014 opt-in for below-threshold)
  - Schedule 1 (default and best practice emissions intensities)
- NGER Regulations 2008 (F2025C01114)
- NGER (Measurement) Determination 2008

**Regulatory guidance:**
- DCCEEW: Safeguard Mechanism reforms factsheet (4.9% decline, ERC definition)
- Clean Energy Regulator: Facility overview for Ravenswood Mine (FY2023\u201324)
- CER: s58B eligibility guidance (referenced in CER guidance)
- CER: Confirmation that existing facilities use Default EI (October 2024)

**Facility-specific data:**
- EID Basis of Preparation (February 2024)
- NGER Section 19 submission (October 2024)
  - Production: 11,624,570 t ROM, 101,540.078 MWh
  - Covered emissions: 137,227 tCO\u2082-e
  - Calculated baseline: 269,728 tCO\u2082-e (FY2023\u201324, ERC = 0.951)
  - SMCs issued: 132,501 (CER, January 2025)
  - Slide 4: FY2024 status and SMC confirmation
  - Slide 5: FY2025\u2013FY2030 production forecast
  - Slide 6: FY2025 baseline calculation (214,665 tCO\u2082-e)
  - Slide 8: Emissions forecast and baseline comparison
  - Slide 9: SMC cumulative forecast and CER s58B guidance

**Emission factors:**
- National Greenhouse Accounts Factors 2021\u20132025
  (Commonwealth of Australia, DCCEEW)

**Model parameters:**
- Grid connection: 1 July 2027 (baked into consolidated CSV)
- Diesel classification: on-site mining equipment = stationary energy (NGER Measurement Determination 2008)
- Transport fuel: road-registered light vehicles only
""")