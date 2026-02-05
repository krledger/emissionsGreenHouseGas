"""
emissions_calc.py
Emissions calculation functions for Ravenswood Gold
Last updated: 2026-02-02 10:00 AEST

================================================================================
AUDIT DOCUMENTATION
================================================================================

PURPOSE:
This file contains ALL emissions calculations used in the Safeguard Mechanism
Model and NGER reporting for Ravenswood Gold Mine operations.

REGULATORY BASIS:
- National Greenhouse and Energy Reporting Act 2007 (NGER Act)
- NGER (Measurement) Determination 2008
- Safeguard Mechanism Rule 2015 (amended 2023)
- Clean Energy Regulator guidance documents

DATA SOURCES:
1. National Greenhouse Account (NGA) Factors
   - Published annually by Department of Climate Change, Energy, the Environment and Water (DCCEEW)
   - Excel files: nationalgreenhouseaccountfactors{YYYY}.xlsx
   - Available years: 2021, 2022, 2023, 2024, 2025
   - Contains emission factors for all fuel types and electricity by state/territory

2. Pronto ERP System
   - Inventory transactions for fuel purchases and consumption
   - Department and cost centre allocations
   - Monthly reconciliation with physical stocktakes

3. Mined to Mill Reconciliation
   - Monthly ROM (Run of Mine) production in tonnes
   - Reconciles geology model with processing plant feed
   - Source: Dec{YY}_Mined_2_Mill_Recon.xlsx files

4. NPI-NGERS Reports
   - Historical s19 reports submitted to Clean Energy Regulator
   - Annual data from FY2009 to present
   - Used for validation and trend analysis

EMISSION SCOPES:
- Scope 1 (Direct): Fuel combustion from mobile equipment and generators
- Scope 2 (Indirect): Purchased electricity (grid-supplied)
- Scope 3 (Other): Transmission and distribution losses from electricity

INTENSITY CALCULATIONS:
Two primary intensity metrics are used for Safeguard Mechanism compliance:

1. MINING INTENSITY (tCOâ‚‚-e per tonne ROM)
   - Emissions from mobile equipment diesel divided by ore mined
   - Formula: (Mobile Diesel ML Ã— 1,000,000 L/ML Ã— EF kg COâ‚‚-e/L) Ã· (ROM tonnes Ã— 1000 kg/t)
   - Emission Factor (EF): From NGA Factors Table 1 - Stationary Energy
   - Typically 2.68 kg COâ‚‚-e/L for diesel (varies slightly by year)

2. POWER GENERATION INTENSITY (tCOâ‚‚-e per MWh)
   - Emissions from power generation diesel divided by electricity generated
   - Formula: (Power Diesel ML Ã— 1,000,000 L/ML Ã— EF kg COâ‚‚-e/L) Ã· (MWh Ã— 1000 kg/t)
   - Used in baseline calculation for grid connection scenario

SAFEGUARD BASELINE:
Facility-Specific Emission Intensity (FSEI) comprises:
- ROM Component: 0.0177 tCOâ‚‚-e/t (mining operations)
- Electricity Component: 0.9081 tCOâ‚‚-e/MWh Ã— site generation ratio
- Site Generation Ratio: 0.008735 MWh/t (8.735 kWh per tonne ROM)
- Total Baseline: 0.02563 tCOâ‚‚-e/t (approved by Clean Energy Regulator)
- Decline Rate: 4.9% per annum from FY2024 baseline to FY2030

UNIT CONVERSIONS:
- Megalitres (ML) to Litres (L): Ã— 1,000,000
- Kilograms (kg) to Tonnes (t): Ã· 1,000
- Megatonnes (Mt) to Tonnes (t): Ã— 1,000,000
- Kilowatt-hours (kWh) to Megawatt-hours (MWh): Ã· 1,000

CRITICAL ASSUMPTIONS:
1. Diesel emission factor remains constant within each reporting year
2. ROM production figures are reconciled and verified monthly
3. Electricity consumption measured by calibrated meters (Â±2% accuracy)
4. Mobile equipment efficiency remains stable year-over-year
5. Grid connection occurs FY2027 (2% diesel backup, 98% grid supply)

FILE DEPENDENCIES:
- config.py: Configuration constants, category mappings, cutoff dates
- loader_nga.py: NGA factor file loading and emission factor lookup
- loader_data.py: Pronto ERP and Mined to Mill data processing

OUTPUT DATA:
All functions return pandas DataFrames or Series with calculated:
- Scope 1, 2, 3 emissions in tCOâ‚‚-e
- Emission intensities in tCOâ‚‚-e/t or tCOâ‚‚-e/MWh
- Monthly and annual aggregations
- Department and cost centre breakdowns

CHANGE LOG:
- 2026-01-31: Added comprehensive audit documentation
- 2026-01-28: Implemented grid connection logic for FY2027+
- 2026-01-20: Added FY2025 NGA factors support
- 2025-12-15: Refactored for Budget Prime architecture

================================================================================
"""

