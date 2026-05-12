"""
export_gri14.py
GRI 14 Mining Sector Disclosure flat-file export

Generates a structured CSV/XLSX databook mapping Ravenswood Gold emissions
data to GRI 14 (Mining Sector 2024) quantitative disclosure requirements.

Architecture:
    - Hardcoded disclosure map defines every quantitative GRI 14 item
    - Extraction functions pull calculated values from PrecomputedData
    - Outputs a flat file with one row per disclosure per reporting year
    - Coverage report summarises auto/collectible/N-A status

Data sources mapped:
    Scope 1/2/3 totals ........... annual_fy (from precompute)
    Gas-by-gas CO2/CH4/N2O ....... NGA individual gas EFs x fuel quantities
    Energy (GJ) by fuel type ..... safeguard_source (Energy_GJ column)
    Electricity (kWh -> GJ) ...... annual_fy Site/Grid kWh
    ROM ore (t) .................. annual_fy ROM_t
    Milled tonnes ................ raw df (Description == 'Milled Tonnes')
    Gold production (oz) ......... raw df (Description == 'Gold Recovered oz')
    Emission intensity ........... annual_fy Scope1 / ROM_t
    SMC issuances/sales/surrenders smc_transactions.csv
    Energy intensity ............. total Energy_GJ / ROM_t

14.5 Waste (Limited):
    Rock waste (t, BCM) ............. operations_metrics_actual Ore Waste
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

Last updated: 2026-03-26
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List

# ─────────────────────────────────────────────────────────────────────
# FY LOOKUP HELPER
# ─────────────────────────────────────────────────────────────────────
# annual_fy uses 'FY2024' string format; safeguard_source uses int 2024.
# This helper normalises lookups so extraction functions accept int FY.

def _fy_row(annual_df, fy_int):
    """Return annual_fy row(s) matching an integer FY.

    Handles both 'FY2024' string and 2024 integer column formats.
    Returns filtered DataFrame (may be empty).
    """
    # Try integer match first (safeguard tables use int FY)
    result = annual_df[annual_df['FY'] == fy_int]
    if not result.empty:
        return result
    # Try string format 'FY2024' or 'CY2024'
    result = annual_df[annual_df['FY'] == f'FY{fy_int}']
    if not result.empty:
        return result
    result = annual_df[annual_df['FY'] == f'CY{fy_int}']
    if not result.empty:
        return result
    # Try Year column as fallback
    if 'Year' in annual_df.columns:
        result = annual_df[annual_df['Year'] == f'FY{fy_int}']
        if not result.empty:
            return result
        result = annual_df[annual_df['Year'] == fy_int]
    return result




# ─────────────────────────────────────────────────────────────────────
# GRI 14 QUANTITATIVE DISCLOSURE MAP
# ─────────────────────────────────────────────────────────────────────
# Each entry is one row in the output.  'calc_fn' names a function
# in _CALC_FN_MAP that returns a value given (precomputed, fy, raw_df).

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

    {'id': 'scope1_site',       'gri_ref': '14.1-sector',  'section': 'Scope 1 GHG Emissions',
     'description': 'Scope 1 by mine site (Ravenswood  - single facility)',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope1_total'},

    # ── SCOPE 2 GHG EMISSIONS ────────────────────────────────────────

    {'id': 'scope2_total',      'gri_ref': '102-6a',       'section': 'Scope 2 GHG Emissions',
     'description': 'Gross location-based Scope 2 GHG emissions',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope2_total'},

    {'id': 'scope2_site',       'gri_ref': '14.1-sector',  'section': 'Scope 2 GHG Emissions',
     'description': 'Scope 2 by mine site (Ravenswood  - single facility)',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope2_total'},

    # ── SCOPE 3 GHG EMISSIONS ────────────────────────────────────────

    {'id': 'scope3_total',      'gri_ref': '102-7a',       'section': 'Scope 3 GHG Emissions',
     'description': 'Gross Scope 3 GHG emissions (fuel combustion + grid T&D only)',
     'unit': 'tCO2-e', 'calc_fn': '_get_scope3_total'},

    # ── EMISSIONS INTENSITY ──────────────────────────────────────────

    {'id': 'ei_scope1_rom',     'gri_ref': '102-8a',       'section': 'GHG Emissions intensity',
     'description': 'Scope 1 emissions intensity (tCO2-e per tonne ROM ore)',
     'unit': 'tCO2-e/t ROM', 'calc_fn': '_get_emission_intensity'},

    {'id': 'rom_total',         'gri_ref': '302-3b',       'section': 'GHG Emissions intensity',
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
     'calc_args': {'common_name': 'Ore milled', 'row_types': ['total']}},

    {'id': 'gold_recovered',   'gri_ref': 'context',       'section': 'Production metrics',
     'description': 'Gold recovered',
     'unit': 'oz', 'calc_fn': '_get_production_metric',
     'calc_args': {'common_name': 'Gold recovered', 'row_types': ['production']}},

    # -- GRI CONSUMABLES (from consolidated_emissions_data.csv ReportingCategory='GRI') --

    {'id': 'cyanide_kg',       'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Sodium cyanide consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Cyanide', 'row_types': ['consumption']}},

    {'id': 'quicklime_t',      'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Quicklime consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Lime', 'row_types': ['consumption']}},

    {'id': 'grinding_media_t', 'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Grinding media consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Grinding media', 'row_types': ['consumption']}},

    {'id': 'caustic_kg',       'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Caustic soda consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Caustic soda', 'row_types': ['consumption']}},

    {'id': 'hcl_kg',           'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Hydrochloric acid consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Hydrochloric acid', 'row_types': ['consumption']}},

    {'id': 'oxygen_m3',        'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Liquid oxygen consumption',
     'unit': 'm3', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Liquid oxygen', 'row_types': ['consumption']}},

    {'id': 'flocculant_kg',    'gri_ref': '14.1-consumables', 'section': 'Reagents and consumables',
     'description': 'Flocculant consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Flocculant', 'row_types': ['consumption']}},

    {'id': 'tyres_each',       'gri_ref': '14.5-waste',       'section': 'Wear items',
     'description': 'Tyres consumed',
     'unit': 'each', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Tyres', 'row_types': ['consumption']}},

    {'id': 'explosives_kg',    'gri_ref': '14.3-emissions',   'section': 'Wear items',
     'description': 'Explosives consumption',
     'unit': 'kg', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Explosives', 'row_types': ['consumption']}},

    # ── ADDITIONAL REAGENTS / CONSUMABLES (GRI 301-1 Materials used) ───

    {'id': 'carbon_t',        'gri_ref': '301-1',            'section': 'Reagents and consumables',
     'description': 'Activated carbon consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Carbon', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'leach_aid_t',     'gri_ref': '301-1',            'section': 'Reagents and consumables',
     'description': 'Leach aid consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Leach aid', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'antiscalant_t',   'gri_ref': '301-1',            'section': 'Reagents and consumables',
     'description': 'Antiscalant consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Antiscalant', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'soda_ash_t',      'gri_ref': '301-1',            'section': 'Reagents and consumables',
     'description': 'Soda ash consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Soda ash', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'sodium_chlorite_t','gri_ref': '301-1',           'section': 'Reagents and consumables',
     'description': 'Sodium chlorite consumption',
     'unit': 't', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Sodium chlorite', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'sodium_hypochlorite_kl', 'gri_ref': '301-1',     'section': 'Reagents and consumables',
     'description': 'Sodium hypochlorite consumption',
     'unit': 'kL', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Sodium hypochlorite', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    {'id': 'dust_suppressant_kl', 'gri_ref': '301-1',        'section': 'Reagents and consumables',
     'description': 'Dust suppressant consumption',
     'unit': 'kL', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Dust suppressant', 'row_types': ['consumption']},
     'gri_topic': '14.1 Climate Change'},

    # ── EMISSION INTENSITY - GOLD (sector benchmark) ──────────────────

    {'id': 'ei_scope1_gold',  'gri_ref': '102-8a',           'section': 'GHG Emissions intensity',
     'description': 'Scope 1 emissions intensity (tCO2-e per oz gold recovered)',
     'unit': 'tCO2-e/oz', 'calc_fn': '_get_emission_intensity_gold',
     'gri_topic': '14.1 Climate Change'},

    {'id': 'gold_sold_oz',    'gri_ref': 'context',           'section': 'Production metrics',
     'description': 'Gold sold',
     'unit': 'oz', 'calc_fn': '_get_production_metric',
     'calc_args': {'common_name': 'Gold sold', 'row_types': ['production']},
     'gri_topic': '14.1 Climate Change'},

    # ── 14.5 WASTE (Limited - rock waste from operations data) ────────

    {'id': 'waste_rock_t',    'gri_ref': '306-3a',            'section': 'Waste - rock waste',
     'description': 'Waste rock moved',
     'unit': 't', 'calc_fn': '_get_ore_waste',
     'calc_args': {'uom': 't'},
     'gri_topic': '14.5 Waste', 'coverage': 'Limited'},

    {'id': 'waste_rock_bcm',  'gri_ref': '306-3a',            'section': 'Waste - rock waste',
     'description': 'Waste rock moved (bank cubic metres)',
     'unit': 'BCM', 'calc_fn': '_get_ore_waste',
     'calc_args': {'uom': 'BCM'},
     'gri_topic': '14.5 Waste', 'coverage': 'Limited'},

    {'id': 'tailings_approx_t','gri_ref': '306-3a',           'section': 'Waste - tailings',
     'description': 'Tailings produced (approx: milled tonnes less gold recovered)',
     'unit': 't', 'calc_fn': '_get_tailings_approx',
     'gri_topic': '14.5 Waste', 'coverage': 'Limited'},

    {'id': 'strip_ratio',     'gri_ref': '14.5-sector',       'section': 'Waste - rock waste',
     'description': 'Strip ratio (waste rock t / ROM ore t)',
     'unit': 'ratio', 'calc_fn': '_get_strip_ratio',
     'gri_topic': '14.5 Waste', 'coverage': 'Limited'},

    # ── 14.8 CLOSURE (Limited - LOM from budget projections) ──────────

    {'id': 'drilling_m',      'gri_ref': 'context',            'section': 'Production metrics',
     'description': 'Total drilling metres',
     'unit': 'm', 'calc_fn': '_get_gri_consumable',
     'calc_args': {'common_name': 'Drilling', 'row_types': ['production']},
     'gri_topic': '14.1 Climate Change'},
]


# ─────────────────────────────────────────────────────────────────────
# NGA INDIVIDUAL GAS EMISSION FACTORS (kgCO2-e/GJ)
# ─────────────────────────────────────────────────────────────────────
# Source: NGA 2025, Table 8 (liquid fuels), Table 3/5 (gaseous fuels)
# Gas-by-gas EFs loaded from nga_factors.csv (CO2, CH4, N2O columns).
# These are read once and cached.  Falls back to zeros if columns
# are missing (backward compatible with pre-2026 nga_factors.csv).

_NGA_GAS_CACHE = None

def _load_nga_gas_split():
    """Load per-gas emission factors from nga_factors.csv.

    Returns dict: {(fuel_name, nga_year): {'CO2': x, 'CH4': y, 'N2O': z}}
    Only Scope 1 rows have gas split data.
    """
    global _NGA_GAS_CACHE
    if _NGA_GAS_CACHE is not None:
        return _NGA_GAS_CACHE

    import os
    csv_path = os.path.join(os.path.dirname(__file__) or '.', 'nga_factors.csv')
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

def _get_scope1_total(precomputed, fy, raw_df=None, **kw):
    """Gross Scope 1 tCO2-e for the given FY."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    val = float(row['Scope1'].iloc[0])
    return round(val, 2) if val > 0 else None


