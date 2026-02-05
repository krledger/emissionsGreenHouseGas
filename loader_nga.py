"""
loader_nga.py
Load National Greenhouse Accounts emission factors from Excel by year
Last updated: 2026-01-07 12:30 AEST
"""

import pandas as pd
import os


class NGAFactorsByYear:
    """Load and provide access to NGA emission factors for multiple years"""

    def __init__(self, folder_path='.'):
        self.folder_path = folder_path
        self.factors_by_year = {}
        self._load_all_years()

    def _load_all_years(self):
        """Load emission factors for all available years"""
        for year in range(2021, 2026):
            # Try with dashes first (official naming)
            filepath = os.path.join(self.folder_path, f'national-greenhouse-account-factors-{year}.xlsx')
            if not os.path.exists(filepath):
                # Try without dashes (alternative naming)
                filepath = os.path.join(self.folder_path, f'nationalgreenhouseaccountfactors{year}.xlsx')

            if os.path.exists(filepath):
                try:
                    self.factors_by_year[year] = self._load_year(filepath, year)
                except Exception as e:
                    print(f"Warning: Could not load factors for {year}: {e}")

    def _load_year(self, filepath, year):
        """Load emission factors for a specific year"""
        factors = {
            'year': year,
            'electricity': {},
            'diesel': {},
            'diesel_by_purpose': {}
        }

        if year == 2021:
            factors['electricity'] = self._load_electricity_2021(filepath)
            factors['diesel'] = self._load_diesel_2021(filepath)
        else:  # 2022-2025
            factors['electricity'] = self._load_electricity_modern(filepath)
            factors['diesel'] = self._load_diesel_modern(filepath)

        # Create purpose-specific factors
        factors['diesel_by_purpose'] = self._create_purpose_factors(factors['diesel'])

        return factors

    def _load_electricity_2021(self, filepath):
        """Load 2021 electricity factors (Table 6 - different structure)"""
        df = pd.read_excel(filepath, sheet_name='Table 6', header=None)

        electricity = {}

        # 2021 only has Scope 2 by grid, not by state
        # Queensland is in NEM
        for idx in range(3, len(df)):
            row = df.iloc[idx]
            grid_name = str(row[0]).strip() if pd.notna(row[0]) else ''
            scope2 = row[1] if pd.notna(row[1]) else None

            if 'National Electricity Market' in grid_name or 'NEM' in grid_name:
                # NEM covers QLD, NSW, VIC, SA, TAS
                nem_scope2 = float(scope2) if scope2 else 0.77
                electricity['QLD'] = {'scope2': nem_scope2, 'scope3': 0.15}  # Estimated Scope 3
                electricity['NSW'] = {'scope2': nem_scope2, 'scope3': 0.15}
                electricity['VIC'] = {'scope2': nem_scope2, 'scope3': 0.15}
                electricity['SA'] = {'scope2': nem_scope2, 'scope3': 0.15}
                electricity['TAS'] = {'scope2': nem_scope2, 'scope3': 0.15}

        # Defaults
        electricity.setdefault('QLD', {'scope2': 0.77, 'scope3': 0.15})
        electricity.setdefault('WA', {'scope2': 0.68, 'scope3': 0.04})
        electricity.setdefault('NT', {'scope2': 0.54, 'scope3': 0.07})

        return electricity

    def _load_electricity_modern(self, filepath):
        """Load 2022-2025 electricity factors (Table 1)"""
        df = pd.read_excel(filepath, sheet_name='Table 1', header=None)

        electricity = {}
        state_mapping = {
            'New South Wales and Australian Capital Territory': 'NSW',
            'Victoria': 'VIC',
            'Queensland': 'QLD',
            'South Australia': 'SA',
            'Tasmania': 'TAS',
        }

        # Detect column structure by checking row 2 (units row)
        # 2022-2023: [nan, 'kg CO2Ã¢â‚¬â€˜e/kWh', 'kg CO2Ã¢â‚¬â€˜e/GJ', 'kg CO2Ã¢â‚¬â€˜e/kWh', 'kg CO2Ã¢â‚¬â€˜e/GJ']
        #            State, Scope2_kWh(1), Scope2_GJ(2), Scope3_kWh(3), Scope3_GJ(4)
        # 2024-2025: [nan, '(kg CO2-e/kWh)', '(kg CO2-e/kWh)']
        #            State, Scope2_kWh(1), Scope3_kWh(2)
        units_row = df.iloc[2] if len(df) > 2 else None

        # Check if we have 5 columns (with GJ columns) or 3 columns (kWh only)
        has_gj_columns = False
        if units_row is not None:
            units_text = ' '.join([str(u) for u in units_row if pd.notna(u)])
            if 'GJ' in units_text:
                has_gj_columns = True

        if has_gj_columns:
            # 2022-2023 format: has both kWh and GJ columns
            scope2_col = 1  # Scope 2 in kWh
            scope3_col = 3  # Scope 3 in kWh (skip the GJ column at position 2)
        else:
            # 2024-2025 format: only kWh columns
            scope2_col = 1
            scope3_col = 2

        for idx in range(3, len(df)):
            row = df.iloc[idx]
            state_name = str(row[0]).strip() if pd.notna(row[0]) else ''
            scope2 = row[scope2_col] if pd.notna(row[scope2_col]) else None
            scope3 = row[scope3_col] if pd.notna(row[scope3_col]) else None

            # Validate that scope values are numeric
            try:
                if scope2 is not None:
                    scope2 = float(scope2)
                if scope3 is not None:
                    scope3 = float(scope3)
            except (ValueError, TypeError):
                # Skip rows with non-numeric values
                continue

            if state_name in state_mapping and scope2 is not None:
                electricity[state_mapping[state_name]] = {
                    'scope2': scope2,
                    'scope3': scope3 if scope3 else 0
                }
            elif 'Western Australia' in state_name and 'SWIS' in state_name:
                if scope2 is not None:
                    electricity['WA'] = {
                        'scope2': scope2,
                        'scope3': scope3 if scope3 else 0
                    }
            elif 'NWIS' in state_name:
                if scope2 is not None:
                    electricity['NT'] = {
                        'scope2': scope2,
                        'scope3': scope3 if scope3 else 0
                    }

        # Defaults
        electricity.setdefault('WA', {'scope2': 0.50, 'scope3': 0.06})
        electricity.setdefault('NT', {'scope2': 0.56, 'scope3': 0.09})

        return electricity

    def _load_diesel_2021(self, filepath):
        """Load 2021 diesel factors (Table 3)"""
        df = pd.read_excel(filepath, sheet_name='Table 3', header=None)

        diesel = {}

        for idx in range(len(df)):
            row = df.iloc[idx]
            fuel_name = str(row[0]).strip() if pd.notna(row[0]) else ''

            if fuel_name == 'Diesel oil':
                energy_content = float(row[1])  # GJ/kL
                co2_factor = float(row[2])       # kg CO2-e/GJ
                ch4_factor = float(row[3])       # kg CO2-e/GJ
                n2o_factor = float(row[4])       # kg CO2-e/GJ

                total_factor_gj = co2_factor + ch4_factor + n2o_factor
                total_factor_kl = energy_content * total_factor_gj

                diesel['energy_content_gj_per_kl'] = energy_content
                diesel['scope1_kg_co2e_per_kl_stationary'] = total_factor_kl
                diesel['scope1_t_co2e_per_kl_stationary'] = total_factor_kl / 1000
                diesel['scope1_t_co2e_per_kl_electricity'] = total_factor_kl / 1000
                diesel['scope1_t_co2e_per_kl_transport'] = 2.71782  # From 2022 data
                diesel['scope3_t_co2e_per_kl'] = 0.66778  # Estimated from 2022
                break

        return diesel

    def _load_diesel_modern(self, filepath):
        """Load 2022-2025 diesel factors from Energy sheets"""
        diesel = {}

        # Scope 1: Energy - Scope 1 sheet
        df_s1 = pd.read_excel(filepath, sheet_name='Energy - Scope 1 ', header=None)

        for idx in range(len(df_s1)):
            row = df_s1.iloc[idx]
            fuel_name = str(row[1]).strip() if pd.notna(row[1]) else ''

            if fuel_name == 'Diesel oil':
                # Stationary diesel
                # Column structure: [0]=Type, [1]=Fuel, [2]=CO2, [3]=CH4, [4]=N2O,
                #                   [5]=Total, [6]=Energy, [7]=Unit, [8]=Total kg/kL, [9]=Unit
                energy_content = float(row[6])  # GJ/kL
                total_kl = float(row[8])  # kg CO2-e/kL

                diesel['energy_content_gj_per_kl'] = energy_content
                diesel['scope1_kg_co2e_per_kl_stationary'] = total_kl
                diesel['scope1_t_co2e_per_kl_stationary'] = total_kl / 1000
                diesel['scope1_t_co2e_per_kl_electricity'] = total_kl / 1000
                break

        # Transport diesel (light vehicles)
        for idx in range(len(df_s1)):
            row = df_s1.iloc[idx]
            fuel_name = str(row[1]).strip() if pd.notna(row[1]) else ''

            if 'Diesel oil-Cars and light commercial' in fuel_name:
                total_kl = float(row[8])  # kg CO2-e/kL
                diesel['scope1_t_co2e_per_kl_transport'] = total_kl / 1000
                break

        # Scope 3
        df_s3 = pd.read_excel(filepath, sheet_name='Energy - Scope 3', header=None)

        for idx in range(len(df_s3)):
            row = df_s3.iloc[idx]
            fuel_name = str(row[1]).strip() if pd.notna(row[1]) else ''

            if fuel_name == 'Diesel oil':
                # Column structure: [0]=Type, [1]=Fuel, [2]=Factor, [3]=Energy, [4]=Unit, [5]=Total kg/kL
                scope3_kl = float(row[5])  # kg CO2-e/kL
                diesel['scope3_t_co2e_per_kl'] = scope3_kl / 1000
                break

        return diesel

    def _create_purpose_factors(self, diesel):
        """Create purpose-specific factor dictionaries"""
        return {
            'electricity': {
                'scope1': diesel.get('scope1_t_co2e_per_kl_electricity', 2.70972),
                'scope3': diesel.get('scope3_t_co2e_per_kl', 0.66778)
            },
            'stationary': {
                'scope1': diesel.get('scope1_t_co2e_per_kl_stationary', 2.70972),
                'scope3': diesel.get('scope3_t_co2e_per_kl', 0.66778)
            },
            'transport': {
                'scope1': diesel.get('scope1_t_co2e_per_kl_transport', 2.71782),
                'scope3': diesel.get('scope3_t_co2e_per_kl', 0.66778)
            },
            'explosives': {
                'scope1': 0,
                'scope3': 0
            }
        }

    def get_factors_for_year(self, year, state='QLD'):
        """Get emission factors for a specific year

        Returns dict with electricity and diesel factors for the year
        """
        # Use closest available year if exact year not found
        if year not in self.factors_by_year:
            available_years = sorted(self.factors_by_year.keys())
            if not available_years:
                return None

            # Find closest year
            if year < min(available_years):
                year = min(available_years)
            elif year > max(available_years):
                year = max(available_years)
            else:
                year = min(available_years, key=lambda y: abs(y - year))

        factors = self.factors_by_year[year].copy()

        # Add convenience fields
        elec = factors['electricity'].get(state, factors['electricity'].get('QLD'))
        factors['scope2'] = elec['scope2']
        factors['scope3'] = elec['scope3']

        return factors

    def get_all_years_summary(self, state='QLD'):
        """Get summary of factors across all years for display"""
        summary = []

        for year in sorted(self.factors_by_year.keys()):
            factors = self.get_factors_for_year(year, state)
            summary.append({
                'Year': year,
                'Elec_Scope2_kg_kWh': factors['scope2'],
                'Elec_Scope3_kg_kWh': factors['scope3'],
                'Diesel_Stationary_S1_t_kL': factors['diesel_by_purpose']['stationary']['scope1'],
                'Diesel_Transport_S1_t_kL': factors['diesel_by_purpose']['transport']['scope1'],
                'Diesel_S3_t_kL': factors['diesel_by_purpose']['stationary']['scope3']
            })

        return pd.DataFrame(summary)