import pandas as pd
import numpy as np
from config import CATEGORY_MAP, MATURITY_CUTOFF


# =============================================================================
# INTENSITY CALCULATION FUNCTIONS
# =============================================================================
# These functions calculate emission intensities per unit of production.
# Used for Safeguard Mechanism baseline calculations and tracking performance
# against regulatory targets.
# =============================================================================

def calculate_mining_intensity(mobile_diesel_ml, rom_tonnes):
    """
    Calculate mining emission intensity per tonne of Run of Mine (ROM) ore.

    REGULATORY CONTEXT:
    This is a key metric for Safeguard Mechanism compliance. The approved
    facility-specific emission intensity (FSEI) ROM component is 0.0177 tCOâ‚‚-e/t.
    Actual intensity must remain below baseline Ã— (1 - decline_rate)^years to
    generate Safeguard Mechanism Credits (SMCs).

    CALCULATION METHOD:
    Step 1: Convert megalitres to litres: ML Ã— 1,000,000
    Step 2: Apply emission factor: L Ã— 2.68 kg COâ‚‚-e/L (from NGA Factors)
    Step 3: Convert kg to tonnes: kg Ã· 1,000
    Step 4: Divide by ROM production: tCOâ‚‚-e Ã· tonnes

    Formula: (Mobile Diesel ML Ã— 1,000,000 L/ML Ã— 2.68 kg COâ‚‚-e/L) / (ROM tonnes Ã— 1000 kg/t)

    EMISSION FACTOR SOURCE:
    NGA Factors Table 1 - Stationary Energy (Combustion)
    Diesel fuel: ~2.68 kg COâ‚‚-e/L (slight variation by year)
    Includes COâ‚‚, CHâ‚„, and Nâ‚‚O in COâ‚‚-e using 100-year GWPs

    TYPICAL VALUES:
    - Mobile diesel: 5-15 ML per month
    - ROM production: 250,000 - 500,000 tonnes per month
    - Resulting intensity: 0.015 - 0.020 tCOâ‚‚-e/t

    EDGE CASES:
    - If ROM = 0: Returns 0.0 (avoids division by zero)
    - Handles both scalar (float) and vector (Series) inputs

    Args:
        mobile_diesel_ml: Mobile equipment diesel consumption in megalitres
                         Type: float or pandas.Series
        rom_tonnes: ROM ore production in tonnes
                   Type: float or pandas.Series

    Returns:
        float or pandas.Series: Mining intensity in tCOâ‚‚-e per tonne ROM
                               Returns 0.0 when rom_tonnes is 0 or negative

    Example:
        >>> calculate_mining_intensity(10.5, 400000)
        0.01827  # tCOâ‚‚-e/t
    """
    # Handle pandas Series (vectorized calculation for multiple periods)
    if isinstance(rom_tonnes, pd.Series):
        # Initialize result series with zeros
        result = pd.Series(0.0, index=rom_tonnes.index)

        # Only calculate where ROM > 0 to avoid division by zero
        mask = rom_tonnes > 0

        # Calculate emissions: ML â†’ L â†’ kg COâ‚‚-e â†’ t COâ‚‚-e
        mobile_emissions = mobile_diesel_ml * 1000000 * 2.68 / 1000  # ML to tCOâ‚‚-e

        # Calculate intensity only for valid periods
        result[mask] = mobile_emissions[mask] / rom_tonnes[mask]
        return result

    # Handle scalar (single period calculation)
    else:
        if rom_tonnes > 0:
            # Calculate emissions: ML â†’ L â†’ kg COâ‚‚-e â†’ t COâ‚‚-e
            mobile_emissions = mobile_diesel_ml * 1000000 * 2.68 / 1000
            return mobile_emissions / rom_tonnes
        return 0.0


def calculate_mining_intensity_from_mt(mobile_diesel_ml, rom_mt):
    """
    Calculate mining intensity: tCOÃ¢â€šâ€š-e per tonne of ROM (accepts Mt input)

    Convenience wrapper that converts Mt to tonnes before calculation

    Args:
        mobile_diesel_ml: Mobile equipment diesel in megalitres (float or Series)
        rom_mt: ROM production in megatonnes (float or Series)

    Returns:
        float or Series: Mining intensity in tCOÃ¢â€šâ€š-e/t ROM (0 if rom_mt is 0)
    """
    rom_tonnes = rom_mt * 1000000  # Mt to tonnes
    return calculate_mining_intensity(mobile_diesel_ml, rom_tonnes)


