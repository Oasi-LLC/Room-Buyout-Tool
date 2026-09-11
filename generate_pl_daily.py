#!/usr/bin/env python3
"""
Comprehensive script to generate pl_daily files for any property.
Handles both cloudbeds and hostaway PMSs correctly.
Adapted for Room Buyout Tool - self-contained version.
"""

import requests
import sys
import time
import pandas as pd
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

# Add utils to path
tool_dir = Path(__file__).parent
sys.path.insert(0, str(tool_dir))

from utils.config import API_KEY, BASE_URL, require_api_key

def get_listing_overrides(listing_id, pms, start_date, end_date, max_retries=3):
    """Get listing overrides for the date range with retry logic."""
    url = f"{BASE_URL}/listings/{listing_id}/overrides"
    headers = {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
    }
    params = {'pms': pms} if pms else {}
    
    # Validate inputs
    if not listing_id:
        raise ValueError("listing_id cannot be empty")
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                if attempt < max_retries - 1:
                    print(f"  ⚠️  Rate limited. Waiting {retry_after}s before retry...")
                    time.sleep(retry_after)
                    continue
                else:
                    response.raise_for_status()
            
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, dict):
                raise ValueError(f"Unexpected response format: {type(data)}")
            
            overrides = data.get('overrides', [])
            if not isinstance(overrides, list):
                overrides = []
            
            # Create a dictionary of date -> override price
            override_prices = {}
            for override in overrides:
                if not isinstance(override, dict):
                    continue
                date = override.get('date')
                if date and start_date <= date <= end_date:
                    try:
                        price = float(override.get('price', 0))
                        override_prices[date] = price
                    except (ValueError, TypeError):
                        print(f"  ⚠️  Invalid price for {date}: {override.get('price')}")
                        continue
            
            return override_prices
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"  ⚠️  Request timeout. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"  ⚠️  Request error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                raise
    
    return {}

def get_daily_data_for_listing(listing_id, pms, start_date, end_date, max_retries=3):
    """Get daily data (pricing, booking status, blocking) for a listing with retry logic."""
    url = f"{BASE_URL}/listing_prices"
    headers = {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        "listings": [
            {
                "id": listing_id,
                "pms": pms,
                "dateFrom": start_date,
                "dateTo": end_date
            }
        ]
    }
    
    # Validate inputs
    if not listing_id:
        raise ValueError("listing_id cannot be empty")
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                if attempt < max_retries - 1:
                    print(f"  ⚠️  Rate limited. Waiting {retry_after}s before retry...")
                    time.sleep(retry_after)
                    continue
                else:
                    response.raise_for_status()
            
            response.raise_for_status()
            data = response.json()
            
            # Process daily data with validation
            daily_data = {}
            if isinstance(data, list) and len(data) > 0:
                listing_data = data[0]
                if isinstance(listing_data, dict) and 'data' in listing_data:
                    entries = listing_data['data']
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict):
                                date = entry.get('date')
                                if date:
                                    daily_data[date] = entry
            
            return daily_data
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"  ⚠️  Request timeout. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"  ⚠️  Request error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                raise
    
    return {}

