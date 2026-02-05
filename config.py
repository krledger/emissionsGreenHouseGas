"""
config.py
Configuration constants and mappings for Ravenswood Gold emissions model
Last updated: 2026-02-05 20:53 AEDT

================================================================================
AUDIT DOCUMENTATION
================================================================================

PURPOSE:
This configuration file serves as the single source of truth for all data
classification standards, unit conversion factors and regulatory constants
used in the Ravenswood Gold Safeguard Mechanism Model.

DESIGN PRINCIPLE:
All classifications are based on the "Description" field only. No complex logic,
fallback rules or inference is used. This ensures:
1. Complete auditability and traceability
2. Clear data quality requirements
3. No "magic" classification decisions
4. Easy verification against source documents

If a Description value does not match the standards defined here, a data quality
error will be flagged rather than attempting to guess the correct classification.

FILE STRUCTURE:
1. Data Classification Standards
   - Diesel fuel classifications (by end-use purpose)
   - Electricity classifications (site vs grid)
   - Other fuel types (LPG, oils, gases)

2. Emission Scope Mappings
   - Scope 1 (Direct): Fuel combustion
   - Scope 2 (Indirect): Purchased electricity
   - Scope 3 (Other): Transmission losses, non-energy fuels

3. Regulatory Constants
   - Safeguard baseline parameters
   - Decline rates and thresholds
   - Reporting period definitions

4. Unit Conversion Factors
   - Volume conversions (ML, L, kL)
   - Mass conversions (t, Mt, kg)
   - Energy conversions (kWh, MWh, GJ)

5. Department Mappings
   - Pronto ERP department codes to operational categories
   - Alignment with organizational structure

6. Visualization Palette
   - Chart colors for consistent dashboard appearance
   - Gold-themed palette for mining industry context

DATA QUALITY REQUIREMENTS:
All input data must use exact Description values as defined in this file:
- Diesel oil - Site power generation (for generators)
- Diesel oil - Mobile equipment (for mining equipment)
- Grid electricity (purchased from network)
- Site electricity (generated on-site)
- Liquefied petroleum gas (LPG)
- Petroleum based oils
- Petroleum based greases
- Other gaseous fossil fuels
- Not reportable (non-energy materials)

Any variation in spelling, capitalization or wording will trigger a validation error.

REGULATORY REFERENCES:
- NGER (Measurement) Determination 2008: Method 1 calculations
- Safeguard Mechanism Rule 2015 (amended 2023): Baseline requirements
- National Greenhouse Account Factors: Annual emission factors by fuel type
- Clean Energy Regulator Guidance: Facility categorization and reporting

CRITICAL CONSTANTS:
- FSEI ROM Component: 0.0177 tCO₂-e/t (mining intensity baseline)
- FSEI Electricity Component: 0.9081 tCO₂-e/MWh (power intensity baseline)
- Site Generation Ratio: 0.008735 MWh/t (8.735 kWh per tonne ROM)
- Decline Rate: 4.9% per annum (FY2024 to FY2030)
- Grid Connection: FY2027 (transition from 100% diesel to 2% diesel + 98% grid)
- 10-Year Exit Rule: Facility exits Safeguard when Scope 1 < 100,000 tCO₂-e
  for 10 consecutive years (grace period FY2027-2036, exit FY2037)

FILE DEPENDENCIES:
Used by all calculation modules:
- emissions_calc.py: Emission calculations
- loader_data.py: Data classification
- nga_loader.py: NGA factor lookup
- projections.py: Baseline and SMC calculations
- All tab modules: Visualization and reporting

CHANGE LOG:
- 2026-02-02: Added comprehensive audit documentation and color palette
- 2026-01-28: Added grid connection scenario parameters
- 2026-01-20: Simplified to Description-only classification
- 2025-12-15: Initial configuration for Budget Prime architecture

================================================================================
"""

import pandas as pd
from datetime import datetime
# Date/calendar functions moved to calc_calendar.py
from calc_calendar import date_to_fy, date_to_cy


# =============================================================================
# DATA CLASSIFICATION STANDARDS
# =============================================================================
#
# This section defines the exact Description values expected in the
# consolidated_emissions_data.csv file and their classification for
# NGERS compliance reporting.
#
# AUDIT NOTE: All fuel and energy classifications are based on the Description
# column only. No complex logic or fallback rules are used. If a Description
# value does not match these standards, a data quality error will be flagged.
#
# REGULATORY BASIS:
# Classifications follow NGER (Measurement) Determination 2008 requirements
# for Method 1 emission calculations. Fuel type and end-use purpose determine
# the applicable emission factors from NGA Factors tables.
#

# -----------------------------------------------------------------------------
# DIESEL FUEL CLASSIFICATIONS
# -----------------------------------------------------------------------------
# Diesel fuel must be classified by end-use purpose for NGERS Method 1 reporting
# as per NGER (Measurement) Determination 2008 Section 2.23-2.26
#
# TWO DIESEL CATEGORIES ONLY:
# 1. Site power generation: Diesel consumed in stationary generators for electricity
# 2. Mobile equipment: Diesel consumed in mining equipment (haul trucks, loaders, etc.)
#
# REGULATORY SIGNIFICANCE:
# - Power generation diesel feeds into electricity intensity calculation
# - Mobile equipment diesel feeds into mining (ROM) intensity calculation
# - Both use the same emission factor (~2.68 kg CO₂-e/L) from NGA Factors Table 1
# - Classification determines which baseline component the emissions affect
#
# EMISSION FACTOR SOURCE:
# NGA Factors Table 1: Diesel Oil (Distillate Fuel Oil)
# - Full combustion factors include CO₂, CH₄, N₂O
# - Global Warming Potentials: 100-year GWP from IPCC AR4/AR5
# - Factor varies slightly by year (2.673-2.694 kg CO₂-e/L range 2021-2025)
#
# DATA SOURCE:
# Pronto ERP inventory transactions with Description field indicating purpose.
# Historical transactions use these exact strings consistently from FY2009 onwards.
#