def calculate_power_intensity(power_diesel_ml, electricity_mwh):
    """
    Calculate power generation emission intensity per megawatt-hour of electricity.

    REGULATORY CONTEXT:
    Used in Safeguard baseline calculation for electricity component. The approved
    facility-specific emission intensity (FSEI) electricity component is 0.9081 tCOâ‚‚-e/MWh.
    After grid connection (FY2027), this intensity drops to near-zero as site generation
    reduces to 2% backup only.

    CALCULATION METHOD:
    Step 1: Convert megalitres to litres: ML Ã— 1,000,000
    Step 2: Apply emission factor: L Ã— 2.68 kg COâ‚‚-e/L (from NGA Factors)
    Step 3: Convert kg to tonnes: kg Ã· 1,000
    Step 4: Divide by electricity generated: tCOâ‚‚-e Ã· MWh

    Formula: (Power Diesel ML Ã— 1,000,000 L/ML Ã— 2.68 kg COâ‚‚-e/L) / (MWh Ã— 1000 kg/t)

    EMISSION FACTOR SOURCE:
    NGA Factors Table 1 - Stationary Energy (Combustion)
    Diesel fuel: ~2.68 kg COâ‚‚-e/L
    Same factor as mobile diesel (fuel type determines factor, not end use)

    SITE GENERATION CONTEXT:
    - Current (pre-grid): 100% diesel generation
    - Site generation ratio: 0.008735 MWh/t ROM (8.735 kWh/t)
    - Monthly generation: 2,000 - 4,000 MWh
    - Post-grid (FY2027+): 2% diesel backup, 98% grid purchase

    TYPICAL VALUES:
    - Power diesel: 0.8 - 1.2 ML per month (100% generation)
    - Electricity generated: 2,500 - 3,500 MWh per month
    - Resulting intensity: 0.85 - 0.95 tCOâ‚‚-e/MWh

    EDGE CASES:
    - If MWh = 0: Returns 0.0 (avoids division by zero)
    - Post-grid: Very low values due to minimal diesel usage
    - Handles both scalar (float) and vector (Series) inputs

    Args:
        power_diesel_ml: Power generation diesel consumption in megalitres
                        Type: float or pandas.Series
        electricity_mwh: Site-generated electricity in megawatt-hours
                        Type: float or pandas.Series

    Returns:
        float or pandas.Series: Power intensity in tCOâ‚‚-e per MWh generated
                               Returns 0.0 when electricity_mwh is 0 or negative

    Example:
        >>> calculate_power_intensity(1.0, 3000)
        0.8933  # tCOâ‚‚-e/MWh
    """
    # Handle pandas Series (vectorized calculation for multiple periods)
    if isinstance(electricity_mwh, pd.Series):
        # Initialize result series with zeros
        result = pd.Series(0.0, index=electricity_mwh.index)

        # Only calculate where electricity > 0 to avoid division by zero
        mask = electricity_mwh > 0

        # Calculate emissions: ML â†’ L â†’ kg COâ‚‚-e â†’ t COâ‚‚-e
        power_emissions = power_diesel_ml * 1000000 * 2.68 / 1000  # ML to tCOâ‚‚-e

        # Calculate intensity only for valid periods
        result[mask] = power_emissions[mask] / electricity_mwh[mask]
        return result

    # Handle scalar (single period calculation)
    else:
        if electricity_mwh > 0:
            # Calculate emissions: ML â†’ L â†’ kg COâ‚‚-e â†’ t COâ‚‚-e
            power_emissions = power_diesel_ml * 1000000 * 2.68 / 1000
            return power_emissions / electricity_mwh
        return 0.0


# =============================================================================
# UNIT CONVERSION FUNCTIONS
# =============================================================================

def convert_litres_to_megalitres(litres):
    """
    Convert litres to megalitres

    Conversion Factor: 1 ML = 1,000,000 L

    Regulatory Reference:
    - Standard SI unit conversion
    - Large fuel volumes reported in ML

    Args (vectorized):
        litres: Volume in litres (float, array, or Series)

    Returns (vectorized):
        float, array, or Series: Volume in megalitres

    Example:
        >>> convert_litres_to_megalitres(5000000)
        5.0
        >>> convert_litres_to_megalitres(np.array([1000000, 2000000, 3000000]))
        array([1., 2., 3.])
    """
    return litres / 1000000


def convert_litres_to_kilolitres(litres):
    """
    Convert litres to kilolitres

    Conversion Factor: 1 kL = 1,000 L

    Regulatory Reference:
    - Standard SI unit conversion
    - NGER reports typically use kL for liquid fuels

    Args (vectorized):
        litres: Volume in litres (float, array, or Series)

    Returns (vectorized):
        float, array, or Series: Volume in kilolitres

    Example:
        >>> convert_litres_to_kilolitres(5000)
        5.0
        >>> convert_litres_to_kilolitres(np.array([1000, 2000, 3000]))
        array([1., 2., 3.])

    Note:
        Vectorized - works with scalars, numpy arrays, or pandas Series
    """
    return np.divide(litres, 1000.0)


def convert_kwh_to_mwh(kwh):
    """
    Convert kilowatt-hours to megawatt-hours

    Conversion Factor: 1 MWh = 1,000 kWh

    Regulatory Reference:
    - Standard SI unit conversion
    - NGER reports use MWh for electricity

    Args (vectorized):
        kwh: Energy in kilowatt-hours (float, array, or Series)

    Returns (vectorized):
        float, array, or Series: Energy in megawatt-hours

    Example:
        >>> convert_kwh_to_mwh(250000)
        250.0
        >>> convert_kwh_to_mwh(np.array([100000, 200000]))
        array([100., 200.])

    Note:
        Vectorized - works with scalars, numpy arrays, or pandas Series
    """
    return np.divide(kwh, 1000.0)