def fetch_all_reservations(pms, start_date, end_date, max_retries=3):
    """Fetch all reservations for the PMS and date range using pagination with retry logic."""
    url = f"{BASE_URL}/reservation_data"
    headers = {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
    }
    limit = 100
    offset = 0
    all_reservations = []
    
    # Validate inputs
    if not pms:
        raise ValueError("pms cannot be empty")
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")
    
    while True:
        params = {
            'pms': pms,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    if attempt < max_retries - 1:
                        print(f"  ⚠️  Rate limited. Waiting {retry_after}s before retry...")
                        time.sleep(retry_after)
                        continue
                    else:
                        response.raise_for_status()
                
                response.raise_for_status()
                data = response.json()
                
                if not isinstance(data, dict):
                    raise ValueError(f"Unexpected response format: {type(data)}")
                
                reservations = data.get('data', [])
                if not isinstance(reservations, list):
                    reservations = []
                
                all_reservations.extend(reservations)
                
                # Break if we got fewer results than requested (last page)
                if len(reservations) < limit:
                    return all_reservations
                
                offset += limit
                break  # Success, exit retry loop
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"  ⚠️  Request timeout. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"  ⚠️  Request error: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise
    
    return all_reservations

def fetch_listing_data(listing, start_date, end_date, all_reservations, pms):
    """Fetch data for a single listing (to be used in parallel)."""
    listing_id = str(listing['id'])
    listing_name = listing.get('name', 'Unknown')
    units = listing.get('units', 1)
    
    print(f"  🏠 Processing {listing_name} ({listing_id}) - {units} units")
    
    # Filter reservations for this listing
    listing_reservations = [r for r in all_reservations if str(r.get('listing_id')) == listing_id]
    print(f"    📊 Found {len(listing_reservations)} reservations")
    
    # Fetch daily data for this listing
    t0 = time.time()
    daily_data = get_daily_data_for_listing(listing_id, pms, start_date, end_date)
    daily_time = time.time() - t0
    print(f"    ⏱️ Daily data fetched in {daily_time:.2f}s")
    
    # Fetch overrides for this listing
    t0 = time.time()
    override_prices = get_listing_overrides(listing_id, pms, start_date, end_date)
    overrides_time = time.time() - t0
    print(f"    ⏱️ Overrides fetched in {overrides_time:.2f}s")
    
    # Process dates for this listing
    t0 = time.time()
    listing_records = []
    current_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
    
    while current_date <= end_datetime:
        date_str = current_date.strftime('%Y-%m-%d')
        date_iso = f"{date_str}T00:00:00.000000"
        daily_info = daily_data.get(date_str, {})
        
        # Get booking status from listing_prices
        booking_status = daily_info.get('booking_status', '')
        is_booked = 'Booked' in booking_status
        
        # Count actual reservations for this date
        date_reservations = []
        for res in listing_reservations:
            check_in = res.get('check_in')
            check_out = res.get('check_out')
            booking_status_res = res.get('booking_status')
            if check_in and check_out and booking_status_res == 'booked':
                if check_in <= date_str < check_out:
                    date_reservations.append(res)
        
        # No. Booked is the count of reservations for this date
        booking_count = len(date_reservations)
        blocking_count = 1 if daily_info.get('unbookable', 0) else 0
        
        # Get revenue from override price or listing price
        revenue = override_prices.get(date_str, daily_info.get('price', 0))
        
        # Calculate derived fields
        bookable_units = units - blocking_count
        vacant_units = units - booking_count - blocking_count
        if vacant_units < 0:
            vacant_units = 0  # Prevent negative vacant units
        blocking_units = blocking_count * units
        
        pl_daily_record = {
            'Listing ID': listing_id,
            'PMS Name': pms,
            'Date': date_iso,
            'Units': units,
            'No. Booked': booking_count,
            'No. Blocked': blocking_count,
            'blocking_units': blocking_units,
            'Bookable Units': bookable_units,
            'nightly_revenue': revenue,
            'Vacant Units': vacant_units
        }
        
        listing_records.append(pl_daily_record)
        current_date += timedelta(days=1)
    
    date_loop_time = time.time() - t0
    print(f"    ⏱️ Date loop for listing took {date_loop_time:.2f}s")
    print(f"    ✅ Generated {len(listing_records)} daily records")
    
    return listing_records

def generate_pl_daily_for_property(property_key, start_date, end_date):
    """Generate pl_daily data for a specific property."""
    require_api_key()

    # Load property config
    config_path = tool_dir / "config" / "properties.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    property_config = config['properties'].get(property_key, {})
    if not property_config:
        print(f"❌ Property {property_key} not found in config")
        return None
    
    pms = property_config.get('pms', 'cloudbeds')
    listings = property_config.get('listings', [])
    property_name = property_config.get('name', property_key)
    
    print(f"🔍 Generating pl_daily data for {property_name} ({property_key})")
    print(f"📅 Date range: {start_date} to {end_date}")
    print(f"🏢 PMS: {pms}")
    print(f"🏠 Listings: {len(listings)}")
    print("=" * 60)
    
    property_start = time.time()
    
    # Get all reservations (will be filtered by listing ID later)
    t0 = time.time()
    all_reservations = fetch_all_reservations(pms, start_date, end_date)
    reservations_time = time.time() - t0
    print(f"📊 Found {len(all_reservations)} total reservations from {pms} (fetched in {reservations_time:.2f}s)\n")
    
    # Process listings in parallel
    all_records = []
    with ThreadPoolExecutor(max_workers=3) as executor:  # Limit to 3 threads to avoid rate limiting
        # Submit all listing tasks
        future_to_listing = {
            executor.submit(fetch_listing_data, listing, start_date, end_date, all_reservations, pms): listing 
            for listing in listings
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_listing):
            listing = future_to_listing[future]
            try:
                listing_records = future.result()
                all_records.extend(listing_records)
                listing_time = time.time() - property_start
                print(f"  ✅ {listing.get('name', 'Unknown')} processed in {listing_time:.2f}s")
            except Exception as exc:
                print(f"  ❌ {listing.get('name', 'Unknown')} generated an exception: {exc}")
    
    property_time = time.time() - property_start
    print(f"\n✅ Generated {len(all_records)} total pl_daily records (property processed in {property_time:.2f}s)")
    
    return all_records

def generate_pl_daily_for_property_batched(property_key, start_date, end_date):
    """Generate pl_daily data for onera property using batch processing to avoid rate limits."""
    require_api_key()

    # Load property config
    config_path = tool_dir / "config" / "properties.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    property_config = config['properties'].get(property_key, {})
    if not property_config:
        print(f"❌ Property {property_key} not found in config")
        return None
    
    pms = property_config.get('pms', 'cloudbeds')
    listings = property_config.get('listings', [])
    property_name = property_config.get('name', property_key)
    
    print(f"🔍 Generating pl_daily data for {property_name} ({property_key}) - BATCH MODE")
    print(f"📅 Date range: {start_date} to {end_date}")
    print(f"🏢 PMS: {pms}")
    print(f"🏠 Listings: {len(listings)} (processing in batches of 6)")
    print("=" * 60)
    
    property_start = time.time()
    
    # Get all reservations (will be filtered by listing ID later)
    t0 = time.time()
    all_reservations = fetch_all_reservations(pms, start_date, end_date)
    reservations_time = time.time() - t0
    print(f"📊 Found {len(all_reservations)} total reservations from {pms} (fetched in {reservations_time:.2f}s)\n")
    
    # Split listings into batches of 6
    batch_size = 6
    batches = [listings[i:i + batch_size] for i in range(0, len(listings), batch_size)]
    
    all_records = []
    failed_batches = []
    
    # Process each batch
    for batch_num, batch_listings in enumerate(batches, 1):
        print(f"📦 Batch {batch_num}/{len(batches)}: Processing listings {((batch_num-1)*batch_size)+1}-{min(batch_num*batch_size, len(listings))}...")
        batch_start = time.time()
        
        batch_records = []
        batch_failed_listings = []
        
        # Process listings in current batch with parallel processing
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all listing tasks for this batch
            future_to_listing = {
                executor.submit(fetch_listing_data, listing, start_date, end_date, all_reservations, pms): listing 
                for listing in batch_listings
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_listing):
                listing = future_to_listing[future]
                try:
                    # Add delay between listings to respect rate limits
                    time.sleep(2.5)
                    
                    listing_records = future.result()
                    batch_records.extend(listing_records)
                    listing_time = time.time() - batch_start
                    print(f"  ✅ {listing.get('name', 'Unknown')} processed in {listing_time:.2f}s")
                except Exception as exc:
                    print(f"  ❌ {listing.get('name', 'Unknown')} generated an exception: {exc}")
                    batch_failed_listings.append(listing)
        
        # Check if batch was successful
        if batch_failed_listings:
            print(f"  ⚠️  Batch {batch_num} had {len(batch_failed_listings)} failures")
            failed_batches.append((batch_num, batch_failed_listings))
        else:
            print(f"  ✅ Batch {batch_num} completed successfully")
        
        all_records.extend(batch_records)
        batch_time = time.time() - batch_start
        print(f"  📊 Batch {batch_num} processed in {batch_time:.2f}s")
        
        # Wait between batches (except for the last one)
        if batch_num < len(batches):
            print(f"⏳ Waiting 75s before next batch...")
            time.sleep(75)
    
    # Retry failed batches once
    if failed_batches:
        print(f"\n🔄 Retrying {len(failed_batches)} failed batches with longer delays...")
        for batch_num, failed_listings in failed_batches:
            print(f"🔄 Retrying Batch {batch_num}...")
            retry_start = time.time()
            
            # Wait longer before retry
            time.sleep(120)
            
            retry_records = []
            for listing in failed_listings:
                try:
                    time.sleep(5)  # Longer delay for retries
                    listing_records = fetch_listing_data(listing, start_date, end_date, all_reservations, pms)
                    retry_records.extend(listing_records)
                    print(f"  ✅ {listing.get('name', 'Unknown')} retry successful")
                except Exception as exc:
                    print(f"  ❌ {listing.get('name', 'Unknown')} retry failed: {exc}")
            
            all_records.extend(retry_records)
            retry_time = time.time() - retry_start
            print(f"  📊 Batch {batch_num} retry completed in {retry_time:.2f}s")
    
    property_time = time.time() - property_start
    print(f"\n✅ Generated {len(all_records)} total pl_daily records (property processed in {property_time:.2f}s)")
    
    return all_records

def save_pl_daily_csv(pl_daily_data, property_key, output_dir=None):
    """Save pl_daily data to CSV file in the data directory."""
    if not pl_daily_data:
        print("❌ No data to save")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(pl_daily_data)
    # Ensure correct column order
    columns = [
        'Listing ID', 'PMS Name', 'Date', 'Units', 'No. Booked', 'No. Blocked',
        'blocking_units', 'Bookable Units', 'nightly_revenue', 'Vacant Units'
    ]
    df = df[columns]
    
    # Determine output directory - use data/{property_key} if not specified
    if output_dir is None:
        output_dir = tool_dir / "data" / property_key
    
    # Create output directory if it doesn't exist
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use the standard naming convention: pl_daily_{property_key}.csv
    filename = f"pl_daily_{property_key}.csv"
    
    filepath = output_dir / filename
    df.to_csv(filepath, index=False)
    print(f"💾 Saved pl_daily data to: {filepath}")
    
    return str(filepath)

def generate_pl_daily(property_key, start_date=None, end_date=None):
    """
    Main function to generate pl_daily file for a property.
    
    Args:
        property_key: Property identifier (e.g., 'onera')
        start_date: Start date in YYYY-MM-DD format (default: from date_manager)
        end_date: End date in YYYY-MM-DD format (default: from date_manager - Jan 3, 2027)
    
    Returns:
        Path to saved CSV file, or None if failed
    """
    # Import date manager
    from utils.date_manager import get_pl_daily_date_range
    
    # Set default date range if not provided (uses centralized date manager)
    if start_date is None or end_date is None:
        default_start, default_end = get_pl_daily_date_range()
        if start_date is None:
            start_date = default_start
        if end_date is None:
            end_date = default_end
    
    print(f"🎯 Generating pl_daily data for {property_key}")
    print(f"📅 Date range: {start_date} to {end_date}")
    print("=" * 60)
    
    # Generate pl_daily data - use batch processing for onera property
    if property_key == 'onera':
        pl_daily_data = generate_pl_daily_for_property_batched(property_key, start_date, end_date)
    else:
        pl_daily_data = generate_pl_daily_for_property(property_key, start_date, end_date)
    
    if pl_daily_data:
        # Save to CSV
        filepath = save_pl_daily_csv(pl_daily_data, property_key)
        return filepath
    else:
        print(f"❌ Failed to generate pl_daily data for {property_key}")
        return None

if __name__ == "__main__":
    from utils.date_manager import get_pl_daily_date_range
    
    # Check if property key is provided as command line argument
    if len(sys.argv) > 1:
        property_key = sys.argv[1]
        
        # Check if start_date and end_date are provided
        if len(sys.argv) >= 4:
            start_date = sys.argv[2]
            end_date = sys.argv[3]
        else:
            # Use default date range from date manager
            start_date, end_date = get_pl_daily_date_range()
            print(f"Using default date range: {start_date} to {end_date}")
        
        generate_pl_daily(property_key, start_date, end_date)
    else:
        default_start, default_end = get_pl_daily_date_range()
        print("Usage: python generate_pl_daily.py <property_key> [start_date] [end_date]")
        print(f"Default date range: {default_start} to {default_end}")
        print("Example: python generate_pl_daily.py onera")
        print("Example: python generate_pl_daily.py onera 2026-09-01 2026-12-31")
        sys.exit(1)