DIESEL_CLASSIFICATIONS = {
    'Diesel oil - Site power generation': {
        'purpose': 'electricity',           # Used for power intensity calculation
        'ngers_method': 'Method 1 - Electricity Generation',
        'scope': 1,                         # Direct emissions (Scope 1)
        'notes': 'Diesel consumed in stationary generators for on-site electricity production. '
                 'Emissions calculated as ML × 1,000,000 L/ML × EF kg CO₂-e/L ÷ 1,000 kg/t. '
                 'This diesel consumption ceases almost entirely after grid connection (FY2027), '
                 'remaining at only 2% for backup generation.'
    },
    'Diesel oil - Mobile equipment': {
        'purpose': 'stationary',            # NGER classification (off-road mobile = stationary)
        'ngers_method': 'Method 1 - Stationary Energy (Off-road)',
        'scope': 1,                         # Direct emissions (Scope 1)
        'notes': 'Diesel consumed in mining equipment: haul trucks, front-end loaders, '
                 'excavators, dozers, graders, water trucks and drill rigs. '
                 'Emissions calculated as ML × 1,000,000 L/ML × EF kg CO₂-e/L ÷ 1,000 kg/t. '
                 'This is the primary source of Scope 1 emissions and drives the ROM intensity metric.'
    }
}

# Expected diesel Description values for data validation
# Any deviation triggers data quality error
VALID_DIESEL_DESCRIPTIONS = list(DIESEL_CLASSIFICATIONS.keys())

# -----------------------------------------------------------------------------
# ELECTRICITY CLASSIFICATIONS
# -----------------------------------------------------------------------------
# Electricity sources for Scope 1 (site generation) and Scope 2 (grid purchase)
#
# TWO ELECTRICITY CATEGORIES:
# 1. Grid electricity: Purchased from network (Scope 2 indirect emissions)
# 2. Site electricity: Generated on-site from diesel (Scope 1 direct emissions)
#
# REGULATORY SIGNIFICANCE:
# - Grid electricity uses NGA Factors state-specific emission factors (Queensland)
# - Site electricity is calculated output, not input (kWh generated, not diesel consumed)
# - Site generation has already been accounted in Scope 1 via power generation diesel
# - Grid connection (FY2027) shifts most electricity from Scope 1 to Scope 2
#
# GRID CONNECTION IMPACT:
# Current state (FY2024-2026):
#   - 100% site generation (diesel-powered)
#   - 0% grid purchase
#   - High Scope 1, zero Scope 2 electricity
#
# Post-connection (FY2027+):
#   - 2% site generation (backup only)
#   - 98% grid purchase
#   - Low Scope 1, high Scope 2 electricity
#
# EMISSION FACTOR SOURCES:
# Grid: NGA Factors Table 4 - Queensland (QLD) emission factor
#       ~0.79 kg CO₂-e/kWh (varies by year as grid decarbonizes)
# Site: Already captured in power generation diesel Scope 1 emissions
#       Do not double-count by applying emission factor to site kWh
#
# SCOPE 3 CONSIDERATION:
# Grid electricity also generates Scope 3 emissions from transmission and
# distribution (T&D) losses. These use NGA Factors Table 6.
#

ELECTRICITY_CLASSIFICATIONS = {
    'Grid electricity': {
        'source': 'grid_purchase',          # Purchased from Queensland grid
        'scope': 2,                         # Indirect emissions (Scope 2)
        'notes': 'Electricity purchased from Queensland grid (CS Energy invoices). '
                 'Emission factor from NGA Factors Table 4 (QLD). '
                 'Currently zero (pre-FY2027), becomes 98% of total electricity post-connection. '
                 'Also generates Scope 3 T&D losses (NGA Factors Table 6). '
                 'Grid is progressively decarbonizing (emission factor declining over time).'
    },
    'Site electricity': {
        'source': 'site_generation',        # Generated on-site from diesel
        'scope': 1,                         # Direct emissions (already counted in diesel)
        'notes': 'Electricity generated on-site from diesel fuel (calculated output in kWh). '
                 'This is NOT an additional emission source - the emissions are already captured '
                 'in "Diesel oil - Site power generation" Scope 1 calculations. '
                 'Site generation is used only for: (1) intensity calculations, (2) baseline '
                 'determination, and (3) operational tracking. '
                 'Currently 100% of electricity (pre-FY2027), reduces to 2% backup post-connection.'
    }
}

# Expected electricity Description values for data validation
# Any deviation triggers data quality error
VALID_ELECTRICITY_DESCRIPTIONS = list(ELECTRICITY_CLASSIFICATIONS.keys())

# -----------------------------------------------------------------------------
# OTHER FUEL CLASSIFICATIONS
# -----------------------------------------------------------------------------

OTHER_FUEL_CLASSIFICATIONS = {
    'Liquefied petroleum gas (LPG)': {
        'scope': 1,
        'ngers_method': 'Method 1 - Stationary Energy',
        'notes': 'LPG for process heating (boilers, furnaces, kilns)'
    },
    'Petroleum based oils': {
        'scope': 3,
        'notes': 'Lubricating oils, hydraulic fluids (combustible but not energy use)'
    },
    'Petroleum based greases': {
        'scope': 3,
        'notes': 'Lubricating greases (combustible but not energy use)'
    },
    'Other gaseous fossil fuels': {
        'scope': 1,
        'ngers_method': 'Method 1 - Stationary Energy',
        'notes': 'Acetylene for welding and cutting'
    },
    'Not reportable': {
        'scope': None,
        'notes': 'Non-combustible materials (oxygen, nitrogen, inert gases, process chemicals)'
    }
}

# -----------------------------------------------------------------------------
# PRODUCTION METRICS
# -----------------------------------------------------------------------------

PRODUCTION_DESCRIPTIONS = {
    'Ore Mined t': {
        'unit': 't',
        'notes': 'Run of Mine (ROM) ore extracted from pit'
    },
    'Milled Tonnes': {
        'unit': 'units',  # Actually tonnes but labeled as units in source
        'notes': 'Ore processed through mill'
    },
    'Crushed Ore t': {
        'unit': 't',
        'notes': 'Ore crushed before milling'
    },
    'Gold Produced': {
        'unit': 'units',  # Ounces as units
        'notes': 'Gold recovered and produced'
    },
    'Gold Recovered oz': {
        'unit': 'oz',
        'notes': 'Gold recovered in metallurgical process'
    },
    'Gold Sold': {
        'unit': 'units',  # Ounces as units
        'notes': 'Gold sold to market'
    }
}

