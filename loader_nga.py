"""
loader_nga.py
Load National Greenhouse Accounts emission factors from nga_factors.csv
Last updated: 2026-02-11

Reads the flat CSV produced by nga_to_csv.py.  This replaces the old
Excel-parsing approach with a single CSV lookup, which is faster, simpler
and gives full traceability back to the NGA workbook via the Source_Table column.

The CSV is the single source of truth for ALL emission factors.  No emission
factors are hardcoded anywhere in the codebase.

MATCHING:
    The consolidated_emissions_data.csv NGAFuel column contains fuel names
    that are prefixes of the full NGA Fuel_Name in nga_factors.csv.
    Matching uses startswith: the CSV prefix matches the NGA full name.
    Exact matches are preferred over partial startswith matches.

    Example:
        CSV NGAFuel: "Diesel oil"
        NGA Fuel_Name: "Diesel oil"  (exact match, preferred)
        NGA Fuel_Name: "Diesel oil-Cars and light commercial vehicles" (also matches, skipped)
"""

import pandas as pd
import os


class NGAFactorsByYear:
    """Provide access to NGA emission factors for multiple years.

    Reads nga_factors.csv and provides lookup methods for any fuel,
    scope, year and state combination.
    """

    def __init__(self, folder_path='.'):
        self.folder_path = folder_path
        self.df = None
        self.available_years = []
        self._load()

    def _load(self):
        """Load nga_factors.csv and index by year."""
        csv_path = os.path.join(self.folder_path, 'nga_factors.csv')
        if not os.path.exists(csv_path):
            raise FileNotFoundError(
                f"nga_factors.csv not found in {self.folder_path}. "
                f"Run nga_to_csv.py first to generate it from NGA Excel files."
            )

        self.df = pd.read_csv(csv_path)
        self.available_years = sorted(self.df['NGA_Year'].unique().tolist())

        # Build startswith index: for each year, map fuel name prefix to full name
        # Sorted shortest-first so exact matches win
        self._fuel_names_by_year = {}
        for year in self.available_years:
            ydf = self.df[self.df['NGA_Year'] == year]
            names = sorted(ydf['Fuel_Name'].unique(), key=len)
            self._fuel_names_by_year[year] = names

        print(f"\u2705 NGA factors loaded: {len(self.df)} rows, "
              f"years {self.available_years}")

    # ------------------------------------------------------------------
    # STARTSWITH MATCHING
    # ------------------------------------------------------------------

    def _resolve_fuel_name(self, year, prefix):
        """Resolve a fuel name prefix to the full NGA Fuel_Name.

        Tries exact match first, then startswith with shortest match.
        Returns None if no match found.
        """
        names = self._fuel_names_by_year.get(year, [])

        # Exact match first
        if prefix in names:
            return prefix

        # Startswith: return shortest match (most specific)
        for name in names:
            if name.startswith(prefix):
                return name

        return None

    # ------------------------------------------------------------------
    # CORE LOOKUP
    # ------------------------------------------------------------------

    def match_fuel_factor(self, year, nga_fuel_prefix, scope, state=''):
        """Look up an emission factor using startswith matching.

        This is the primary lookup method.  The nga_fuel_prefix comes from
        the NGAFuel column in the consolidated CSV and may be a prefix of
        the full NGA Fuel_Name.

        Args:
            year: NGA publication year (int)
            nga_fuel_prefix: Fuel name or prefix from CSV NGAFuel column
            scope: 1, 2, or 3
            state: State code for electricity (e.g. 'QLD'), empty for fuels

        Returns:
            dict with keys: EF_kgCO2e_per_unit, EF_Unit, Energy_Content,
                           Energy_Unit, Fuel_Name (resolved full name)
            or None if not found
        """
        year = self._resolve_year(year)
        if year is None:
            return None

        full_name = self._resolve_fuel_name(year, nga_fuel_prefix)
        if full_name is None:
            return None

        mask = (
            (self.df['NGA_Year'] == year)
            & (self.df['Fuel_Name'] == full_name)
            & (self.df['Scope'] == scope)
        )
        if state:
            mask = mask & (self.df['State'] == state)
        else:
            # Fuels: State is blank or NaN
            mask = mask & (self.df['State'].isna() | (self.df['State'] == ''))

        matches = self.df[mask]
        if len(matches) == 0:
            return None

        row = matches.iloc[0]
        return {
            'EF_kgCO2e_per_unit': row['EF_kgCO2e_per_unit'],
            'EF_Unit': row['EF_Unit'] if pd.notna(row['EF_Unit']) else '',
            'Energy_Content': row['Energy_Content'] if pd.notna(row['Energy_Content']) else None,
            'Energy_Unit': row['Energy_Unit'] if pd.notna(row['Energy_Unit']) else '',
            'Fuel_Name': full_name,
        }

    def expected_uom(self, ef_unit):
        """Derive the expected CSV UOM from an NGA EF_Unit string.

        NGA EF_Unit is like 'kg CO2-e/kL' or 'kg CO2-e/m3'.
        The denominator after '/' is the expected quantity unit.

        Returns:
            str: expected UOM (e.g. 'kL', 'm3', 'kWh') or '' if not parseable
        """
        if '/' in ef_unit:
            return ef_unit.split('/')[-1].strip()
        return ''

    # ------------------------------------------------------------------
    # ELECTRICITY
    # ------------------------------------------------------------------

    def get_electricity_factor(self, year, state, scope):
        """Get electricity emission factor for a state and scope.

        Args:
            year: NGA year
            state: State code (e.g. 'QLD')
            scope: 2 or 3

        Returns:
            float: kgCO2-e/kWh, or None
        """
        result = self.match_fuel_factor(year, 'Grid electricity', scope, state)
        if result is None:
            return None
        return result['EF_kgCO2e_per_unit']

    # ------------------------------------------------------------------
    # TAB 4 DISPLAY SUPPORT
    # ------------------------------------------------------------------

    def get_factors_for_year(self, year, state='QLD'):
        """Get emission factors for a specific year (used by tab4_nger.py).

        Returns dict of factors for display.  Raises ValueError if required
        factors are missing from nga_factors.csv - no hardcoded fallbacks.
        """
        year = self._resolve_year(year)
        if year is None:
            raise ValueError(f"No NGA factors available for year {year}")

        ydf = self.df[self.df['NGA_Year'] == year]
        if len(ydf) == 0:
            raise ValueError(f"No NGA factors found for year {year}")

        # --- Electricity ---
        electricity = {}
        elec_rows = ydf[ydf['Fuel_Type'] == 'Electricity']
        for _, row in elec_rows.iterrows():
            st = row['State']
            if pd.isna(st) or not st:
                continue
            if st not in electricity:
                electricity[st] = {}
            scope_key = f"scope{int(row['Scope'])}"
            electricity[st][scope_key] = row['EF_kgCO2e_per_unit']

        # --- Diesel ---
        d_stat = self.match_fuel_factor(year, 'Diesel oil', 1)
        d_s3   = self.match_fuel_factor(year, 'Diesel oil', 3)
        d_trans = self.match_fuel_factor(year, 'Diesel oil-Cars and light commercial vehicles', 1)

        if not d_stat:
            raise ValueError(f"No Diesel oil Scope 1 factor in NGA {year}")
        if not d_s3:
            raise ValueError(f"No Diesel oil Scope 3 factor in NGA {year}")

        s1_stat_kl  = d_stat['EF_kgCO2e_per_unit']
        s3_kl       = d_s3['EF_kgCO2e_per_unit']
        s1_trans_kl = d_trans['EF_kgCO2e_per_unit'] if d_trans else s1_stat_kl
        energy      = d_stat['Energy_Content']
        if not energy:
            raise ValueError(f"No Diesel oil Energy_Content in NGA {year}")

        diesel = {
            'energy_content_gj_per_kl': energy,
            'scope1_kg_co2e_per_kl_stationary': s1_stat_kl,
            'scope1_t_co2e_per_kl_stationary': s1_stat_kl / 1000,
            'scope1_t_co2e_per_kl_electricity': s1_stat_kl / 1000,
            'scope1_t_co2e_per_kl_transport': s1_trans_kl / 1000,
            'scope3_t_co2e_per_kl': s3_kl / 1000,
        }

        diesel_by_purpose = {
            'electricity': {'scope1': diesel['scope1_t_co2e_per_kl_electricity'],
                           'scope3': diesel['scope3_t_co2e_per_kl']},
            'stationary':  {'scope1': diesel['scope1_t_co2e_per_kl_stationary'],
                           'scope3': diesel['scope3_t_co2e_per_kl']},
            'transport':   {'scope1': diesel['scope1_t_co2e_per_kl_transport'],
                           'scope3': diesel['scope3_t_co2e_per_kl']},
            'explosives':  {'scope1': 0, 'scope3': 0},
        }

        if state not in electricity:
            raise ValueError(
                f"No electricity factors for state '{state}' in NGA {year}. "
                f"Available states: {list(electricity.keys())}"
            )
        elec_state = electricity[state]

        return {
            'year': year,
            'electricity': electricity,
            'diesel': diesel,
            'diesel_by_purpose': diesel_by_purpose,
            'scope2': elec_state['scope2'],
            'scope3': elec_state['scope3'],
        }

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    def _resolve_year(self, year):
        """Resolve year to closest available NGA year."""
        if year in self.available_years:
            return year
        if not self.available_years:
            return None
        if year < min(self.available_years):
            return min(self.available_years)
        elif year > max(self.available_years):
            return max(self.available_years)
        else:
            return min(self.available_years, key=lambda y: abs(y - year))