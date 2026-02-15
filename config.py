"""
config.py
Configuration constants for Ravenswood Gold emissions model
Last updated: 2026-02-12

Contains:
    Safeguard Mechanism parameters (FSEI, decline rates, thresholds)
    Hybrid EI transition schedule (Section 11)
    s58B opt-in eligibility parameters
    Phase date boundaries (for labelling only â€” multipliers baked into CSV)
    Grid connection parameters
    Carbon market defaults
    Colour palette
    Cost centre category map

Safeguard Mechanism baseline formula per Section 11:
    Baseline = ERC Ã— Î£p [(h Ã— EI_p + (1âˆ’h) Ã— EIF_p) Ã— Q_p] + BA
    Where:
        ERC  = Emissions Reduction Contribution (linear decline)
        h    = Transition proportion (Default EI weighting, increases yearly)
        EI_p = Default (industry-average) emissions intensity
        EIF_p = Facility-specific emissions intensity (from EID)
        Q_p  = Production quantity
        BA   = Borrowing Adjustment (zero for Ravenswood)
"""

from datetime import datetime


# =============================================================================
# FISCAL YEAR
# =============================================================================

NGER_FY_START_MONTH = 7       # July start for NGER reporting
DEFAULT_FY_START_MONTH = NGER_FY_START_MONTH

DEFAULT_DISPLAY_YEAR = 2025
DEFAULT_YEAR_TYPE = 'CY'
DEFAULT_DATA_SOURCE = 'Actual'


# =============================================================================
# SAFEGUARD MECHANISM â€” APPROVED FSEI (CER October 2024)
# =============================================================================
# Per EID Basis of Preparation (Turner & Townsend, Feb 2024)
# Two production variables approved:
#   1. ROM metal ore (tonnes)
#   2. Electricity generation (MWh)

FSEI_ELEC = 0.9081            # tCO2-e/MWh site generation (EIF_p for electricity)
FSEI_ROM = 0.0177             # tCO2-e/t ROM (EIF_p for ROM metal ore)
SITE_GENERATION_RATIO = 0.008735  # MWh/t ROM (8.735 kWh/t)

# Industry benchmarks â€” Default EI values from Safeguard Rule Schedule 1
# These are the industry-average emissions intensity values (EI_p in Section 11)
# Used in hybrid baseline blending with FSEI values above
# Confirmed by CER October 2024: existing facilities use Default EI (not Best Practice)
DEFAULT_INDUSTRY_EI_ROM = 0.00859   # tCO2-e/t ROM (industry average)
DEFAULT_INDUSTRY_EI_ELEC = 0.539    # tCO2-e/MWh (industry average)

# Best Practice EI (for reference only â€” applies to NEW facilities/products)
# Risk: If EID lapses, existing PVs fall to Best Practice (catastrophic for SMCs)
BEST_PRACTICE_EI_ROM = 0.00247     # tCO2-e/t ROM
BEST_PRACTICE_EI_ELEC = 0.236      # tCO2-e/MWh


# =============================================================================
# GRID CONNECTION PARAMETERS
# =============================================================================
# Grid connection transfer is baked into the consolidated CSV (1-Jul-2027).
# These constants are retained for metric extraction only.

GRID_SITE_ELEC_DESCRIPTION = 'Site electricity'
GRID_GRID_ELEC_DESCRIPTION = 'Grid electricity'

# Description constants used in projections.py for metric extraction
DESC_GRID_ELECTRICITY = 'Grid electricity'
DESC_ROM_COSTCENTRE = 'ROM'
DESC_ROM_KEYWORD = 'Ore'

# NGER diesel classification
# Per NGER Measurement Determination 2008, on-site mining equipment is
# stationary energy.  Only road-registered light vehicles are transport.
DIESEL_TRANSPORT_COSTCENTRES = ['Light Vehicles']
DIESEL_TRANSPORT_NGAFUEL = 'Diesel oil-Cars and light commercial vehicles'