def _get_scope2_total(precomputed, fy, raw_df=None, **kw):
    """Gross location-based Scope 2 tCO2-e."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    val = float(row['Scope2'].iloc[0])
    return round(val, 2) if val > 0 else None


def _get_scope3_total(precomputed, fy, raw_df=None, **kw):
    """Gross Scope 3 tCO2-e (fuel combustion + grid T&D)."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    val = float(row['Scope3'].iloc[0])
    return round(val, 2) if val > 0 else None


def _get_scope1_gas(precomputed, fy, raw_df=None, gas='CO2', **kw):
    """Scope 1 split by individual greenhouse gas (CO2, CH4, N2O).

    Method: For each fuel type, take the Energy_GJ total for the FY,
    multiply by the gas-specific EF (kgCO2-e/GJ), convert to tCO2-e.
    This reproduces the NGA Method 1 calculation at gas level.

    tCO2-e(gas) = sum over fuels [ Energy_GJ * EF_gas(kgCO2-e/GJ) / 1000 ]
    """
    src = precomputed.safeguard_source
    if src.empty:
        return None

    mask = (src['FY'] == fy) & (src['DataSet'] == 'Actual')
    if not mask.any():
        return None

    total = 0.0
    for _, row in src[mask].iterrows():
        nga_fuel = str(row['NGAFuel'])
        energy_gj = float(row['Energy_GJ'])
        if energy_gj <= 0:
            continue

        # Look up gas-specific EF from nga_factors.csv
        ef_gas = _get_gas_ef(nga_fuel, gas)
        if ef_gas == 0.0 and gas == 'CO2':
            continue  # No data for this fuel
        total += energy_gj * ef_gas / 1000.0

    return round(total, 2) if total > 0 else 0.0


