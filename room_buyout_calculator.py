#!/usr/bin/env python3
"""
Room Buyout Calculator - Backend
Calculates individual room rates and total buyout costs for any property and date range.
"""

import pandas as pd
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
import logging

from utils.date_manager import get_reservation_query_range

logger = logging.getLogger(__name__)


@dataclass
class RoomRate:
    """Represents rate information for a single listing/room"""
    listing_id: str
    listing_name: str
    units: int  # Number of units this listing has
    rates_by_date: Dict[str, float]  # date -> rate
    availability_by_date: Dict[str, bool]  # date -> available
    vacant_units_by_date: Dict[str, int]  # date -> vacant units count
    min_stay: int = 1
    currency: str = "USD"
    selected_units: int = None  # Number of units actually selected (for buyout calculation)
    
    def get_total_for_stay(self, dates: List[str], num_units: int = None) -> float:
        """
        Calculate total cost for this listing across all dates
        
        Args:
            dates: List of dates
            num_units: Number of units to calculate for (default: all units)
        """
        if num_units is None:
            num_units = self.units
        total = 0.0
        for date_str in dates:
            if date_str in self.rates_by_date:
                total += self.rates_by_date[date_str] * num_units
        return total
    
    def get_avg_rate_per_night(self, dates: List[str]) -> float:
        """Calculate average rate per room per night"""
        if not dates:
            return 0.0
        # Calculate average rate per room per night (not total for all units)
        total_rate = 0.0
        for date_str in dates:
            if date_str in self.rates_by_date:
                total_rate += self.rates_by_date[date_str]  # This is already per room
        return total_rate / len(dates) if dates else 0.0
    
    def is_available_for_all_dates(self, dates: List[str]) -> bool:
        """Check if listing is available for all dates"""
        return all(self.availability_by_date.get(date_str, False) for date_str in dates)
    
    def get_available_units_for_dates(self, dates: List[str]) -> int:
        """
        Get number of available units (minimum vacant units across all dates)
        Returns 0 if any date has no availability
        """
        if not dates:
            return 0
        
        # Check if we have vacant units data
        if any(date_str in self.vacant_units_by_date for date_str in dates):
            # Use actual vacant units count
            min_vacant = min(self.vacant_units_by_date.get(date_str, 0) for date_str in dates)
            return max(0, min_vacant)  # Ensure non-negative
        
        # Fallback to boolean availability
        if not self.is_available_for_all_dates(dates):
            return 0
        return self.units