# =============================================================================
# UNIT CONVERSION FACTORS
# =============================================================================
#
# Physical unit conversions (NOT emission factors)
# These are for converting between different measurement units
#
# AUDIT NOTE: These are standard physical conversion factors, not site-specific.
# Emission factors are maintained separately in NGA files.
#

# -----------------------------------------------------------------------------
# MASS CONVERSIONS
# -----------------------------------------------------------------------------

MASS_CONVERSIONS = {
    # Base unit: kg (kilogram)
    'g_to_kg': 0.001,           # 1 gram = 0.001 kg
    'kg_to_g': 1000,            # 1 kilogram = 1000 g
    'kg_to_t': 0.001,           # 1 kilogram = 0.001 tonnes
    't_to_kg': 1000,            # 1 tonne = 1000 kg
    'lb_to_kg': 0.453592,       # 1 pound = 0.453592 kg
    'oz_to_kg': 0.0283495,      # 1 ounce = 0.0283495 kg
}

# -----------------------------------------------------------------------------
# VOLUME CONVERSIONS
# -----------------------------------------------------------------------------

VOLUME_CONVERSIONS = {
    # Base unit: L (litre)
    'mL_to_L': 0.001,           # 1 millilitre = 0.001 L
    'L_to_mL': 1000,            # 1 litre = 1000 mL
    'L_to_kL': 0.001,           # 1 litre = 0.001 kilolitres
    'kL_to_L': 1000,            # 1 kilolitre = 1000 L
    'L_to_ML': 0.000001,        # 1 litre = 0.000001 megalitres
    'ML_to_L': 1000000,         # 1 megalitre = 1,000,000 L
    'gal_to_L': 3.78541,        # 1 US gallon = 3.78541 L
    'm3_to_L': 1000,            # 1 cubic metre = 1000 L
}

# -----------------------------------------------------------------------------
# ENERGY CONVERSIONS
# -----------------------------------------------------------------------------

ENERGY_CONVERSIONS = {
    # Base unit: kWh (kilowatt-hour)
    'Wh_to_kWh': 0.001,         # 1 watt-hour = 0.001 kWh
    'kWh_to_Wh': 1000,          # 1 kilowatt-hour = 1000 Wh
    'kWh_to_MWh': 0.001,        # 1 kilowatt-hour = 0.001 MWh
    'MWh_to_kWh': 1000,         # 1 megawatt-hour = 1000 kWh
    'kWh_to_GWh': 0.000001,     # 1 kilowatt-hour = 0.000001 GWh
    'GWh_to_kWh': 1000000,      # 1 gigawatt-hour = 1,000,000 kWh
    'GJ_to_kWh': 277.778,       # 1 gigajoule = 277.778 kWh
    'kWh_to_GJ': 0.0036,        # 1 kilowatt-hour = 0.0036 GJ
}

# =============================================================================
# FINANCIAL YEAR DEFINITION
# =============================================================================

# =============================================================================
# FISCAL YEAR CONFIGURATION
# =============================================================================

# Note: NGER_FY_START_MONTH defined in calc_calendar.py (always 7 for NGERS/Safeguard)
# Fiscal year start month for NGER reporting
NGER_FY_START_MONTH = 7  # July - required for backward compatibility with loader_data

# Default year for display in GHG tab
DEFAULT_DISPLAY_YEAR = 2025  # Year to show by default in year selectors
DEFAULT_YEAR_TYPE = 'CY'     # Default year type: 'CY' (Calendar Year) or 'FY' (Financial Year)
DEFAULT_DATA_SOURCE = 'Base'  # Default data source: 'Base', 'NPI-NGERS', or 'All'
# US fiscal year (Oct-Sep):           start_month = 10 (October)


def calculate_fy(year, month, fy_start_month=None):
    """Calculate financial year from calendar date

    Args:
        year: Calendar year
        month: Calendar month (1-12)
        fy_start_month: Fiscal year start month (1-12). If None, uses DEFAULT_FY_START_MONTH

    Returns:
        Financial year

    Examples (fy_start_month=1 - Calendar year):
        calculate_fy(2024, 1, 1) = 2024   # Jan 2024 = FY2024
        calculate_fy(2024, 7, 1) = 2024   # Jul 2024 = FY2024
        calculate_fy(2024, 12, 1) = 2024  # Dec 2024 = FY2024

    Examples (fy_start_month=7 - NGER year):
        calculate_fy(2023, 7, 7) = 2024   # Jul 2023 = FY2024
        calculate_fy(2024, 1, 7) = 2024   # Jan 2024 = FY2024
        calculate_fy(2024, 6, 7) = 2024   # Jun 2024 = FY2024
        calculate_fy(2024, 7, 7) = 2025   # Jul 2024 = FY2025
    """
    if fy_start_month is None:
        fy_start_month = DEFAULT_FY_START_MONTH

    if fy_start_month == 1:
        # Calendar year - simple case
        return year
    else:
        # Mid-year start (e.g., July-June)
        # If we're in or after the start month, FY is next calendar year
        if month >= fy_start_month:
            return year + 1
        else:
            return year


def get_fy_month_name(month_num):
    """Get month name from month number"""
    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    return month_names[month_num]


def get_fy_end_month(start_month):
    """Calculate FY end month (12 months after start)"""
    end_month = start_month - 1
    if end_month == 0:
        end_month = 12
    return end_month


def get_fy_description(fy_start_month=None):
    """Get human-readable description of fiscal year configuration

    Args:
        fy_start_month: Fiscal year start month (1-12). If None, uses DEFAULT_FY_START_MONTH

    Returns:
        String describing the fiscal year period
    """
    if fy_start_month is None:
        fy_start_month = DEFAULT_FY_START_MONTH

    end_month = get_fy_end_month(fy_start_month)
    start_name = get_fy_month_name(fy_start_month)
    end_name = get_fy_month_name(end_month)

    if fy_start_month == 1:
        return f"Calendar Year ({start_name}–{end_name})"
    elif fy_start_month == 7:
        return f"NGER Financial Year ({start_name}–{end_name})"
    else:
        return f"Custom Fiscal Year ({start_name}–{end_name})"

