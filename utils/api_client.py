"""
PriceLabs API Client for Room Buyout Tool
"""
import requests
from typing import List, Dict, Optional
import logging
import time
from functools import lru_cache
from datetime import datetime, timedelta
from .config import API_KEY, BASE_URL

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


class PriceLabsAPI:
    def __init__(self, enable_caching=True, cache_ttl=300):
        self.api_key = API_KEY
        if not self.api_key:
            raise ValueError("PRICELABS_API_KEY environment variable is required")
        
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(base_delay=1.0, max_delay=60.0)
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
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                self.rate_limiter.handle_rate_limit(retry_after=retry_after)
                raise requests.exceptions.HTTPError(f"Rate limit exceeded. Retry after: {retry_after}")
            
            response.raise_for_status()
            
            # Cache successful GET responses
            if method.upper() == 'GET' and self.enable_caching:
                cache_key = self._get_cache_key(url, params=kwargs.get('params'))
                self._cache_response(cache_key, response.json())
            
            self.rate_limiter.handle_success()
            return response
            
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                raise  # Re-raise rate limit errors
            self.rate_limiter.handle_error()
            raise
        except requests.exceptions.RequestException as e:
            self.rate_limiter.handle_error()
            raise

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
                
            response = self._make_request(
                'GET',
                f"{self.base_url}/listings/{listing_id}/overrides",
                params=params
            )
            return response.json()
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
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching daily data for listing {listing_id}: {e}")
            raise PriceLabsAPIError(f"Error fetching daily data: {e}")
    
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
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching reservations: {e}")
            raise PriceLabsAPIError(f"Error fetching reservations: {e}")
    
    def clear_cache(self):
        """Clear the API response cache"""
        self._cache.clear()
        logger.info("API cache cleared")

class PriceLabsAPIError(Exception):
    """Custom exception for API errors"""
    pass
