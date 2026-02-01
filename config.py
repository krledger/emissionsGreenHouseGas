"""
config.py
Configuration constants and mappings for Ravenswood Gold emissions model
Last updated: 2026-02-02 09:00 AEST

AUDIT READY: This file contains all data classification standards and unit
conversion factors in a single location for easy auditor review.
All classifications are based on Description field only - no complex logic.
"""

import pandas as pd



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

# -----------------------------------------------------------------------------
# DIESEL FUEL CLASSIFICATIONS
# -----------------------------------------------------------------------------
# Diesel fuel must be classified by end-use purpose for NGERS Method 1 reporting
# as per NGER (Measurement) Determination 2008 Section 2.23-2.26

DIESEL_CLASSIFICATIONS = {
    'Diesel oil - Site power generation': {
        'purpose': 'electricity',
        'ngers_method': 'Method 1 - Electricity Generation',
        'scope': 1,
        'notes': 'Diesel consumed in stationary generators for on-site electricity production'
    },
    'Diesel oil - Mobile equipment': {
        'purpose': 'stationary',
        'ngers_method': 'Method 1 - Stationary Energy (Off-road)',
        'scope': 1,
        'notes': 'Diesel consumed in mining equipment (haul trucks, loaders, drills, etc.)'
    }
}

# Expected diesel Description values (for validation)
VALID_DIESEL_DESCRIPTIONS = list(DIESEL_CLASSIFICATIONS.keys())

# -----------------------------------------------------------------------------
# ELECTRICITY CLASSIFICATIONS
# -----------------------------------------------------------------------------
# Electricity sources for Scope 1 (site generation) and Scope 2 (grid purchase)

ELECTRICITY_CLASSIFICATIONS = {
    'Grid electricity': {
        'source': 'grid_purchase',
        'scope': 2,
        'notes': 'Electricity purchased from Queensland grid (CS Energy invoices)'
    },
    'Site electricity': {
        'source': 'site_generation',
        'scope': 1,
        'notes': 'Electricity generated on-site from diesel fuel (calculated output in kWh)'
    }
}

# Expected electricity Description values (for validation)
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

# Default fiscal year start month (can be overridden in app)
DEFAULT_FY_START_MONTH = 1   # January = 1, July = 7
NGER_FY_START_MONTH = 7      # NGER/Safeguard always uses July-June FY
# Default year for display in GHG tab
DEFAULT_DISPLAY_YEAR = 2025  # Year to show by default in year selectors


# Common configurations:
# Calendar year (internal reporting): start_month = 1 (January)
# NGER financial year (regulatory):   start_month = 7 (July)
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
        return f"Calendar Year ({start_name}ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â{end_name})"
    elif fy_start_month == 7:
        return f"NGER Financial Year ({start_name}ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â{end_name})"
    else:
        return f"Custom Fiscal Year ({start_name}ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â{end_name})"

# =============================================================================
# SAFEGUARD MECHANISM PARAMETERS
# =============================================================================

# FSEI Factors (CER Approved October 2024)
FSEI_ELEC = 0.9081  # tCO2-e per MWh on-site generation
FSEI_ROM = 0.0177   # tCO2-e per tonne ROM ore

# Baseline decline
DECLINE_RATE = 0.049    # 4.9% p.a.
DECLINE_FROM = 2024     # FY baseline decline starts
DECLINE_TO = 2030       # FY baseline decline ends

# Safeguard Mechanism Credit generation
CREDIT_START_FY = 2024  # First FY credits can be earned (FY2023-24 = 2024 under NGER July-June)

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

# Default phase timing
DEFAULT_END_MINING_FY = 2035
DEFAULT_END_PROCESSING_FY = 2038
DEFAULT_END_REHABILITATION_FY = 2045

# =============================================================================
# PROJECTION DEFAULTS
# =============================================================================

DEFAULT_START_FY = 2023

# Baseline year for projections (last stable operational year)
BASELINE_YEAR = 2024  # FY2024 is the stable baseline (post-expansion, pre-slowdown)

# Projection variability (for realistic year-to-year variation)
PROJECTION_RANDOMNESS = 0.05  # Ã‚Â±5% random variation in projections
RANDOM_SEED_BASE = 42  # Base seed for reproducible randomness

# =============================================================================
# CARBON MARKET DEFAULTS
# =============================================================================

# Carbon Credit Market
DEFAULT_CARBON_CREDIT_PRICE = 35.0  # $/tCOÃƒÂ¢Ã¢â‚¬Å¡Ã¢â‚¬Å¡-e
DEFAULT_CREDIT_ESCALATION = 0.03    # 3% per annum

# Carbon Tax Scenario
DEFAULT_TAX_START_FY = 2030
DEFAULT_TAX_RATE = 15.0             # $/tCOÃƒÂ¢Ã¢â‚¬Å¡Ã¢â‚¬Å¡-e initial rate
DEFAULT_TAX_ESCALATION = 0.02       # 2% per annum

# =============================================================================
# GRID CONNECTION DEFAULTS
# =============================================================================

DEFAULT_GRID_CONNECTION_FY = 2027   # Year grid electricity becomes available (diesel generation stops)
GRID_CONNECTION_MONTH = 7  # Month of grid connection (1-12, 7=July = mid-year for NGER FY)

# =============================================================================
# INDUSTRY BENCHMARKS (from Safeguard Rule)
# =============================================================================

DEFAULT_INDUSTRY_EI_ROM = 0.00859   # Industry default tCOÃƒÂ¢Ã¢â‚¬Å¡Ã¢â‚¬Å¡-e/t ROM
DEFAULT_INDUSTRY_EI_ELEC = 0.539    # Industry default tCOÃƒÂ¢Ã¢â‚¬Å¡Ã¢â‚¬Å¡-e/MWh

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