# =============================================================================
# =============================================================================
# SAFEGUARD MECHANISM PARAMETERS
# =============================================================================
#
# REGULATORY CONTEXT:
# The Safeguard Mechanism (SMM) was established under the NGER Act 2007 and
# commenced 1 July 2016. Reformed in July 2023 to include declining baselines
# and credit generation for over-performance.
#
# FACILITY DETAILS:
# - Facility: Ravenswood Gold Mine
# - Facility ID: Not disclosed in model (commercial confidentiality)
# - Responsible Entity: Ravenswood Gold Group Pty Ltd
# - Baseline Type: Production-adjusted (intensity-based)
# - Baseline Method: Facility-Specific Emission Intensity (FSEI)
#
# EMISSION INTENSITY DETERMINATION (EID):
# Approved by Clean Energy Regulator October 2024 following independent
# assurance engagement. Based on FY2024 operational data as the most
# representative baseline year (post-expansion, stable operations).
#
# BASELINE FORMULA:
# Annual Baseline (tCO₂-e) = ROM Production (t) × Baseline Intensity (tCO₂-e/t)
#
# where:
# Baseline Intensity = ROM Component + (Site Gen Ratio × Elec Component) × (1 - decline_rate)^years
#                    = 0.0177 + (0.008735 × 0.9081) × (1 - 0.049)^(year - 2024)
#                    = 0.02563 tCO₂-e/t (FY2024)
#                    = declining 4.9% p.a. to FY2030, then flat
#
# SAFEGUARD MECHANISM CREDITS (SMCs):
# Generated when: Actual Scope 1 Emissions < Annual Baseline
# SMC Amount (tCO₂-e) = Baseline - Actual (when positive)
# Credit Value ($) = SMC Amount × Carbon Credit Price × (1 + escalation)^years
#
# 10-YEAR EXIT RULE:
# Facility exits Safeguard Mechanism when Scope 1 emissions < 100,000 tCO₂-e
# for 10 consecutive financial years. Once exited, no further SMCs generated.
# Grace period: FY2027-2036 (grid connection in FY2027 drops Scope 1 below threshold)
# Exit year: FY2037 (after 10-year grace period expires)
#
# GRID CONNECTION IMPACT:
# FY2027 grid connection fundamentally changes emissions profile:
# - Scope 1 drops from ~195,000 to ~99,000 tCO₂-e (50% reduction)
# - Scope 2 increases from ~95,000 to ~180,000 tCO₂-e (grid electricity)
# - Total emissions remain similar (~290,000 tCO₂-e) but shift from Scope 1 to 2
# - Baseline continues declining 4.9% p.a. through FY2030
# - SMC generation accelerates dramatically (larger gap: Actual < Baseline)
# - Cumulative credits FY2024-2036: ~440,000 tCO₂-e (~$16M @ escalating prices)
#

# -----------------------------------------------------------------------------
# APPROVED FACILITY-SPECIFIC EMISSION INTENSITY (FSEI) FACTORS
# -----------------------------------------------------------------------------
# Source: Clean Energy Regulator Emission Intensity Determination
# Approval Date: October 2024
# Baseline Year: FY2024 (July 2023 - June 2024)
# Assurance: Independent limited assurance engagement completed April 2024
#

FSEI_ELEC = 0.9081  # tCO₂-e per MWh of on-site electricity generation
                     # Derived from: Power diesel consumption ÷ electricity output
                     # FY2024 data: ~1,080 ML diesel Â¢Ã¢â‚¬Â Ã¢â‚¬â„¢ ~108,000 MWh generation
                     # Calculation: (1,080 ML × 1,000,000 L/ML × 2.68 kg/L ÷ 1,000) ÷ 108,000 MWh
                     #            = 2,894,400 kg CO₂-e ÷ 108,000 MWh = 0.9081 tCO₂-e/MWh

FSEI_ROM = 0.0177   # tCO₂-e per tonne of Run of Mine (ROM) ore extracted
                     # Derived from: Mobile diesel consumption ÷ ROM production
                     # FY2024 data: ~5,300 ML diesel Â¢Ã¢â‚¬Â Ã¢â‚¬â„¢ ~4,280,000 t ROM
                     # Calculation: (5,300 ML × 1,000,000 L/ML × 2.68 kg/L ÷ 1,000) ÷ 4,280,000 t
                     #            = 14,204,000 kg CO₂-e ÷ 4,280,000 t = 0.0177 tCO₂-e/t

# Site Generation Ratio (calculated from FY2024 operations)
SITE_GENERATION_RATIO = 0.008735  # MWh per tonne ROM (8.735 kWh/t)
                                  # Derived from: Electricity output ÷ ROM production
                                  # Calculation: 108,000 MWh ÷ 4,280,000 t = 0.008735 MWh/t
                                  # Used in baseline calculation to scale electricity component

# Combined Baseline Intensity (FY2024)
# = FSEI_ROM + (SITE_GENERATION_RATIO × FSEI_ELEC)
# = 0.0177 + (0.008735 × 0.9081)
# = 0.0177 + 0.007931
# = 0.02563 tCO₂-e/t ROM

# -----------------------------------------------------------------------------
# BASELINE DECLINE TRAJECTORY
# -----------------------------------------------------------------------------
# Safeguard Mechanism (Reformed 2023) requires declining baselines to drive
# emissions reduction. Decline rate is facility-specific based on sector.
#

# Two-stage decline per Safeguard Mechanism legislation
DECLINE_RATE_PHASE1 = 0.049     # 4.9% per annum (FY2024-FY2030)
DECLINE_RATE_PHASE2 = 0.03285   # 3.285% per annum (FY2031-FY2050, indicative)

DECLINE_PHASE1_START = 2024     # FY2024: Phase 1 decline starts
DECLINE_PHASE1_END = 2030       # FY2030: Phase 1 ends
DECLINE_PHASE2_START = 2031     # FY2031: Phase 2 decline starts
DECLINE_PHASE2_END = 2050       # FY2050: Phase 2 ends, flat thereafter

