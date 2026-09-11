"""
PriceLabs API Client for Room Buyout Tool
"""
import requests
from typing import List, Dict, Optional
import logging
import time
from .config import API_KEY, BASE_URL, OVERRIDE_REQUEST_DELAY

logger = logging.getLogger(__name__)

class RateLimiter:
    """Dynamic rate limiter that adjusts delays based on API responses"""
    def __init__(self, base_delay=1.0, max_delay=60.0, backoff_factor=2.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.current_delay = base_delay
        self.last_request_time = 0
        self.consecutive_errors = 0
        
    def wait_if_needed(self):
        """Wait if needed to respect rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.current_delay:
            sleep_time = self.current_delay - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def handle_success(self):
        """Reset delay on successful request"""
        if self.consecutive_errors > 0:
            self.consecutive_errors = 0
            # Gradually reduce delay back to base
            self.current_delay = max(self.base_delay, self.current_delay / self.backoff_factor)
    
    def handle_rate_limit(self, retry_after=None):
        """Handle rate limit error (429)"""
        self.consecutive_errors += 1
        if retry_after:
            self.current_delay = float(retry_after) + 1.0
        else:
            self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay)
        logger.warning(f"Rate limit hit. New delay: {self.current_delay:.2f}s")
    
    def handle_error(self):
        """Handle other API errors"""
        self.consecutive_errors += 1
        self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay)
    
    def get_delay(self):
        """Get current delay value"""
        return self.current_delay


def parse_listing_overrides(payload, start_date: str = None, end_date: str = None) -> Dict[str, Dict]:
    """
    Parse a PriceLabs overrides response into {date: {price, min_stay}}.

    Accepts `{ "overrides": [...] }` or `{ "data": [...] }` (or a bare list).
    Dates outside start_date/end_date (inclusive, YYYY-MM-DD) are dropped.
    """
    if isinstance(payload, dict):
        raw = payload.get('overrides')
        if raw is None:
            raw = payload.get('data', [])
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []

    if not isinstance(raw, list):
        raw = []

    parsed = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        date_val = item.get('date')
        if not date_val:
            continue
        date_str = str(date_val)[:10]
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        try:
            price = float(item.get('price', 0) or 0)
        except (TypeError, ValueError):
            continue
        min_stay = 1
        if item.get('min_stay') is not None:
            try:
                min_stay = max(1, int(item['min_stay']))
            except (TypeError, ValueError):
                min_stay = 1
        parsed[date_str] = {'price': price, 'min_stay': min_stay}
    return parsed


def parse_listing_prices(payload, start_date: str = None, end_date: str = None) -> Dict[str, Dict]:
    """
    Parse POST /listing_prices into {date: {price, booking_status, unbookable}}.

    Typical body is `[{ "data": [ {date, price, booking_status, unbookable}, ... ] }]`.
    """
    entries = []
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            entries = first.get('data', [])
    elif isinstance(payload, dict):
        entries = payload.get('data', [])
        if not isinstance(entries, list):
            entries = []
    if not isinstance(entries, list):
        entries = []

    parsed = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        date_val = item.get('date')
        if not date_val:
            continue
        date_str = str(date_val)[:10]
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        price = 0.0
        try:
            price = float(item.get('price', 0) or 0)
        except (TypeError, ValueError):
            price = 0.0
        parsed[date_str] = {
            'price': price,
            'booking_status': str(item.get('booking_status') or ''),
            'unbookable': bool(item.get('unbookable')),
        }
    return parsed


def count_reservations_by_date(reservations, listing_id: str, dates: List[str]) -> Dict[str, int]:
    """Count booked reservations per night: check_in <= date < check_out."""
    counts = {d: 0 for d in dates}
    listing_id = str(listing_id)
    for res in reservations or []:
        if not isinstance(res, dict):
            continue
        if str(res.get('listing_id')) != listing_id:
            continue
        if str(res.get('booking_status') or '').lower() != 'booked':
            continue
        check_in = str(res.get('check_in') or '')[:10]
        check_out = str(res.get('check_out') or '')[:10]
        if not check_in or not check_out:
            continue
        for date_str in dates:
            if check_in <= date_str < check_out:
                counts[date_str] += 1
    return counts


def compute_nightly_occupancy(
    units: int,
    dates: List[str],
    daily_by_date: Dict[str, Dict],
    reserved_by_date: Optional[Dict[str, int]] = None,
) -> Dict[str, Dict]:
    """
    Occupancy for one listing.

    1-unit: booked if 'Booked' in listing_prices booking_status.
    Multi-unit: booked count from reservation_data; listing_prices only for unbookable.
    Fully booked when booked >= units.
    """
    try:
        units = int(units)
    except (TypeError, ValueError):
        units = 1
    if units < 1:
        units = 1
    reserved_by_date = reserved_by_date or {}
    result = {}
    for date_str in dates:
        daily = daily_by_date.get(date_str)
        if units == 1 and not daily:
            result[date_str] = {
                'booked': 0,
                'blocked': 0,
                'vacant': 0,
                'available': False,
            }
            continue
        daily = daily or {}
        blocked = 1 if daily.get('unbookable') else 0
        if units == 1:
            status = str(daily.get('booking_status') or '')
            booked = 1 if 'Booked' in status else 0
        else:
            try:
                booked = int(reserved_by_date.get(date_str, 0) or 0)
            except (TypeError, ValueError):
                booked = 0
        vacant = max(0, units - booked - blocked)
        if booked >= units:
            vacant = 0
        result[date_str] = {
            'booked': booked,
            'blocked': blocked,
            'vacant': vacant,
            'available': vacant > 0,
        }
    return result


def _response_json(result):
    if hasattr(result, 'json'):
        return result.json()
    return result


class PriceLabsAPI:
    def __init__(self, enable_caching=True, cache_ttl=300, base_delay=None):
        self.api_key = API_KEY
        if not self.api_key:
            raise ValueError("PRICELABS_API_KEY environment variable is required")
        
        self.base_url = BASE_URL
        self.session = requests.Session()
        delay = OVERRIDE_REQUEST_DELAY if base_delay is None else base_delay
        self.rate_limiter = RateLimiter(base_delay=delay, max_delay=60.0)
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl  # Cache TTL in seconds
        self._cache = {}  # Simple in-memory cache
        
        # Configure connection pooling for better performance
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # Create a retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        
        # Create HTTP adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=retry_strategy
        )
        
        # Mount the adapter for both HTTP and HTTPS
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set headers
        self.session.headers.update({
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json',
            'Connection': 'keep-alive'
        })
    
    def _get_cache_key(self, url, params=None, json_data=None):
        """Generate cache key from request parameters"""
        key_parts = [url]
        if params:
            key_parts.append(str(sorted(params.items())))
        if json_data:
            key_parts.append(str(sorted(json_data.items())))
        return hash(tuple(key_parts))
    
    def _get_cached_response(self, cache_key):
        """Get cached response if available and not expired"""
        if not self.enable_caching:
            return None
        
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_data
            else:
                # Remove expired cache entry
                del self._cache[cache_key]
        return None
    
    def _cache_response(self, cache_key, data):
        """Cache response data"""
        if self.enable_caching:
            self._cache[cache_key] = (data, time.time())
    
    def _make_request(self, method, url, **kwargs):
        """Make API request with rate limiting and error handling"""
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            self.rate_limiter.wait_if_needed()

            # Check cache for GET requests
            if method.upper() == 'GET' and self.enable_caching:
                cache_key = self._get_cache_key(url, params=kwargs.get('params'))
                cached_response = self._get_cached_response(cache_key)
                if cached_response is not None:
                    logger.debug(f"Cache hit for {url}")
                    return cached_response

            try:
                response = self.session.request(method, url, **kwargs)

                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    self.rate_limiter.handle_rate_limit(retry_after=retry_after)
                    last_error = requests.exceptions.HTTPError(
                        f"Rate limit exceeded. Retry after: {retry_after}"
                    )
                    if attempt < max_attempts - 1:
                        time.sleep(self.rate_limiter.current_delay)
                        continue
                    raise last_error

                response.raise_for_status()

                if method.upper() == 'GET' and self.enable_caching:
                    cache_key = self._get_cache_key(url, params=kwargs.get('params'))
                    self._cache_response(cache_key, response.json())

                self.rate_limiter.handle_success()
                return response

            except requests.exceptions.HTTPError as e:
                last_error = e
                if e.response is not None and e.response.status_code == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    self.rate_limiter.handle_rate_limit(retry_after=retry_after)
                    if attempt < max_attempts - 1:
                        time.sleep(self.rate_limiter.current_delay)
                        continue
                    raise
                self.rate_limiter.handle_error()
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                self.rate_limiter.handle_error()
                if attempt < max_attempts - 1:
                    time.sleep(self.rate_limiter.current_delay)
                    continue
                raise

        if last_error:
            raise last_error

    def get_listing_overrides(self, listing_id: str, pms: str = None, start_date: str = None, end_date: str = None) -> Dict:
        """Fetch overrides for a specific listing"""
        try:
            params = {}
            if pms:
                params['pms'] = pms
            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date
                
            result = self._make_request(
                'GET',
                f"{self.base_url}/listings/{listing_id}/overrides",
                params=params
            )
            return _response_json(result)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching overrides for listing {listing_id}: {e}")
            raise PriceLabsAPIError(f"Error fetching overrides: {e}")
    
    def get_daily_data_for_listing(self, listing_id: str, pms: str, start_date: str, end_date: str) -> Dict:
        """Get daily data (pricing, booking status, blocking) for a listing"""
        try:
            url = f"{self.base_url}/listing_prices"
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
            
            response = self._make_request('POST', url, json=payload)
            return _response_json(response)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching daily data for listing {listing_id}: {e}")
            raise PriceLabsAPIError(f"Error fetching daily data: {e}")

    def get_listing_daily_data(self, listing_id: str, pms: str, start_date: str, end_date: str) -> Dict[str, Dict]:
        """POST /listing_prices parsed into {date: {price, booking_status, unbookable}}."""
        raw = self.get_daily_data_for_listing(listing_id, pms, start_date, end_date)
        return parse_listing_prices(raw, start_date=start_date, end_date=end_date)
    
    def fetch_reservations(self, pms: str, start_date: str, end_date: str, limit: int = 100, offset: int = 0) -> Dict:
        """Fetch reservations for the PMS and date range"""
        try:
            params = {
                'pms': pms,
                'start_date': start_date,
                'end_date': end_date,
                'limit': limit,
                'offset': offset
            }
            
            response = self._make_request(
                'GET',
                f"{self.base_url}/reservation_data",
                params=params
            )
            return _response_json(response)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching reservations: {e}")
            raise PriceLabsAPIError(f"Error fetching reservations: {e}")

    def fetch_all_reservations(self, pms: str, start_date: str, end_date: str, limit: int = 100) -> List[Dict]:
        """Page GET /reservation_data until a page has fewer than `limit` rows."""
        offset = 0
        all_reservations = []
        while True:
            payload = self.fetch_reservations(pms, start_date, end_date, limit=limit, offset=offset)
            rows = []
            if isinstance(payload, dict):
                rows = payload.get('data', []) or []
            elif isinstance(payload, list):
                rows = payload
            if not isinstance(rows, list):
                rows = []
            all_reservations.extend(rows)
            if len(rows) < limit:
                return all_reservations
            offset += limit
    
    def clear_cache(self):
        """Clear the API response cache"""
        self._cache.clear()
        logger.info("API cache cleared")

class PriceLabsAPIError(Exception):
    """Custom exception for API errors"""
    pass
