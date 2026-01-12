"""
report_generator.py
Helper functions to generate Safeguard Mechanism compliance report
Last updated: 2025-12-23
"""

import json
import subprocess
import os
from pathlib import Path
from datetime import datetime

def prepare_report_data(projection, energy_summary, nga_factors, report_year, config):
    """
    Prepare all data needed for the compliance report in JSON format.
    
    Args:
        projection: DataFrame with projection data
        energy_summary: Dict with energy consumption summary
        nga_factors: Dict with NGA emission factors
        report_year: int, year for the report
        config: Dict with configuration parameters
    
    Returns:
        Tuple of (projection_json, energy_json, nga_json, config_json)
    """
    
    # 1. Projection data for report year
    report_row = projection[projection['FY'] == f'FY{report_year}']
    if len(report_row) == 0:
        raise ValueError(f"No data available for FY{report_year}")
    
    report_data = report_row.iloc[0].to_dict()
    
    # Convert to native Python types for JSON serialization
    projection_list = []
    for record in projection.to_dict('records'):
        converted_record = {}
        for key, value in record.items():
            if hasattr(value, 'item'):  # numpy/pandas types
                converted_record[key] = value.item()
            else:
                converted_record[key] = value
        projection_list.append(converted_record)
    
    # 2. Energy data - need to create monthly profile and category breakdown
    baseline_data = energy_summary['baseline_data']
    by_costcentre = energy_summary['by_costcentre']
    
    # Aggregate by category
    category_map = {
        'Power': 'Power Generation',
        'Mining': 'Mining Operations', 
        'Processing': 'Processing',
        'Fixed': 'Fixed/Transport'
    }
    
    by_category = []
    for category, name in category_map.items():
        cat_data = by_costcentre[by_costcentre['Category'] == category]
        if len(cat_data) > 0:
            total_fuel = float(cat_data['Fuel'].sum())
            total_s1 = float(cat_data['Total_tCO2e_S1'].sum())
            by_category.append({
                'category': name,
                'fuel_kL': total_fuel,
                'scope1': total_s1
            })
    
    # Create monthly profile (simplified - equal distribution)
    months = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']
    total_fuel = float(baseline_data.get('total_fuel', 0))
    total_s1 = float(baseline_data.get('scope1_fuel', 0))
    
    monthly = []
    for month in months:
        monthly.append({
            'month': month,
            'fuel_kL': total_fuel / 12,
            'scope1': total_s1 / 12
        })
    
    energy_data = {
        'by_category': by_category,
        'monthly': monthly,
        'total_fuel_kL': total_fuel,
        'site_mwh': float(baseline_data.get('site_mwh', 0))
    }
    
    # 3. NGA factors data
    nga_data = {
        'diesel': {
            'energy_content_gj_per_kl': nga_factors['diesel']['energy_content_gj_per_kl'],
            'scope1_kg_co2e_per_gj_stationary': nga_factors['diesel']['scope1_stationary'],
            'scope1_kg_co2e_per_gj_transport': nga_factors['diesel']['scope1_transport'],
            'scope3_kg_co2e_per_gj': nga_factors['diesel']['scope3'],
            'scope1_t_co2e_per_kl_stationary': nga_factors['diesel']['scope1_stationary'] * nga_factors['diesel']['energy_content_gj_per_kl'] / 1000,
            'scope1_t_co2e_per_kl_transport': nga_factors['diesel']['scope1_transport'] * nga_factors['diesel']['energy_content_gj_per_kl'] / 1000,
            'scope3_t_co2e_per_kl': nga_factors['diesel']['scope3'] * nga_factors['diesel']['energy_content_gj_per_kl'] / 1000
        },
        'electricity': {
            'QLD': {
                'scope2': nga_factors['scope2']['QLD'],
                'scope3': nga_factors['scope3']['QLD']
            }
        }
    }
    
    # 4. Configuration data
    config_data = {
        'decline_rate': config['decline_rate'],
        'decline_from': config['decline_from'],
        'decline_to': config['decline_to'],
        'grid_fy': config['grid_fy'],
        'end_mining_fy': config['end_mining_fy'],
        'end_processing_fy': config['end_processing_fy']
    }
    
    return (
        json.dumps(projection_list),
        json.dumps(energy_data),
        json.dumps(nga_data),
        json.dumps(config_data)
    )


def generate_report(projection, energy_summary, nga_factors, report_year, config):
    """
    Generate Safeguard Mechanism compliance report.
    
    Args:
        projection: DataFrame with projection data
        energy_summary: Dict with energy consumption summary
        nga_factors: Dict with NGA emission factors
        report_year: int, year for the report
        config: Dict with configuration parameters
    
    Returns:
        Path to generated report file
    """
    
    # Prepare data
    proj_json, energy_json, nga_json, config_json = prepare_report_data(
        projection, energy_summary, nga_factors, report_year, config
    )
    
    # Write temporary JSON files
    temp_dir = Path('/tmp')
    proj_file = temp_dir / 'projection_data.json'
    energy_file = temp_dir / 'energy_data.json'
    nga_file = temp_dir / 'nga_data.json'
    config_file = temp_dir / 'config_data.json'
    
    proj_file.write_text(proj_json)
    energy_file.write_text(energy_json)
    nga_file.write_text(nga_json)
    config_file.write_text(config_json)
    
    # Call JavaScript generator
    js_script = Path('/mnt/user-data/outputs/generate_safeguard_report.js')
    
    try:
        result = subprocess.run(
            ['node', str(js_script), str(report_year), 
             str(proj_file), str(energy_file), str(nga_file), str(config_file)],
            capture_output=True,
            text=True,
            check=True
        )
        
        output_file = f'/mnt/user-data/outputs/Safeguard_Report_FY{report_year}.docx'
        
        if not Path(output_file).exists():
            raise RuntimeError(f"Report generation failed. Output: {result.stdout}\nError: {result.stderr}")
        
        return output_file
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Report generation failed: {e.stderr}")
    
    finally:
        # Clean up temp files
        for f in [proj_file, energy_file, nga_file, config_file]:
            if f.exists():
                f.unlink()