def convert_kg_to_tonnes(kg):
    """
    Convert kilograms to tonnes

    Conversion Factor: 1 tonne = 1,000 kg

    Regulatory Reference:
    - Standard SI unit conversion
    - NGER reports emissions in tCO2-e (tonnes)

    Args (vectorized):
        kg: Mass in kilograms (float, array, or Series)

    Returns (vectorized):
        float, array, or Series: Mass in tonnes

    Example:
        >>> convert_kg_to_tonnes(2500)
        2.5
        >>> convert_kg_to_tonnes(np.array([1000, 2000]))
        array([1., 2.])

    Note:
        Vectorized - works with scalars, numpy arrays, or pandas Series
    """
    return np.divide(kg, 1000.0)


# =============================================================================
# SCOPE 1 EMISSIONS CALCULATIONS
# =============================================================================

def calculate_scope1_diesel(quantity_litres, nga_factor_kg_per_litre):
    """
    Calculate Scope 1 emissions from diesel consumption

    Methodology (NGER Method 1):
    1. Apply NGA emission factor (kgCO2-e per litre)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 1 (Transport fuels)
    - Factor: "Diesel oil" in kgCO2-e/L
    - Includes CO2, CH4, N2O emissions

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.24
    - Method 1: Default emission factors

    Args (vectorized):
        quantity_litres: Diesel quantity in litres (scalar, array, or Series)
        nga_factor_kg_per_litre: NGA emission factor in kgCO2-e/L (scalar or array)

    Returns (vectorized):
        float, array, or Series: Scope 1 emissions in tCO2-e

    Example:
        >>> calculate_scope1_diesel(1000, 2.68446)
        2.68446
        >>> calculate_scope1_diesel(np.array([1000, 2000]), 2.68446)
        array([2.68446, 5.36892])

    Note:
        Vectorized - works with scalars, numpy arrays, or pandas Series.
        Purpose-specific factors (transport, stationary, electricity generation)
        use the same base factor but may be classified differently for NGER reporting.
    """
    kg_co2e = quantity_litres * nga_factor_kg_per_litre
    return convert_kg_to_tonnes(kg_co2e)


def calculate_scope1_lpg(quantity_kg, nga_factor_kg_per_kg):
    """
    Calculate Scope 1 emissions from LPG consumption

    Methodology (NGER Method 1):
    1. Apply NGA emission factor (kgCO2-e per kg)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 1 (Transport fuels)
    - Factor: "Liquefied petroleum gas" in kgCO2-e/kg

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.24

    Args (vectorized):
        quantity_kg: LPG quantity in kilograms
        nga_factor_kg_per_kg: NGA emission factor (kgCO2-e/kg)

    Returns (vectorized):
        float, array, or Series: Scope 1 emissions in tCO2-e

    Example:
        >>> calculate_scope1_lpg(500, 2.99312)
        1.49656
    """
    kg_co2e = quantity_kg * nga_factor_kg_per_kg
    return convert_kg_to_tonnes(kg_co2e)


def calculate_scope1_petrol(quantity_litres, nga_factor_kg_per_litre):
    """
    Calculate Scope 1 emissions from petrol/gasoline consumption

    Methodology (NGER Method 1):
    1. Apply NGA emission factor (kgCO2-e per litre)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 1 (Transport fuels)
    - Factor: "Automotive gasoline/petrol" in kgCO2-e/L

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.24

    Args (vectorized):
        quantity_litres: Petrol quantity in litres
        nga_factor_kg_per_litre: NGA emission factor (kgCO2-e/L)

    Returns (vectorized):
        float, array, or Series: Scope 1 emissions in tCO2-e

    Example:
        >>> calculate_scope1_petrol(1000, 2.28998)
        2.28998
    """
    kg_co2e = quantity_litres * nga_factor_kg_per_litre
    return convert_kg_to_tonnes(kg_co2e)


def calculate_scope1_oils(quantity_litres, nga_factor_kg_per_litre):
    """
    Calculate Scope 1 emissions from petroleum oils consumption

    Methodology (NGER Method 1):
    1. Apply NGA emission factor (kgCO2-e per litre)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 1 (Industrial fuels)
    - Factor: "Petroleum based oils" in kgCO2-e/L

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.24

    Args (vectorized):
        quantity_litres: Oil quantity in litres
        nga_factor_kg_per_litre: NGA emission factor (kgCO2-e/L)

    Returns (vectorized):
        float, array, or Series: Scope 1 emissions in tCO2-e

    Example:
        >>> calculate_scope1_oils(100, 2.84)
        0.284
    """
    kg_co2e = quantity_litres * nga_factor_kg_per_litre
    return convert_kg_to_tonnes(kg_co2e)