def _get_emission_intensity(precomputed, fy, raw_df=None, **kw):
    """Scope 1 emissions intensity: tCO2-e per tonne ROM ore."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    rom_t = float(row['ROM_t'].iloc[0])
    s1 = float(row['Scope1'].iloc[0])
    if rom_t <= 0 or s1 <= 0:
        return None
    return round(s1 / rom_t, 6)


def _get_energy_intensity(precomputed, fy, raw_df=None, **kw):
    """Energy intensity: total fuel GJ per tonne ROM ore."""
    rom_t = _get_rom_tonnes(precomputed, fy)
    fuel_gj = _get_total_fuel_gj(precomputed, fy)
    if rom_t is None or fuel_gj is None or rom_t <= 0:
        return None
    return round(fuel_gj / rom_t, 6)


def _get_rom_tonnes(precomputed, fy, raw_df=None, **kw):
    """Total ROM ore tonnes."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    val = float(row['ROM_t'].iloc[0])
    return round(val, 0) if val > 0 else None


def _get_smc_by_type(precomputed, fy, raw_df=None, txn_type='Issuance', **kw):
    """SMC transaction quantity by type for the given FY.

    Types: 'Issuance', 'Sale', 'Surrender'
    Sales are stored as negative quantities in the CSV.
    Returns absolute value for reporting purposes.
    """
    smc = precomputed.smc_transactions
    if smc.empty:
        return None
    mask = (smc['Type'] == txn_type) & (smc['Applies_To_FY'] == fy)
    if not mask.any():
        return None
    val = float(smc.loc[mask, 'Quantity'].sum())
    return round(abs(val), 0) if val != 0 else None