# Legacy constants (for backward compatibility)
DECLINE_RATE = DECLINE_RATE_PHASE1   # Default to Phase 1 rate
DECLINE_FROM = DECLINE_PHASE1_START
DECLINE_TO = DECLINE_PHASE2_END
# -----------------------------------------------------------------------------
# SAFEGUARD MECHANISM CREDIT (SMC) GENERATION
# -----------------------------------------------------------------------------
# Credits can be generated when actual emissions are below baseline.
# Credits are Australian Carbon Credit Units (ACCUs) that can be traded or
# held to offset future above-baseline emissions.
#

SAFEGUARD_THRESHOLD = 100000  # tCOšâ€š-e - Facilities above this threshold are
                              # subject to Safeguard Mechanism requirements

# Reformed Safeguard Mechanism start date (legislation effective date)
SAFEGUARD_START_DATE = datetime(2023, 7, 1)  # July 1, 2023
CREDIT_START_DATE = datetime(2023, 7, 1)     # July 1, 2023 (first date credits can be earned)
SAFEGUARD_DATE = datetime(2023, 7, 1)         # July 1, 2023 (reformed Safeguard Mechanism start)

# Prior to July 1, 2023, the reformed mechanism did not exist
# Exit year calculations only consider dates >= SAFEGUARD_START_DATE

SMC_EXIT_PERIOD_YEARS = 10  # Years SMC credits remain valid after dropping below 100,000 tCO2-e threshold
                             # Per Safeguard Mechanism Rule 2015

# =============================================================================
# PRODUCTION ASSUMPTIONS
# =============================================================================

BASE_MWH = 108000        # Annual on-site generation (MWh) - pre-grid connection
POST_GRID_MWH = 2160     # Residual on-site generation post-grid (2% of baseline for portable/backup)
PRE_GRID_PURCHASE_MWH = 120000  # Existing grid purchase pre-connection (based on FY2024-2025 average)

# Post-grid connection: Site generation shifts to grid
# Total power remains similar, just the source changes
# POST_GRID_TOTAL = PRE_GRID_PURCHASE + (BASE_MWH * 0.98 shifted from diesel to grid)
POST_GRID_TOTAL_MWH = 226000  # 120k existing + 106k shifted from site generation

# Phase-specific grid power levels (% of POST_GRID_TOTAL_MWH)
GRID_MINING_FACTOR = 1.00      # 100% during mining (full operations)
GRID_PROCESSING_FACTOR = 0.95  # 95% when mining stops (processing continues)
GRID_REHABILITATION_FACTOR = 0.05  # 5% during rehabilitation (minimal)

# Maturity cutoff
MATURITY_CUTOFF = pd.Timestamp('2023-08-01')

# =============================================================================
# COST CENTRE MAPPINGS
# =============================================================================

# Display category grouping
CATEGORY_MAP = {
    'Supplemental Power Supply': 'Power',
    'Site Power Generation': 'Power',  # Standardized name for power generation
    'Hauling': 'Mining',
    'Loading': 'Mining',
    'Drilling - Production': 'Mining',
    'Blasting': 'Mining',
    'Supplementary Load and Haul': 'Mining',
    'Rehandling': 'Fixed',
    'Mobile Equipment': 'Fixed',
    'Grade Control': 'Mining',
    'Geotechnical': 'Fixed',
    'Crushing - Fixed': 'Processing',
    'Crushing - Supplemental': 'Processing',
    'New Crusher': 'Processing',
    'Nolans South Crusher': 'Processing',
    'Milling': 'Processing',
    'Tailings Disposal': 'Processing',
    'Light Vehicles': 'Fixed',
    'Management Services': 'Fixed',
    'Operations Administration': 'Fixed',
    'Exploration and Development': 'Fixed',
    'Environment': 'Fixed',
    'Rehabilitation': 'Fixed',
    'Gold Room': 'Processing',
    'Village and Housing': 'Fixed',
    'Leach & Adsorption': 'Processing',
    'Laboratory': 'Processing',
    'Supp Crushing Mobile Equipment': 'Processing',
    'Stores & Supply': 'Fixed',
    'Mobile Equipment Workshop': 'Fixed',
    'Infrastructure': 'Fixed',
    'NPE Dredge': 'Mining',  # Mining equipment
}

# NGER purpose classification (determines emission factor table)
NGER_PURPOSE_MAP = {
    'Supplemental Power Supply': 'electricity',
    'Site Power Generation': 'electricity',  # Standardized name for power generation
    'Hauling': 'stationary',
    'Loading': 'stationary',
    'Drilling - Production': 'stationary',
    'Supplementary Load and Haul': 'stationary',
    'Mobile Equipment': 'stationary',
    'Rehandling': 'stationary',
    'Grade Control': 'stationary',
    'Geotechnical': 'stationary',
    'Crushing - Fixed': 'stationary',
    'Crushing - Supplemental': 'stationary',
    'New Crusher': 'stationary',
    'Nolans South Crusher': 'stationary',
    'Milling': 'stationary',
    'Tailings Disposal': 'stationary',
    'Light Vehicles': 'transport',
    'Management Services': 'transport',
    'Operations Administration': 'transport',
    'Exploration and Development': 'stationary',
    'Environment': 'stationary',
    'Blasting': 'explosives',
    'Rehabilitation': 'stationary',
    'Gold Room': 'stationary',
    'Village and Housing': 'stationary',
    'Leach & Adsorption': 'stationary',
    'Laboratory': 'stationary',
    'Supp Crushing Mobile Equipment': 'stationary',
    'Stores & Supply': 'stationary',
    'Mobile Equipment Workshop': 'stationary',
    'Infrastructure': 'stationary',
    'NPE Dredge': 'stationary',  # Mining equipment
}

# =============================================================================
# OPERATIONAL PHASE PROFILES
# =============================================================================

# Phase transition dates (actual dates - first day of fiscal year)
# Dates are the source of truth for all phase logic and comparisons.
DEFAULT_START_DATE = datetime(2023, 7, 1)               # July 1, 2023 (FY2024)
DEFAULT_END_MINING_DATE = datetime(2034, 7, 1)          # July 1, 2034
DEFAULT_END_PROCESSING_DATE = datetime(2037, 7, 1)      # July 1, 2037
DEFAULT_END_REHABILITATION_DATE = datetime(2044, 7, 1)  # July 1, 2044

