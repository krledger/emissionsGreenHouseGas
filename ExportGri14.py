"""
ExportGri14.py
GRI 14 Mining Sector Disclosure flat-file export

Generates a structured CSV/XLSX databook mapping Ravenswood Gold emissions
data to GRI 14 (Mining Sector 2024) quantitative disclosure requirements.

Architecture:
    - Hardcoded disclosure map defines every quantitative GRI 14 item
    - Extraction functions pull calculated values from PrecomputedData
    - Outputs a flat file with one row per disclosure per reporting year
    - Coverage report summarises auto/collectible/N-A status

Data sources mapped:
    Scope 1/2/3 totals ........... gri_annual, calendar year (CalcGri)
    Gas-by-gas CO2/CH4/N2O ....... NGA individual gas EFs x fuel quantities
    Energy (GJ) by fuel type ..... gri_source, recorded months (CalcGri)
    Electricity (kWh -> GJ) ...... gri_annual Site/Grid kWh
    ROM ore (t) .................. gri_annual ROM_t
    Milled tonnes ................ raw df (Description == 'Milled Tonnes')
    Gold production (oz) ......... raw df (Description == 'Gold Recovered oz')
    Emission intensity ........... gri_annual Scope1 / ROM_t
    SMC issuances/sales/surrenders SmcTransactions.csv
    Energy intensity ............. total Energy_GJ / ROM_t

14.5 Waste (Limited):
    Rock waste (t, BCM) ............. OperationsMetricsActual Ore Waste
    Tailings (t, approx) ........... derived from milled tonnes
    Strip ratio .................... waste rock / ROM ore

Additional reagents (GRI 301-1):
    Carbon, Leach aid, Antiscalant, Soda ash, Sodium chlorite,
    Sodium hypochlorite, Dust suppressant

Additional production:
    Gold sold (oz), Gold intensity (tCO2-e/oz), Drilling (m)

Coverage flag:
    Auto    = fully calculated from available data
    Limited = partial data; user should source remaining items externally

Disclosures NOT populated (require separate data sources):
    14.3 Air emissions (NOx, SOx, PM etc) ... needs NPI data
    14.4 Biodiversity (Ha) .................. needs land management system
    14.5 Non-mineral waste .................. needs waste tracking register
    14.7 Water (ML) ......................... needs water balance model
    14.8 Closure ($AUD, Ha) ................. needs closure cost model

Last updated: 2026-05-12
"""

import pandas as pd

import Paths as _PATHS
import numpy as np
from typing import Optional, Dict, Any, List

from CalcUnits import UnitError, factor as uom_factor, GJ_PER_KWH
from CalcCalendar import period_filter, year_to_date_range, date_to_fy

# ─────────────────────────────────────────────────────────────────────
# DATE-RANGE LOOKUP HELPERS
# ─────────────────────────────────────────────────────────────────────
# annual tables have a 'Date' column from the Grouper index.
# _period_row filters by date range instead of FY label.

def _period_row(annual_df, start_date, end_date):
    """Return annual_df row(s) whose Date falls within [start_date, end_date).

    The annual tables produced by aggregate_by_year_type() have a 'Date'
    column that holds the period-start timestamp from the Grouper.
    Returns filtered DataFrame (may be empty).
    """
    if annual_df is None or len(annual_df) == 0:
        return pd.DataFrame()
    if 'Date' in annual_df.columns:
        return period_filter(annual_df, start_date, end_date, date_col='Date')
    # Fallback: derive FY from the date range and match on label
    fy_int = date_to_fy(start_date + (end_date - start_date) / 2)
    result = annual_df[annual_df['FY'] == fy_int]
    if not result.empty:
        return result
    result = annual_df[annual_df['FY'] == f'FY{fy_int}']
    if not result.empty:
        return result
    result = annual_df[annual_df['FY'] == f'CY{fy_int}']
    return result


def _gri_annual(precomputed):
    """The calendar year totals this export reads: its own frame (CalcGri).

    Never a Safeguard or NGER frame.  Those are financial year frames for the
    regulator and are the wrong period and the wrong boundary for GRI.
    """
    return getattr(precomputed, 'gri_annual', pd.DataFrame())


def _gri_source_rows(precomputed, start_date, end_date):
    """Recorded emission sources inside the period, from the GRI source frame.

    Half-open on the end date, as every period in this export is.  Returns an
    empty frame where the build carries no GRI source.
    """
    src = getattr(precomputed, 'gri_source', None)
    if src is None or len(src) == 0:
        return pd.DataFrame()
    dates = pd.to_datetime(src['Date'])
    return src[(dates >= pd.Timestamp(start_date))
               & (dates < pd.Timestamp(end_date))]


def _date_range_to_fy(start_date, end_date):
    """Derive the integer FY from a date range (for FY-based lookups).

    Uses the start date of the range to determine the FY.  This gives
    the correct result for both FY and CY ranges:
        FY2024 (2023-07-01, 2024-07-01) -> date_to_fy(2023-07-01) = 2024
        CY2024 (2024-01-01, 2025-01-01) -> date_to_fy(2024-01-01) = 2024
    """
    return date_to_fy(start_date)




# ─────────────────────────────────────────────────────────────────────
# GRI 14 QUANTITATIVE DISCLOSURE MAP
# ─────────────────────────────────────────────────────────────────────
# Each entry is one row in the output.  'calc_fn' names a function
# in _CALC_FN_MAP that returns a value given (precomputed, start_date, end_date, raw_df).