class RoomBuyoutCalculator:
    """Main calculator class for room buyout calculations"""
    
    @staticmethod
    def generate_date_range(start_date: str, end_date: str) -> List[str]:
        """
        Generate a list of dates from start_date to end_date (exclusive of end_date)
        
        Args:
            start_date: Check-in date in YYYY-MM-DD format (inclusive)
            end_date: Check-out date in YYYY-MM-DD format (exclusive - this date is NOT included)
        
        Returns:
            List of date strings in YYYY-MM-DD format
        
        Example:
            generate_date_range('2026-09-07', '2026-09-09') returns ['2026-09-07', '2026-09-08']
        """
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        dates = []
        current = start
        while current < end:  # Exclude checkout date
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        return dates
    
    def __init__(self, data_root: str = None, config_path: str = None):
        """
        Initialize calculator
        
        Args:
            data_root: Root directory for data files (default: data/ in tool directory)
            config_path: Path to properties.yaml config file (default: config/properties.yaml in tool directory)
        """
        # Set default paths relative to this file's location (tool directory)
        tool_dir = Path(__file__).parent
        if data_root is None:
            self.data_root = tool_dir / "data"
        else:
            self.data_root = Path(data_root)
        
        if config_path is None:
            self.config_path = tool_dir / "config" / "properties.yaml"
        else:
            self.config_path = Path(config_path)
        
        self.properties_config = self._load_properties_config()
    
    def _load_properties_config(self) -> Dict:
        """Load properties configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config.get('properties', {})
        except FileNotFoundError:
            print(f"Warning: Config file not found at {self.config_path}")
            return {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}
    
    def _get_listing_metadata(self, property_name: str) -> Dict[str, Dict]:
        """
        Get listing metadata (name, units) from config
        
        Returns:
            Dict mapping listing_id -> {name: str, units: int}
        """
        metadata = {}
        if property_name not in self.properties_config:
            return metadata
        
        prop_config = self.properties_config[property_name]
        for listing in prop_config.get('listings', []):
            listing_id = str(listing.get('id', ''))
            if listing_id:
                metadata[listing_id] = {
                    'name': listing.get('name', listing_id),
                    'units': listing.get('units', 1)
                }
        return metadata
    
    def _validate_live_rates_csv(self, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
        """
        Validate live rates CSV structure
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_columns = ['listing_id', 'date', 'price']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}"
        
        if df.empty:
            return False, "CSV file is empty"
        
        # Validate date column
        try:
            pd.to_datetime(df['date'])
        except Exception as e:
            return False, f"Invalid date format in 'date' column: {e}"
        
        # Check for null values in critical columns
        if df['listing_id'].isna().any():
            return False, "Found null values in 'listing_id' column"
        if df['price'].isna().any():
            return False, "Found null values in 'price' column"
        
        return True, None
    
    def _load_live_rates(self, property_name: str, dates: List[str]) -> Dict[str, Dict]:
        """
        Load live rates from nightly_pulled_overrides file
        
        Returns:
            Dict mapping "listing_id_date" -> {price: float, min_stay: int, currency: str}
        """
        live_rates = {}
        live_rates_path = self.data_root / property_name / f"{property_name}_nightly_pulled_overrides.csv"
        
        if not live_rates_path.exists():
            return live_rates
        
        try:
            df = pd.read_csv(live_rates_path)
            
            # Validate CSV structure
            is_valid, error_msg = self._validate_live_rates_csv(df)
            if not is_valid:
                print(f"Warning: Invalid live rates CSV structure for {property_name}: {error_msg}")
                return live_rates
            
            # Filter for requested dates
            df = df[df['date'].isin(dates)].copy()
            
            for _, row in df.iterrows():
                try:
                    listing_id = str(row['listing_id']).strip()
                    if not listing_id or listing_id == 'nan':
                        continue
                    
                    date_str = str(row['date']).strip()
                    key = f"{listing_id}_{date_str}"
                    
                    # Validate and convert price
                    price_val = row['price']
                    try:
                        price = float(price_val) if pd.notna(price_val) else 0.0
                    except (ValueError, TypeError):
                        print(f"Warning: Invalid price value for {listing_id} on {date_str}: {price_val}")
                        continue
                    
                    # Get optional fields with defaults
                    min_stay = 1
                    if 'min_stay' in df.columns:
                        min_stay_val = row.get('min_stay', 1)
                        try:
                            min_stay = int(min_stay_val) if pd.notna(min_stay_val) else 1
                            min_stay = max(1, min_stay)  # Ensure at least 1
                        except (ValueError, TypeError):
                            min_stay = 1
                    
                    currency = 'USD'
                    if 'currency' in df.columns:
                        currency_val = row.get('currency', 'USD')
                        currency = str(currency_val).strip() if pd.notna(currency_val) else 'USD'
                    
                    live_rates[key] = {
                        'price': price,
                        'min_stay': min_stay,
                        'currency': currency
                    }
                except Exception as row_error:
                    print(f"Warning: Error processing row in live rates file: {row_error}")
                    continue
        except pd.errors.EmptyDataError:
            print(f"Warning: Live rates CSV file for {property_name} is empty")
        except pd.errors.ParserError as e:
            print(f"Error: Failed to parse live rates CSV for {property_name}: {e}")
        except Exception as e:
            print(f"Error loading live rates for {property_name}: {e}")
            import traceback
            traceback.print_exc()
        
        return live_rates
    
    def _validate_pl_daily_csv(self, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
        """
        Validate pl_daily CSV structure
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_columns = ['Date', 'Listing ID']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}"
        
        if df.empty:
            return False, "CSV file is empty"
        
        # Check for required data columns (at least one rate column)
        rate_columns = ['nightly_revenue', 'Live Rate $']
        if not any(col in df.columns for col in rate_columns):
            return False, f"Missing rate column. Expected one of: {', '.join(rate_columns)}"
        
        # Check for availability column
        if 'Vacant Units' not in df.columns:
            return False, "Missing 'Vacant Units' column"
        
        # Validate date column can be parsed
        try:
            pd.to_datetime(df['Date'])
        except Exception as e:
            return False, f"Invalid date format in 'Date' column: {e}"
        
        # Check for null values in critical columns
        if df['Listing ID'].isna().any():
            return False, "Found null values in 'Listing ID' column"
        
        return True, None
    
    def _load_pl_daily_rates(self, property_name: str, dates: List[str]) -> Tuple[Dict[str, float], Dict[str, bool], Dict[str, int]]:
        """
        Load rates and availability from pl_daily file (fallback)
        
        Returns:
            Tuple of (rates_dict, availability_dict, vacant_units_dict)
            rates_dict: "listing_id_date" -> rate
            availability_dict: "listing_id_date" -> available (bool)
            vacant_units_dict: "listing_id_date" -> vacant_units (int)
        """
        rates = {}
        availability = {}
        vacant_units_dict = {}
        pl_daily_path = self.data_root / property_name / f"pl_daily_{property_name}.csv"
        
        if not pl_daily_path.exists():
            return rates, availability, vacant_units_dict
        
        try:
            df = pd.read_csv(pl_daily_path)
            
            # Validate CSV structure
            is_valid, error_msg = self._validate_pl_daily_csv(df)
            if not is_valid:
                print(f"Warning: Invalid pl_daily CSV structure for {property_name}: {error_msg}")
                return rates, availability, vacant_units_dict
            
            # Extract date part
            df['Date_clean'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            df = df[df['Date_clean'].isin(dates)].copy()
            
            for _, row in df.iterrows():
                try:
                    listing_id = str(row['Listing ID']).strip()
                    if not listing_id or listing_id == 'nan':
                        continue
                    
                    date_str = str(row['Date_clean'])
                    key = f"{listing_id}_{date_str}"
                    
                    # Get rate (prefer nightly_revenue, fallback to other columns)
                    rate = 0.0
                    if 'nightly_revenue' in df.columns:
                        rate_val = row.get('nightly_revenue', 0)
                        try:
                            rate = float(rate_val) if pd.notna(rate_val) else 0.0
                        except (ValueError, TypeError):
                            rate = 0.0
                    elif 'Live Rate $' in df.columns:
                        rate_val = row.get('Live Rate $', 0)
                        try:
                            rate = float(rate_val) if pd.notna(rate_val) else 0.0
                        except (ValueError, TypeError):
                            rate = 0.0
                    
                    rates[key] = rate
                    
                    # Check availability (Vacant Units > 0 means available)
                    vacant_units_val = row.get('Vacant Units', 0)
                    try:
                        vacant_units = int(vacant_units_val) if pd.notna(vacant_units_val) else 0
                        vacant_units = max(0, vacant_units)  # Ensure non-negative
                    except (ValueError, TypeError):
                        vacant_units = 0

                    # Fully booked nights: No. Booked >= Units (occupancy is not on the live-rates GET)
                    booked = 0
                    units_count = 0
                    if 'No. Booked' in df.columns:
                        try:
                            booked_val = row.get('No. Booked', 0)
                            booked = int(booked_val) if pd.notna(booked_val) else 0
                        except (ValueError, TypeError):
                            booked = 0
                    if 'Units' in df.columns:
                        try:
                            units_val = row.get('Units', 0)
                            units_count = int(units_val) if pd.notna(units_val) else 0
                        except (ValueError, TypeError):
                            units_count = 0
                    if units_count > 0 and booked >= units_count:
                        vacant_units = 0
                    
                    availability[key] = vacant_units > 0
                    vacant_units_dict[key] = vacant_units
                except Exception as row_error:
                    print(f"Warning: Error processing row in pl_daily file: {row_error}")
                    continue
        except pd.errors.EmptyDataError:
            print(f"Warning: pl_daily CSV file for {property_name} is empty")
        except pd.errors.ParserError as e:
            print(f"Error: Failed to parse pl_daily CSV for {property_name}: {e}")
        except Exception as e:
            print(f"Error loading pl_daily rates for {property_name}: {e}")
            import traceback
            traceback.print_exc()
        
        return rates, availability, vacant_units_dict
    
    def fetch_live_stay_data(
        self,
        property_name: str,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Live prices (GET overrides) and occupancy for a stay.

        Occupancy:
          - 1-unit: POST /listing_prices (`Booked` in booking_status, unbookable)
          - multi-unit: GET /reservation_data for booked count; listing_prices for unbookable
        Units come from properties.yaml. Falls back to local CSVs if the API is unavailable.
        """
        dates = self.generate_date_range(start_date, end_date)
        pl_rates, pl_availability, pl_vacant = self._load_pl_daily_rates(property_name, dates)
        csv_rates = self._load_live_rates(property_name, dates)
        empty = {
            'live_rates': {},
            'occupancy': {'availability': {}, 'vacant_units': {}},
            'rate_source': 'none',
            'occupancy_source': 'none',
        }
        if not dates:
            return empty

        prop_config = self.properties_config.get(property_name, {})
        pms = prop_config.get('pms', 'cloudbeds')
        listings = prop_config.get('listings', [])

        try:
            from utils.api_client import (
                PriceLabsAPI,
                parse_listing_overrides,
                count_reservations_by_date,
                compute_nightly_occupancy,
            )
            api = PriceLabsAPI(enable_caching=False)
        except Exception as e:
            logger.warning(f"Live stay fetch unavailable: {e}")
            result = dict(empty)
            if csv_rates:
                result['live_rates'] = csv_rates
                result['rate_source'] = 'csv'
            if pl_availability:
                result['occupancy'] = {
                    'availability': pl_availability,
                    'vacant_units': pl_vacant,
                }
                result['occupancy_source'] = 'csv'
            return result

        has_multi = any(int(listing.get('units', 1) or 1) > 1 for listing in listings)
        reservations = []
        total_steps = len(listings) + (1 if has_multi else 0)
        step = 0

        if has_multi:
            if progress_callback:
                progress_callback(step, total_steps, "Reservations")
            try:
                res_start, res_end = get_reservation_query_range(start_date, end_date)
                reservations = api.fetch_all_reservations(pms, res_start, res_end)
            except Exception as e:
                logger.warning(f"reservation_data fetch failed: {e}")
                reservations = []
            step += 1

        live_rates = {}
        occupancy_avail = {}
        occupancy_vacant = {}
        last_night = dates[-1]
        got_live_occupancy = bool(reservations)

        for listing in listings:
            listing_id = str(listing.get('id', ''))
            listing_label = listing.get('name', listing_id)
            if progress_callback:
                progress_callback(step, total_steps, listing_label)
            step += 1
            if not listing_id:
                continue

            try:
                units = int(listing.get('units', 1) or 1)
            except (TypeError, ValueError):
                units = 1

            daily = {}
            try:
                daily = api.get_listing_daily_data(listing_id, pms, dates[0], last_night)
                if daily:
                    got_live_occupancy = True
            except Exception as e:
                logger.warning(f"listing_prices failed for {listing_label} ({listing_id}): {e}")

            reserved = {}
            if units > 1:
                reserved = count_reservations_by_date(reservations, listing_id, dates)

            occ = compute_nightly_occupancy(units, dates, daily, reserved)
            for date_str, info in occ.items():
                key = f"{listing_id}_{date_str}"
                occupancy_avail[key] = info['available']
                occupancy_vacant[key] = info['vacant']

            try:
                payload = api.get_listing_overrides(listing_id, pms=pms)
                parsed = parse_listing_overrides(payload, start_date=dates[0], end_date=last_night)
                for date_str, info in parsed.items():
                    if date_str in dates:
                        live_rates[f"{listing_id}_{date_str}"] = {
                            'price': info['price'],
                            'min_stay': info.get('min_stay', 1),
                            'currency': 'USD'
                        }
            except Exception as e:
                logger.warning(f"Override GET failed for {listing_label} ({listing_id}): {e}")

        rate_source = 'api' if live_rates else ('csv' if csv_rates else 'none')
        if not live_rates and csv_rates:
            live_rates = csv_rates

        occupancy_source = 'api' if got_live_occupancy else ('csv' if pl_availability else 'none')
        occupancy = {'availability': occupancy_avail, 'vacant_units': occupancy_vacant}
        if occupancy_source != 'api' and pl_availability:
            occupancy = {'availability': pl_availability, 'vacant_units': pl_vacant}

        return {
            'live_rates': live_rates,
            'occupancy': occupancy,
            'rate_source': rate_source,
            'occupancy_source': occupancy_source,
        }

    def fetch_live_override_rates(
        self,
        property_name: str,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[Dict[str, Dict], str]:
        """Live prices for a stay. Prefers GET listing overrides, then local CSV."""
        stay = self.fetch_live_stay_data(
            property_name, start_date, end_date, progress_callback=progress_callback
        )
        return stay['live_rates'], stay['rate_source']

    def fetch_live_occupancy(
        self,
        property_name: str,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[Dict, str]:
        """Live occupancy for a stay. Falls back to local pl_daily."""
        stay = self.fetch_live_stay_data(
            property_name, start_date, end_date, progress_callback=progress_callback
        )
        return stay['occupancy'], stay['occupancy_source']

    def get_room_rates(
        self, 
        property_name: str, 
        start_date: str, 
        end_date: str,
        use_live_rates: bool = True,
        live_rates: Optional[Dict[str, Dict]] = None,
        use_live_occupancy: bool = True,
        occupancy: Optional[Dict] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[RoomRate]:
        """
        Get room rates for a property and date range
        
        Args:
            property_name: Property identifier (e.g., 'onera')
            start_date: Check-in date in YYYY-MM-DD format (inclusive)
            end_date: Check-out date in YYYY-MM-DD format (exclusive - this date is NOT included)
            use_live_rates: Fetch GET /listings/{id}/overrides for prices
            live_rates: Pre-fetched live rate map, keyed "listing_id_date" -> {price, min_stay, currency}
            use_live_occupancy: Fetch live occupancy (listing_prices / reservation_data)
            occupancy: Pre-fetched {availability, vacant_units} maps
            progress_callback: Optional (index, total, listing_name) during live fetches
        
        Returns:
            List of RoomRate objects
        
        Note:
            The end_date is treated as checkout date (exclusive). For example:
            - start_date='2026-09-07', end_date='2026-09-09' means nights of Sept 7 and 8 only
            - This follows standard hotel booking convention where checkout date is not charged
        """
        dates = self.generate_date_range(start_date, end_date)
        listing_metadata = self._get_listing_metadata(property_name)
        pl_rates, pl_availability, pl_vacant_units = self._load_pl_daily_rates(property_name, dates)

        need_live = (
            (live_rates is None and use_live_rates)
            or (occupancy is None and use_live_occupancy)
        )
        stay = None
        if need_live:
            stay = self.fetch_live_stay_data(
                property_name, start_date, end_date, progress_callback=progress_callback
            )

        if live_rates is None and use_live_rates:
            live_rates = stay['live_rates'] if stay else {}
        elif live_rates is None:
            live_rates = {}

        if occupancy is None and use_live_occupancy:
            occupancy = stay['occupancy'] if stay else {'availability': {}, 'vacant_units': {}}
        elif occupancy is None:
            occupancy = {'availability': {}, 'vacant_units': {}}

        live_avail = occupancy.get('availability') or {}
        live_vacant = occupancy.get('vacant_units') or {}
        
        # Build RoomRate objects
        room_rates = []
        for listing_id, metadata in listing_metadata.items():
            rates_by_date = {}
            availability_by_date = {}
            vacant_units_by_date = {}
            min_stay = 1
            currency = "USD"
            
            for date_str in dates:
                live_key = f"{listing_id}_{date_str}"

                if live_key in live_rates:
                    rates_by_date[date_str] = live_rates[live_key]['price']
                    min_stay = max(min_stay, live_rates[live_key].get('min_stay', 1))
                    currency = live_rates[live_key].get('currency', 'USD')
                else:
                    rates_by_date[date_str] = pl_rates.get(live_key, 0.0)

                if live_key in live_vacant:
                    vacant_units_by_date[date_str] = live_vacant[live_key]
                    availability_by_date[date_str] = live_avail.get(
                        live_key, live_vacant[live_key] > 0
                    )
                elif live_key in pl_vacant_units:
                    vacant_units_by_date[date_str] = pl_vacant_units[live_key]
                    availability_by_date[date_str] = pl_availability.get(live_key, False)
                else:
                    vacant_units_by_date[date_str] = 0
                    availability_by_date[date_str] = False
            
            # Only include listings that have at least some rate data
            if any(rates_by_date.values()):
                room_rate = RoomRate(
                    listing_id=listing_id,
                    listing_name=metadata['name'],
                    units=metadata['units'],
                    rates_by_date=rates_by_date,
                    availability_by_date=availability_by_date,
                    vacant_units_by_date=vacant_units_by_date,
                    min_stay=min_stay,
                    currency=currency
                )
                room_rates.append(room_rate)
        
        return room_rates
    
    def select_cheapest_rooms(
        self,
        room_rates: List[RoomRate],
        num_rooms_needed: int,
        dates: List[str],
        only_available: bool = True
    ) -> Tuple[List[RoomRate], int]:
        """
        Select cheapest rooms to meet the required number
        
        Args:
            room_rates: List of available room rates
            num_rooms_needed: Number of rooms needed
            dates: List of dates in YYYY-MM-DD format
            only_available: Only select rooms available for all dates
        
        Returns:
            Tuple of (selected_room_rates, total_rooms_selected)
        """
        # Filter by availability if requested
        if only_available:
            available_rates = [
                rr for rr in room_rates 
                if rr.is_available_for_all_dates(dates)
            ]
        else:
            available_rates = room_rates
        
        # Calculate cost per room for sorting (total cost / available units)
        # This ensures we prioritize listings with better value
        def get_cost_per_available_room(room_rate: RoomRate) -> float:
            available_units = room_rate.get_available_units_for_dates(dates)
            if available_units <= 0:
                return float('inf')  # Not available, put at end
            total_cost = room_rate.get_total_for_stay(dates, num_units=available_units)
            return total_cost / available_units
        
        # Sort by cost per available room (cheapest first)
        available_rates.sort(key=get_cost_per_available_room)
        
        # Select rooms until we have enough
        selected = []
        total_rooms = 0
        
        for room_rate in available_rates:
            if total_rooms >= num_rooms_needed:
                break
            
            available_units = room_rate.get_available_units_for_dates(dates)
            if available_units > 0:
                # Only take as many units as we need
                units_needed = num_rooms_needed - total_rooms
                units_to_take = min(available_units, units_needed)
                
                # Store how many units we're actually using from this listing
                room_rate.selected_units = units_to_take
                selected.append(room_rate)
                total_rooms += units_to_take
        
        return selected, total_rooms
    
    def select_rooms_manually(
        self,
        room_rates: List[RoomRate],
        manual_selections: List[Dict[str, any]],
        dates: List[str],
        validate_availability: bool = True
    ) -> Tuple[List[RoomRate], int]:
        """
        Select rooms manually based on user-provided selections
        
        Args:
            room_rates: List of available room rates
            manual_selections: List of dicts with 'listing_id' and 'units' keys
                Example: [{'listing_id': '203812___643760', 'units': 1}, ...]
            dates: List of dates in YYYY-MM-DD format
            validate_availability: Whether to check if selected units are available
        
        Returns:
            Tuple of (selected_room_rates, total_rooms_selected)
        
        Raises:
            ValueError: If listing_id not found or insufficient units available
        """
        # Create a mapping of listing_id to RoomRate
        listing_map = {room.listing_id: room for room in room_rates}
        
        selected = []
        total_rooms = 0
        
        for selection in manual_selections:
            listing_id = str(selection.get('listing_id', ''))
            units_requested = int(selection.get('units', 0))
            
            if not listing_id:
                raise ValueError(f"Invalid selection: missing listing_id")
            
            if units_requested <= 0:
                raise ValueError(f"Invalid selection for {listing_id}: units must be > 0")
            
            # Find the room rate
            if listing_id not in listing_map:
                raise ValueError(f"Listing ID {listing_id} not found in available room rates")
            
            room_rate = listing_map[listing_id]
            
            # Check availability if requested
            if validate_availability:
                available_units = room_rate.get_available_units_for_dates(dates)
                if units_requested > available_units:
                    raise ValueError(
                        f"Listing {room_rate.listing_name} ({listing_id}): "
                        f"Requested {units_requested} units, but only {available_units} available"
                    )
            
            # Check if we already selected this listing
            existing_selection = next((r for r in selected if r.listing_id == listing_id), None)
            if existing_selection:
                # Add to existing selection
                existing_units = getattr(existing_selection, 'selected_units', existing_selection.get_available_units_for_dates(dates))
                existing_selection.selected_units = existing_units + units_requested
                total_rooms += units_requested
            else:
                # New selection
                room_rate.selected_units = units_requested
                selected.append(room_rate)
                total_rooms += units_requested
        
        return selected, total_rooms
    
    def get_available_listings_for_selection(
        self,
        room_rates: List[RoomRate],
        dates: List[str]
    ) -> List[Dict]:
        """
        Get all available listings with details for manual selection
        
        Args:
            room_rates: List of available room rates
            dates: List of dates in YYYY-MM-DD format
        
        Returns:
            List of dictionaries with listing details for selection UI
        """
        available_listings = []
        
        for room in room_rates:
            available_units = room.get_available_units_for_dates(dates)
            if available_units > 0:
                total_cost = room.get_total_for_stay(dates, num_units=available_units)
                # Calculate rate per room per night (not total cost divided by units)
                # This is the average nightly rate for one room
                avg_rate_per_room_per_night = room.get_avg_rate_per_night(dates)
                
                available_listings.append({
                    'listing_id': room.listing_id,
                    'listing_name': room.listing_name,
                    'total_units': room.units,
                    'available_units': available_units,
                    'total_cost_for_available': round(total_cost, 2),
                    'cost_per_room': round(avg_rate_per_room_per_night, 2),  # Rate per room per night
                    'avg_rate_per_night': round(room.get_avg_rate_per_night(dates), 2),
                    'rates_by_date': {
                        date_str: round(rate, 2) 
                        for date_str, rate in room.rates_by_date.items()
                    },
                    'vacant_units_by_date': {
                        date_str: room.vacant_units_by_date.get(date_str, 0)
                        for date_str in dates
                    },
                    'is_available': room.is_available_for_all_dates(dates)
                })
        
        # Sort by cost per room (cheapest first) for easier selection
        available_listings.sort(key=lambda x: x['cost_per_room'])
        
        return available_listings
    
    def calculate_buyout(
        self,
        selected_rooms: List[RoomRate],
        dates: List[str]
    ) -> Dict:
        """
        Calculate total buyout cost and summary statistics
        
        Args:
            selected_rooms: List of selected RoomRate objects
            dates: List of dates in YYYY-MM-DD format
        
        Returns:
            Dictionary with buyout calculations
        """
        if not selected_rooms or not dates:
            return {
                'total_buyout': 0.0,
                'total_rooms': 0,
                'avg_rate_per_room': 0.0,
                'avg_rate_per_night': 0.0,
                'breakdown_by_night': {},
                'breakdown_by_listing': []
            }
        
        # Calculate totals (using selected units, not all available units)
        total_buyout = 0.0
        total_rooms = 0
        for room in selected_rooms:
            # Use selected_units if set, otherwise use all available units
            if hasattr(room, 'selected_units') and room.selected_units is not None:
                units_to_use = room.selected_units
            else:
                units_to_use = room.get_available_units_for_dates(dates)
            total_buyout += room.get_total_for_stay(dates, num_units=units_to_use)
            total_rooms += units_to_use
        
        # Calculate averages
        avg_rate_per_room = total_buyout / total_rooms if total_rooms > 0 else 0.0
        avg_rate_per_night = total_buyout / len(dates) if dates else 0.0
        
        # Breakdown by night
        breakdown_by_night = {}
        for date_str in dates:
            night_total = 0.0
            for room in selected_rooms:
                if date_str in room.rates_by_date:
                    # Use selected_units if set, otherwise use all units
                    if hasattr(room, 'selected_units') and room.selected_units is not None:
                        units_to_use = room.selected_units
                    else:
                        units_to_use = room.get_available_units_for_dates(dates)
                    night_total += room.rates_by_date[date_str] * units_to_use
            breakdown_by_night[date_str] = night_total
        
        # Breakdown by listing with individual room rates
        breakdown_by_listing = []
        for room in selected_rooms:
            # Use selected_units if set, otherwise use all available units
            if hasattr(room, 'selected_units') and room.selected_units is not None:
                units_to_use = room.selected_units
            else:
                units_to_use = room.get_available_units_for_dates(dates)
            
            available_units = room.get_available_units_for_dates(dates)
            # Calculate per-room rates for each date
            rates_per_room_by_date = {
                date_str: rate for date_str, rate in room.rates_by_date.items()
            }
            
            breakdown_by_listing.append({
                'listing_name': room.listing_name,
                'listing_id': room.listing_id,
                'total_units': room.units,
                'available_units': available_units,
                'selected_units': units_to_use,  # Units actually used in buyout
                'total_cost': room.get_total_for_stay(dates, num_units=units_to_use),
                'avg_rate_per_night': room.get_avg_rate_per_night(dates),
                'rate_per_room_per_night': {
                    date_str: rate for date_str, rate in room.rates_by_date.items()
                },
                'vacant_units_by_date': {
                    date_str: room.vacant_units_by_date.get(date_str, 0)
                    for date_str in dates
                }
            })
        
        return {
            'total_buyout': round(total_buyout, 2),
            'total_rooms': total_rooms,
            'avg_rate_per_room': round(avg_rate_per_room, 2),
            'avg_rate_per_night': round(avg_rate_per_night, 2),
            'breakdown_by_night': breakdown_by_night,
            'breakdown_by_listing': breakdown_by_listing,
            'num_nights': len(dates)
        }


def main():
    """Test the calculator"""
    print("🧪 Testing Room Buyout Calculator\n")
    
    calculator = RoomBuyoutCalculator()
    
    # Test with onera, Sept 7-9, 2026 (checkout on Sept 9 = nights of Sept 7 & 8)
    property_name = "onera"
    start_date = "2026-09-07"
    end_date = "2026-09-09"  # Checkout date (exclusive)
    num_rooms = 30
    
    print(f"Property: {property_name}")
    print(f"Check-in: {start_date}, Check-out: {end_date}")
    dates = calculator.generate_date_range(start_date, end_date)
    print(f"Nights: {', '.join(dates)} ({len(dates)} nights)")
    print(f"Rooms needed: {num_rooms}\n")
    
    # Get room rates
    print("Loading room rates...")
    room_rates = calculator.get_room_rates(
        property_name, start_date, end_date, use_live_rates=False, use_live_occupancy=False
    )
    print(f"Found {len(room_rates)} listings with rate data\n")
    
    # Select cheapest
    selected, total_selected = calculator.select_cheapest_rooms(
        room_rates, num_rooms, dates, only_available=True
    )
    
    print(f"Selected {len(selected)} listings ({total_selected} total rooms)\n")
    
    # Calculate buyout
    buyout = calculator.calculate_buyout(selected, dates)
    
    print("=" * 60)
    print("BUYOUT SUMMARY")
    print("=" * 60)
    print(f"Total Buyout Cost: ${buyout['total_buyout']:,.2f}")
    print(f"Total Rooms: {buyout['total_rooms']}")
    print(f"Average Rate per Room: ${buyout['avg_rate_per_room']:.2f}")
    print(f"Average Rate per Night: ${buyout['avg_rate_per_night']:.2f}")
    print(f"\nBreakdown by Night:")
    for date_str, cost in buyout['breakdown_by_night'].items():
        print(f"  {date_str}: ${cost:,.2f}")
    print(f"\nBreakdown by Listing:")
    for listing in buyout['breakdown_by_listing']:
        print(f"  {listing['listing_name']} ({listing['units']} units): ${listing['total_cost']:,.2f}")


if __name__ == "__main__":
    main()
