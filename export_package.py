"""
export_package.py
Export charts and data as a downloadable package
Last updated: 2026-02-04 14:30 AEST

Creates a zip file containing:
- High-resolution chart images (PNG)
- Data tables (CSV)
- README with explanations
"""
"""
WARNING: This file contains Unicode emojis (UTF-8).
When editing, ALWAYS use binary-safe methods to prevent corruption.
"""

import io
import zipfile
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go


def create_export_package(charts_dict, data_dict, metadata=None):
    """
    Create a zip file with charts and data
    
    Args:
        charts_dict: Dict of {filename: plotly_figure}
        data_dict: Dict of {filename: pandas_dataframe}
        metadata: Dict with report info (optional)
    
    Returns:
        BytesIO object containing zip file
    """
    
    # Create in-memory zip file
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        
        # Add README
        readme_content = generate_readme(charts_dict, data_dict, metadata)
        zip_file.writestr('README.txt', readme_content)
        
        # Add charts
        for filename, fig in charts_dict.items():
            if fig is not None:
                # Convert Plotly figure to PNG bytes
                img_bytes = fig.to_image(format='png', width=1920, height=1080, scale=2)
                zip_file.writestr(f'charts/{filename}', img_bytes)
        
        # Add data CSVs
        for filename, df in data_dict.items():
            if df is not None and not df.empty:
                csv_bytes = df.to_csv(index=False).encode('utf-8')
                zip_file.writestr(f'data/{filename}', csv_bytes)
    
    zip_buffer.seek(0)
    return zip_buffer


def generate_readme(charts_dict, data_dict, metadata=None):
    """Generate README content for the export package"""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    readme = f"""
RAVENSWOOD GOLD MINE - EMISSIONS ANALYSIS EXPORT
Generated: {timestamp}

================================================================================
CONTENTS
================================================================================

This package contains emissions analysis charts and data exported from the
Ravenswood Gold Mine Safeguard Mechanism dashboard.

FOLDERS:
--------
charts/     High-resolution PNG images (1920x1080, 300 DPI equivalent)
data/       CSV data files

FILES:
------

CHARTS ({len(charts_dict)} files):
"""
    
    for filename in sorted(charts_dict.keys()):
        readme += f"  - charts/{filename}\n"
    
    readme += f"\nDATA ({len(data_dict)} files):\n"
    
    for filename in sorted(data_dict.keys()):
        readme += f"  - data/{filename}\n"
    
    if metadata:
        readme += f"""

================================================================================
REPORT PARAMETERS
================================================================================

"""
        for key, value in metadata.items():
            readme += f"{key}: {value}\n"
    
    readme += """

================================================================================
USAGE
================================================================================

CHARTS:
- PNG format, high resolution (suitable for printing)
- Insert into Word, PowerPoint, or other documents
- Use in reports, presentations, or email

DATA:
- CSV format, compatible with Excel, Python, R
- Open in Excel for analysis
- Import into databases or other tools

================================================================================
NOTES
================================================================================

- All emission values in tCO₂-e (tonnes CO₂ equivalent)
- Financial years run July-June (e.g., FY2024 = 2023-07-01 to 2024-06-30)
- Charts show projections based on parameters set at export time
- Data may be updated in the live dashboard - this is a snapshot

For questions, contact: Ravenswood Gold Mine Environmental Team

================================================================================
"""
    
    return readme


def export_current_tab_data(tab_name, df, projection_df=None, summary_df=None, **kwargs):
    """
    Export data for a specific tab
    
    Args:
        tab_name: Name of the tab (for filenames)
        df: Main emissions DataFrame
        projection_df: Projection data (optional)
        summary_df: Summary table (optional)
        **kwargs: Additional dataframes
    
    Returns:
        Dict of {filename: dataframe}
    """
    
    data_dict = {}
    
    # Clean tab name for filenames
    tab_slug = tab_name.lower().replace(' ', '_').replace('&', 'and')
    timestamp = datetime.now().strftime('%Y%m%d')
    
    # Main emissions data (filtered to relevant years if needed)
    if df is not None and not df.empty:
        data_dict[f'{tab_slug}_emissions_{timestamp}.csv'] = df
    
    # Projection data
    if projection_df is not None and not projection_df.empty:
        data_dict[f'{tab_slug}_projections_{timestamp}.csv'] = projection_df
    
    # Summary table
    if summary_df is not None and not summary_df.empty:
        data_dict[f'{tab_slug}_summary_{timestamp}.csv'] = summary_df
    
    # Additional dataframes
    for key, value in kwargs.items():
        if isinstance(value, pd.DataFrame) and not value.empty:
            data_dict[f'{tab_slug}_{key}_{timestamp}.csv'] = value
    
    return data_dict


def get_download_filename():
    """Generate filename for the export package"""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    return f'ravenswood_emissions_export_{timestamp}.zip'