def _get_total_fuel_gj(precomputed, fy, raw_df=None, **kw):
    """Total fuel energy consumption in GJ (excludes electricity)."""
    src = precomputed.safeguard_source
    if src.empty:
        return None
    mask = (src['FY'] == fy) & (src['DataSet'] == 'Actual')
    if not mask.any():
        return None
    val = float(src.loc[mask, 'Energy_GJ'].sum())
    return round(val, 2) if val > 0 else None


def _get_fuel_gj_by_nga(precomputed, fy, raw_df=None, nga_prefix='', exclude_prefix='', **kw):
    """Energy GJ for a specific NGAFuel prefix.

    Args:
        nga_prefix: NGAFuel must start with this string.
        exclude_prefix: If set, exclude rows whose NGAFuel starts with this
                        (e.g. exclude 'Diesel oil-Cars' from 'Diesel oil' to
                        get stationary diesel only).
    """
    src = precomputed.safeguard_source
    if src.empty:
        return None
    mask = (
        (src['FY'] == fy)
        & (src['DataSet'] == 'Actual')
        & (src['NGAFuel'].astype(str).str.startswith(nga_prefix))
    )
    if exclude_prefix:
        mask = mask & (~src['NGAFuel'].astype(str).str.startswith(exclude_prefix))
    if not mask.any():
        return None
    val = float(src.loc[mask, 'Energy_GJ'].sum())
    return round(val, 2) if val > 0 else None


