"""
calc_emissions.py
Emissions calculation functions for Ravenswood Gold
Last updated: 2026-02-10

Regulatory basis:
    NGER (Measurement) Determination 2008 - Method 1 calculations
    National Greenhouse Account (NGA) Factors (annual, DCCEEW)
    Safeguard Mechanism Rule 2015 (amended 2023)

Calculation method (universal for all fuels):
    tCO2-e = Quantity (native unit) * kgCO2-e_per_unit / 1000

    Consolidated CSV uses NGA-native units:
        Liquids:     kL   (NGA factor in kgCO2-e/kL)
        Gas:         m3   (NGA factor in kgCO2-e/m3)
        Electricity: kWh  (NGA factor in kgCO2-e/kWh)

    Energy content:
        Energy_GJ = Quantity * GJ_per_native_unit (from NGA Energy_Content)

Dependencies:
    loader_nga.py: NGAFactorsByYear class for factor lookup
"""

import pandas as pd
import numpy as np


def build_year_factor_map(nga_by_year, unique_years, state='QLD'):
    """Build NGA emission factor lookup by FY year number.

    All factors come from nga_factors.csv via the NGAFactorsByYear class.
    No hardcoded emission factors.  No unit conversions.

    Args:
        nga_by_year: NGAFactorsByYear instance (from loader_nga.py)
        unique_years: Iterable of FY year numbers (e.g. [2023, 2024, 2025])
        state: NEM state for grid electricity factors (default 'QLD')

    Returns:
        dict: {year: {nga_fuel_prefix: {
            's1': kgCO2-e/unit or 0,
            's2': kgCO2-e/unit or 0,
            's3': kgCO2-e/unit or 0,
            'energy': GJ per native unit or 0,
            'expected_uom': str (e.g. 'kL', 'm3', 'kWh'),
        }}}
    """
    # Known NGAFuel prefixes from consolidated CSV.
    # These match nga_factors.csv Fuel_Name via startswith.
    FUEL_PREFIXES = [
        'Diesel oil-Cars and light commercial vehicles',  # Transport (NGER)
        'Diesel oil',                                      # Stationary (default)
        'Liquefied petroleum gas (LPG)',
        'Petroleum based oils',
        'Petroleum based greases',
        'Gaseous fossil fuels other than',
    ]

    factor_map = {}

    for year in unique_years:
        year_factors = {}

        # --- Fuel factors (Scope 1 and 3) ---
        for prefix in FUEL_PREFIXES:
            s1 = nga_by_year.match_fuel_factor(year, prefix, 1)
            s3 = nga_by_year.match_fuel_factor(year, prefix, 3)

            if s1 is None:
                raise ValueError(
                    f"No NGA Scope 1 factor for '{prefix}' in FY{year}. "
                    f"Available years: {nga_by_year.available_years}."
                )

            # Energy content from NGA (e.g. 38.6 GJ/kL for diesel)
            energy_per_unit = s1['Energy_Content'] if s1['Energy_Content'] else 0

            # Expected UOM from NGA factor unit denominator
            expected_uom = nga_by_year.expected_uom(s1['EF_Unit'])

            year_factors[prefix] = {
                's1': s1['EF_kgCO2e_per_unit'],
                's2': 0,
                's3': s3['EF_kgCO2e_per_unit'] if s3 else 0,
                'energy': energy_per_unit,
                'expected_uom': expected_uom,
            }

        # --- Grid electricity (Scope 2 and 3, state-specific) ---
        s2 = nga_by_year.get_electricity_factor(year, state, 2)
        s3 = nga_by_year.get_electricity_factor(year, state, 3)

        if s2 is None:
            raise ValueError(
                f"No NGA electricity Scope 2 factor for {state} in FY{year}."
            )

        year_factors['Grid electricity'] = {
            's1': 0,
            's2': s2,
            's3': s3 if s3 else 0,
            'energy': 0.0036,  # 1 kWh = 0.0036 GJ (physical constant)
            'expected_uom': 'kWh',
        }

        factor_map[year] = year_factors

    return factor_map