def calculate_scope1_greases(quantity_kg, nga_factor_kg_per_kg):
    """
    Calculate Scope 1 emissions from petroleum greases consumption

    Methodology (NGER Method 1):
    1. Apply NGA emission factor (kgCO2-e per kg)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 1 (Industrial fuels)
    - Factor: "Petroleum based greases" in kgCO2-e/kg

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.24

    Args (vectorized):
        quantity_kg: Grease quantity in kilograms
        nga_factor_kg_per_kg: NGA emission factor (kgCO2-e/kg)

    Returns (vectorized):
        float, array, or Series: Scope 1 emissions in tCO2-e

    Example:
        >>> calculate_scope1_greases(50, 3.07)
        0.1535
    """
    kg_co2e = quantity_kg * nga_factor_kg_per_kg
    return convert_kg_to_tonnes(kg_co2e)


def calculate_scope1_acetylene(quantity_m3, nga_factor_kg_per_m3):
    """
    Calculate Scope 1 emissions from acetylene gas consumption

    Methodology (NGER Method 1):
    1. Apply NGA emission factor (kgCO2-e per mÃ‚Â³)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 1 (Gaseous fuels)
    - Factor: "Other gaseous fossil fuels" (acetylene) in kgCO2-e/mÃ‚Â³

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.24

    Args (vectorized):
        quantity_m3: Acetylene quantity in cubic metres
        nga_factor_kg_per_m3: NGA emission factor (kgCO2-e/mÃ‚Â³)

    Returns (vectorized):
        float, array, or Series: Scope 1 emissions in tCO2-e

    Example:
        >>> calculate_scope1_acetylene(10, 2.34)
        0.0234
    """
    kg_co2e = quantity_m3 * nga_factor_kg_per_m3
    return convert_kg_to_tonnes(kg_co2e)


# =============================================================================
# SCOPE 2 EMISSIONS CALCULATIONS
# =============================================================================

def calculate_scope2_grid_electricity(quantity_mwh, nga_factor_t_per_mwh):
    """
    Calculate Scope 2 emissions from purchased grid electricity

    Methodology (NGER):
    1. Apply state-specific NGA emission factor (tCO2-e per MWh)
    2. Return result in tonnes

    Emission Factor Source:
    - NGA Factors Table 6 (State-based grid electricity)
    - Factor: State-specific factor (e.g., Queensland) in tCO2-e/MWh
    - Factors updated annually based on grid generation mix

    Regulatory Reference:
    - NGER (Measurement) Determination 2008, Section 2.76
    - Scope 2 emissions from purchased electricity

    Args (vectorized):
        quantity_mwh: Electricity consumed in megawatt-hours
        nga_factor_t_per_mwh: NGA emission factor (tCO2-e/MWh) - standard units

    Returns (vectorized):
        float, array, or Series: Scope 2 emissions in tCO2-e

    Example:
        >>> calculate_scope2_grid_electricity(1000, 0.79)
        790.0

    Note:
        Queensland grid factor ~0.67-0.79 tCO2-e/MWh depending on year
        On-site generation does NOT contribute to Scope 2
    """
    return quantity_mwh * nga_factor_t_per_mwh


# =============================================================================
# SCOPE 3 EMISSIONS CALCULATIONS
# =============================================================================

def calculate_scope3_diesel(quantity_litres, nga_factor_kg_per_litre):
    """
    Calculate Scope 3 emissions from diesel extraction and refining

    Methodology:
    1. Apply NGA upstream emission factor (kgCO2-e per litre)
    2. Convert result from kg to tonnes

    Emission Factor Source:
    - NGA Factors Table 5 (Upstream emissions)
    - Factor: Diesel oil extraction and refining in kgCO2-e/L

    Regulatory Reference:
    - Not required for NGER reporting
    - Voluntary disclosure for Scope 3 Category 3 (upstream fuel)

    Args (vectorized):
        quantity_litres: Diesel quantity in litres
        nga_factor_kg_per_litre: NGA Scope 3 emission factor (kgCO2-e/L)

    Returns (vectorized):
        float, array, or Series: Scope 3 emissions in tCO2-e

    Example:
        >>> calculate_scope3_diesel(1000, 0.452)
        0.452
    """
    kg_co2e = quantity_litres * nga_factor_kg_per_litre
    return convert_kg_to_tonnes(kg_co2e)


def calculate_scope3_grid_electricity(quantity_mwh, nga_factor_t_per_mwh):
    """
    Calculate Scope 3 emissions from grid electricity transmission losses

    Methodology:
    1. Apply NGA transmission/distribution loss factor (tCO2-e per MWh)
    2. Return result in tonnes

    Emission Factor Source:
    - NGA Factors Table 6 (Grid electricity transmission losses)
    - Factor: State-specific transmission loss factor in tCO2-e/MWh

    Regulatory Reference:
    - Not required for NGER reporting
    - Voluntary disclosure for Scope 3 Category 3 (upstream electricity)

    Args (vectorized):
        quantity_mwh: Electricity consumed in megawatt-hours
        nga_factor_t_per_mwh: NGA Scope 3 emission factor (tCO2-e/MWh) - standard units

    Returns (vectorized):
        float, array, or Series: Scope 3 emissions in tCO2-e

    Example:
        >>> calculate_scope3_grid_electricity(1000, 0.0643)
        64.3
    """
    return quantity_mwh * nga_factor_t_per_mwh