# =============================================================================
# SAFEGUARD MECHANISM â€” BASELINE DECLINE (ERC)
# =============================================================================
# ERC = Emissions Reduction Contribution
# Per DCCEEW: "ERC is 0.951 in 2023-24, 0.902 in 2024-25, and so on"
# This is LINEAR subtraction: ERC = 1 - (n x decline_rate)
# where n = FY - 2023 (i.e. n=1 for FY2024, the first reform year)

DECLINE_RATE_PHASE1 = 0.049   # 4.9% p.a. (FY2024-FY2030) â€” legislated
DECLINE_RATE_PHASE2 = 0.03285 # 3.285% p.a. (FY2031-FY2050) â€” indicative

# FY boundaries for decline phases
DECLINE_PHASE1_START = 2024   # First FY with ERC < 1.0
DECLINE_PHASE1_END = 2030     # Last FY of Phase 1
DECLINE_PHASE2_START = 2031
DECLINE_PHASE2_END = 2050

# Legacy aliases (used in some older code paths)
DECLINE_RATE = DECLINE_RATE_PHASE1
DECLINE_FROM = DECLINE_PHASE1_START
DECLINE_TO = DECLINE_PHASE2_END

# Safeguard thresholds and dates
SAFEGUARD_THRESHOLD = 100000          # tCO2-e facility threshold
SAFEGUARD_MINIMUM_BASELINE = 100000   # tCO2-e minimum baseline floor (CER rule)
SAFEGUARD_START_DATE = datetime(2023, 7, 1)
SAFEGUARD_DATE = datetime(2023, 7, 1)
CREDIT_START_DATE = datetime(2023, 7, 1)
# SMC_EXIT_PERIOD_YEARS removed - s58B lookback replaces hardcoded timer


# =============================================================================
# HYBRID EI TRANSITION SCHEDULE (Section 11)
# =============================================================================
# Per Safeguard Rule Section 11, the transition proportion 'h' determines
# the weighting between Default (industry-average) and Facility-specific EI.
#
# Formula: Hybrid_EI = h x Default_EI + (1-h) x FSEI
#
# h increases each year, shifting from FSEI toward Default EI.
# Per CER: transition increases from 10% per year to 20% from FY2027-28.

TRANSITION_SCHEDULE = {
    2024: 0.10,   # FY2023-24:  10% Default, 90% FSEI
    2025: 0.20,   # FY2024-25:  20% Default, 80% FSEI
    2026: 0.30,   # FY2025-26:  30% Default, 70% FSEI
    2027: 0.40,   # FY2026-27:  40% Default, 60% FSEI
    2028: 0.60,   # FY2027-28:  60% Default, 40% FSEI  (step-up to 20%/yr)
    2029: 0.80,   # FY2028-29:  80% Default, 20% FSEI
    2030: 1.00,   # FY2029-30: 100% Default,  0% FSEI
}


def get_transition_proportion(fy):
    """Get the transition proportion (h) for a given financial year.

    Returns the Default EI weighting for the hybrid baseline calculation.
    Before FY2024: h=0 (pure FSEI, pre-reform)
    FY2024-FY2030: per legislated schedule
    After FY2030: h=1.0 (pure Default EI)
    """
    if fy < DECLINE_PHASE1_START:
        return 0.0
    elif fy in TRANSITION_SCHEDULE:
        return TRANSITION_SCHEDULE[fy]
    else:
        return 1.0


# =============================================================================
# s58B OPT-IN ELIGIBILITY PARAMETERS
# =============================================================================
# Per Safeguard Mechanism Rule 2015 s58B(2)
# Two conditions for below-threshold facilities to opt in:
#   1. Date gate: FY must begin after 30 June 2028 (earliest = FY2029)
#   2. Coverage history: facility covered >= 3 of previous 5 FYs