# Grid connection date (calendar date when grid becomes available)
DEFAULT_GRID_CONNECTION_DATE = datetime(2026, 7, 1)     # July 1, 2026 (FY2027)

# =============================================================================
# PROJECTION DEFAULTS
# =============================================================================


# Baseline year for projections (last stable operational year)

# Projection variability (for realistic year-to-year variation)

# =============================================================================
# CARBON MARKET DEFAULTS
# =============================================================================

# Carbon Credit Market
DEFAULT_CARBON_CREDIT_PRICE = 35.0  # $/tCO–Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡-e
DEFAULT_CREDIT_ESCALATION = 0.03    # 3% per annum

# Carbon Tax Scenario
DEFAULT_TAX_START_DATE = datetime(2029, 7, 1)  # July 1, 2029 (FY2030)
DEFAULT_TAX_RATE = 15.0             # $/tCO–Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡-e initial rate
DEFAULT_TAX_ESCALATION = 0.02       # 2% per annum

# =============================================================================

# =============================================================================
# INDUSTRY BENCHMARKS (from Safeguard Rule)
# =============================================================================

DEFAULT_INDUSTRY_EI_ROM = 0.00859   # Industry default tCO–Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡-e/t ROM
DEFAULT_INDUSTRY_EI_ELEC = 0.539    # Industry default tCO–Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡Æ’Ã†â€™â€šÃ‚Â¢Æ’Ã‚Â¢Â¢šÂ¬Ã…Â¡â€šÃ‚Â¬Æ’Ã¢â‚¬Â¦â€šÃ‚Â¡-e/MWh

# Phase 1: Active Mining (up to End of Mining FY)
# All cost centres operate at 100%
PHASE_MINING = {
    'Supplemental Power Supply': 1.00,
    'Hauling': 1.00,
    'Loading': 1.00,
    'Drilling - Production': 1.00,
    'Blasting': 1.00,
    'Supplementary Load and Haul': 1.00,
    'Rehandling': 1.00,
    'Mobile Equipment': 1.00,
    'Grade Control': 1.00,
    'Geotechnical': 1.00,
    'Crushing - Fixed': 1.00,
    'Crushing - Supplemental': 1.00,
    'New Crusher': 1.00,
    'Nolans South Crusher': 1.00,
    'Milling': 1.00,
    'Tailings Disposal': 1.00,
    'Light Vehicles': 1.00,
    'Management Services': 1.00,
    'Operations Administration': 1.00,
    'Exploration and Development': 1.00,
    'Environment': 1.00,
    'Rehabilitation': 1.00,
    'Gold Room': 1.00,
    'Village and Housing': 1.00,
    'Leach & Adsorption': 1.00,
    'Laboratory': 1.00,
    'Supp Crushing Mobile Equipment': 1.00,
    'Stores & Supply': 1.00,
    'Mobile Equipment Workshop': 1.00,
    'Infrastructure': 1.00,
}

# Phase 1a: Active Mining POST-GRID CONNECTION
# All operations continue but site power generation drops to 2% (portable/backup only)
PHASE_MINING_POST_GRID = {
    'Supplemental Power Supply': 0.02,  # Only 2% - portable generators and backup
    'Hauling': 1.00,
    'Loading': 1.00,
    'Drilling - Production': 1.00,
    'Blasting': 1.00,
    'Supplementary Load and Haul': 1.00,
    'Rehandling': 1.00,
    'Mobile Equipment': 1.00,
    'Grade Control': 1.00,
    'Geotechnical': 1.00,
    'Crushing - Fixed': 1.00,
    'Crushing - Supplemental': 1.00,
    'New Crusher': 1.00,
    'Nolans South Crusher': 1.00,
    'Milling': 1.00,
    'Tailings Disposal': 1.00,
    'Light Vehicles': 1.00,
    'Management Services': 1.00,
    'Operations Administration': 1.00,
    'Exploration and Development': 1.00,
    'Environment': 1.00,
    'Rehabilitation': 1.00,
    'Gold Room': 1.00,
    'Village and Housing': 1.00,
    'Leach & Adsorption': 1.00,
    'Laboratory': 1.00,
    'Supp Crushing Mobile Equipment': 1.00,
    'Stores & Supply': 1.00,
    'Mobile Equipment Workshop': 1.00,
    'Infrastructure': 1.00,
}

# Phase 2: Processing Only (after End of Mining, before End of Processing)
# Mining operations cease, processing continues with rehabilitation
# Grid power: 95% of post-grid total (5% reduction from full mining operations)
PHASE_PROCESSING = {
    'Supplemental Power Supply': 0.02,  # Minimal site power (post-grid level maintained)
    'Hauling': 0.00,                    # Mining stopped
    'Loading': 0.00,                    # Mining stopped
    'Drilling - Production': 0.00,      # Mining stopped
    'Blasting': 0.00,                   # Mining stopped
    'Supplementary Load and Haul': 0.00,  # Mining stopped
    'Rehandling': 0.00,                 # Mining stopped
    'Mobile Equipment': 0.00,           # Mining stopped
    'Grade Control': 0.00,              # Mining stopped
    'Geotechnical': 0.00,               # Reduced
    'Crushing - Fixed': 1.00,           # Processing stockpiles
    'Crushing - Supplemental': 0.00,    # Reduced
    'New Crusher': 1.00,                # Processing stockpiles
    'Nolans South Crusher': 1.00,       # Processing stockpiles
    'Milling': 1.00,                    # Processing stockpiles
    'Tailings Disposal': 1.00,          # Processing continues
    'Light Vehicles': 1.00,             # Ongoing operations
    'Management Services': 1.00,        # Ongoing operations
    'Operations Administration': 1.00,  # Ongoing operations
    'Exploration and Development': 0.00,  # Ceased
    'Environment': 0.50,                # Reduced monitoring
    'Rehabilitation': 1.00,             # Active rehabilitation
    'Gold Room': 1.00,                  # Processing continues
    'Village and Housing': 1.00,        # Ongoing operations
    'Leach & Adsorption': 1.00,         # Processing continues
    'Laboratory': 1.00,                 # Ongoing analysis
    'Supp Crushing Mobile Equipment': 0.00,  # Reduced
    'Stores & Supply': 1.00,            # Ongoing operations
    'Mobile Equipment Workshop': 1.00,  # Ongoing maintenance
    'Infrastructure': 1.00,             # Ongoing operations
    'Mining': 0.00,                     # ROM production stopped (ore extraction ceased)
}