def _get_fuel_gj_by_desc(precomputed, fy, raw_df=None, descriptions=None, **kw):
    """Energy GJ for specific Description values from safeguard source."""
    if descriptions is None:
        return None
    src = precomputed.safeguard_source
    if src.empty:
        return None
    mask = (
        (src['FY'] == fy)
        & (src['DataSet'] == 'Actual')
        & (src['Description'].isin(descriptions))
    )
    if not mask.any():
        return None
    val = float(src.loc[mask, 'Energy_GJ'].sum())
    return round(val, 2) if val > 0 else None


def _get_grid_electricity_gj(precomputed, fy, raw_df=None, **kw):
    """Purchased grid electricity in GJ.  1 kWh = 0.0036 GJ."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    kwh = float(row['Grid_Electricity_kWh'].iloc[0])
    return round(kwh * 0.0036, 2) if kwh > 0 else None


def _get_grid_electricity_kwh(precomputed, fy, raw_df=None, **kw):
    """Purchased grid electricity in kWh."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    val = float(row['Grid_Electricity_kWh'].iloc[0])
    return round(val, 0) if val > 0 else None


def _get_site_electricity_gj(precomputed, fy, raw_df=None, **kw):
    """Self-generated electricity in GJ."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    kwh = float(row['Site_Electricity_kWh'].iloc[0])
    return round(kwh * 0.0036, 2) if kwh > 0 else None


def _get_site_electricity_kwh(precomputed, fy, raw_df=None, **kw):
    """Self-generated electricity in kWh."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    val = float(row['Site_Electricity_kWh'].iloc[0])
    return round(val, 0) if val > 0 else None


def _get_production_metric(precomputed, fy, raw_df=None, common_name='', row_types=None, desc='', **kw):
    """Production quantity from raw data by CommonName.

    Used for Ore milled, Gold recovered, Gold sold, etc.
    These are not in the precomputed annual tables so we need raw_df.

    Falls back to Description match if CommonName column is not present.

    Args:
        common_name: CommonName value to match (preferred)
        row_types:   List of RowType values to include (e.g. ['total'] for
                     Ore milled total, ['production'] for Gold recovered)
        desc:        Legacy Description match (fallback only)
    """
    if raw_df is None:
        return None

    # Prefer CommonName if the column exists and a value was provided
    if common_name and 'CommonName' in raw_df.columns:
        mask = (
            (raw_df['FY'] == fy)
            & (raw_df['DataSet'] == 'Actual')
            & (raw_df['CommonName'].astype(str) == common_name)
        )
        if row_types and 'RowType' in raw_df.columns:
            mask = mask & (raw_df['RowType'].astype(str).isin(row_types))
    else:
        # Fallback: match by Description (legacy behaviour)
        lookup = desc if desc else common_name
        mask = (
            (raw_df['FY'] == fy)
            & (raw_df['DataSet'] == 'Actual')
            & (raw_df['Description'].astype(str) == lookup)
        )

    if not mask.any():
        return None
    val = float(raw_df.loc[mask, 'Quantity'].sum())
    return round(val, 0) if val > 0 else None


