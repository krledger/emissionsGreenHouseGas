"""
CalcEmissions.py
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
    LoaderNga.py: NGAFactorsByYear class for factor lookup
"""

import pandas as pd
import numpy as np

from CalcUnits import (UnitError, factor as uom_factor,
                       KG_PER_TONNE_CO2E, GJ_PER_KWH)


# =============================================================================
# ACTUAL OVER BUDGET
# =============================================================================
# One implementation of the supersession rule, used by the projection, the
# Scope 3 build and every view.  A recorded month replaces the budget for the
# same line, so a period that is part recorded and part forecast is counted
# once.  Written as index arithmetic rather than a test per row, because the
# budget frame runs to several hundred thousand rows.


def _pair_codes(actuals, budget, key_col):
    """Integer code per (Date, key) pair, shared across the two frames."""
    keys = pd.concat([actuals[key_col], budget[key_col]],
                     ignore_index=True).astype(str)
    dates = pd.concat([actuals['Date'], budget['Date']], ignore_index=True)
    key_codes = pd.factorize(keys)[0].astype('int64')
    date_codes = pd.factorize(dates)[0].astype('int64')
    return date_codes * (key_codes.max() + 1) + key_codes


def merge_key_column(frame):
    """Column the supersession rule matches on."""
    return 'MatchKey' if 'MatchKey' in frame.columns else 'SubActivity'


def superseded_by_actual(budget, actuals, key_col=None):
    """Boolean array over budget rows, true where an actual covers the line."""
    if len(budget) == 0:
        return np.zeros(len(budget), dtype=bool)
    if len(actuals) == 0:
        return np.zeros(len(budget), dtype=bool)
    key_col = key_col or merge_key_column(budget)
    pairs = _pair_codes(actuals, budget, key_col)
    split = len(actuals)
    return np.isin(pairs[split:], np.unique(pairs[:split]))


def dedupe_actual_over_budget(frame, dataset='Actual'):
    """Drop budget rows superseded by an actual on the same month and line."""
    if frame is None or len(frame) == 0 or 'DataSet' not in frame.columns:
        return frame
    is_actual = (frame['DataSet'] == dataset).to_numpy()
    is_budget = (frame['DataSet'] == 'Budget').to_numpy()
    if not is_actual.any() or not is_budget.any():
        return frame
    actuals = frame[is_actual]
    budget = frame[is_budget]
    keep = ~superseded_by_actual(budget, actuals)
    return pd.concat([actuals, budget[keep]], ignore_index=True)


def resolve_factor_key(nga_fuel, year_factors):
    """The factor a line is charged against, by name.

    Exact match first, then the longest key that is a prefix of the name, then
    a key the name is itself a prefix of.  The longest prefix rule is what
    keeps 'Diesel oil-Cars and light commercial vehicles' on the transport
    factor rather than falling back to the stationary 'Diesel oil'.

    Returns None where nothing matches.  A line that matches nothing is
    reported by name and contributes nothing; it is never charged against a
    neighbouring factor.

    Extracted so the emissions engine and the canonical table resolve a factor
    the same way, rather than each carrying its own copy of the rule.
    """
    if not nga_fuel:
        return None
    if nga_fuel in year_factors:
        return nga_fuel
    prefixes = [(k, len(k)) for k in year_factors if nga_fuel.startswith(k)]
    if prefixes:
        return max(prefixes, key=lambda pair: pair[1])[0]
    reverse = [k for k in year_factors if k.startswith(nga_fuel)]
    return reverse[0] if reverse else None