# =============================================================================
# BASELINE AND SAFEGUARD CALCULATIONS
# =============================================================================


def summarise_energy(energy_df, baseline_fy=None, annualize_partial=True):
    """Summarise energy consumption and emissions by cost centre

    Args (vectorized):
        energy_df: DataFrame from load_energy_data()
        baseline_fy: Financial year to use as baseline
        annualize_partial: If True, scale partial years to 12 months (default True)

    Returns (vectorized):
        Dict with energy summaries by FY and cost centre
    """
    if baseline_fy is None:
        baseline_fy = energy_df['FY'].max()

    # =======================
    # FY TOTALS WITH OPTIONAL ANNUALIZATION
    # =======================

    by_fy = {}
    for fy in energy_df['FY'].unique():
        fy_data = energy_df[energy_df['FY'] == fy]
        months = fy_data['Month'].nunique()

        # Calculate actual values from new detailed structure
        fuel_litres_actual = (fy_data['Diesel_Electricity_L'].sum() +
                             fy_data['Diesel_Transport_L'].sum() +
                             fy_data['Diesel_Stationary_L'].sum() +
                             fy_data['Diesel_Explosives_L'].sum())
        fuel_kL_actual = fy_data['Diesel_Total_kL'].sum()
        grid_kwh_actual = fy_data['GridPower_kWh'].sum()
        grid_mwh_actual = fy_data['GridPower_MWh'].sum()
        site_kwh_actual = fy_data['SitePower_kWh'].sum()
        site_mwh_actual = fy_data['SitePower_MWh'].sum()
        scope1_actual = fy_data['Total_Scope1_tCO2e'].sum()
        scope2_actual = fy_data['Total_Scope2_tCO2e'].sum()
        scope3_actual = fy_data['Total_Scope3_tCO2e'].sum()

        # Apply annualization if requested and partial year
        if annualize_partial and months < 12 and months > 0:
            scale_factor = 12.0 / months
            by_fy[fy] = {
                'fuel_litres': fuel_litres_actual * scale_factor,
                'fuel_kL': fuel_kL_actual * scale_factor,
                'grid_kwh': grid_kwh_actual * scale_factor,
                'grid_mwh': grid_mwh_actual * scale_factor,
                'site_kwh': site_kwh_actual * scale_factor,
                'site_mwh': site_mwh_actual * scale_factor,
                'scope1_fuel': scope1_actual * scale_factor,
                'scope2_grid': scope2_actual * scale_factor,
                'scope3_fuel': scope3_actual * scale_factor,  # Now includes all scope 3
                'scope3_grid': 0,  # Included in scope3_fuel above
                'months_actual': months,
                'is_complete': False,
                'is_annualized': True,
                'scale_factor': scale_factor
            }
        else:
            by_fy[fy] = {
                'fuel_litres': fuel_litres_actual,
                'fuel_kL': fuel_kL_actual,
                'grid_kwh': grid_kwh_actual,
                'grid_mwh': grid_mwh_actual,
                'site_kwh': site_kwh_actual,
                'site_mwh': site_mwh_actual,
                'scope1_fuel': scope1_actual,
                'scope2_grid': scope2_actual,
                'scope3_fuel': scope3_actual,  # Now includes all scope 3
                'scope3_grid': 0,  # Included in scope3_fuel above
                'months_actual': months,
                'is_complete': months == 12,
                'is_annualized': False,
                'scale_factor': 1.0
            }

    # =======================
    # BASELINE YEAR BY COST CENTRE WITH OPTIONAL ANNUALIZATION
    # =======================

    fy_data = energy_df[energy_df['FY'] == baseline_fy]
    months = fy_data['Month'].nunique()

    # Apply scaling factor if annualizing partial year
    if annualize_partial and months < 12 and months > 0:
        scale_factor = 12.0 / months
    else:
        scale_factor = 1.0

    # Aggregate by cost centre with new column structure
    agg_dict = {
        'Diesel_Electricity_L': 'sum',
        'Diesel_Transport_L': 'sum',
        'Diesel_Stationary_L': 'sum',
        'Diesel_Explosives_L': 'sum',
        'Diesel_Total_kL': 'sum',
        'GridPower_kWh': 'sum',
        'GridPower_MWh': 'sum',
        'SitePower_kWh': 'sum',
        'SitePower_MWh': 'sum',
        'Total_Scope1_tCO2e': 'sum',
        'Total_Scope2_tCO2e': 'sum',
        'Total_Scope3_tCO2e': 'sum'
    }

    by_cc = fy_data.groupby('Costcentre').agg(agg_dict).reset_index()

    # Create simplified column names for backward compatibility
    by_cc['Fuel'] = (by_cc['Diesel_Electricity_L'] + by_cc['Diesel_Transport_L'] +
                     by_cc['Diesel_Stationary_L'] + by_cc['Diesel_Explosives_L'])
    by_cc['Fuel_kL'] = by_cc['Diesel_Total_kL']
    by_cc['GridPower'] = by_cc['GridPower_kWh']
    by_cc['SitePower'] = by_cc['SitePower_kWh']

    # Apply scale factor to all numeric columns
    numeric_cols = by_cc.select_dtypes(include=['number']).columns
    by_cc[numeric_cols] = by_cc[numeric_cols] * scale_factor

    # Add metadata
    by_cc['Months_Actual'] = months
    by_cc['Is_Annualized'] = (scale_factor != 1.0)

    # Add category
    by_cc['Category'] = by_cc['Costcentre'].map(CATEGORY_MAP).fillna('Fixed')

    # Calculate totals
    by_cc['Total_tCO2e_S1'] = by_cc['Total_Scope1_tCO2e']
    by_cc['Total_tCO2e_S2'] = by_cc['Total_Scope2_tCO2e']
    by_cc['Total_tCO2e_S3'] = by_cc['Total_Scope3_tCO2e']
    by_cc['Total_tCO2e'] = by_cc['Total_tCO2e_S1'] + by_cc['Total_tCO2e_S2'] + by_cc['Total_tCO2e_S3']

    # Percentages
    total_fuel = by_cc['Fuel'].sum()
    total_grid = by_cc['GridPower'].sum()

    by_cc['Fuel_Pct'] = (by_cc['Fuel'] / total_fuel * 100) if total_fuel > 0 else 0
    by_cc['Grid_Pct'] = (by_cc['GridPower'] / total_grid * 100) if total_grid > 0 else 0

    # Sort by total emissions
    by_cc = by_cc.sort_values('Total_tCO2e', ascending=False)

    # =======================
    # SEASONAL PATTERNS
    # =======================

    mature = energy_df[energy_df['Date'] >= MATURITY_CUTOFF]
    seasonal_fuel = mature.groupby('Month')['Diesel_Total_kL'].mean().to_dict()
    seasonal_grid = mature.groupby('Month')['GridPower_MWh'].mean().to_dict()
    seasonal_site = mature.groupby('Month')['SitePower_MWh'].mean().to_dict()

    # =======================
    # RETURN SUMMARY
    # =======================

    return {
        'by_fy': by_fy,
        'by_costcentre': by_cc,
        'baseline_fy': baseline_fy,
        'baseline_data': by_fy.get(baseline_fy, {}),
        'seasonal_fuel': seasonal_fuel,
        'seasonal_grid': seasonal_grid,
        'seasonal_site': seasonal_site,
        'total_scope1': by_cc['Total_tCO2e_S1'].sum(),
        'total_scope2': by_cc['Total_tCO2e_S2'].sum(),
        'total_scope3': by_cc['Total_tCO2e_S3'].sum(),
    }