def _get_gri_consumable(precomputed, fy, raw_df=None, common_name='', row_types=None, desc='', **kw):
    """Get GRI consumable quantity from raw data using CommonName.

    Matches rows by CommonName (normalised grouping key) rather than
    Description, so variant descriptions (e.g. 'Explosives Loaded - BRW')
    are correctly captured alongside the base description.

    Optionally filters by RowType to distinguish consumption vs purchased
    vs detail rows.  Defaults to 'consumption' if row_types is not specified.

    Falls back to Description match if CommonName column is not present
    (backward compatibility with pre-CommonName CSVs).

    Args:
        common_name: CommonName value to match (preferred)
        row_types:   List of RowType values to include.  Default ['consumption']
        desc:        Legacy Description match (fallback only)
    """
    if raw_df is None:
        return None

    # Prefer CommonName if the column exists and a value was provided
    if common_name and 'CommonName' in raw_df.columns:
        mask = (
            (raw_df['FY'] == fy)
            & (raw_df['DataSet'] == 'Actual')
            & (raw_df['CommonName'].astype(str) == common_name)
        )
        # Filter by RowType if available
        if row_types and 'RowType' in raw_df.columns:
            mask = mask & (raw_df['RowType'].astype(str).isin(row_types))
    else:
        # Fallback: match by Description (legacy behaviour)
        lookup = desc if desc else common_name
        mask = (
            (raw_df['FY'] == fy)
            & (raw_df['DataSet'] == 'Actual')
            & (raw_df['Description'].astype(str) == lookup)
        )

    if not mask.any():
        return None
    val = float(raw_df.loc[mask, 'Quantity'].sum())
    return round(val, 2) if abs(val) > 0.001 else None


def _get_emission_intensity_gold(precomputed, fy, raw_df=None, **kw):
    """Scope 1 emissions intensity: tCO2-e per troy ounce gold recovered."""
    row = _fy_row(kw.get('annual_df', precomputed.annual_fy), fy)
    if row.empty:
        return None
    s1 = float(row['Scope1'].iloc[0])
    gold_oz = _get_production_metric(precomputed, fy, raw_df=raw_df,
                                      common_name='Gold recovered', row_types=['production'])
    if gold_oz is None or gold_oz <= 0 or s1 <= 0:
        return None
    return round(s1 / gold_oz, 4)


def _get_ore_waste(precomputed, fy, raw_df=None, uom='t', **kw):
    """Ore waste quantity for the given FY, filtered by UOM (t or BCM).

    Waste rock is reported in both tonnes and BCM depending on the
    measurement method.  Returns the total for the requested UOM only.
    """
    if raw_df is None:
        return None
    mask = (
        (raw_df['FY'] == fy)
        & (raw_df['DataSet'] == 'Actual')
        & (raw_df['SubActivity'].astype(str) == 'Ore Waste')
        & (raw_df['UOM'].astype(str) == uom)
    )
    if not mask.any():
        return None
    val = float(raw_df.loc[mask, 'Quantity'].sum())
    return round(val, 0) if val > 0 else None


def _get_tailings_approx(precomputed, fy, raw_df=None, **kw):
    """Approximate tailings tonnage: milled tonnes less gold recovered.

    Almost all milled material reports to tailings.  Gold recovery
    is negligible by mass but included for completeness.
    """
    milled = _get_production_metric(precomputed, fy, raw_df=raw_df,
                                     common_name='Ore milled', row_types=['total'])
    if milled is None or milled <= 0:
        return None
    # Gold is in oz, ~31.1g/oz - negligible relative to milled tonnes
    return round(milled, 0)


def _get_strip_ratio(precomputed, fy, raw_df=None, **kw):
    """Strip ratio: waste rock tonnes / ROM ore tonnes."""
    waste_t = _get_ore_waste(precomputed, fy, raw_df=raw_df, uom='t')
    rom_t = _get_rom_tonnes(precomputed, fy)
    if waste_t is None or rom_t is None or rom_t <= 0:
        return None
    return round(waste_t / rom_t, 2)


def _get_zero(precomputed, fy, raw_df=None, **kw):
    """Return 0.0 for disclosures that are definitively zero."""
    return 0.0


# ── Function dispatch table ──────────────────────────────────────────

