"""
Config.py
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

import os
import re
from datetime import datetime

from LoaderLom import LOM

# ---------------------------------------------------------------------
# ASSUMPTIONS
# ---------------------------------------------------------------------
# Every rate, threshold and intensity below is read from
# Data/Assumptions.yaml rather than written here.  An assumption in code is
# an assumption nobody finds when it is time to review it, and each of these
# has a source and a review date that belong beside the value.
#
# The names are unchanged, so every module that imports them is unchanged
# too.  What has moved is where the number lives, not what it is called.

import yaml as _yaml

_ASSUMPTIONS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'Data', 'Assumptions.yaml')

with open(_ASSUMPTIONS_PATH, encoding='utf-8') as _handle:
    _ASSUMPTIONS = _yaml.safe_load(_handle)


def _assumption(group, name):
    """One value, or a clear failure.

    A missing assumption is not something to default: a silent zero for a
    decline rate produces a baseline that looks plausible and is wrong.
    """
    try:
        return _ASSUMPTIONS[group][name]
    except KeyError:
        raise KeyError(
            '%s.%s is not in Data/Assumptions.yaml.  Every assumption the '
            'model applies is declared there.' % (group, name))


NGER_FY_START_MONTH = _assumption('reporting', 'NGER_FY_START_MONTH')
DEFAULT_FY_START_MONTH = NGER_FY_START_MONTH
DEFAULT_DISPLAY_YEAR = _assumption('reporting', 'DEFAULT_DISPLAY_YEAR')

FSEI_ELEC = _assumption('facility_intensity', 'FSEI_ELEC')
FSEI_ROM = _assumption('facility_intensity', 'FSEI_ROM')
SITE_GENERATION_RATIO = _assumption('facility_intensity',
                                    'SITE_GENERATION_RATIO')

DEFAULT_INDUSTRY_EI_ROM = _assumption('industry_intensity',
                                      'DEFAULT_INDUSTRY_EI_ROM')
DEFAULT_INDUSTRY_EI_ELEC = _assumption('industry_intensity',
                                       'DEFAULT_INDUSTRY_EI_ELEC')
BEST_PRACTICE_EI_ROM = _assumption('industry_intensity',
                                   'BEST_PRACTICE_EI_ROM')
BEST_PRACTICE_EI_ELEC = _assumption('industry_intensity',
                                    'BEST_PRACTICE_EI_ELEC')

DECLINE_RATE_PHASE1 = _assumption('safeguard', 'DECLINE_RATE_PHASE1')
DECLINE_RATE_PHASE2 = _assumption('safeguard', 'DECLINE_RATE_PHASE2')
DECLINE_PHASE1_START = _assumption('safeguard', 'DECLINE_PHASE1_START')
DECLINE_PHASE1_END = _assumption('safeguard', 'DECLINE_PHASE1_END')
DECLINE_PHASE2_START = _assumption('safeguard', 'DECLINE_PHASE2_START')
DECLINE_PHASE2_END = _assumption('safeguard', 'DECLINE_PHASE2_END')
DECLINE_RATE = DECLINE_RATE_PHASE1
DECLINE_FROM = DECLINE_PHASE1_START
DECLINE_TO = DECLINE_PHASE2_END
SAFEGUARD_THRESHOLD = _assumption('safeguard', 'SAFEGUARD_THRESHOLD')
SAFEGUARD_MINIMUM_BASELINE = _assumption('safeguard',
                                         'SAFEGUARD_MINIMUM_BASELINE')
SAFEGUARD_FINAL_FY = _assumption('safeguard', 'SAFEGUARD_FINAL_FY')

S58B_EARLIEST_FY = _assumption('section_58b', 'S58B_EARLIEST_FY')
S58B_LOOKBACK = _assumption('section_58b', 'S58B_LOOKBACK')
S58B_MIN_COVERED = _assumption('section_58b', 'S58B_MIN_COVERED')

GHG_EXPLOSIVES_EF_T_CO2_PER_T = _assumption(
    'explosives', 'GHG_EXPLOSIVES_EF_T_CO2_PER_T')
GHG_EXPLOSIVES_EF_KG_CO2_PER_KG = _assumption(
    'explosives', 'GHG_EXPLOSIVES_EF_KG_CO2_PER_KG')

DEFAULT_TAX_RATE = _assumption('carbon_market', 'DEFAULT_TAX_RATE')
DEFAULT_TAX_ESCALATION = _assumption('carbon_market', 'DEFAULT_TAX_ESCALATION')
DEFAULT_EF2_DECLINE_RATE = _assumption('carbon_market',
                                       'DEFAULT_EF2_DECLINE_RATE')

# A movement is reported only where the prior period is material against the
# current total.  Below the threshold a percentage swing is arithmetic on
# noise and reads as a finding.
MATERIALITY_THRESHOLD = _assumption('materiality', 'MATERIALITY_THRESHOLD')

WEEKS_PER_YEAR = _assumption('periods', 'WEEKS_PER_YEAR')

GRADE_TOLERANCE = _assumption('verification', 'GRADE_TOLERANCE')
RECOVERY_TOLERANCE = _assumption('verification', 'RECOVERY_TOLERANCE')
THROUGHPUT_TOLERANCE = _assumption('verification', 'THROUGHPUT_TOLERANCE')
RECOVERY_PLAUSIBLE_LOW = _assumption('verification', 'RECOVERY_PLAUSIBLE_LOW')
RECOVERY_PLAUSIBLE_HIGH = _assumption('verification',
                                      'RECOVERY_PLAUSIBLE_HIGH')

IMPORT_SPIKE_MULTIPLE = _assumption('import_checks', 'IMPORT_SPIKE_MULTIPLE')
IMPORT_SPIKE_MINIMUM = _assumption('import_checks', 'IMPORT_SPIKE_MINIMUM')
IMPORT_RESTATE_TOLERANCE = _assumption('import_checks',
                                       'IMPORT_RESTATE_TOLERANCE')

TRANSITION_SCHEDULE = {int(_year): float(_value) for _year, _value
                       in _ASSUMPTIONS['transition_schedule'].items()}



# =============================================================================
# FISCAL YEAR
# =============================================================================


DEFAULT_YEAR_TYPE = 'CY'
DEFAULT_DATA_SOURCE = 'Actual'


# =============================================================================
# SAFEGUARD MECHANISM â€” APPROVED FSEI (CER October 2024)
# =============================================================================
# Per EID Basis of Preparation (Turner & Townsend, Feb 2024)
# Two production variables approved:
#   1. ROM metal ore (tonnes)
#   2. Electricity generation (MWh)


# Industry benchmarks â€” Default EI values from Safeguard Rule Schedule 1
# These are the industry-average emissions intensity values (EI_p in Section 11)
# Used in hybrid baseline blending with FSEI values above
# Confirmed by CER October 2024: existing facilities use Default EI (not Best Practice)

# Best Practice EI (for reference only â€” applies to NEW facilities/products)
# Risk: If EID lapses, existing PVs fall to Best Practice (catastrophic for SMCs)


# =============================================================================
# GRID CONNECTION PARAMETERS
# =============================================================================
# Grid connection transfer is baked into the operations metrics CSVs (1-Jul-2027).
# These constants are retained for metric extraction only.

GRID_SITE_ELEC_DESCRIPTION = 'Site electricity'
GRID_GRID_ELEC_DESCRIPTION = 'Grid electricity'

# Description constants used in Projections.py for metric extraction
DESC_GRID_ELECTRICITY = 'Grid electricity'
DESC_ROM_COSTCENTRE = 'ROM'
DESC_ROM_KEYWORD = 'Ore'

# NGER diesel classification
# Per NGER Measurement Determination 2008, on-site mining equipment is
# stationary energy.  Only road-registered light vehicles are transport.
DIESEL_TRANSPORT_COSTCENTRES = ['Light Vehicles']
DIESEL_TRANSPORT_NGAFUEL = 'Diesel oil-Cars and light commercial vehicles'


# =============================================================================
# SUBACTIVITY-BASED MATCHING KEYS (2026-03 CSV restructure)
# =============================================================================
# The OperationsMetrics CSVs now use Activity/SubActivity instead of embedded
# Description keys.  These constants replace the old CostCentre/Description
# matching patterns used in Projections.py and CalcNga.py.

# ROM ore identification: SubActivity == 'Ore ROM' replaces CostCentre == 'ROM'
ROM_SUBACTIVITY = 'Ore ROM'

# Gold output identification: SubActivity == 'Gold Sold'.
# 'Gold Recovered' exists only in the actuals CSV; the budget CSV carries
# 'Gold Sold' and 'Gold Poured' only.  'Gold Sold' is present in BOTH files
# for the full life of mine, so it is the only denominator that supports an
# intensity series across the whole projection horizon.
GOLD_SUBACTIVITY = 'Gold Sold'

# Electricity identification via CommonName (set by LookupIdentifiers.py)
# Replaces the old Description == 'Site electricity' / 'Grid electricity' pattern
SITE_ELEC_COMMONNAME = 'Site electricity'
GRID_ELEC_COMMONNAME = 'Grid electricity'


# =============================================================================
# SAFEGUARD MECHANISM â€” BASELINE DECLINE (ERC)
# =============================================================================
# ERC = Emissions Reduction Contribution
# Per DCCEEW: "ERC is 0.951 in 2023-24, 0.902 in 2024-25, and so on"
# This is LINEAR subtraction: ERC = 1 - (n x decline_rate)
# where n = FY - 2023 (i.e. n=1 for FY2024, the first reform year)


# FY boundaries for decline phases

# Legacy aliases (used in some older code paths)

# Safeguard thresholds and dates
SAFEGUARD_START_DATE = datetime(2023, 7, 1)

# s10(3): the baseline emissions number is zero for a financial year
# beginning after 30 June 2049.  FY2050 begins on 1 July 2049, so FY2050 is
# the first year that qualifies and the last year carrying a baseline is
# FY2049.  The model horizon reaches this.
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



# =============================================================================
# PHASE TRANSITION DATES
# =============================================================================
# Used for phase LABELS only.  All quantity adjustments (ROM ratios,
# processing ratios, grid connection transfer) are baked into the CSV.

# Data/LOM.yaml is the authority for every milestone.  It is written by hand
# when a new life of mine revision lands and is read by PrepData, the forecast
# engine and this model, so one set of dates governs all three.  The literals
# below are the fallback used only where the file is absent or a key missing,
# and each is annotated with the value LOM Dec25 REV04 carries.

_FALLBACK_START_DATE = datetime(2023, 7, 1)
_FALLBACK_END_MINING_DATE = datetime(2037, 12, 31)          # last ore mined
_FALLBACK_END_PROCESSING_DATE = datetime(2039, 12, 31)      # last ore milled
_FALLBACK_END_REHABILITATION_DATE = datetime(2049, 12, 31)  # reporting horizon
_FALLBACK_GRID_CONNECTION_DATE = datetime(2028, 7, 1)       # site generation ceases

DEFAULT_START_DATE = _FALLBACK_START_DATE
DEFAULT_END_MINING_DATE = LOM.milestone('end_of_mining', _FALLBACK_END_MINING_DATE)
DEFAULT_END_PROCESSING_DATE = LOM.milestone('end_of_processing', _FALLBACK_END_PROCESSING_DATE)
DEFAULT_END_REHABILITATION_DATE = LOM.milestone('end_of_rehabilitation', _FALLBACK_END_REHABILITATION_DATE)
DEFAULT_GRID_CONNECTION_DATE = LOM.milestone('grid_connection', _FALLBACK_GRID_CONNECTION_DATE)

# Boundary between recorded and forecast data.  Used for labelling only; the
# actual/budget precedence rule lives in Projections.build_projection().
DEFAULT_ACTUALS_TO_DATE = LOM.milestone('actuals_to')
DEFAULT_FORECAST_FROM_DATE = LOM.milestone('forecast_from')

# Where the dates in force came from, for the About panel and the sidebar.
MILESTONE_SOURCE = LOM.provenance()


def get_phase_name(date, end_mining_date, end_processing_date,
                   end_rehabilitation_date, grid_connected_date=None):
    """Determine operational phase label for a given date.

    Compares dates directly -- no FY/CY conversion.
    Three phases: Mining, Processing, Rehabilitation.  Grid connection is a
    milestone within mining, not a phase of its own, so it is marked on the
    charts and does not split the phase.  The argument is kept so existing
    call sites read unchanged.
    """
    if date <= end_mining_date:
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
# FACTOR SOURCES
# =============================================================================
# One name per publication.  The same source was being written four ways -
# NgaFactors.csv, National Greenhouse Account Factors, NGA Factors and NGA -
# which makes a factor look like four when it is one, and makes any grouping
# by source wrong.  A source is named once, here, and every consumer uses it.
#
# The scope is not part of a source name.  Which scope a figure is belongs in
# the scope column, and repeating it in the source only creates a second
# place for the two to disagree.

FACTOR_SET_NGA = 'NgaFactors'          # National Greenhouse Account factors
FACTOR_SET_EPA = 'EPA SCEF'            # US EPA supply chain factors
FACTOR_SET_EPA_MARGIN = 'EPA SCEF Margins'
FACTOR_SET_AUSLCI = 'AusLCI'
FACTOR_SET_AGO = 'AGO'
FACTOR_SET_COMPANY = 'Company'         # stated here, from no publication
FACTOR_SET_DEFRA = 'DEFRA'             # UK conversion factors
FACTOR_SET_WORLDSTEEL = 'worldsteel'   # World Steel Association
FACTOR_SET_NONE = ''

FACTOR_SETS = (FACTOR_SET_NGA, FACTOR_SET_EPA, FACTOR_SET_EPA_MARGIN,
               FACTOR_SET_AUSLCI, FACTOR_SET_AGO, FACTOR_SET_DEFRA,
               FACTOR_SET_WORLDSTEEL, FACTOR_SET_COMPANY)


# One level above the source, and a different question.  The source says who
# published a number; the class says who governs it, which is what decides
# whether anybody here may change it and where it is maintained.
#
#   Internal      this company selected it and keeps it current, whoever
#                 published it - a capital band converted from the EPA
#                 factors, the AusLCI explosives factor, a worldsteel steel
#                 figure chosen for grinding media
#   NGA           the National Greenhouse Accounts, used as published
#   Spend-based   the environmentally extended input output database, used
#                 as published, priced per dollar of expenditure
#
# The two questions are recorded separately, so a factor can be Internal by
# governance and worldsteel by publication without either fact being lost.
# Where a factor was published for.  It was carried only for electricity,
# as a state, because that is the one place the Accounts publish it
# explicitly.  Every factor has one: the US EPA supply chain factors are
# published for the United States and say so in their own limitations, the
# National Greenhouse Accounts for Australia, worldsteel for the world.
#
# Written down, the question "is this factor published for where we buy"
# stops being a paragraph in a method document and becomes a column that can
# be counted.  That is the grinding media finding in one field.
REGION_AUSTRALIA = 'Australia'
REGION_USA = 'USA'
REGION_GLOBAL = 'Global'
REGION_UK = 'United Kingdom'
REGION_UNSTATED = ''

# The grids the National Greenhouse Accounts publish separately.  A region
# narrower than a country, and the reason electricity carried a state.
NGA_GRIDS = ('NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'NWIS', 'DKIS',
             'National')

_REGION_BY_SET = {
    'NgaFactors': REGION_AUSTRALIA,
    'EPA SCEF': REGION_USA,
    'EPA SCEF Margins': REGION_USA,
    'AusLCI': REGION_AUSTRALIA,
    'AGO': REGION_AUSTRALIA,
    'DEFRA': REGION_UK,
    'worldsteel': REGION_GLOBAL,
}


def factor_region(source, stated=''):
    """Where a factor was published for.

    A stated region wins, because a company factor is only as good as what
    somebody says about it - a supplier declaration for Chinese media is
    published for China whoever compiled it.  Otherwise it follows the
    publication, which is a property of the publication and not a guess.
    """
    if str(stated or '').strip():
        return str(stated).strip()
    return _REGION_BY_SET.get(factor_set(source), REGION_UNSTATED)


# Class says which publication governs a factor, and that decides whether it
# may be edited.  A factor derived from a publication by a published
# conversion is still that publication's: we choose neither the factor, nor
# the price index, nor the exchange rate, so there is nothing here to defend
# a different value with.  Only our own research is ours to change.
CLASS_INTERNAL = 'Internal'
CLASS_INDUSTRY = 'Industry'
CLASS_NGA = 'NGA'
CLASS_SPEND = 'Spend-based'
FACTOR_CLASSES = (CLASS_NGA, CLASS_SPEND, CLASS_INDUSTRY,
                  CLASS_INTERNAL)

# The only class a person may edit.  Everything else is used as
# published, and shown greyed rather than hidden, because a locked
# figure somebody can still read is what makes the lock credible.
EDITABLE_CLASSES = (CLASS_INTERNAL,)

_SPEND_SETS = (FACTOR_SET_EPA, FACTOR_SET_EPA_MARGIN)

# Two questions, and conflating them loses information.
#
# The publication says where the number came from.  A capital spend band
# comes from the US EPA supply chain factors whether or not somebody here
# converted it to Australian dollars, and a screen that answers "Company"
# has thrown away the provenance an assessor is asking for.
#
# The derivation says what was done to it on the way in.  Published means
# the figure is the publication's own; derived means somebody here converted,
# banded or calibrated it, and that arithmetic is a judgement that has to
# stay maintainable.  Unattributed means no publication was named at all,
# which is a gap rather than a category.
DERIVATION_PUBLISHED = 'Published'
DERIVATION_DERIVED = 'Derived'
DERIVATION_UNATTRIBUTED = 'Unattributed'
DERIVATIONS = (DERIVATION_PUBLISHED, DERIVATION_DERIVED,
               DERIVATION_UNATTRIBUTED)

# Publications relied on as published.  A figure taken verbatim from one of
# these is not the Company's to retype.  Anything derived from one is, whatever
# it was derived from, because the judgement is in the derivation.
REGULATED_SETS = (FACTOR_SET_NGA, FACTOR_SET_EPA, FACTOR_SET_EPA_MARGIN)

# What marks a figure as having been worked on here rather than used as
# published.  Tested before the publication patterns, and independently of
# them, so a derived factor keeps the publication it was derived from.
_DERIVED_PATTERNS = ('band calibrated', 'calibrated', 'screening factor',
                     'derived', 'stated', 'assumed', 'assumption',
                     'estimated here', 'override', 'config')

# Spellings seen in the registers and in code, longest first so a prefix does
# not match before the fuller name does.
_SET_PATTERNS = (
    ('epa scef margins', FACTOR_SET_EPA_MARGIN),
    ('epa scef', FACTOR_SET_EPA),
    ('us epa', FACTOR_SET_EPA),
    ('national greenhouse account', FACTOR_SET_NGA),
    ('ngafactors', FACTOR_SET_NGA),
    ('nga factors', FACTOR_SET_NGA),
    ('nga ', FACTOR_SET_NGA),
    ('nga,', FACTOR_SET_NGA),
    ('auslci', FACTOR_SET_AUSLCI),
    ('worldsteel', FACTOR_SET_WORLDSTEEL),
    ('world steel', FACTOR_SET_WORLDSTEEL),
    ('ago ', FACTOR_SET_AGO),
    ('australian greenhouse office', FACTOR_SET_AGO),
    ('defra', FACTOR_SET_DEFRA),
    ('desnz', FACTOR_SET_DEFRA),
    ('scope3factors.csv', FACTOR_SET_COMPANY),
)


def factor_set(source):
    """Which publication a factor came from, from its source text.

    The publication survives a conversion.  A capital band calibrated from
    the US EPA supply chain factors still came from the US EPA, and saying
    so is the difference between a factor an assessor can trace and one that
    reads as invented here.

    Returns one of FACTOR_SETS, or blank where the source names no
    publication at all.  A blank is a gap to close, not a category.
    """
    text = str(source or '').strip().lower()
    if not text:
        return FACTOR_SET_NONE
    for needle, name in _SET_PATTERNS:
        if needle in text:
            return name
    return FACTOR_SET_COMPANY


def factor_derivation(source):
    """Published as it stands, worked on here, or attributed to nothing."""
    text = str(source or '').strip().lower()
    if not text:
        return DERIVATION_UNATTRIBUTED
    for needle in _DERIVED_PATTERNS:
        if needle in text:
            return DERIVATION_DERIVED
    if factor_set(text) in (FACTOR_SET_NONE, FACTOR_SET_COMPANY):
        return DERIVATION_UNATTRIBUTED
    return DERIVATION_PUBLISHED


def factor_class(source):
    """Which of the three families a factor belongs to.

    A factor used as its publisher issued it belongs to that publisher's
    family.  Anything converted, banded, calibrated or simply chosen here is
    this company's to keep current, whatever it was derived from.
    """
    publication = factor_set(source)
    if factor_derivation(source) != DERIVATION_PUBLISHED:
        return CLASS_INTERNAL
    if publication == FACTOR_SET_NGA:
        return CLASS_NGA
    if publication in _SPEND_SETS:
        return CLASS_SPEND
    return CLASS_INTERNAL


# How a source string carries a publication and a name in one field.  Both
# separators appear in the registers; the em dash is the EPA convention and
# the comma everything else.
_NAME_SEPARATORS = (' \u2014 ', ' - ', ', ')


def factor_name(source, fallback=''):
    """The factor's own name, with the publication taken off the front.

    "EPA SCEF - Iron Foundries" is a publication and a name in one field, and
    reading it as either alone loses half of it.  Where the string carries no
    name of its own - the capital bands all cite the same publication and
    differ only in the figure - the fallback is used, which is the asset
    class or the product group the row already names.
    """
    text = str(source or '').strip()
    if not text:
        return str(fallback or '').strip()
    publication = factor_set(text)
    for separator in _NAME_SEPARATORS:
        if separator in text:
            head, tail = text.split(separator, 1)
            if publication and factor_set(head) == publication:
                return tail.strip()
    return str(fallback or '').strip() or text


def factor_is_regulated(source):
    """Whether a factor stands as published and is not the Company's to edit.

    Both halves matter.  A figure derived from a regulated publication is
    the Company's own arithmetic and has to stay maintainable, and a figure
    attributed to nothing is a gap that somebody has to be able to fill.
    """
    return (factor_set(source) in REGULATED_SETS
            and factor_derivation(source) == DERIVATION_PUBLISHED)


# Scope qualifiers that some sources carried.  Removed on read: the scope is
# in the scope column.
_SCOPE_NOISE = (', scope 3', ', scope 1', ', scope 2', ' scope 3', ' scope 1',
                ' scope 2')


def canonical_factor_source(source):
    """A source string written the one way, with the scope taken out."""
    text = str(source or '').strip()
    if not text:
        return ''
    # A file extension is not part of a source's name.  Which file a factor
    # is stored in is an implementation detail; what the reader wants is the
    # publication.
    text = re.sub(r'\.csv\b', '', text, flags=re.IGNORECASE).strip()
    lowered = text.lower()
    for noise in _SCOPE_NOISE:
        if lowered.endswith(noise):
            text = text[:len(text) - len(noise)].rstrip(' ,')
            lowered = text.lower()
    # A source that is only the publication is written as the publication.
    for needle, name in (('national greenhouse account factors', FACTOR_SET_NGA),
                         ('ngafactors.csv', FACTOR_SET_NGA),
                         ('nga factors', FACTOR_SET_NGA),
                         ('nga', FACTOR_SET_NGA)):
        if lowered == needle:
            return name
    # Otherwise keep the detail, but write the publication part one way.
    for old, new in (('NgaFactors.csv', FACTOR_SET_NGA),
                     ('National Greenhouse Account Factors', FACTOR_SET_NGA),
                     ('NGA Factors', FACTOR_SET_NGA),
                     ('NGA \u2014 ', FACTOR_SET_NGA + ', '),
                     ('NGA - ', FACTOR_SET_NGA + ', ')):
        if text.startswith(old):
            text = new + text[len(old):]
            break
    return text.strip().rstrip(',').strip()


# =============================================================================
# REPORTING UNIT RECONCILIATION
# =============================================================================
# The physicals carry each line in the unit it is actually reported in, which
# is not always the unit the NGA factor is published against.  PrepData moved
# six lines to a smaller unit in August 2026 because the quantity they carry
# was unreadable in the larger one; greases went from kL to L and greases are
# the only one of the six with an NGA factor.
#
# The factor is published per kL, so a litre quantity charged against it
# overstates the line a thousandfold.  These conversions reconcile the two.
# Every entry is an exact definition, not an assumption: a litre is a
# thousandth of a kilolitre and a cubic metre is a kilolitre.
#
# Key is (unit in the data, unit the factor expects); value multiplies the
# quantity.  A pair that is not here raises rather than converting on a guess.

# =============================================================================
# REPORTING UNIT RECONCILIATION
# =============================================================================
# Units are defined in one place, CalcUnits.py, and converted there.  Nothing
# in this file, or anywhere else in the model, defines a unit or a conversion
# of its own.  The names below are aliases so existing call sites read
# unchanged.
#
#   UOM_SYNONYMS      spelling.  Two ways of writing one unit, so the
#                     quantity is untouched.
#   UOM_CONVERSIONS   arithmetic.  Derived from the unit table, so a
#                     conversion and its inverse cannot disagree.

from CalcUnits import SYNONYMS as UOM_SYNONYMS
from CalcUnits import conversion_pairs as _conversion_pairs

UOM_CONVERSIONS = _conversion_pairs()


# =============================================================================
# GHG PROTOCOL — EXPLOSIVES (NOT NGER)
# =============================================================================

# GHG Protocol Scope 1 emission factor for ANFO detonation.
# Source: AGO / Dept of Climate Change, NGA Factors (0.17 t CO2/t ANFO).
# Pending confirmation against current NGA publication year.
#
# NGER treatment: NOT reportable (CER guideline s2.7, July 2025).
# Fuel oil component reported as consumed without combustion by Orica
# (operational control at point of final mixing, NGER Measurement
# Determination s2.68).
#
# Contracted blasting (Orica detonates on site) means under GHG Protocol
# operational control approach these are Scope 3 for this facility.
# However, many Australian mining companies report ANFO detonation as
# Scope 1 in GHG/GRI disclosures using AGO methods (precedent: Balmoral
# South Iron Ore Project GHG Assessment, Kewan Bond 2008).
# =============================================================================
# DEPARTMENT NAMES
# =============================================================================
# The chart of accounts writes the mining department three ways and the
# processing department two, so a grouping by department splits one operation
# across several rows and every total has to be added up by eye.  There is one
# mining operation and it is called Mining.
#
# Matching against the chart of accounts still accepts every spelling; only
# what is reported is settled here.

DEPARTMENT_ALIASES = {
    'Mining Open Pit': 'Mining',
    'Open Pit': 'Mining',
    'Mining - Open Pit': 'Mining',
    '40 - Processing': 'Processing',
    'Admin': 'Commercial & Administration',
    'HST': 'Health, Safety and Training',
}


def canonical_department(name):
    """The department as it is reported, whatever the ledger called it."""
    if name is None:
        return name
    text = str(name).strip()
    return DEPARTMENT_ALIASES.get(text, text)


GHG_EXPLOSIVES_SOURCE = 'AGO 2004, Table 11, ANFO detonation'


# =============================================================================
# CARBON MARKET DEFAULTS
# =============================================================================

DEFAULT_CARBON_CREDIT_PRICE = 35.0
DEFAULT_CREDIT_ESCALATION = 0.03

DEFAULT_TAX_START_DATE = datetime(2029, 7, 1)


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
    'actual': 'OperationsMetricsActual.csv',
    'budget': 'OperationsMetricsBudget.csv',
    'nga': 'Data/NgaSource/NationalGreenhouseAccountFactors2026.xlsx',
}