def summarise_rom(rom_df, annualize_partial=True):
    """Summarise ROM production by financial year

    Args (vectorized):
        rom_df: DataFrame from load_rom_data()
        annualize_partial: If True, scale partial years to 12 months (default True)

    Returns (vectorized):
        Dict with ROM totals by FY
    """
    by_fy = {}
    for fy in rom_df['FY'].unique():
        fy_data = rom_df[rom_df['FY'] == fy]
        months = fy_data['Month'].nunique()

        rom_actual = fy_data['ROM'].sum()

        # Apply annualization if requested and partial year
        if annualize_partial and months < 12 and months > 0:
            scale_factor = 12.0 / months
            rom_annualized = rom_actual * scale_factor
            by_fy[fy] = {
                'rom_tonnes': rom_annualized,
                'rom_tonnes_actual': rom_actual,
                'months_actual': months,
                'is_complete': False,
                'is_annualized': True,
                'scale_factor': scale_factor
            }
        else:
            by_fy[fy] = {
                'rom_tonnes': rom_actual,
                'rom_tonnes_actual': rom_actual,
                'months_actual': months,
                'is_complete': months == 12,
                'is_annualized': False,
                'scale_factor': 1.0
            }

    return by_fy


def calc_baseline(rom_tonnes, site_mwh, baseline_fy, fsei_rom=0.0177, fsei_elec=0.9081, apply_decline=False):
    """
    Calculate Safeguard Mechanism baseline emissions using FSEI methodology

    Methodology (Safeguard Mechanism):
    1. ROM component: ROM tonnes Ãƒâ€” FSEI_ROM
    2. Electricity component: Site generation MWh Ãƒâ€” FSEI_ELEC
    3. Total baseline = ROM component + Electricity component
    4. Optional: Apply decline rate (4.9% p.a. from FY2024)

    Facility-Specific Emission Intensity (FSEI):
    - FSEI_ROM: 0.0177 tCO2-e per tonne ROM (mining and processing emissions per tonne ore)
    - FSEI_ELEC: 0.9081 tCO2-e per MWh (onsite power generation emissions per MWh)
    - Calculated from FY2024 baseline year operational data
    - These are INDEPENDENT components, not normalized

    Decline Rate:
    - 4.9% per annum from FY2024 baseline
    - Applied cumulatively: (1 - 0.049)^(years_from_baseline)
    - Mandatory from FY2024 under amended Safeguard Mechanism

    Regulatory Reference:
    - Safeguard Mechanism Rule 2015 (as amended 2023)
    - Production-adjusted baseline methodology
    - FSEI determination approved by Clean Energy Regulator

    Args (vectorized):
        rom_tonnes: ROM production in tonnes
        site_mwh: On-site electricity generation in MWh
        baseline_fy: Financial year for baseline calculation (e.g., 2024)
        fsei_rom: FSEI for ROM production (tCO2-e/t), default 0.0177
        fsei_elec: FSEI for electricity generation (tCO2-e/MWh), default 0.9081
        apply_decline: If True, apply 4.9% decline rate from FY2024

    Returns (vectorized):
        float, array, or Series: Baseline emissions in tCO2-e

    Example:
        >>> calc_baseline(9_130_000, 106_572, 2025, apply_decline=True)
        245_718  # Baseline for FY2025 with 4.9% decline from FY2024

    Calculation Detail (FY2025 example):
        ROM component:     9,130,000 t Ãƒâ€” 0.0177 = 161,601 tCO2-e
        Elec component:      106,572 MWh Ãƒâ€” 0.9081 = 96,778 tCO2-e
        Subtotal:                                   258,379 tCO2-e
        Decline factor (1 year): 0.951 (4.9% decline)
        Final baseline:    258,379 Ãƒâ€” 0.951 =        245,718 tCO2-e
    """
    from config import DECLINE_RATE, DECLINE_FROM, DECLINE_TO

    baseline = (rom_tonnes * fsei_rom) + (site_mwh * fsei_elec)

    if apply_decline and baseline_fy >= DECLINE_FROM and baseline_fy <= DECLINE_TO:
        years_since = baseline_fy - DECLINE_FROM
        decline_factor = (1 - DECLINE_RATE) ** years_since
        baseline *= decline_factor

    return baseline