def apply_emissions_to_df(agg_df, year_factor_map, fy_col='FY'):
    """Apply emission calculations to a DataFrame using NGA factors.

    Shared logic used by both loader_data.py (actuals) and projections.py
    (budget/forecast).  Uses the NGAFuel column to match factors from NGA CSV.

    Universal calculation (all fuels, no unit conversion needed):
        tCO2-e = Quantity * kgCO2-e_per_unit / 1000
        Energy_GJ = Quantity * GJ_per_native_unit

    Args:
        agg_df: DataFrame with columns: Description, NGAFuel, UOM, Quantity, and fy_col
        year_factor_map: Dict from build_year_factor_map()
        fy_col: Name of the FY column (default 'FY')

    Returns:
        DataFrame with Scope1_tCO2e, Scope2_tCO2e, Scope3_tCO2e, Energy_GJ added
    """
    import logging
    logger = logging.getLogger(__name__)

    # Initialise emission and energy columns
    agg_df['Scope1_tCO2e'] = 0.0
    agg_df['Scope2_tCO2e'] = 0.0
    agg_df['Scope3_tCO2e'] = 0.0
    agg_df['Energy_GJ'] = 0.0

    # Skip rows with no NGAFuel (production data, non-energy items)
    has_fuel = agg_df['NGAFuel'].notna() & (agg_df['NGAFuel'] != '')
    if not has_fuel.any():
        return agg_df

    fuel_values = agg_df.loc[has_fuel, 'NGAFuel'].unique()

    for nga_fuel in fuel_values:
        mask = has_fuel & (agg_df['NGAFuel'] == nga_fuel)
        if not mask.any():
            continue

        # Find matching factor key (startswith match)
        sample_year = agg_df.loc[mask, fy_col].iloc[0]
        year_factors = year_factor_map.get(sample_year)
        if year_factors is None:
            logger.warning(f"No factors for FY{sample_year}, skipping {nga_fuel}")
            continue

        # Match NGAFuel to factor key: exact match first, then longest prefix
        # Ensures 'Diesel oil-Cars...' matches transport, not stationary 'Diesel oil'
        factor_key = None
        if nga_fuel in year_factors:
            factor_key = nga_fuel
        else:
            # Longest key that is a prefix of nga_fuel
            prefixes = [(k, len(k)) for k in year_factors if nga_fuel.startswith(k)]
            if prefixes:
                factor_key = max(prefixes, key=lambda x: x[1])[0]
            else:
                # nga_fuel is a prefix of a key (truncated name in data)
                reverse = [k for k in year_factors if k.startswith(nga_fuel)]
                if reverse:
                    factor_key = reverse[0]

        if factor_key is None:
            logger.warning(f"No factor match for NGAFuel='{nga_fuel}', skipping")
            continue

        # UOM validation
        expected_uom = year_factors[factor_key].get('expected_uom', '')
        if expected_uom and 'UOM' in agg_df.columns:
            actual_uoms = agg_df.loc[mask, 'UOM'].unique()
            for uom in actual_uoms:
                if uom != expected_uom:
                    logger.error(
                        f"UOM MISMATCH: {nga_fuel} has UOM='{uom}' but NGA expects "
                        f"'{expected_uom}'.  Emissions will be WRONG for these rows."
                    )

        # Apply factors per year
        for year in agg_df.loc[mask, fy_col].unique():
            ymask = mask & (agg_df[fy_col] == year)
            if not ymask.any():
                continue

            yf = year_factor_map.get(year, {}).get(factor_key)
            if yf is None:
                logger.warning(f"No factors for {factor_key} in FY{year}")
                continue

            qty = agg_df.loc[ymask, 'Quantity']

            # Universal: tCO2-e = qty * kgCO2-e/unit / 1000
            if yf['s1']:
                agg_df.loc[ymask, 'Scope1_tCO2e'] = qty * yf['s1'] / 1000
            if yf['s2']:
                agg_df.loc[ymask, 'Scope2_tCO2e'] = qty * yf['s2'] / 1000
            if yf['s3']:
                agg_df.loc[ymask, 'Scope3_tCO2e'] = qty * yf['s3'] / 1000

            # Energy: GJ = qty * GJ/native-unit
            if yf['energy']:
                agg_df.loc[ymask, 'Energy_GJ'] = qty * yf['energy']

    return agg_df