S58B_EARLIEST_FY = 2029
S58B_LOOKBACK = 5
S58B_MIN_COVERED = 3


# =============================================================================
# PHASE TRANSITION DATES
# =============================================================================
# Used for phase LABELS only.  All quantity adjustments (ROM ratios,
# processing ratios, grid connection transfer) are baked into the CSV.

DEFAULT_START_DATE = datetime(2023, 7, 1)
DEFAULT_END_MINING_DATE = datetime(2037, 3, 31)          # Last day of mining operations
DEFAULT_END_PROCESSING_DATE = datetime(2039, 12, 31)     # Last day of processing operations
DEFAULT_END_REHABILITATION_DATE = datetime(2044, 12, 31)  # Last day of rehabilitation
DEFAULT_GRID_CONNECTION_DATE = datetime(2027, 7, 1)


def get_phase_name(date, end_mining_date, end_processing_date,
                   end_rehabilitation_date, grid_connected_date=None):
    """Determine operational phase label for a given date.

    Compares dates directly -- no FY/CY conversion.
    Returns phase name string for display purposes.
    """
    if date <= end_mining_date:
        if grid_connected_date is not None and date >= grid_connected_date:
            return 'Mining (Grid)'
        return 'Mining'
    elif date <= end_processing_date:
        return 'Processing'
    elif date <= end_rehabilitation_date:
        return 'Rehabilitation'
    else:
        return 'Closed'


def get_phase_name_for_date(date, end_mining_date, end_processing_date,
                            end_rehabilitation_date, grid_connected_date):
    """Date-based phase label.  Direct date comparison, no FY conversion."""
    return get_phase_name(date, end_mining_date, end_processing_date,
                          end_rehabilitation_date, grid_connected_date)


# =============================================================================
# CARBON MARKET DEFAULTS
# =============================================================================

DEFAULT_CARBON_CREDIT_PRICE = 35.0
DEFAULT_CREDIT_ESCALATION = 0.03

DEFAULT_TAX_START_DATE = datetime(2029, 7, 1)
DEFAULT_TAX_RATE = 15.0
DEFAULT_TAX_ESCALATION = 0.02


# =============================================================================
# COST CENTRE CATEGORY MAP (display grouping)
# =============================================================================

CATEGORY_MAP = {
    'Supplemental Power Supply': 'Power',
    'Site Power Generation': 'Power',
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
    'NPE Dredge': 'Mining',
    'Projects and Work Orders': 'Fixed',
    'Brisbane Office': 'Admin',
    'Residential': 'Admin',
    'Stuart Office': 'Admin',
    'Suhrs Creek Rd': 'Admin',
}


# =============================================================================
# COLOUR PALETTE
# =============================================================================

# Gold theme (primary â€” used in Tabs 1â€“3)
GOLD_METALLIC = '#DBB12A'
BRIGHT_GOLD = '#E8AC41'
DARK_GOLDENROD = '#AE8B0F'
SEPIA = '#734B1A'
CAFE_NOIR = '#39250B'
GRID_GREEN = '#2A9D8F'
BASELINE_BLACK = '#000000'

# Legacy palette (Tab 4 and export)
COLORS = {
    'scope1': '#2C3E50',
    'scope2': '#3498DB',
    'scope3': '#95A5A6',
    'actual_intensity': '#E74C3C',
    'baseline': '#34495E',
    'power': '#F39C12',
    'mining': '#E67E22',
    'processing': '#16A085',
    'fixed': '#7F8C8D',
    'credits': '#27AE60',
    'deficit': '#C0392B',
    'tax': '#C0392B',
    'rom': '#95A5A6',
    'smc': '#27AE60',
    'base': '#2C3E50',
    'npi': '#3498DB',
}


# =============================================================================
# FILE PATHS
# =============================================================================

DEFAULT_PATHS = {
    'consolidated': 'consolidated_emissions_data.csv',
    'nga': 'national-greenhouse-account-factors-2025.xlsx',
}