def calculate_emissions(energy_df, fy, rom_tonnes, nga_factors, annualize_partial=True):
    """Calculate emissions for a specific financial year

    Args (vectorized):
        energy_df: DataFrame from load_energy_data()
        fy: Financial year - can be int (2024) or string ('FY2024')
        rom_tonnes: ROM production for the year (tonnes)
        nga_factors: Dict from load_nga_factors()
        annualize_partial: If True, scale partial years to 12 months (default True)

    Returns (vectorized):
        Dict with scope1, scope2, scope3, total emissions
        Returns None if no data exists for this FY
    """
    # Convert FY to integer if it's a string like "FY2024"
    if isinstance(fy, str):
        fy_int = int(fy.replace('FY', ''))
    else:
        fy_int = fy

    # Filter to the specific FY
    fy_data = energy_df[energy_df['FY'] == fy_int]

    if len(fy_data) == 0:
        # No data for this FY - return None, not zeros
        return None

    # Count actual months
    months = fy_data['Month'].nunique()

    # Calculate actual values using new detailed structure
    scope1_actual = fy_data['Total_Scope1_tCO2e'].sum()
    scope2_actual = fy_data['Total_Scope2_tCO2e'].sum()
    scope3_actual = fy_data['Total_Scope3_tCO2e'].sum()

    # Fuel breakdown for reporting
    fuel_kl_actual = fy_data['Diesel_Total_kL'].sum()
    grid_mwh_actual = fy_data['GridPower_MWh'].sum()
    site_mwh_actual = fy_data['SitePower_MWh'].sum()

    # Apply annualization if requested and partial year
    if annualize_partial and months < 12 and months > 0:
        scale_factor = 12.0 / months
        return {
            'scope1': scope1_actual * scale_factor,
            'scope2': scope2_actual * scale_factor,
            'scope3': scope3_actual * scale_factor,
            'total': (scope1_actual + scope2_actual + scope3_actual) * scale_factor,
            'fuel_kl': fuel_kl_actual * scale_factor,
            'grid_mwh': grid_mwh_actual * scale_factor,
            'site_mwh': site_mwh_actual * scale_factor,
            'rom_tonnes': rom_tonnes,
            'months_actual': months,
            'is_complete': False,
            'is_annualized': True,
            'scale_factor': scale_factor
        }
    else:
        return {
            'scope1': scope1_actual,
            'scope2': scope2_actual,
            'scope3': scope3_actual,
            'total': scope1_actual + scope2_actual + scope3_actual,
            'fuel_kl': fuel_kl_actual,
            'grid_mwh': grid_mwh_actual,
            'site_mwh': site_mwh_actual,
            'rom_tonnes': rom_tonnes,
            'months_actual': months,
            'is_complete': months == 12,
            'is_annualized': False,
            'scale_factor': 1.0
        }