# Phase 3: Rehabilitation Only (after End of Processing)
# Only rehabilitation and minimal support operations
PHASE_REHABILITATION = {
    'Supplemental Power Supply': 0.00,  # All operations ceased
    'Hauling': 0.00,
    'Loading': 0.00,
    'Drilling - Production': 0.00,
    'Blasting': 0.00,
    'Supplementary Load and Haul': 0.00,
    'Rehandling': 0.00,
    'Mobile Equipment': 0.10,           # Minimal equipment for rehab
    'Grade Control': 0.00,
    'Geotechnical': 0.00,
    'Crushing - Fixed': 0.00,           # Processing ceased
    'Crushing - Supplemental': 0.00,
    'New Crusher': 0.00,
    'Nolans South Crusher': 0.00,
    'Milling': 0.00,
    'Tailings Disposal': 0.00,
    'Light Vehicles': 0.10,             # Minimal transport
    'Management Services': 0.10,        # Minimal admin
    'Operations Administration': 0.10,  # Minimal admin
    'Exploration and Development': 0.00,
    'Environment': 0.25,                # Ongoing monitoring
    'Rehabilitation': 1.00,             # Active rehabilitation
    'Gold Room': 0.00,                  # Processing ceased
    'Village and Housing': 0.10,        # Minimal
    'Leach & Adsorption': 0.00,         # Processing ceased
    'Laboratory': 0.10,                 # Minimal environmental testing
    'Supp Crushing Mobile Equipment': 0.00,  # Ceased
    'Stores & Supply': 0.10,            # Minimal supplies
    'Mobile Equipment Workshop': 0.10,  # Minimal maintenance
    'Infrastructure': 0.10,             # Minimal upkeep
    'Mining': 0.00,                     # ROM production stopped (ore extraction ceased)
}

# Phase profile lookup
PHASE_PROFILES = {
    'mining': PHASE_MINING,
    'mining_post_grid': PHASE_MINING_POST_GRID,
    'processing': PHASE_PROCESSING,
    'rehabilitation': PHASE_REHABILITATION,
}

def get_phase_profile(fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy, grid_connected_fy=None):
    """Determine operational phase and return activity profile

    Args:
        fy: Financial year
        end_mining_fy: Last year of mining operations
        end_processing_fy: Last year of processing operations
        end_rehabilitation_fy: Last year of rehabilitation
        grid_connected_fy: Year grid connection occurs (optional)

    Returns:
        Tuple of (phase_name, profile_dict, is_active)
        - phase_name: 'mining', 'mining_post_grid', 'processing', 'rehabilitation', or 'closed'
        - profile_dict: Cost centre activity multipliers
        - is_active: Boolean indicating if facility is operational
    """
    if fy <= end_mining_fy:
        # Check if grid connected during mining phase
        if grid_connected_fy is not None and fy >= grid_connected_fy:
            return ('mining_post_grid', PHASE_MINING_POST_GRID, True)
        else:
            return ('mining', PHASE_MINING, True)
    elif fy <= end_processing_fy:
        return ('processing', PHASE_PROCESSING, True)
    elif fy <= end_rehabilitation_fy:
        return ('rehabilitation', PHASE_REHABILITATION, True)
    else:
        return ('closed', {}, False)

def apply_phase_profile(fuel_data, phase_profile):
    """Apply phase profile multipliers to fuel consumption data

    Args:
        fuel_data: DataFrame with fuel consumption by cost centre
        phase_profile: Dict of cost centre activity multipliers

    Returns:
        DataFrame with adjusted fuel consumption
    """
    adjusted = fuel_data.copy()

    for cost_centre, multiplier in phase_profile.items():
        mask = adjusted['Costcentre'] == cost_centre
        adjusted.loc[mask, 'Fuel'] *= multiplier

    return adjusted

# =============================================================================
# COLOR PALETTE - Gold Mining Theme
# =============================================================================
#
# Professional gold-themed color palette consistent across all tabs.
# Theme reflects the mining/gold industry with warm metallic tones.
#
# Last updated: 2026-02-02 09:00 AEST
#
# DESIGN RATIONALE:
# - Gold tones for production metrics and positive values (ROM, credits, cumulative)
# - Dark brown for analytical lines and annual values
# - Green accent for grid connection (clean energy transition)
# - Black for regulatory baselines (authoritative reference)
#
# =============================================================================

# -----------------------------------------------------------------------------
# PRIMARY PALETTE - Gold Tones
# -----------------------------------------------------------------------------

GOLD_METALLIC = '#DBB12A'      # Primary gold - main bars, ROM production
BRIGHT_GOLD = '#E8AC41'        # Secondary gold - site electricity (top of stack)
DARK_GOLDENROD = '#AE8B0F'    # Tertiary gold - grid electricity (bottom of stack)

# Usage:
# - GOLD_METALLIC: ROM production bars, Scope 1 bars, SMC credit bars,
#                  cumulative tax bars, all primary metrics
# - BRIGHT_GOLD: Site-generated electricity (top of stacked bars)
# - DARK_GOLDENROD: Grid-purchased electricity (bottom of stacked bars)

# -----------------------------------------------------------------------------
# ACCENT COLORS
# -----------------------------------------------------------------------------

SEPIA = '#734B1A'              # Accent brown - rarely used
CAFE_NOIR = '#39250B'          # Dark brown - lines, text, annual values

# Usage:
# - CAFE_NOIR: Actual intensity lines, annual tax line, credit value line,
#              all analytical trend lines
# - SEPIA: Reserved for special emphasis (currently unused)

# -----------------------------------------------------------------------------
# FUNCTIONAL COLORS
# -----------------------------------------------------------------------------

GRID_GREEN = '#2A9D8F'         # Grid connection marker (clean energy)
BASELINE_BLACK = '#000000'     # Regulatory baseline (dashed lines)