def build_year_factor_map(nga_by_year, unique_years, state='QLD'):
    """Build NGA emission factor lookup by FY year number.

    All factors come from NgaFactors.csv via the NGAFactorsByYear class.
    No hardcoded emission factors.  No unit conversions.

    Args:
        nga_by_year: NGAFactorsByYear instance (from LoaderNga.py)
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
    # These match NgaFactors.csv Fuel_Name via startswith.
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
            # Energy content of a kilowatt hour, from the unit table.
            'energy': GJ_PER_KWH,
            'expected_uom': 'kWh',
        }

        # Record which NGA publication year was actually used (for audit trail).
        # _resolve_year falls back to the latest available NGA year for future FYs.
        resolved_nga_year = nga_by_year._resolve_year(year)
        year_factors['_nga_year'] = resolved_nga_year

        factor_map[year] = year_factors

    return factor_map


def apply_emissions_to_df(agg_df, year_factor_map, fy_col='FY'):
    """Apply emission calculations to a DataFrame using NGA factors.

    Shared logic used by both LoaderData.py (actuals) and Projections.py
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

    # Rows this function computes are the ones carrying an NGA fuel, and only
    # those are reset before it calculates.  A row without an NGA fuel may
    # still carry an emission, put there by something that knows a factor
    # this function does not: explosives are Scope 1 under the GHG Protocol,
    # carry no NGA combustion factor, and are set by CalcGhg.
    #
    # Zeroing every row on entry destroyed that value whenever the frame was
    # recalculated, which the projection does for every budget row.  The
    # effect was that explosives counted in recorded years and silently
    # vanished from every forecast year.
    has_fuel = agg_df['NGAFuel'].notna() & (agg_df['NGAFuel'] != '')

    # Only the rows this function will actually compute are reset.  That is
    # narrower than "has a fuel name": explosives are named as a source and
    # resolve to no NGA factor, because the National Greenhouse Accounts do
    # not publish one for detonation.  Their Scope 1 is set by CalcGhg from a
    # factor this function does not hold.
    #
    # Resetting every named row destroyed that value whenever the frame was
    # recalculated, which the projection does for every budget row.  The
    # effect was that explosives counted in recorded years and vanished from
    # every forecast year.
    keys = next(iter(year_factor_map.values()), {}) if year_factor_map else {}
    computed_fuels = {
        name for name in agg_df.loc[has_fuel, 'NGAFuel'].astype(str).unique()
        if resolve_factor_key(name, keys) is not None
    }
    will_compute = agg_df['NGAFuel'].astype(str).isin(computed_fuels)

    for column in ('Scope1_tCO2e', 'Scope2_tCO2e', 'Scope3_tCO2e',
                   'Energy_GJ'):
        if column not in agg_df.columns:
            agg_df[column] = 0.0
            continue
        # Widen to float64 before writing anything.  The loader stores these
        # float32 to save memory, and the results below are float64: pandas
        # refuses to write one into the other rather than silently losing
        # precision, which is the right behaviour and has to be respected
        # here.  Assigning the whole column used to do this by accident, by
        # replacing it; now that the column survives, the widening is
        # explicit.
        agg_df[column] = agg_df[column].astype('float64').fillna(0.0)
        agg_df.loc[will_compute, column] = 0.0

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

        factor_key = resolve_factor_key(nga_fuel, year_factors)

        if factor_key is None:
            # A source that already carries an emission was priced by
            # something that holds a factor this function does not, such as
            # explosives under the GHG Protocol.  That is deliberate and is
            # not worth a warning on every run.  A source carrying nothing is
            # a real gap and still says so.
            priced = (agg_df.loc[mask, 'Scope1_tCO2e'].abs().sum()
                      + agg_df.loc[mask, 'Scope2_tCO2e'].abs().sum()) > 0
            if not priced:
                logger.warning(
                    f"No NGA factor for source '{nga_fuel}'; it contributes "
                    f"nothing.  Add a factor or a classification.")
            continue

        # UOM reconciliation.
        # The line is reported in the unit the site records it in; the factor
        # is published against the NGA unit.  Where the two differ, the
        # quantity is converted on an exact definition from Config.  An
        # unknown pair raises: a factor applied to the wrong unit is out by
        # orders of magnitude and must not pass unnoticed.
        expected_uom = year_factors[factor_key].get('expected_uom', '')
        uom_scale = pd.Series(1.0, index=agg_df.index[mask])
        if expected_uom and 'UOM' in agg_df.columns:
            row_uoms = agg_df.loc[mask, 'UOM'].astype(str)
            for uom in row_uoms.unique():
                if uom == expected_uom:
                    continue
                try:
                    conversion = uom_factor(uom, expected_uom)
                except UnitError as exc:
                    raise ValueError(
                        f"UOM MISMATCH: '{nga_fuel}' is reported in '{uom}' but "
                        f"the NGA factor is per '{expected_uom}'.  {exc}"
                    ) from exc
                uom_scale.loc[row_uoms.index[row_uoms == uom]] = conversion
                logger.warning(
                    f"UOM converted: {nga_fuel} reported in '{uom}', factor is "
                    f"per '{expected_uom}'; quantity multiplied by {conversion}."
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

            # Quantity in the unit the factor is published against.
            qty = agg_df.loc[ymask, 'Quantity'] * uom_scale.loc[agg_df.index[ymask]]

            # Universal: tCO2-e = qty * kgCO2-e/unit, kilograms to tonnes
            if yf['s1']:
                agg_df.loc[ymask, 'Scope1_tCO2e'] = qty * yf['s1'] / KG_PER_TONNE_CO2E
            if yf['s2']:
                agg_df.loc[ymask, 'Scope2_tCO2e'] = qty * yf['s2'] / KG_PER_TONNE_CO2E
            if yf['s3']:
                agg_df.loc[ymask, 'Scope3_tCO2e'] = qty * yf['s3'] / KG_PER_TONNE_CO2E

            # Energy: GJ = qty * GJ/native-unit
            if yf['energy']:
                agg_df.loc[ymask, 'Energy_GJ'] = qty * yf['energy']

    return agg_df

def build_safeguard_source_table(df, year_factor_map):
    """Build a detailed source table for Safeguard Mechanism validation and NGER filing.

    Aggregates actuals data to annual level (FY), enriches each row with the
    NGA emission factors and energy content that produced the emissions, so a
    third party can independently verify every tCO2-e line item.

    Calculation shown in each row:
        Quantity_Factor_Basis = Quantity * UOM_Conversion
        tCO2-e    = Quantity_Factor_Basis * EF_kgCO2e_per_unit / 1000
        Energy_GJ = Quantity_Factor_Basis * Energy_GJ_per_unit

    Quantity stays in the unit the site reports it in.  UOM_Conversion is the
    exact definition that carries it to the unit the factor is published
    against, and is 1.0 where the two already agree.  Both are on the row so
    it reconciles without the reader knowing which units disagreed.

    Only rows that have an NGAFuel assignment are included (i.e. consumable
    energy items — not production or ROM data).

    Args:
        df:               Processed DataFrame from load_all_data()
                          Must contain: FY, Description, Department, CostCentre,
                          NGAFuel, UOM, Quantity, Scope1_tCO2e, Scope2_tCO2e,
                          Scope3_tCO2e, Energy_GJ
        year_factor_map:  Dict from build_year_factor_map() — provides the exact
                          NGA factor values used during emissions calculation.

    Returns:
        DataFrame with one row per FY / Description / NGAFuel combination,
        ready for CSV download.  Columns:
            FY, Description, Department, CostCentre, NGAFuel, NGA_Year,
            UOM, Quantity, Factor_UOM, UOM_Conversion, Quantity_Factor_Basis,
            EF_Scope1_kgCO2e_per_unit, Energy_GJ_per_unit,
            Scope1_tCO2e, Energy_GJ
    """
    # Filter to rows that carry an NGAFuel (energy / consumable lines only).
    # Exclude grid electricity: Scope 1 = 0 for purchased electricity, and the
    # kWh quantities are already provided in the electricity production table
    # (build_safeguard_production_table).  Including them here adds zero-emission
    # rows that clutter the audit trail without adding information.
    fuel_mask = (
        df['NGAFuel'].notna()
        & (df['NGAFuel'].astype(str) != '')
        & (df['NGAFuel'].astype(str) != 'Grid electricity')
    )
    source = df[fuel_mask].copy()

    if source.empty:
        return pd.DataFrame()

    # --- Annual aggregation ---
    # Group to FY / Description / Department / CostCentre / NGAFuel / UOM
    # UOM is included so split fuel types (kL vs m3) stay separate.
    agg = source.groupby(
        ['FY', 'DataSet', 'Description', 'Department', 'CostCentre', 'NGAFuel', 'UOM'],
        observed=True, dropna=False
    ).agg(
        Quantity=('Quantity', 'sum'),
        Scope1_tCO2e=('Scope1_tCO2e', 'sum'),
        Energy_GJ=('Energy_GJ', 'sum'),
    ).reset_index()

    # --- Attach NGA factor values ---
    # Resolve the factor key the same way apply_emissions_to_df() does so
    # the EF columns reflect exactly what was used in the calculation.
    ef_s1 = []
    ef_energy = []
    nga_years = []
    factor_uoms = []
    conversions = []

    for _, row in agg.iterrows():
        fy = int(row['FY'])
        nga_fuel = str(row['NGAFuel'])
        yf_all = year_factor_map.get(fy, {})

        # Resolve factor key: exact then longest prefix, then reverse prefix
        factor_key = None
        if nga_fuel in yf_all:
            factor_key = nga_fuel
        else:
            prefixes = [(k, len(k)) for k in yf_all if nga_fuel.startswith(k)]
            if prefixes:
                factor_key = max(prefixes, key=lambda x: x[1])[0]
            else:
                reverse = [k for k in yf_all if k.startswith(nga_fuel)]
                if reverse:
                    factor_key = reverse[0]

        if factor_key and factor_key in yf_all:
            yf = yf_all[factor_key]
            ef_s1.append(yf.get('s1', 0))
            ef_energy.append(yf.get('energy', 0))

            # The row keeps the quantity in the unit the site reports it in.
            # Where that differs from the unit the factor is published
            # against, the conversion is shown so the row reconciles:
            #     Quantity x UOM_Conversion x EF / 1000 = tCO2-e
            factor_uom = yf.get('expected_uom', '') or ''
            row_uom = str(row['UOM'])
            factor_uoms.append(factor_uom)
            if factor_uom:
                try:
                    conversions.append(uom_factor(row_uom, factor_uom))
                except UnitError:
                    conversions.append(None)
            else:
                conversions.append(1.0)
        else:
            ef_s1.append(None)
            ef_energy.append(None)
            factor_uoms.append(None)
            conversions.append(None)

        nga_years.append(yf_all.get('_nga_year', fy))

    agg['Factor_UOM'] = factor_uoms
    agg['UOM_Conversion'] = conversions
    agg['Quantity_Factor_Basis'] = agg['Quantity'] * agg['UOM_Conversion']
    agg['EF_Scope1_kgCO2e_per_unit'] = ef_s1
    agg['Energy_GJ_per_unit'] = ef_energy
    agg['NGA_Year'] = nga_years

    # --- Column order for auditor readability ---
    col_order = [
        'FY', 'DataSet', 'Description', 'Department', 'CostCentre', 'NGAFuel',
        'NGA_Year',
        'UOM', 'Quantity',
        'Factor_UOM', 'UOM_Conversion', 'Quantity_Factor_Basis',
        'EF_Scope1_kgCO2e_per_unit', 'Energy_GJ_per_unit',
        'Scope1_tCO2e', 'Energy_GJ',
    ]
    agg = agg[[c for c in col_order if c in agg.columns]]

    return agg.sort_values(['FY', 'DataSet', 'Description', 'NGAFuel']).reset_index(drop=True)


def build_safeguard_production_table(df):
    """Build annual physical quantities table for Safeguard FSEI target validation.

    The Safeguard baseline target is calculated using pre-defined FSEI constants:

        Baseline = ERC x ((FSEI_ROM x ROM_t) + (FSEI_Elec x Site_MWh))

    FSEI values are fixed — a third party only needs the physical quantities
    (tonnes and kWh) to independently verify the target.  No emissions columns
    are included here; those are in build_safeguard_source_table().

    Two physical quantity datasets:

    1. ROM Ore (SubActivity=='Ore ROM', UOM==t)
          All ore grades by beneficiation status (BRW/SARS, HG/MG/LG/VLG).
          Matches the ROM_t variable used in projections.aggregate_to_monthly().
          Subtotal row per FY/DataSet.

    2. Electricity — kWh (UOM==kWh, CommonName in ['Site electricity', 'Grid electricity'])
          Site electricity (CommonName=='Site electricity') feeds Site_MWh in the
          FSEI formula.  Grid electricity (CommonName=='Grid electricity') covers
          all cost centres including Residential, which is an attributed portion
          of the grid supply and must be included.
          Both are shown in one table for cross-reference.
          Subtotal rows per FY/DataSet/Description type.

    Args:
        df: Processed DataFrame from load_all_data()

    Returns:
        dict with keys 'ore' and 'electricity', each a DataFrame with columns:
            FY, DataSet, Description, CostCentre, UOM, Quantity
        Sorted by FY, DataSet, Description.
    """

    def _aggregate(subset):
        """Aggregate to FY/DataSet/Description/CostCentre/UOM — no totals rows."""
        if subset.empty:
            return pd.DataFrame()
        return subset.groupby(
            ['FY', 'DataSet', 'Description', 'CostCentre', 'UOM'],
            observed=True, dropna=False
        ).agg(Quantity=('Quantity', 'sum')).reset_index().sort_values(
            ['FY', 'DataSet', 'Description']
        ).reset_index(drop=True)

    # --- 1. ROM Ore --- matches Projections.py aggregate_to_monthly() ROM filter:
    #   SubActivity == 'Ore ROM' (2026-03 CSV restructure)
    #   Previously matched CostCentre == 'ROM' but actuals now use CostCentre == 'Hauling'
    #   while budget retains CostCentre == 'ROM'.  SubActivity is the reliable key.
    rom_mask = (df['SubActivity'].astype(str) == 'Ore ROM')
    ore_df = _aggregate(df[rom_mask].copy())

    # --- 2. Electricity kWh --- via CommonName (set by LookupIdentifiers.py)
    #   CommonName == 'Site electricity' captures all site generation
    #   CommonName == 'Grid electricity' captures Grid Power + Residential + Warehouse + Water Delivery
    #   All cost centres included — Residential is an attributed portion of grid supply
    elec_mask = (
        (df['UOM'].astype(str) == 'kWh') &
        (df['CommonName'].astype(str).isin(['Site electricity', 'Grid electricity']))
    )
    elec_df = _aggregate(df[elec_mask].copy())

    return {'ore': ore_df, 'electricity': elec_df}