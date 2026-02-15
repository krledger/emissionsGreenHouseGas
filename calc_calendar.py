"""
calc_calendar.py
Calendar and date calculation functions for NGERS financial year and calendar year handling
Last updated: 2026-02-05 15:00 AEST

Handles conversions between:
- Dates (datetime objects)
- Financial Years (FY) - July 1 to June 30
- Calendar Years (CY) - January 1 to December 31

Key principle: Data stores dates only. Calculate FY/CY for display/aggregation.
"""

import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


# =============================================================================
# CONSTANTS
# =============================================================================

NGER_FY_START_MONTH = 7  # July = Financial year start for NGERS/Safeguard


# =============================================================================
# FINANCIAL YEAR (FY) FUNCTIONS
# =============================================================================

def date_to_fy(date):
    """
    Determine which FY a date falls in (for labeling/grouping).

    Args:
        date: datetime object or pandas Timestamp

    Returns:
        int: Financial year number

    Examples:
        date_to_fy(datetime(2023, 6, 30))  → 2023  # Before July
        date_to_fy(datetime(2023, 7, 1))   → 2024  # July onwards
        date_to_fy(datetime(2024, 6, 30))  → 2024  # Last day of FY2024
    """
    if pd.isna(date):
        return None

    if isinstance(date, pd.Timestamp):
        date = date.to_pydatetime()

    if date.month >= NGER_FY_START_MONTH:
        return date.year + 1
    else:
        return date.year


def fy_to_date_range(fy):
    """
    Convert FY number to start and end dates.

    Args:
        fy: Financial year number

    Returns:
        tuple: (start_date, end_date)

    Examples:
        fy_to_date_range(2024) → (datetime(2023, 7, 1), datetime(2024, 6, 30))
        fy_to_date_range(2028) → (datetime(2027, 7, 1), datetime(2028, 6, 30))
    """
    start_date = datetime(fy - 1, NGER_FY_START_MONTH, 1)
    end_date = datetime(fy, NGER_FY_START_MONTH - 1, 30) if NGER_FY_START_MONTH > 1 else datetime(fy, 12, 31)

    # Correct calculation for June 30
    if NGER_FY_START_MONTH == 7:
        end_date = datetime(fy, 6, 30)

    return start_date, end_date


# =============================================================================
# CALENDAR YEAR (CY) FUNCTIONS
# =============================================================================

def date_to_cy(date):
    """
    Determine which CY a date falls in (for labeling/grouping).

    Args:
        date: datetime object or pandas Timestamp

    Returns:
        int: Calendar year number

    Examples:
        date_to_cy(datetime(2024, 1, 1))   → 2024
        date_to_cy(datetime(2024, 12, 31)) → 2024
    """
    if pd.isna(date):
        return None

    if isinstance(date, pd.Timestamp):
        date = date.to_pydatetime()

    return date.year


def cy_to_date_range(cy):
    """
    Convert CY number to start and end dates.

    Args:
        cy: Calendar year number

    Returns:
        tuple: (start_date, end_date)

    Examples:
        cy_to_date_range(2024) → (datetime(2024, 1, 1), datetime(2024, 12, 31))
    """
    start_date = datetime(cy, 1, 1)
    end_date = datetime(cy, 12, 31)
    return start_date, end_date


# =============================================================================
# AGGREGATION FUNCTIONS
# =============================================================================

def aggregate_by_year_type(df, year_type='FY', agg_dict=None):
    """
    Aggregate monthly data to annual by year type.
    Uses pandas Grouper for clean date-based grouping.

    Args:
        df: DataFrame with 'Date' column (datetime)
        year_type: 'FY' or 'CY'
        agg_dict: Optional dict of column: aggregation function
                 If None, sums all numeric columns

    Returns:
        DataFrame: Aggregated to annual with year labels

    Examples:
        # Sum all numeric columns by FY
        annual_fy = aggregate_by_year_type(monthly_df, 'FY')

        # Custom aggregation
        annual_cy = aggregate_by_year_type(monthly_df, 'CY', {
            'Scope1': 'sum',
            'ROM_t': 'sum',
            'SMC_Cumulative': 'last'  # Take end-of-year value
        })
    """
    df = df.copy()

    # Ensure Date is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = pd.to_datetime(df['Date'])

    # Set Date as index for Grouper
    df_indexed = df.set_index('Date')

    # Group by year type
    if year_type == 'FY':
        # YS-JUL = Year Start in July
        if agg_dict:
            annual = df_indexed.groupby(pd.Grouper(freq='YS-JUL')).agg(agg_dict)
        else:
            annual = df_indexed.groupby(pd.Grouper(freq='YS-JUL')).sum(numeric_only=True)
        # Label as FY
        annual['Year'] = annual.index.map(lambda d: f"FY{date_to_fy(d)}")
    else:  # CY
        # YS-JAN = Year Start in January
        if agg_dict:
            annual = df_indexed.groupby(pd.Grouper(freq='YS-JAN')).agg(agg_dict)
        else:
            annual = df_indexed.groupby(pd.Grouper(freq='YS-JAN')).sum(numeric_only=True)
        # Label as CY
        annual['Year'] = annual.index.map(lambda d: f"CY{date_to_cy(d)}")

    annual = annual.reset_index()
    return annual


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def add_years(date, years):
    """
    Add years to a date (handles leap years correctly).

    Args:
        date: datetime object
        years: Number of years to add (can be negative)

    Returns:
        datetime: Date with years added

    Examples:
        add_years(datetime(2024, 7, 1), 10) → datetime(2034, 7, 1)
        add_years(datetime(2024, 2, 29), 1) → datetime(2025, 2, 28)  # Leap year handling
    """
    return date + relativedelta(years=years)


def get_fy_label(date):
    """
    Get FY label string for a date.

    Args:
        date: datetime object

    Returns:
        str: FY label (e.g., "FY2024")

    Examples:
        get_fy_label(datetime(2023, 7, 1)) → "FY2024"
    """
    return f"FY{date_to_fy(date)}"


def get_cy_label(date):
    """
    Get CY label string for a date.

    Args:
        date: datetime object

    Returns:
        str: CY label (e.g., "CY2024")

    Examples:
        get_cy_label(datetime(2024, 3, 15)) → "CY2024"
    """
    return f"CY{date_to_cy(date)}"


def filter_by_fy(df, fy):
    """
    Filter DataFrame to a specific FY.

    Args:
        df: DataFrame with 'Date' column
        fy: Financial year number

    Returns:
        DataFrame: Filtered to the specified FY

    Examples:
        fy2024_data = filter_by_fy(monthly_df, 2024)
    """
    start_date, end_date = fy_to_date_range(fy)
    return df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]


def filter_by_cy(df, cy):
    """
    Filter DataFrame to a specific CY.

    Args:
        df: DataFrame with 'Date' column
        cy: Calendar year number

    Returns:
        DataFrame: Filtered to the specified CY

    Examples:
        cy2024_data = filter_by_cy(monthly_df, 2024)
    """
    start_date, end_date = cy_to_date_range(cy)
    return df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]


def filter_by_date_range(df, start_date, end_date):
    """
    Filter DataFrame to a date range.

    Args:
        df: DataFrame with 'Date' column
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        DataFrame: Filtered to the date range
    """
    return df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]