# Usage:
# - GRID_GREEN: Vertical line marking grid connection year on all charts
# - BASELINE_BLACK: Safeguard baseline intensity (dashed reference line)

# -----------------------------------------------------------------------------
# COLOR USAGE BY TAB
# -----------------------------------------------------------------------------
#
# TAB 1 - GHG EMISSIONS:
#   ROM Production: GOLD_METALLIC bars
#   Total Emissions: GOLD_METALLIC bars + CAFE_NOIR line (intensity)
#   Scope Breakdown: Standard scope colors (see legacy palette below)
#
# TAB 2 - SAFEGUARD MECHANISM:
#   ROM Production: GOLD_METALLIC bars
#   Electricity (stacked): DARK_GOLDENROD (grid bottom) + BRIGHT_GOLD (site top)
#   Scope 1 Emissions: GOLD_METALLIC bars
#   Intensity Lines: CAFE_NOIR (actual) + BASELINE_BLACK (baseline dashed)
#   SMC Credits: GOLD_METALLIC bars + CAFE_NOIR line (credit value)
#   Grid Marker: GRID_GREEN vertical line on all charts
#
# TAB 3 - CARBON TAX:
#   Tax Liability: GOLD_METALLIC bars (cumulative) + CAFE_NOIR line (annual)
#
# TAB 4 - NGER DATA:
#   All charts: Standard scope colors (see legacy palette below)
#
# =============================================================================

# -----------------------------------------------------------------------------
# LEGACY COLOR PALETTE (Pre-Gold Theme)
# -----------------------------------------------------------------------------
# Maintained for backward compatibility with Tab 4 (NGER) and any custom charts
# These colors are from the original corporate blue/gray palette

COLORS = {
    # Scope colors (for emissions breakdown charts)
    'scope1': '#2C3E50',          # Navy blue - direct emissions
    'scope2': '#3498DB',          # Medium blue - indirect (purchased)
    'scope3': '#95A5A6',          # Light gray - value chain

    # Metrics and references
    'actual_intensity': '#E74C3C', # Red - performance metric
    'baseline': '#34495E',        # Dark gray - reference standard

    # Operational categories (if needed for detailed breakdowns)
    'power': '#F39C12',           # Amber - power generation
    'mining': '#E67E22',          # Orange - mining operations
    'processing': '#16A085',      # Teal - processing
    'fixed': '#7F8C8D',           # Gray - fixed/admin

    # Financial indicators
    'credits': '#27AE60',         # Green - positive credits
    'deficit': '#C0392B',         # Dark red - deficit
    'tax': '#C0392B',             # Tax liability

    # Production and datasets
    'rom': '#95A5A6',             # Light gray - production
    'smc': '#27AE60',             # SMC credits
    'base': '#2C3E50',            # Base dataset
    'npi': '#3498DB',             # NPI-NGERS dataset
}

# -----------------------------------------------------------------------------
# RECOMMENDED COLOR SELECTION
# -----------------------------------------------------------------------------
#
# For NEW charts, use the gold theme colors directly:
#   - Import: from config import GOLD_METALLIC, CAFE_NOIR, etc.
#   - Bars: GOLD_METALLIC
#   - Lines: CAFE_NOIR
#   - Grid marker: GRID_GREEN
#
# For EXISTING charts (Tab 4), continue using COLORS dict:
#   - Import: from config import COLORS
#   - Access: COLORS['scope1'], COLORS['scope2'], etc.
#
# =============================================================================

# =============================================================================
# SCOPE NAMING CONVENTIONS
# =============================================================================

SCOPE_NAMES = {
    'scope1': 'Scope 1 (Direct)',
    'scope2': 'Scope 2 (Indirect)',
    'scope3': 'Scope 3 (Value Chain)',
}

# =============================================================================
# NGA EMISSION FACTORS (2025)
# =============================================================================
# National Greenhouse Account emission factors
# Source: nationalgreenhouseaccountfactors2025.xlsx

# Energy content factors (GJ/unit)
ENERGY_CONTENT = {
    'diesel_gj_per_kl': 38.6,
    'lpg_gj_per_kl': 25.7,
    'petroleum_oil_gj_per_kl': 38.8,
    'petroleum_grease_gj_per_kl': 38.8,
    'acetylene_gj_per_m3': 0.0393,
    'gasoline_gj_per_kl': 34.2,
}

# Conversion factors
CONVERSIONS = {
    'lpg_density': 0.51,        # kg/L
    'grease_density': 0.9,      # kg/L (approx)
}

# Diesel emission factors by purpose (kg CO2-e/GJ)
DIESEL_FACTORS = {
    'electricity_generation': {
        'scope1_co2': 69.9,
        'scope1_ch4': 0.1,
        'scope1_n2o': 0.2,
        'scope1_total': 70.2,
    },
    'transport': {
        'scope1_co2': 69.9,
        'scope1_ch4': 0.01,  # Lower CH4 for modern transport
        'scope1_n2o': 0.5,   # Higher N2O for transport
        'scope1_total': 70.41,
    },
    'stationary': {
        'scope1_co2': 69.9,
        'scope1_ch4': 0.1,
        'scope1_n2o': 0.2,
        'scope1_total': 70.2,
    },
    'explosives': {  # ANFO combustion
        'scope1_co2': 69.9,
        'scope1_ch4': 0.1,
        'scope1_n2o': 0.2,
        'scope1_total': 70.2,
    },
    'scope3': 17.3,  # kg CO2-e/GJ (same for all diesel uses)
}

# LPG emission factors (kg CO2-e/GJ)
LPG_FACTORS = {
    'scope1': 60.6,
    'scope3': 20.2,
}

# Petroleum products emission factors (kg CO2-e/GJ)
PETROLEUM_FACTORS = {
    'oils_scope3': 18.0,
    'greases_scope3': 18.0,
}

# Gaseous fuels emission factors (kg CO2-e/GJ)
GASEOUS_FACTORS = {
    'acetylene_scope1': 51.53,  # "Gaseous fossil fuels other than..."
}

# =============================================================================
# FILE PATHS
# =============================================================================

DEFAULT_PATHS = {
    'consolidated': 'consolidated_emissions_data.csv',
    'nga': 'national-greenhouse-account-factors-2025.xlsx'
}