GRI14_QUANTITATIVE_MAP = [

    # ── SCOPE 1 GHG EMISSIONS ────────────────────────────────────────

    {'id': 'scope1_total',      'gri_ref': '102-5a',       'section': 'Scope 1 GHG Emissions',
     'description': 'Gross Scope 1 GHG emissions',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope1_total'},

    {'id': 'scope1_co2',        'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - CO2 component',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope1_gas', 'calc_args': {'gas': 'CO2'}},

    {'id': 'scope1_ch4',        'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - CH4 component',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope1_gas', 'calc_args': {'gas': 'CH4'}},

    {'id': 'scope1_n2o',        'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - N2O component',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope1_gas', 'calc_args': {'gas': 'N2O'}},

    # Biogenic carbon dioxide is reported separately and is not part of the
    # gross Scope 1 figure above.  The facility has no material biogenic
    # source, but the disclosure requires the nil to be stated rather than
    # left out.
    {'id': 'scope1_biogenic',   'gri_ref': '102-5c', 'section': 'Scope 1 GHG Emissions',
     'description': 'Biogenic CO2, reported separately from gross Scope 1',
     'unit': 'tCO2-e', 'calc_fn': '_get_zero'},

    {'id': 'scope1_hfcs',       'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - HFCs',
     'unit': 'tCO2-e', 'calc_fn': '_get_zero'},  # No HFC sources

    {'id': 'scope1_pfcs',       'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - PFCs',
     'unit': 'tCO2-e', 'calc_fn': '_get_zero'},

    {'id': 'scope1_sf6',        'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - SF6',
     'unit': 'tCO2-e', 'calc_fn': '_get_zero'},

    {'id': 'scope1_nf3',        'gri_ref': '102-5b',       'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1  - NF3',
     'unit': 'tCO2-e', 'calc_fn': '_get_zero'},

    {'id': 'scope1_site',       'gri_ref': '102-5a (site)','section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1 by mine site (Ravenswood  - single facility)',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope1_total'},

    # ── SCOPE 2 GHG EMISSIONS ────────────────────────────────────────

    {'id': 'scope2_total',      'gri_ref': '102-6a',       'section': 'Scope 2 GHG Emissions',
     'description': 'Gross location-based Scope 2 GHG emissions',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope2_total'},

    {'id': 'scope2_site',       'gri_ref': '102-6a (site)','section': 'Scope 2 GHG Emissions',
     'description': 'Scope 2 by mine site (Ravenswood  - single facility)',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope2_total'},

    # ── SCOPE 3 GHG EMISSIONS ────────────────────────────────────────

    {'id': 'scope3_total',      'gri_ref': '102-7a',       'section': 'Scope 3 GHG Emissions',
     'description': 'Gross Scope 3 GHG emissions, all fifteen categories',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_total'},

    # The disclosure requires the categories included in the measure to be
    # stated.  Each is published as its own line, so a reader sees which
    # categories carry a figure and which are nil, rather than a total alone.
    {'id': 'scope3_cat1',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 1  - Purchased goods and services',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 1}},

    {'id': 'scope3_cat2',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 2  - Capital goods',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 2}},

    {'id': 'scope3_cat3',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 3  - Fuel and energy related activities',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 3}},

    {'id': 'scope3_cat4',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 4  - Upstream transportation and distribution',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 4}},

    {'id': 'scope3_cat5',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 5  - Waste generated in operations',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 5}},

    {'id': 'scope3_cat6',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 6  - Business travel',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 6}},

    {'id': 'scope3_cat7',       'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 7  - Employee commuting',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 7}},

    {'id': 'scope3_cat10',      'gri_ref': '102-7b',       'section': 'Scope 3 GHG Emissions',
     'description': 'Category 10  - Processing of sold products',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_category', 'calc_args': {'category': 10}},

    {'id': 'scope3_categories',  'gri_ref': '102-7b',      'section': 'Scope 3 GHG Emissions',
     'description': 'Categories carrying a figure (of fifteen considered)',
     'unit': 'count', 'calc_fn': '_get_scope3_category_count'},

    # ── EMISSIONS INTENSITY ──────────────────────────────────────────

    {'id': 'ei_scope1_rom',     'gri_ref': '102-8a',       'section': 'GHG Emissions intensity',
     'description': 'Scope 1 emissions intensity (tCO2-e per tonne ROM ore)',
     'unit': 'tCO2-e/t ROM', 'calc_fn': '_get_emission_intensity'},

    {'id': 'rom_total',         'gri_ref': '102-8b',       'section': 'GHG Emissions intensity',
     'description': 'Total ROM ore mined (intensity denominator)',
     'unit': 't', 'calc_fn': '_get_rom_tonnes'},

    {'id': 'energy_intensity',  'gri_ref': '103-4a',       'section': 'Energy intensity',
     'description': 'Energy intensity (GJ per tonne ROM ore)',
     'unit': 'GJ/t ROM', 'calc_fn': '_get_energy_intensity'},

    # ── CARBON CREDITS (SMC) ─────────────────────────────────────────

    {'id': 'smc_issued',        'gri_ref': '102-10a',      'section': 'Carbon credits',
     'description': 'SMC credits issued by CER',
     'unit': 'tCO2-e', 'calc_fn': '_get_smc_by_type', 'calc_args': {'txn_type': 'Issuance'}},

    {'id': 'smc_surrendered',   'gri_ref': '102-10a',      'section': 'Carbon credits',
     'description': 'SMC credits surrendered / cancelled',
     'unit': 'tCO2-e', 'calc_fn': '_get_smc_by_type', 'calc_args': {'txn_type': 'Surrender'}},

    {'id': 'smc_sold',          'gri_ref': '102-10a',      'section': 'Carbon credits',
     'description': 'SMC credits sold / transferred',
     'unit': 'tCO2-e', 'calc_fn': '_get_smc_by_type', 'calc_args': {'txn_type': 'Sale'}},

    # ── ENERGY CONSUMPTION ───────────────────────────────────────────

    {'id': 'fuel_total_gj',     'gri_ref': '103-2a',       'section': 'Energy consumption',
     'description': 'Total fuel consumption within the organisation',
     'unit': 'GJ', 'calc_fn': '_get_total_fuel_gj'},

    {'id': 'fuel_nonrenew_gj',  'gri_ref': '103-2a-i',     'section': 'Energy consumption',
     'description': 'Non-renewable fuel consumption (all fuel is non-renewable)',
     'unit': 'GJ', 'calc_fn': '_get_total_fuel_gj'},

    {'id': 'fuel_renew_gj',     'gri_ref': '103-2a-i',     'section': 'Energy consumption',
     'description': 'Renewable fuel consumption',
     'unit': 'GJ', 'calc_fn': '_get_zero'},

    {'id': 'fuel_diesel_stat_gj', 'gri_ref': '103-2a-ii', 'section': 'Energy consumption',
     'description': 'Diesel  - stationary (mining, processing, power gen)',
     'unit': 'GJ', 'calc_fn': '_get_fuel_gj_by_nga',
     'calc_args': {'nga_prefix': 'Diesel oil', 'exclude_prefix': 'Diesel oil-Cars'}},

    {'id': 'fuel_diesel_transport_gj', 'gri_ref': '103-2a-ii', 'section': 'Energy consumption',
     'description': 'Diesel  - transport (light vehicles)',
     'unit': 'GJ', 'calc_fn': '_get_fuel_gj_by_nga',
     'calc_args': {'nga_prefix': 'Diesel oil-Cars'}},

    {'id': 'fuel_lpg_gj',      'gri_ref': '103-2a-ii',    'section': 'Energy consumption',
     'description': 'LPG (bulk liquid + cylinders)',
     'unit': 'GJ', 'calc_fn': '_get_fuel_gj_by_nga',
     'calc_args': {'nga_prefix': 'Liquefied petroleum gas'}},

    {'id': 'fuel_gas_gj',      'gri_ref': '103-2a-ii',    'section': 'Energy consumption',
     'description': 'Gaseous fossil fuels (acetylene)',
     'unit': 'GJ', 'calc_fn': '_get_fuel_gj_by_nga',
     'calc_args': {'nga_prefix': 'Gaseous fossil fuels'}},

    {'id': 'fuel_oils_gj',     'gri_ref': '103-2a-ii',    'section': 'Energy consumption',
     'description': 'Petroleum based oils (engine, gear, hydraulic, transmission)',
     'unit': 'GJ', 'calc_fn': '_get_fuel_gj_by_nga',
     'calc_args': {'nga_prefix': 'Petroleum based oils'}},

    {'id': 'fuel_greases_gj',  'gri_ref': '103-2a-ii',    'section': 'Energy consumption',
     'description': 'Petroleum based greases',
     'unit': 'GJ', 'calc_fn': '_get_fuel_gj_by_nga',
     'calc_args': {'nga_prefix': 'Petroleum based greases'}},

    {'id': 'elec_grid_gj',     'gri_ref': '103-2b',       'section': 'Energy consumption',
     'description': 'Purchased grid electricity',
     'unit': 'GJ', 'calc_fn': '_get_grid_electricity_gj'},

    {'id': 'elec_grid_kwh',    'gri_ref': '103-2b',       'section': 'Energy consumption',
     'description': 'Purchased grid electricity (kWh)',
     'unit': 'kWh', 'calc_fn': '_get_grid_electricity_kwh'},

    {'id': 'elec_site_gj',     'gri_ref': '103-2c',       'section': 'Energy consumption',
     'description': 'Self-generated electricity (diesel generation)',
     'unit': 'GJ', 'calc_fn': '_get_site_electricity_gj'},

    {'id': 'elec_site_kwh',    'gri_ref': '103-2c',       'section': 'Energy consumption',
     'description': 'Self-generated electricity (kWh)',
     'unit': 'kWh', 'calc_fn': '_get_site_electricity_kwh'},

    {'id': 'elec_sold_gj',     'gri_ref': '103-2d',       'section': 'Energy consumption',
     'description': 'Electricity sold (nil  - no export)',
     'unit': 'GJ', 'calc_fn': '_get_zero'},

    # ── PRODUCTION METRICS (useful context for intensity ratios) ─────

    {'id': 'milled_tonnes',    'gri_ref': 'context',       'section': 'Production metrics',
     'description': 'Milled tonnes (ore processed through mill)',
     'unit': 't', 'calc_fn': '_get_production_metric',
     'calc_args': {'common_name': 'Ore milled', 'row_types': ['total'], 'uom': 't'}},

    {'id': 'gold_recovered',   'gri_ref': 'context',       'section': 'Production metrics',
     'description': 'Gold recovered',
     'unit': 'oz', 'calc_fn': '_get_production_metric',
     'calc_args': {'common_name': 'Gold recovered', 'row_types': ['production'], 'uom': 'oz'}},

    # -- GRI CONSUMABLES (from consolidated_emissions_data.csv ReportingCategory='GRI') --

    {'id': 'cyanide_kg',       'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Sodium cyanide consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Cyanide', 'row_types': ['consumption'], 'uom': 'kg'}},

    {'id': 'quicklime_t',      'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Quicklime consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Lime', 'row_types': ['consumption'], 'uom': 't'}},

    {'id': 'grinding_media_t', 'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Grinding media consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Grinding media', 'row_types': ['consumption'], 'uom': 't'}},

    {'id': 'caustic_kg',       'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Caustic soda consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Caustic soda', 'row_types': ['consumption'], 'uom': 'kg'}},

    {'id': 'hcl_kg',           'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Hydrochloric acid consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Hydrochloric acid', 'row_types': ['consumption'], 'uom': 'kg'}},

    {'id': 'oxygen_m3',        'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Liquid oxygen consumption',
     'unit': 'm3', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Liquid oxygen', 'row_types': ['consumption'], 'uom': 'm3'}},

    {'id': 'flocculant_kg',    'gri_ref': '301-1a', 'section': 'Reagents and consumables',
     'description': 'Flocculant consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Flocculant', 'row_types': ['consumption'], 'uom': 'kg'}},

    {'id': 'tyres_each',       'gri_ref': '301-1a',           'section': 'Wear items',
     'description': 'Tyres consumed',
     'unit': 'each', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Tyres', 'row_types': ['consumption'], 'uom': 'each'}},

    {'id': 'explosives_kg',    'gri_ref': '301-1a',           'section': 'Wear items',
     'description': 'Explosives consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Explosives', 'row_types': ['consumption'], 'uom': 'kg'}},

    # ── ADDITIONAL REAGENTS / CONSUMABLES (GRI 301-1 Materials used) ───

    {'id': 'carbon_t',        'gri_ref': '301-1a',            'section': 'Reagents and consumables',
     'description': 'Activated carbon consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Activated carbon', 'row_types': ['consumption'], 'uom': 't'},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'leach_aid_t',     'gri_ref': '301-1a',            'section': 'Reagents and consumables',
     'description': 'Leach aid consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Leach aid', 'row_types': ['consumption'], 'uom': 't'},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'antiscalant_t',   'gri_ref': '301-1a',            'section': 'Reagents and consumables',
     'description': 'Antiscalant consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Antiscalant', 'row_types': ['consumption'], 'uom': 't'},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'soda_ash_t',      'gri_ref': '301-1a',            'section': 'Reagents and consumables',
     'description': 'Soda ash consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Soda ash', 'row_types': ['consumption'], 'uom': 't'},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'sodium_chlorite_t','gri_ref': '301-1a',           'section': 'Reagents and consumables',
     'description': 'Sodium chlorite consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Sodium chlorite', 'row_types': ['consumption'], 'uom': 't'},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'sodium_hypochlorite_kl', 'gri_ref': '301-1a',     'section': 'Reagents and consumables',
     'description': 'Sodium hypochlorite consumption',
     'unit': 'kL', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Sodium hypochlorite', 'row_types': ['consumption'], 'uom': 'kL'},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'dust_suppressant_kl', 'gri_ref': '301-1a',        'section': 'Reagents and consumables',
     'description': 'Dust suppressant consumption',
     'unit': 'kL', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Dust suppressant', 'row_types': ['consumption'], 'uom': 'kL'},
     'gri_topic': '14.1 Climate Change'},

    # ── EMISSION INTENSITY - GOLD (sector benchmark) ──────────────────

    {'id': 'ei_scope1_gold',  'gri_ref': '102-8a',           'section': 'GHG Emissions intensity',
     'description': 'Scope 1 emissions intensity (tCO2-e per oz gold recovered)',
     'unit': 'tCO2-e/oz', 'calc_fn': '_get_emission_intensity_gold',
     'gri_topic': '14.1 Climate Change'},

    {'id': 'gold_sold_oz',    'gri_ref': 'context',           'section': 'Production metrics',
     'description': 'Gold sold',
     'unit': 'oz', 'calc_fn': '_get_production_metric',
     'calc_args': {'common_name': 'Gold sold', 'row_types': ['production'], 'uom': 'oz'},
     'gri_topic': '14.1 Climate Change'},

    # ── 14.5 WASTE (Limited - rock waste from operations data) ────────

    # 306-3 asks for total waste generated and a breakdown by composition.
    # Rock waste and tailings are the two streams GRI 14 names for this
    # sector, both come from the monthly operating report, and both are
    # therefore reported inside the total rather than beside it.
    {'id': 'waste_total_t',   'gri_ref': '306-3a',            'section': 'Waste - total',
     'description': 'Total waste generated (rock waste plus tailings)',
     'unit': 't', 'calc_fn': '_get_waste_total',
     'gri_topic': '14.5 Waste', 'coverage': 'Full'},

    {'id': 'waste_rock_t',    'gri_ref': '306-3a',            'section': 'Waste - rock waste',
     'description': 'Waste rock moved',
     'unit': 't', 'calc_fn': '_get_ore_waste',
     'calc_args': {'uom': 't'},
     'gri_topic': '14.5 Waste', 'coverage': 'Full'},

    {'id': 'waste_rock_bcm',  'gri_ref': '306-3a',            'section': 'Waste - rock waste',
     'description': 'Waste rock moved (bank cubic metres)',
     'unit': 'BCM', 'calc_fn': '_get_ore_waste',
     'calc_args': {'uom': 'BCM'},
     'gri_topic': '14.5 Waste', 'coverage': 'Full'},

    {'id': 'tailings_approx_t','gri_ref': '306-3a',           'section': 'Waste - tailings',
     'description': 'Tailings produced (approx: milled tonnes less gold recovered)',
     'unit': 't', 'calc_fn': '_get_tailings_approx',
     'gri_topic': '14.5 Waste', 'coverage': 'Full'},

    {'id': 'strip_ratio',     'gri_ref': 'sector rec.',       'section': 'Waste - rock waste',
     'description': 'Strip ratio (waste rock t / ROM ore t)',
     'unit': 'ratio', 'calc_fn': '_get_strip_ratio',
     'gri_topic': '14.5 Waste', 'coverage': 'Full'},

    # ── 14.8 CLOSURE (Limited - LOM from budget projections) ──────────

    {'id': 'drilling_m',      'gri_ref': 'context',            'section': 'Production metrics',
     'description': 'Total drilling metres',
     'unit': 'm', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Drilling', 'row_types': ['production'], 'uom': 'm'},
     'gri_topic': '14.1 Climate Change'},
]


# ─────────────────────────────────────────────────────────────────────
# NGA INDIVIDUAL GAS EMISSION FACTORS (kgCO2-e/GJ)
# ─────────────────────────────────────────────────────────────────────
# Source: NGA 2025, Table 8 (liquid fuels), Table 3/5 (gaseous fuels)
# Gas-by-gas EFs loaded from NgaFactors.csv (CO2, CH4, N2O columns).
# These are read once and cached.  Falls back to zeros if columns
# are missing (backward compatible with pre-2026 NgaFactors.csv).

_NGA_GAS_CACHE = None

def _load_nga_gas_split():
    """Load per-gas emission factors from NgaFactors.csv.

    Returns dict: {(fuel_name, nga_year): {'CO2': x, 'CH4': y, 'N2O': z}}
    Only Scope 1 rows have gas split data.
    """
    global _NGA_GAS_CACHE
    if _NGA_GAS_CACHE is not None:
        return _NGA_GAS_CACHE

    import os
    csv_path = _PATHS.data('NgaFactors.csv')
    if not os.path.exists(csv_path):
        _NGA_GAS_CACHE = {}
        return _NGA_GAS_CACHE
    ndf = pd.read_csv(csv_path)
    cache = {}

    s1 = ndf[ndf['Scope'] == 1]
    for _, row in s1.iterrows():
        fuel = str(row['Fuel_Name'])
        year = int(row['NGA_Year'])
        co2 = float(row['EF_CO2_kgCO2e_per_GJ']) if pd.notna(row.get('EF_CO2_kgCO2e_per_GJ')) else 0.0
        ch4 = float(row['EF_CH4_kgCO2e_per_GJ']) if pd.notna(row.get('EF_CH4_kgCO2e_per_GJ')) else 0.0
        n2o = float(row['EF_N2O_kgCO2e_per_GJ']) if pd.notna(row.get('EF_N2O_kgCO2e_per_GJ')) else 0.0
        cache[(fuel, year)] = {'CO2': co2, 'CH4': ch4, 'N2O': n2o}

    _NGA_GAS_CACHE = cache
    return _NGA_GAS_CACHE


def _get_gas_ef(nga_fuel, gas, nga_year=None):
    """Get individual gas EF (kgCO2-e/GJ) for a fuel.

    Looks up by exact fuel name first, then by prefix match.
    If nga_year is None, uses the latest available year.
    Returns 0.0 if not found.
    """
    cache = _load_nga_gas_split()
    if not cache:
        return 0.0

    if nga_year is None:
        years = set(y for (_, y) in cache.keys())
        nga_year = max(years) if years else 2025

    # Exact match
    key = (nga_fuel, nga_year)
    if key in cache:
        return cache[key].get(gas, 0.0)

    # Prefix match (longest first)
    best_match = None
    best_len = 0
    for (fuel, year), factors in cache.items():
        if year == nga_year and nga_fuel.startswith(fuel) and len(fuel) > best_len:
            best_match = factors
            best_len = len(fuel)

    if best_match:
        return best_match.get(gas, 0.0)

    return 0.0


# ─────────────────────────────────────────────────────────────────────
# VALUE EXTRACTION FUNCTIONS
# ─────────────────────────────────────────────────────────────────────

def _get_scope1_total(precomputed, start_date, end_date, raw_df=None, **kw):
    """Gross Scope 1 tCO2-e for the given period."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    val = float(row['Scope1'].iloc[0])
    return round(val, 2) if val > 0 else None


def _get_scope2_total(precomputed, start_date, end_date, raw_df=None, **kw):
    """Gross location-based Scope 2 tCO2-e."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    val = float(row['Scope2'].iloc[0])
    return round(val, 2) if val > 0 else None


def _get_scope3_total(precomputed, start_date, end_date, raw_df=None, **kw):
    """Gross Scope 3 tCO2-e, every category.

    The disclosure is gross Scope 3, which means all fifteen GHG Protocol
    categories and not the fuel and energy related coefficients alone.  The
    annual frame carries both: Scope3 is Category 3 on its own, and
    Scope3_Total is Category 3 plus the other fourteen.  Prefer the total and
    fall back only where the Scope 3 build did not run, so a partial figure is
    never published as a gross one.
    """
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    column = 'Scope3_Total' if 'Scope3_Total' in row.columns else 'Scope3'
    val = float(row[column].iloc[0])
    return round(val, 2) if val > 0 else None


def _get_scope3_category(precomputed, start_date, end_date, raw_df=None,
                         category=None, **kw):
    """One Scope 3 category for the period.

    The disclosure requires the categories included in the measure to be
    stated, not only the total, so each category is published as its own line
    and the reader can see which carry a figure and which are nil.
    """
    result = getattr(precomputed, 'scope3', None)
    if result is None or category is None:
        return None
    detail = getattr(result, 'detail', None)
    if detail is None or detail.empty:
        return None
    # period_filter is the half-open window the rest of this module uses.  A
    # closed window here pulls in the first day of the next period, and the
    # categories then do not sum to the total.
    rows = period_filter(detail, start_date, end_date, date_col='Date')
    rows = rows[rows['Category'] == category]
    if rows.empty:
        return None
    val = float(rows['tCO2e'].sum())
    return round(val, 2) if val > 0 else None


def _get_scope3_category_count(precomputed, start_date, end_date, raw_df=None, **kw):
    """How many of the fifteen categories carry a figure for the period."""
    result = getattr(precomputed, 'scope3', None)
    if result is None:
        return None
    detail = getattr(result, 'detail', None)
    if detail is None or detail.empty:
        return None
    rows = period_filter(detail, start_date, end_date, date_col='Date')
    if rows.empty:
        return None
    carrying = rows.groupby('Category', observed=True)['tCO2e'].sum()
    return int((carrying > 0).sum())


def _get_scope1_gas(precomputed, start_date, end_date, raw_df=None, gas='CO2', **kw):
    """Scope 1 split by individual greenhouse gas (CO2, CH4, N2O).

    Method: For each fuel type, take the Energy_GJ total for the period,
    multiply by the gas-specific EF (kgCO2-e/GJ), convert to tCO2-e.
    This reproduces the NGA Method 1 calculation at gas level.

    tCO2-e(gas) = sum over fuels [ Energy_GJ * EF_gas(kgCO2-e/GJ) / 1000 ]

    Source: the GRI source frame (CalcGri), recorded rows inside the period.
    """
    rows = _gri_source_rows(precomputed, start_date, end_date)
    if rows.empty:
        return None

    total = 0.0
    for _, row in rows.iterrows():
        nga_fuel = str(row['NGAFuel'])
        # Detonation of explosives is carbon dioxide and has no energy
        # content, so it is taken as recorded and counted under CO2 only.
        if nga_fuel == 'Explosives':
            if gas == 'CO2':
                total += float(row['Scope1_tCO2e'])
            continue
        energy_gj = float(row['Energy_GJ'])
        if energy_gj <= 0:
            continue

        # Look up gas-specific EF from NgaFactors.csv
        ef_gas = _get_gas_ef(nga_fuel, gas)
        if ef_gas == 0.0 and gas == 'CO2':
            continue  # No data for this fuel
        total += energy_gj * ef_gas / 1000.0

    return round(total, 2) if total > 0 else 0.0


def _get_emission_intensity(precomputed, start_date, end_date, raw_df=None, **kw):
    """Scope 1 emissions intensity: tCO2-e per tonne ROM ore."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    rom_t = float(row['ROM_t'].iloc[0])
    s1 = float(row['Scope1'].iloc[0])
    if rom_t <= 0 or s1 <= 0:
        return None
    return round(s1 / rom_t, 6)


def _get_energy_intensity(precomputed, start_date, end_date, raw_df=None, **kw):
    """Energy intensity: total fuel GJ per tonne ROM ore."""
    rom_t = _get_rom_tonnes(precomputed, start_date, end_date, **kw)
    fuel_gj = _get_total_fuel_gj(precomputed, start_date, end_date)
    if rom_t is None or fuel_gj is None or rom_t <= 0:
        return None
    return round(fuel_gj / rom_t, 6)


def _get_rom_tonnes(precomputed, start_date, end_date, raw_df=None, **kw):
    """Total ROM ore tonnes."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    val = float(row['ROM_t'].iloc[0])
    return round(val, 0) if val > 0 else None


def _get_smc_by_type(precomputed, start_date, end_date, raw_df=None, txn_type='Issuance', **kw):
    """SMC transaction quantity by type for the given period.

    Types: 'Issuance', 'Sale', 'Surrender'
    Sales are stored as negative quantities in the CSV.
    Returns absolute value for reporting purposes.

    SMC transactions use Applies_To_FY (always FY-based per legislation)
    so we derive the FY from the date range for lookup.
    """
    smc = precomputed.smc_transactions
    if smc.empty:
        return None
    fy = _date_range_to_fy(start_date, end_date)
    mask = (smc['Type'] == txn_type) & (smc['Applies_To_FY'] == fy)
    if not mask.any():
        return None
    val = float(smc.loc[mask, 'Quantity'].sum())
    return round(abs(val), 0) if val != 0 else None


def _get_total_fuel_gj(precomputed, start_date, end_date, raw_df=None, **kw):
    """Total fuel energy consumption in GJ (excludes electricity).

    Source: the GRI source frame (CalcGri), calendar period.
    """
    rows = _gri_source_rows(precomputed, start_date, end_date)
    if rows.empty:
        return None
    val = float(rows['Energy_GJ'].sum())
    return round(val, 2) if val > 0 else None


def _get_fuel_gj_by_nga(precomputed, start_date, end_date, raw_df=None, nga_prefix='', exclude_prefix='', **kw):
    """Energy GJ for a specific NGAFuel prefix.

    Source: the GRI source frame (CalcGri), calendar period.

    Args:
        nga_prefix: NGAFuel must start with this string.
        exclude_prefix: If set, exclude rows whose NGAFuel starts with this
                        (e.g. exclude 'Diesel oil-Cars' from 'Diesel oil' to
                        get stationary diesel only).
    """
    src = _gri_source_rows(precomputed, start_date, end_date)
    if src.empty:
        return None
    mask = src['NGAFuel'].astype(str).str.startswith(nga_prefix)
    if exclude_prefix:
        mask = mask & (~src['NGAFuel'].astype(str).str.startswith(exclude_prefix))
    if not mask.any():
        return None
    val = float(src.loc[mask, 'Energy_GJ'].sum())
    return round(val, 2) if val > 0 else None


def _get_grid_electricity_gj(precomputed, start_date, end_date, raw_df=None, **kw):
    """Purchased grid electricity in GJ.  1 kWh = 0.0036 GJ."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    kwh = float(row['Grid_Electricity_kWh'].iloc[0])
    return round(kwh * GJ_PER_KWH, 2) if kwh > 0 else None


def _get_grid_electricity_kwh(precomputed, start_date, end_date, raw_df=None, **kw):
    """Purchased grid electricity in kWh."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    val = float(row['Grid_Electricity_kWh'].iloc[0])
    return round(val, 0) if val > 0 else None


def _get_site_electricity_gj(precomputed, start_date, end_date, raw_df=None, **kw):
    """Self-generated electricity in GJ."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    kwh = float(row['Site_Electricity_kWh'].iloc[0])
    return round(kwh * GJ_PER_KWH, 2) if kwh > 0 else None


def _get_site_electricity_kwh(precomputed, start_date, end_date, raw_df=None, **kw):
    """Self-generated electricity in kWh."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    val = float(row['Site_Electricity_kWh'].iloc[0])
    return round(val, 0) if val > 0 else None


# ---------------------------------------------------------------------
# UNIT GUARD
# ---------------------------------------------------------------------

def _finalise(value):
    """Round a disclosure value, and report nothing rather than a nil."""
    if value is None:
        return None
    return round(value, 2) if abs(value) > 0.001 else None


def _sum_in_uom(frame, mask, to_uom, label):
    """Total the matched rows in the unit the disclosure is published in.

    A GRI figure carries a unit, and the physicals carry their own.  Cyanide
    is recorded in tonnes and the disclosure is in kilograms; summing the
    quantity and printing it as kilograms understates it a thousandfold.  Each
    row is therefore carried to the reporting unit before it is added.

    Conversion comes from CalcUnits, the one place units are defined.  A row
    whose unit cannot be carried to the reporting unit is reported and left
    out: that is a count against a mass, or a stores line that has taken the
    name of a mapped line, and it must not be added in either case.
    """
    import logging

    if not mask.any():
        return None

    rows = frame.loc[mask]
    if not to_uom or 'UOM' not in rows.columns:
        return float(rows['Quantity'].sum())

    total = 0.0
    excluded = {}
    for unit, group in rows.groupby(rows['UOM'].astype(str), observed=True):
        try:
            total += float(group['Quantity'].sum()) * uom_factor(unit, to_uom)
        except UnitError:
            excluded[unit] = int(len(group))

    if excluded:
        logging.getLogger(__name__).warning(
            f"GRI '{label}' is reported in '{to_uom}' and matched rows in "
            f"{excluded} that cannot be carried to it.  Those rows are "
            f"excluded."
        )
    return total


def _get_production_metric(precomputed, start_date, end_date, raw_df=None, common_name='', row_types=None, desc='', uom='', **kw):
    """Production quantity from raw data by CommonName.

    Used for Ore milled, Gold recovered, Gold sold, etc.
    These are not in the precomputed annual tables so we need raw_df.

    Falls back to Description match if CommonName column is not present.
    Uses date-range filtering on raw_df (which has a Date column).

    Args:
        common_name: CommonName value to match (preferred)
        row_types:   List of RowType values to include (e.g. ['total'] for
                     Ore milled total, ['production'] for Gold recovered)
        desc:        Legacy Description match (fallback only)
    """
    if raw_df is None:
        return None

    # Date-range filter first
    filtered = period_filter(raw_df, start_date, end_date)

    # Prefer CommonName if the column exists and a value was provided
    if common_name and 'CommonName' in filtered.columns:
        mask = (
            (filtered['DataSet'] == 'Actual')
            & (filtered['CommonName'].astype(str) == common_name)
        )
        if row_types and 'RowType' in filtered.columns:
            mask = mask & (filtered['RowType'].astype(str).isin(row_types))
        return _finalise(_sum_in_uom(filtered, mask, uom, common_name))

    # Fallback: match by Description (legacy behaviour)
    lookup = desc if desc else common_name
    mask = (
        (filtered['DataSet'] == 'Actual')
        & (filtered['Description'].astype(str) == lookup)
    )
    if not mask.any():
        return None
    val = float(filtered.loc[mask, 'Quantity'].sum())
    return round(val, 0) if val > 0 else None


def _get_gri_consumable(precomputed, start_date, end_date, raw_df=None, common_name='', row_types=None, desc='', uom='', **kw):
    """Get GRI consumable quantity from raw data using CommonName.

    Matches rows by CommonName (normalised grouping key) rather than
    Description, so variant descriptions (e.g. 'Explosives Loaded - BRW')
    are correctly captured alongside the base description.

    Optionally filters by RowType to distinguish consumption vs purchased
    vs detail rows.  Defaults to 'consumption' if row_types is not specified.

    Falls back to Description match if CommonName column is not present
    (backward compatibility with pre-CommonName CSVs).

    Uses date-range filtering on raw_df (which has a Date column).

    Args:
        common_name: CommonName value to match (preferred)
        row_types:   List of RowType values to include.  Default ['consumption']
        desc:        Legacy Description match (fallback only)
    """
    if raw_df is None:
        return None

    # Date-range filter first
    filtered = period_filter(raw_df, start_date, end_date)

    # Prefer CommonName if the column exists and a value was provided
    if common_name and 'CommonName' in filtered.columns:
        mask = (
            (filtered['DataSet'] == 'Actual')
            & (filtered['CommonName'].astype(str) == common_name)
        )
        # Filter by RowType if available
        if row_types and 'RowType' in filtered.columns:
            mask = mask & (filtered['RowType'].astype(str).isin(row_types))
        return _finalise(_sum_in_uom(filtered, mask, uom, common_name))
    else:
        # Fallback: match by Description (legacy behaviour)
        lookup = desc if desc else common_name
        mask = (
            (filtered['DataSet'] == 'Actual')
            & (filtered['Description'].astype(str) == lookup)
        )

    return _finalise(_sum_in_uom(filtered, mask, uom, common_name or desc))


def _get_emission_intensity_gold(precomputed, start_date, end_date, raw_df=None, **kw):
    """Scope 1 emissions intensity: tCO2-e per troy ounce gold recovered."""
    row = _period_row(kw.get('annual_df', _gri_annual(precomputed)), start_date, end_date)
    if row.empty:
        return None
    s1 = float(row['Scope1'].iloc[0])
    gold_oz = _get_production_metric(precomputed, start_date, end_date, raw_df=raw_df,
                                      common_name='Gold recovered', row_types=['production'])
    if gold_oz is None or gold_oz <= 0 or s1 <= 0:
        return None
    return round(s1 / gold_oz, 4)


def _get_ore_waste(precomputed, start_date, end_date, raw_df=None, uom='t', **kw):
    """Ore waste quantity for the given period, filtered by UOM (t or BCM).

    Waste rock is reported in both tonnes and BCM depending on the
    measurement method.  Returns the total for the requested UOM only.
    Uses date-range filtering on raw_df.
    """
    if raw_df is None:
        return None
    filtered = period_filter(raw_df, start_date, end_date)
    mask = (
        (filtered['DataSet'] == 'Actual')
        & (filtered['SubActivity'].astype(str) == 'Ore Waste')
        & (filtered['UOM'].astype(str) == uom)
    )
    if not mask.any():
        return None
    val = float(filtered.loc[mask, 'Quantity'].sum())
    return round(val, 0) if val > 0 else None


def _get_tailings_approx(precomputed, start_date, end_date, raw_df=None, **kw):
    """Approximate tailings tonnage: milled tonnes less gold recovered.

    Almost all milled material reports to tailings.  Gold recovery
    is negligible by mass but included for completeness.
    """
    milled = _get_production_metric(precomputed, start_date, end_date, raw_df=raw_df,
                                     common_name='Ore milled', row_types=['total'])
    if milled is None or milled <= 0:
        return None
    # Gold is in oz, ~31.1g/oz - negligible relative to milled tonnes
    return round(milled, 0)


def _get_waste_total(precomputed, start_date, end_date, raw_df=None, **kw):
    """Total waste generated, being rock waste plus tailings.

    306-3 asks for a total and a breakdown by composition.  The two streams
    below are the breakdown; this is the total they sum to, so the disclosure
    is complete rather than a pair of loose lines.  Both streams come from the
    monthly operating report.

    Process residue retained on site is reported here.  Whether it is waste
    "transferred for treatment" is a separate question the Company answers in
    its contextual disclosure under 306-3(b); it is not a reason to leave the
    tonnage out of the total.
    """
    rock = _get_ore_waste(precomputed, start_date, end_date, raw_df=raw_df,
                          uom='t')
    tails = _get_tailings_approx(precomputed, start_date, end_date,
                                 raw_df=raw_df)
    if rock is None and tails is None:
        return None
    return round((rock or 0.0) + (tails or 0.0), 2)


def _get_strip_ratio(precomputed, start_date, end_date, raw_df=None, **kw):
    """Strip ratio: waste rock tonnes / ROM ore tonnes."""
    waste_t = _get_ore_waste(precomputed, start_date, end_date, raw_df=raw_df, uom='t')
    rom_t = _get_rom_tonnes(precomputed, start_date, end_date, **kw)
    if waste_t is None or rom_t is None or rom_t <= 0:
        return None
    return round(waste_t / rom_t, 2)


def _get_zero(precomputed, start_date, end_date, raw_df=None, **kw):
    """Return 0.0 for disclosures that are definitively zero."""
    return 0.0


# ── Function dispatch table ──────────────────────────────────────────

_CALC_FN_MAP = {
    '_get_scope1_total':          _get_scope1_total,
    '_get_scope2_total':          _get_scope2_total,
    '_get_scope3_total':          _get_scope3_total,
    '_get_scope3_category':       _get_scope3_category,
    '_get_scope3_category_count': _get_scope3_category_count,
    '_get_scope1_gas':            _get_scope1_gas,
    '_get_emission_intensity':    _get_emission_intensity,
    '_get_energy_intensity':      _get_energy_intensity,
    '_get_rom_tonnes':            _get_rom_tonnes,
    '_get_smc_by_type':           _get_smc_by_type,
    '_get_total_fuel_gj':         _get_total_fuel_gj,
    '_get_fuel_gj_by_nga':        _get_fuel_gj_by_nga,
    '_get_grid_electricity_gj':   _get_grid_electricity_gj,
    '_get_grid_electricity_kwh':  _get_grid_electricity_kwh,
    '_get_site_electricity_gj':   _get_site_electricity_gj,
    '_get_site_electricity_kwh':  _get_site_electricity_kwh,
    '_get_production_metric':     _get_production_metric,
    '_get_gri_consumable':        _get_gri_consumable,
    '_get_emission_intensity_gold': _get_emission_intensity_gold,
    '_get_ore_waste':             _get_ore_waste,
    '_get_tailings_approx':       _get_tailings_approx,
    '_get_waste_total':           _get_waste_total,
    '_get_strip_ratio':           _get_strip_ratio,
    '_get_zero':                  _get_zero,
}


# ─────────────────────────────────────────────────────────────────────
# METHODOLOGY NOTES
# ─────────────────────────────────────────────────────────────────────

_METHODOLOGY = {
    'scope1_total':       'NGER Method 1: Quantity x NGA EF (kgCO2-e/unit) / 1000.  Fuels: diesel, LPG, petroleum oils/greases, acetylene.  NGA factors per DCCEEW annual publication.',
    'scope1_co2':         'CO2 component: Energy_GJ x gas-specific EF (kgCO2-e/GJ) / 1000 per fuel.  Gas EFs from NGA Table 8 (liquid) / Table 3 (gaseous).',
    'scope1_ch4':         'CH4 component: Energy_GJ x CH4 EF (kgCO2-e/GJ) / 1000 per fuel.  Expressed as CO2-equivalent using AR5 GWP100.',
    'scope1_n2o':         'N2O component: Energy_GJ x N2O EF (kgCO2-e/GJ) / 1000 per fuel.  Expressed as CO2-equivalent using AR5 GWP100.',
    'scope1_hfcs':        'No HFC sources at Ravenswood Gold Mine.',
    'scope1_pfcs':        'No PFC sources at Ravenswood Gold Mine.',
    'scope1_sf6':         'No SF6 sources at Ravenswood Gold Mine.',
    'scope1_nf3':         'No NF3 sources at Ravenswood Gold Mine.',
    'scope1_site':        'Single facility.  Site total = facility total.',
    'scope2_total':       'Location-based: Grid kWh x NGA Scope 2 EF for QLD (kgCO2-e/kWh) / 1000.',
    'scope2_site':        'Single facility.  Location-based method, QLD grid factor.',
    'scope3_total':       'Gross Scope 3, all fifteen GHG Protocol categories: Category 3 from NGA indirect factors and grid transmission and distribution losses, plus the other fourteen from CalcGhgCategories.  See Documentation/Scope3Method.md.',
    'scope3_categories':  'Count of the fifteen categories carrying a figure for the period.  Every category is considered; those reporting nil are stated with their reason in Documentation/Scope3Method.md.',
    'scope1_biogenic':    'Biogenic CO2 is reported separately and is not included in gross Scope 1.  The facility has no material biogenic source, so the figure is nil, stated rather than omitted.',
    'ei_scope1_rom':      'Scope 1 tCO2-e / ROM ore tonnes.  Operational control boundary.',
    'rom_total':          'Sum of all ROM ore grades (HG, MG, LG, VLG) from BRW and SARS beneficiation streams.',
    'energy_intensity':   'Total fuel Energy_GJ / ROM ore tonnes.  Excludes electricity.',
    'smc_issued':         'CER registry issuance (SmcTransactions.csv).  Issuances lag the reporting FY.',
    'smc_surrendered':    'CER registry surrender for compliance.',
    'smc_sold':           'CER registry transfer/sale.  Absolute value of negative quantity.',
    'fuel_total_gj':      'Sum of Energy_GJ across all fuel types.  Energy content from NGA factors (GJ per native unit).',
    'fuel_nonrenew_gj':   'All fuel at Ravenswood is non-renewable (diesel, LPG, petroleum products, acetylene).',
    'fuel_renew_gj':      'No renewable fuel sources at Ravenswood.',
    'fuel_diesel_stat_gj':'Diesel (stationary + power gen) x NGA energy content (38.6 GJ/kL).  Excludes light vehicle transport diesel.',
    'fuel_diesel_transport_gj': 'Diesel  - light vehicles only (NGER transport classification).  NGA energy content 38.6 GJ/kL.',
    'fuel_lpg_gj':        'LPG (bulk + cylinders) x NGA energy content (25.7 GJ/kL).',
    'fuel_gas_gj':        'Acetylene gas x NGA energy content.',
    'fuel_oils_gj':       'Engine, gear, hydraulic, transmission oil x NGA energy content (38.8 GJ/kL).',
    'fuel_greases_gj':    'Petroleum grease x NGA energy content (38.8 GJ/kL).',
    'elec_grid_gj':       'Grid kWh x 0.0036 GJ/kWh (physical constant).',
    'elec_grid_kwh':      'Purchased grid electricity  - metered kWh from energy provider.',
    'elec_site_gj':       'Site diesel generation kWh x 0.0036 GJ/kWh.',
    'elec_site_kwh':      'Site diesel generation  - metered kWh.',
    'elec_sold_gj':       'No electricity exported.  All generation consumed on site.',
    'milled_tonnes':      'Ore processed through mill circuit.  Source: production reporting system.',
    'gold_recovered':     'Gold recovered (troy ounces).  Source: production reporting system.',
    'cyanide_kg':         'Sodium cyanide reagent consumption.  Source: INV03 inventory system (CYAN product group).',
    'quicklime_t':        'Quicklime (unslaked) consumption.  Source: INV03 inventory system (LIME product group).',
    'grinding_media_t':   'Grinding media (steel balls) consumption.  Source: INV03 inventory system (GMED product group).  Converted from kg to tonnes.',
    'caustic_kg':         'Caustic soda (NaOH) consumption.  Source: INV03 inventory system (CAUS product group).',
    'hcl_kg':             'Hydrochloric acid (HCl 32%) consumption.  Source: INV03 inventory system (ACID product group).',
    'oxygen_m3':          'Liquid oxygen consumption.  Source: INV03 inventory system (OXYG product group).',
    'flocculant_kg':      'Flocculant consumption (process + water treatment).  Source: INV03 inventory system (FLOC product group).  Converted from bags to kg (15 kg/bag).',
    'tyres_each':         'Tyre consumption (all sizes).  Source: INV03 inventory system (TYRE product group).',
    'explosives_kg':      'Explosives consumption.  Source: INV03 inventory system (EXPL product group).',
    'carbon_t':           'Activated carbon consumption.  Source: INV03 inventory system.',
    'leach_aid_t':        'Leach aid consumption.  Source: INV03 inventory system.',
    'antiscalant_t':      'Antiscalant consumption.  Source: INV03 inventory system.',
    'soda_ash_t':         'Soda ash (Na2CO3) consumption.  Source: INV03 inventory system.',
    'sodium_chlorite_t':  'Sodium chlorite consumption.  Source: INV03 inventory system.',
    'sodium_hypochlorite_kl': 'Sodium hypochlorite consumption.  Source: INV03 inventory system.',
    'dust_suppressant_kl':'Dust suppressant consumption.  Source: INV03 inventory system.',
    'ei_scope1_gold':     'Scope 1 tCO2-e / gold recovered (oz).  Common sector benchmark for gold mining.',
    'gold_sold_oz':       'Gold sold (troy ounces).  Source: production reporting system.',
    'waste_rock_t':       'Waste rock moved (tonnes).  Source: operations metrics actual (SubActivity=Ore Waste, UOM=t).  Limited: does not include non-mineral waste streams.',
    'waste_rock_bcm':     'Waste rock moved (BCM).  Source: operations metrics actual (SubActivity=Ore Waste, UOM=BCM).  Limited: volumetric measure only.',
    'tailings_approx_t':  'Approximate tailings: milled tonnes less gold recovered.  Gold mass is negligible.  Limited: does not account for reagent additions or moisture content.',
    'strip_ratio':        'Strip ratio: waste rock (t) / ROM ore (t).  Indicator of mining efficiency and waste intensity.',
    'drilling_m':         'Total drilling metres.  Source: operations metrics actual (SubActivity=Drilling).',
}


# ─────────────────────────────────────────────────────────────────────
# MAIN EXPORT FUNCTION
# ─────────────────────────────────────────────────────────────────────

def build_gri14_export(precomputed, raw_df=None, reporting_fys=None,
                       reporting_periods=None, year_type='FY'):
    """Build the GRI 14 flat-file export from precomputed data.

    Args:
        precomputed: PrecomputedData instance from CalcPrecompute
        raw_df: Raw DataFrame from load_all_data() -- needed for production
                metrics (milled tonnes, gold oz) not in precomputed tables.
                Pass None to skip those rows.
        reporting_fys: (Deprecated) List of FY integers to report.
                       Converted to reporting_periods internally.
        reporting_periods: List of (start_date, end_date, label) tuples.
                           Preferred interface for date-range filtering.
        year_type: 'FY' or 'CY' -- selects which annual table to use.

    Returns:
        DataFrame with columns:
            GRI_Topic, Section, GRI_Reference, Description, Unit,
            FY, Value, Data_Source, Methodology_Note
    """
    # Convert deprecated reporting_fys to reporting_periods
    if reporting_periods is None:
        if reporting_fys is not None:
            reporting_periods = []
            for fy in reporting_fys:
                start, end = year_to_date_range(fy, year_type)
                prefix = 'CY' if year_type == 'CY' else 'FY'
                reporting_periods.append((start, end, f"{prefix}{fy}"))
        else:
            # Auto-detect from annual table
            annual = _gri_annual(precomputed)
            mask = annual['Scope1'] > 0
            raw_fys = annual.loc[mask, 'FY'].unique()
            prefix = 'CY' if year_type == 'CY' else 'FY'
            year_ints = sorted([
                int(str(f).replace('FY', '').replace('CY', '')) for f in raw_fys
            ])
            reporting_periods = []
            for yi in year_ints:
                start, end = year_to_date_range(yi, year_type)
                reporting_periods.append((start, end, f"{prefix}{yi}"))

    rows = []

    for entry in GRI14_QUANTITATIVE_MAP:
        fn = _CALC_FN_MAP.get(entry['calc_fn'])
        if fn is None:
            continue

        calc_args = entry.get('calc_args', {})

        for start_date, end_date, label in reporting_periods:
            # The export's own calendar year frame (CalcGri).  It carries
            # gross Scope 3 across all fifteen categories.  There is no
            # fallback to a Safeguard or NGER frame: a missing frame gives
            # blank values, which is visible, where a substituted frame
            # gives wrong ones, which is not.
            annual_df = _gri_annual(precomputed)
            value = fn(precomputed, start_date, end_date, raw_df=raw_df,
                       annual_df=annual_df, **calc_args)

            # Extract numeric year from label for the FY column
            fy_numeric = int(label.replace('FY', '').replace('CY', ''))

            rows.append({
                'GRI_Topic': entry.get('gri_topic', '14.1 Climate Change'),
                'Section': entry['section'],
                'GRI_Reference': entry['gri_ref'],
                'Description': entry['description'],
                'Unit': entry['unit'],
                'FY': fy_numeric,
                'Value': value,
                'Coverage': entry.get('coverage', 'Auto'),
                'Data_Source': 'Ravenswood Emissions Model',
                'Methodology_Note': _METHODOLOGY.get(entry['id'], ''),
            })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────
# COVERAGE REPORT
# ─────────────────────────────────────────────────────────────────────
# Comprehensive status of all 137 quantitative disclosures across GRI 14.

GRI14_COVERAGE = {
    '14.1 Climate Change': {
        'auto': [
            ('102-5a',   'Scope 1 total',                              'tCO2-e'),
            ('102-5b',   'Scope 1 gas-by-gas (CO2, CH4, N2O)',        'tCO2-e'),
            ('102-5b',   'Scope 1 HFCs, PFCs, SF6, NF3 (all zero)',   'tCO2-e'),
            ('102-6a',   'Scope 2 total (location-based)',             'tCO2-e'),
            ('102-7a',   'Scope 3 total (fuel + grid T&D)',            'tCO2-e'),
            ('102-8a',   'Emissions intensity (Scope 1 / ROM t)',      'tCO2-e/t'),
            ('102-8b',   'ROM ore tonnes, intensity denominator',      't'),
            ('102-10a',  'SMC issued, surrendered, sold',              'tCO2-e'),
            ('103-2a',   'Total fuel consumption + by type',           'GJ'),
            ('103-2b',   'Purchased grid electricity (GJ + kWh)',      'GJ'),
            ('103-2c',   'Self-generated electricity (GJ + kWh)',      'GJ'),
            ('103-2d',   'Electricity sold (zero)',                     'GJ'),
            ('103-4a',   'Energy intensity (GJ / ROM t)',              'GJ/t'),
            ('14.1-sect','By-site breakdowns (single site)',           'tCO2-e'),
            ('context',  'Milled tonnes, gold recovered oz',           'various'),
            ('14.1-cons','Reagent consumption (cyanide, lime, caustic, acid, oxygen, flocculant)', 'various'),
            ('14.5-waste','Wear items (tyres, grinding media)',          'various'),
            ('14.3-emis','Explosives consumption',                       'kg'),
        ],
        'collectible': [
            ('102-4a',  'GHG reduction targets + progress',  'tCO2-e',
             'Requires corporate target-setting.  Store targets in Config.py, auto-calculate progress.'),
            ('102-6b',  'Scope 2 gas-by-gas (CO2, CH4, N2O)',  'tCO2-e',
             'NGA electricity factors have gas splits.  Extend NGA loader to extract per-gas EFs for grid.'),
            ('103-3a',  'Upstream/downstream energy',  'GJ',
             'Scope 3 fuel energy already calculated.  Extend with transport estimates for purchased goods.'),
        ],
        'not_available': [
            ('102-9a/b', 'GHG removals / storage pools', 'tCO2-e',
             'No carbon sequestration activities at Ravenswood.'),
        ],
    },
    '14.3 Air Emissions': {
        'auto': [],
        'collectible': [
            ('305-7a', 'NOx, SOx, PM, VOC, HAP, POP (7 items)', 'kg',
             'Requires NPI data or DCCEEW emission estimation techniques for mining.  Add loader_npi.py.'),
        ],
        'not_available': [],
    },
    '14.4 Biodiversity': {
        'auto': [],
        'collectible': [
            ('101-2b/c', 'Restoration/rehabilitation area (4 items)', 'Ha',
             'Data in closure plans.  Cross-reference land disturbance register.'),
            ('101-5a',   'Site size with biodiversity impacts', 'Ha',
             'Mining lease areas known.  Add to Config.py.'),
            ('101-6b/c', 'Water at biodiversity sites + pollutant loads (4 items)', 'ML/kg',
             'Cross-reference from 14.7 water data and environmental monitoring.'),
        ],
        'not_available': [],
    },
    '14.5 Waste': {
        'auto': [
            ('306-3a',   'Waste rock moved (t)',                           't'),
            ('306-3a',   'Waste rock moved (BCM)',                         'BCM'),
            ('306-3a',   'Tailings produced (approx from milled tonnes)',  't'),
            ('14.5-sect','Strip ratio (waste rock / ROM ore)',             'ratio'),
        ],
        'limited': [
            ('306-3a',   'Rock waste and tailings quantities are from operations data only.  Does not include non-mineral waste (hazardous, general, recycled).  Tailings is approximate (milled tonnes less gold).', 't'),
        ],
        'collectible': [
            ('306-3a',   'Non-mineral waste by type (hazardous, general, recycled)', 't',
             'Requires waste tracking register.  Add loader_waste.py.'),
            ('306-4/5',  'Waste diverted + disposed breakdown (35 items)', 't',
             'Waste tracking data.  Scats reuse is main diversion stream.'),
        ],
        'not_available': [],
    },
    '14.7 Water and Effluents': {
        'auto': [],
        'collectible': [
            ('303-3a/b', 'Water withdrawal by source (10 items)', 'ML',
             'Partial FY2024 data exists (surface 3,088 ML, groundwater 2,139 ML).  Add loader_water.py from WIMS.'),
            ('303-4a/b', 'Water discharge by destination (10 items)', 'ML',
             'EA conditions require discharge monitoring.  Data in compliance reports.'),
            ('303-5a/b/c','Water consumption (3 items)', 'ML',
             'Withdrawal minus discharge.  Needs both upstream sources.'),
        ],
        'not_available': [],
    },
    '14.8 Closure and Rehabilitation': {
        'auto': [],
        'collectible': [
            ('14.8.6',  'Land disturbed / rehabilitated (2 items)', 'Ha',
             'FY2023=858/133 Ha, FY2024=867/134 Ha already in databook.  Annual survey data.'),
            ('14.8.7',  'Estimated life of mine', 'Year',
             'Derivable from DEFAULT_END_MINING_DATE in Config.py.'),
            ('14.8.8',  'Closure cost estimate', '$AUD',
             'Separate closure cost model.  Single value in Config.py if appropriate.'),
        ],
        'not_available': [],
    },
}


def build_coverage_report():
    """Build a summary DataFrame showing GRI 14 quantitative disclosure coverage.

    Returns:
        DataFrame with: GRI_Topic, GRI_Reference, Description, Unit,
                        Status, Implementation_Notes
        Status: 'Auto' | 'Collectible' | 'N/A'
    """
    rows = []
    for topic, cats in GRI14_COVERAGE.items():
        for ref, desc, unit in cats.get('auto', []):
            rows.append({'GRI_Topic': topic, 'GRI_Reference': ref,
                         'Description': desc, 'Unit': unit,
                         'Status': 'Auto', 'Implementation_Notes': ''})
        for entry in cats.get('collectible', []):
            rows.append({'GRI_Topic': topic, 'GRI_Reference': entry[0],
                         'Description': entry[1], 'Unit': entry[2],
                         'Status': 'Collectible', 'Implementation_Notes': entry[3]})
        for entry in cats.get('not_available', []):
            rows.append({'GRI_Topic': topic, 'GRI_Reference': entry[0],
                         'Description': entry[1], 'Unit': entry[2],
                         'Status': 'N/A', 'Implementation_Notes': entry[3]})
    return pd.DataFrame(rows)


def coverage_summary_counts():
    """Return a dict summarising disclosure counts by topic and status."""
    report = build_coverage_report()
    summary = {}
    for topic in report['GRI_Topic'].unique():
        sub = report[report['GRI_Topic'] == topic]
        summary[topic] = {
            'auto': len(sub[sub['Status'] == 'Auto']),
            'collectible': len(sub[sub['Status'] == 'Collectible']),
            'not_available': len(sub[sub['Status'] == 'N/A']),
        }
    return summary