# Legacy function for backward compatibility
def load_nga_factors(filepath):
    """Load NGA factors from single file (legacy compatibility)

    For new code, use NGAFactorsByYear class instead
    """
    nga = NGAFactorsByYear(os.path.dirname(filepath))

    # Extract year from filename (handles both with and without dashes)
    filename = os.path.basename(filepath)
    try:
        # Try with dashes first: national-greenhouse-account-factors-2025.xlsx
        if 'national-greenhouse-account-factors-' in filename:
            year = int(filename.split('-')[-1].replace('.xlsx', ''))
        else:
            # Fallback to no dashes: nationalgreenhouseaccountfactors2025.xlsx
            year = int(filename.replace('nationalgreenhouseaccountfactors', '').replace('.xlsx', ''))
    except:
        year = 2025  # Default to latest

    factors = nga.get_factors_for_year(year, 'QLD')

    if factors is None:
        # Return default factors (in tCO2e/MWh - standard units)
        return {
            'electricity': {'QLD': {'scope2': 0.67, 'scope3': 0.09}},
            'diesel': {},
            'diesel_by_purpose': {},
            'diesel_s3_by_purpose': {},
            'scope2': 0.67,  # tCO2e/MWh (standard units)
            'scope3': 0.09   # tCO2e/MWh (standard units)
        }

    # Build legacy structure
    diesel_s1_by_purpose = {
        'electricity': factors['diesel_by_purpose']['electricity']['scope1'],
        'stationary': factors['diesel_by_purpose']['stationary']['scope1'],
        'transport': factors['diesel_by_purpose']['transport']['scope1'],
        'explosives': 0
    }

    diesel_s3_by_purpose = {
        'electricity': factors['diesel_by_purpose']['electricity']['scope3'],
        'stationary': factors['diesel_by_purpose']['stationary']['scope3'],
        'transport': factors['diesel_by_purpose']['transport']['scope3'],
        'explosives': 0
    }

    return {
        'electricity': factors['electricity'],
        'diesel': factors['diesel'],
        'diesel_by_purpose': diesel_s1_by_purpose,
        'diesel_s3_by_purpose': diesel_s3_by_purpose,
        'scope2': factors['scope2'],  # tCO2e/MWh (standard units)
        'scope3': factors['scope3']   # tCO2e/MWh (standard units)
    }