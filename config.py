"""
config.py
Configuration constants and mappings for Ravenswood Gold emissions model
Last updated: 2026-01-12 07:30 AEST
"""

import pandas as pd

# =============================================================================
# FINANCIAL YEAR DEFINITION
# =============================================================================

# Default fiscal year start month (can be overridden in app)
DEFAULT_FY_START_MONTH = 1   # January = 1, July = 7

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
        return f"Calendar Year ({start_name}–{end_name})"
    elif fy_start_month == 7:
        return f"NGER Financial Year ({start_name}–{end_name})"
    else:
        return f"Custom Fiscal Year ({start_name}–{end_name})"

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

# =============================================================================
# PRODUCTION ASSUMPTIONS
# =============================================================================

BASE_MWH = 108000        # Annual on-site generation (MWh) - pre-grid
POST_GRID_MWH = 18000    # Residual on-site generation post-grid (MWh)
GRID_PURCHASE_MWH = 90000  # Grid electricity purchased post-grid (MWh)
PRE_GRID_SCOPE2_MWH = 3000  # Existing grid purchase

# Maturity cutoff
MATURITY_CUTOFF = pd.Timestamp('2023-08-01')

# =============================================================================
# COST CENTRE MAPPINGS
# =============================================================================

# Display category grouping
CATEGORY_MAP = {
    'Supplemental Power Supply': 'Power',
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
}

# NGER purpose classification (determines emission factor table)
NGER_PURPOSE_MAP = {
    'Supplemental Power Supply': 'electricity',
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

DEFAULT_START_FY = 2021

# =============================================================================
# CARBON MARKET DEFAULTS
# =============================================================================

# Carbon Credit Market
DEFAULT_CARBON_CREDIT_PRICE = 35.0  # $/tCOâ‚‚-e
DEFAULT_CREDIT_ESCALATION = 0.03    # 3% per annum

# Carbon Tax Scenario
DEFAULT_TAX_START_FY = 2030
DEFAULT_TAX_RATE = 15.0             # $/tCOâ‚‚-e initial rate
DEFAULT_TAX_ESCALATION = 0.02       # 2% per annum

# =============================================================================
# GRID CONNECTION DEFAULTS
# =============================================================================

DEFAULT_GRID_CONNECTION_FY = 2027   # Year grid electricity becomes available (diesel generation stops)

# =============================================================================
# INDUSTRY BENCHMARKS (from Safeguard Rule)
# =============================================================================

DEFAULT_INDUSTRY_EI_ROM = 0.00859   # Industry default tCOâ‚‚-e/t ROM
DEFAULT_INDUSTRY_EI_ELEC = 0.539    # Industry default tCOâ‚‚-e/MWh

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
}

# Phase 2: Processing Only (after End of Mining, before End of Processing)
# Mining operations cease, processing continues with rehabilitation
PHASE_PROCESSING = {
    'Supplemental Power Supply': 1.00,  # Continue power generation
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
}

# Phase profile lookup
PHASE_PROFILES = {
    'mining': PHASE_MINING,
    'processing': PHASE_PROCESSING,
    'rehabilitation': PHASE_REHABILITATION,
}

def get_phase_profile(fy, end_mining_fy, end_processing_fy, end_rehabilitation_fy):
    """Determine operational phase and return activity profile

    Args:
        fy: Financial year
        end_mining_fy: Last year of mining operations
        end_processing_fy: Last year of processing operations
        end_rehabilitation_fy: Last year of rehabilitation

    Returns:
        Tuple of (phase_name, profile_dict, is_active)
        - phase_name: 'mining', 'processing', 'rehabilitation', or 'closed'
        - profile_dict: Cost centre activity multipliers
        - is_active: Boolean indicating if facility is operational
    """
    if fy <= end_mining_fy:
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
# COLOR PALETTE - Professional Corporate
# =============================================================================

COLORS = {
    'scope1': '#2C3E50',          # Navy blue - direct emissions
    'scope2': '#3498DB',          # Medium blue - indirect (purchased)
    'scope3': '#95A5A6',          # Light gray - value chain
    'actual_intensity': '#E74C3C', # Red - performance metric
    'baseline': '#34495E',        # Dark gray - reference standard
    'power': '#F39C12',           # Amber - power generation
    'mining': '#E67E22',          # Orange - mining operations
    'processing': '#16A085',      # Teal - processing
    'fixed': '#7F8C8D',           # Gray - fixed/admin
    'credits': '#27AE60',         # Green - positive credits
    'deficit': '#C0392B',         # Dark red - deficit
    'rom': '#95A5A6',             # Light gray - production
}

# =============================================================================
# SCOPE NAMING CONVENTIONS
# =============================================================================

SCOPE_NAMES = {
    'scope1': 'Scope 1 (Direct)',
    'scope2': 'Scope 2 (Indirect)',
    'scope3': 'Scope 3 (Value Chain)',
}

# =============================================================================
# FILE PATHS
# =============================================================================

DEFAULT_PATHS = {
    'energy': 'Energy.csv',
    'rom': 'ROM.csv',
    'nga': 'national-greenhouse-account-factors-2025.xlsx'
}