_CALC_FN_MAP = {
    '_get_scope1_total':          _get_scope1_total,
    '_get_scope2_total':          _get_scope2_total,
    '_get_scope3_total':          _get_scope3_total,
    '_get_scope1_gas':            _get_scope1_gas,
    '_get_emission_intensity':    _get_emission_intensity,
    '_get_energy_intensity':      _get_energy_intensity,
    '_get_rom_tonnes':            _get_rom_tonnes,
    '_get_smc_by_type':           _get_smc_by_type,
    '_get_total_fuel_gj':         _get_total_fuel_gj,
    '_get_fuel_gj_by_nga':        _get_fuel_gj_by_nga,
    '_get_fuel_gj_by_desc':       _get_fuel_gj_by_desc,
    '_get_grid_electricity_gj':   _get_grid_electricity_gj,
    '_get_grid_electricity_kwh':  _get_grid_electricity_kwh,
    '_get_site_electricity_gj':   _get_site_electricity_gj,
    '_get_site_electricity_kwh':  _get_site_electricity_kwh,
    '_get_production_metric':     _get_production_metric,
    '_get_gri_consumable':        _get_gri_consumable,
    '_get_emission_intensity_gold': _get_emission_intensity_gold,
    '_get_ore_waste':             _get_ore_waste,
    '_get_tailings_approx':       _get_tailings_approx,
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
    'scope3_total':       'Fuel combustion Scope 3 (NGA indirect factors) + grid T&D losses.  Does not include purchased goods, transport or other Scope 3 categories.',
    'ei_scope1_rom':      'Scope 1 tCO2-e / ROM ore tonnes.  Operational control boundary.',
    'rom_total':          'Sum of all ROM ore grades (HG, MG, LG, VLG) from BRW and SARS beneficiation streams.',
    'energy_intensity':   'Total fuel Energy_GJ / ROM ore tonnes.  Excludes electricity.',
    'smc_issued':         'CER registry issuance (smc_transactions.csv).  Issuances lag the reporting FY.',
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

def build_gri14_export(precomputed, raw_df=None, reporting_fys=None, year_type='FY'):
    """Build the GRI 14 flat-file export from precomputed data.

    Args:
        precomputed: PrecomputedData instance from calc_precompute
        raw_df: Raw DataFrame from load_all_data()  - needed for production
                metrics (milled tonnes, gold oz) not in precomputed tables.
                Pass None to skip those rows.
        reporting_fys: List of FY integers to report.
                       Default: all FYs with actual Scope 1 data.
        year_type: 'FY' or 'CY' — selects which annual table to use.

    Returns:
        DataFrame with columns:
            GRI_Topic, Section, GRI_Reference, Description, Unit,
            FY, Value, Data_Source, Methodology_Note
    """
    if reporting_fys is None:
        # Select annual table based on year_type
        annual = precomputed.annual_cy if year_type == 'CY' else precomputed.annual_fy
        mask = annual['Scope1'] > 0
        raw_fys = annual.loc[mask, 'FY'].unique()
        prefix = 'CY' if year_type == 'CY' else 'FY'
        reporting_fys = sorted([
            int(str(f).replace('FY', '').replace('CY', '')) for f in raw_fys
        ])

    rows = []

    for entry in GRI14_QUANTITATIVE_MAP:
        fn = _CALC_FN_MAP.get(entry['calc_fn'])
        if fn is None:
            continue

        calc_args = entry.get('calc_args', {})

        for fy in reporting_fys:
            # Pass selected annual table so extraction functions use correct year_type
            annual_df = precomputed.annual_cy if year_type == 'CY' else precomputed.annual_fy
            value = fn(precomputed, fy, raw_df=raw_df, annual_df=annual_df, **calc_args)

            rows.append({
                'GRI_Topic': entry.get('gri_topic', '14.1 Climate Change'),
                'Section': entry['section'],
                'GRI_Reference': entry['gri_ref'],
                'Description': entry['description'],
                'Unit': entry['unit'],
                'FY': int(fy),
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
            ('302-3b',   'ROM ore tonnes',                             't'),
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
             'Requires corporate target-setting.  Store targets in config.py, auto-calculate progress.'),
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
             'Mining lease areas known.  Add to config.py.'),
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
             'Derivable from DEFAULT_END_MINING_DATE in config.py.'),
            ('14.8.8',  'Closure cost estimate', '$AUD',
             'Separate closure cost model.  Single value in config.py if appropriate.'),
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