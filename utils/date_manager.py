"""
Date Manager for PL Daily Generation Scripts
Provides centralized date range configuration for pl_daily file generation.
"""

from datetime import datetime, date, timedelta

# Pad reservation fetches so stays that start before or end after the quote
# still count on nights inside the stay.
RESERVATION_WINDOW_PAD_DAYS = 90


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


def get_reservation_query_range(start_date: str, end_date: str, pad_days: int = None):
    """
    Expand a stay window for GET /reservation_data.

    Pads `pad_days` before check-in and after checkout so overlapping
    reservations are not missed.
    """
    if pad_days is None:
        pad_days = RESERVATION_WINDOW_PAD_DAYS
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    return (
        (start - timedelta(days=pad_days)).strftime('%Y-%m-%d'),
        (end + timedelta(days=pad_days)).strftime('%Y-%m-%d'),
    )
