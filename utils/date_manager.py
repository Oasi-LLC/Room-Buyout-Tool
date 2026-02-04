"""
Date Manager for PL Daily Generation Scripts
Provides centralized date range configuration for pl_daily file generation.
"""

from datetime import datetime, date

def get_pl_daily_date_range():
    """
    Get the default date range for pl_daily file generation.
    
    Returns:
        tuple: (start_date_str, end_date_str) in YYYY-MM-DD format
        - start_date: Today's date
        - end_date: January 3, 2027
    """
    start_date = datetime.now().date()
    end_date = date(2027, 1, 3)  # January 3, 2027
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def get_pl_daily_date_range_objects():
    """
    Get the default date range as date objects.
    
    Returns:
        tuple: (start_date, end_date) as date objects
    """
    start_date = datetime.now().date()
    end_date = date(2027, 1, 3)  # January 3, 2027
    
    return start_date, end_date
