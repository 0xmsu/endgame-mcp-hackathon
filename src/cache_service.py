import os
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic, Union

T = TypeVar('T')

class CacheEntry(Generic[T]):
    """Class representing a cache entry with data and expiration time."""
    def __init__(self, data: T, ttl: int):
        self.data = data
        self.timestamp = int(time.time() * 1000)  # milliseconds
        self.expires_at = self.timestamp + ttl

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return int(time.time() * 1000) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "data": self.data,
            "timestamp": self.timestamp,
            "expiresAt": self.expires_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create a CacheEntry from a dictionary."""
        entry = cls(data["data"], 0)  # ttl is not used here
        entry.timestamp = data["timestamp"]
        entry.expires_at = data["expiresAt"]
        return entry


class TaoStatsCacheService:
    """
    Caching service for TaoStats API
    Significantly reduces API calls by caching results
    and implementing rate limiting per minute
    """
    
    def __init__(self, options: Dict[str, Any] = None):
        if options is None:
            options = {}
            
        # Configure cache path
        self.cache_path = options.get('cache_path') or os.path.join(
            os.getcwd(), '.cache', 'tao-cache.json')
        
        # Configure rate limits
        self.minute_request_limit = options.get('minute_request_limit', 5)
        
        # Enable/disable persistent cache
        self.persistent_cache_enabled = options.get('persistent_cache_enabled', True)
        
        # Initialize cache
        self.cache: Dict[str, CacheEntry] = {}
        self.pending_requests: Dict[str, Any] = {}
        self.request_timestamps: List[int] = []
        self.window_size_ms = 60 * 1000  # 1 minute window
        
        # Initialize cache from disk
        self._initialize_cache()
        
        # Handle shutdown properly
        import atexit
        atexit.register(self._persist_cache)
    
    def _initialize_cache(self) -> None:
        """Initialize cache from persistent storage."""
        if not self.persistent_cache_enabled:
            logging.info('TaoStats persistent cache is disabled')
            return
        
        try:
            # Check if cache directory exists
            cache_dir = os.path.dirname(self.cache_path)
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            
            # Try to load existing cache
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Restore request timestamps, but filter those too old
                if 'requestTimestamps' in cache_data and isinstance(cache_data['requestTimestamps'], list):
                    now = int(time.time() * 1000)
                    self.request_timestamps = [
                        ts for ts in cache_data['requestTimestamps']
                        if now - ts < self.window_size_ms
                    ]
                
                # Restore cache entries
                if 'entries' in cache_data and isinstance(cache_data['entries'], list):
                    for entry in cache_data['entries']:
                        if isinstance(entry, list) and len(entry) == 2:
                            key, value = entry
                            # Only restore non-expired entries
                            cache_entry = CacheEntry.from_dict(value)
                            if not cache_entry.is_expired():
                                self.cache[key] = cache_entry
                
                logging.info(f'Loaded TaoStats cache with {len(self.cache)} entries')
            
            except (FileNotFoundError, json.JSONDecodeError):
                logging.info('No valid TaoStats cache found, starting with empty cache')
        
        except Exception as e:
            logging.error(f'Error initializing TaoStats cache: {e}')
    
    def _persist_cache(self) -> None:
        """Save cache to persistent storage."""
        if not self.persistent_cache_enabled:
            return
        
        try:
            # Create cache structure
            cache_data = {
                "timestamp": int(time.time() * 1000),
                "requestTimestamps": self.request_timestamps,
                "entries": [[key, entry.to_dict()] for key, entry in self.cache.items()]
            }
            
            # Ensure directory exists
            cache_dir = os.path.dirname(self.cache_path)
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            
            # Write cache to file
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            
            logging.debug(f'TaoStats cache persisted with {len(self.cache)} entries')
        
        except Exception as e:
            logging.error(f'Failed to persist TaoStats cache: {e}')
    
    def _cleanup_expired_timestamps(self) -> None:
        """Clean up expired request timestamps (older than window)."""
        now = int(time.time() * 1000)
        self.request_timestamps = [
            ts for ts in self.request_timestamps
            if now - ts < self.window_size_ms
        ]
    
    def _has_reached_rate_limit(self) -> bool:
        """Check if we've reached the rate limit."""
        self._cleanup_expired_timestamps()
        return len(self.request_timestamps) >= self.minute_request_limit
    
    def _record_request(self) -> None:
        """Record a request timestamp."""
        self.request_timestamps.append(int(time.time() * 1000))
    
    def _get_wait_time_ms(self) -> int:
        """Calculate wait time before next request can be made."""
        if not self.request_timestamps:
            return 0
        
        now = int(time.time() * 1000)
        # Sort timestamps to get the oldest
        sorted_timestamps = sorted(self.request_timestamps)
        oldest_request = sorted_timestamps[0]
        
        # Calculate when we can make a new request
        time_until_window_frees = (oldest_request + self.window_size_ms) - now
        return max(0, time_until_window_frees)
    
    async def with_cache(self, 
                         key: str,
                         fetch_fn: Callable[[], Any],
                         options: Dict[str, Any] = None) -> Any:
        """
        Execute a function with result caching
        
        Args:
            key: Unique cache key
            fetch_fn: Async function that makes the actual API call
            options: Cache options
                ttl: Time-to-live in milliseconds
                force_refresh: Force refresh even if in cache
                fallback_to_cache: Use cache even if expired in case of error
                critical: Indicates if this request is critical (priority)
                fail_silently: Don't raise error if rate limit is reached
        
        Returns:
            Result from function or cache
        """
        if options is None:
            options = {}
        
        # Default options
        ttl = options.get('ttl', 3600000)  # 1 hour default
        force_refresh = options.get('force_refresh', False)
        fallback_to_cache = options.get('fallback_to_cache', True)  # Default True
        critical = options.get('critical', False)
        fail_silently = options.get('fail_silently', False)
        
        try:
            # Check if we already have a pending request for this key
            if key in self.pending_requests and not force_refresh:
                logging.debug(f'Using pending request for key: {key}')
                return await self.pending_requests[key]
            
            # Check if we have a valid cache entry
            cached_entry = self.cache.get(key)
            if cached_entry and not force_refresh and not cached_entry.is_expired():
                logging.debug(f'Cache hit for key: {key}')
                return cached_entry.data
            
            # Check if we've reached the rate limit
            if self._has_reached_rate_limit() and not critical:
                # If we have a cache entry, even expired, use it
                if cached_entry and fallback_to_cache:
                    wait_time = self._get_wait_time_ms()
                    logging.warning(
                        f'API rate limit reached ({len(self.request_timestamps)}/{self.minute_request_limit} per minute), '
                        f'wait time: {wait_time // 1000}s, using expired cache for: {key}'
                    )
                    return cached_entry.data
                
                # Otherwise, raise an error or return None based on fail_silently
                wait_time = self._get_wait_time_ms()
                message = (
                    f'TaoStats API rate limit reached ({len(self.request_timestamps)}/{self.minute_request_limit} per minute), '
                    f'need to wait {wait_time // 1000} seconds'
                )
                
                if fail_silently:
                    logging.warning(f'{message}, returning None for: {key}')
                    return None
                else:
                    raise Exception(message)
            
            # Create a promise for the request
            async def execute_fetch():
                try:
                    # Record the request for rate tracking
                    self._record_request()
                    
                    # Make the actual API request
                    logging.info(
                        f'TaoStats API request ({len(self.request_timestamps)}/{self.minute_request_limit} per minute) for: {key}'
                    )
                    result = await fetch_fn()
                    
                    # Update the cache
                    self.cache[key] = CacheEntry(result, ttl)
                    
                    # Persist the cache after each new result
                    self._persist_cache()
                    
                    return result
                except Exception as error:
                    # If a cache entry exists, use it even if expired
                    if fallback_to_cache and cached_entry:
                        logging.warning(f'Error fetching {key}, falling back to cache: {error}')
                        return cached_entry.data
                    
                    # Otherwise, propagate the error
                    raise
                finally:
                    # Clean up the pending request
                    if key in self.pending_requests:
                        del self.pending_requests[key]
            
            # Register the promise to avoid duplicate requests
            fetch_promise = execute_fetch()
            self.pending_requests[key] = fetch_promise
            
            return await fetch_promise
        
        except Exception as error:
            logging.error(f'Cache error for key {key}: {error}')
            raise
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the current cache state."""
        # Clean up expired timestamps first
        self._cleanup_expired_timestamps()
        
        # Calculate time until a request is possible again
        window_reset_time = 'N/A'
        if self.request_timestamps and len(self.request_timestamps) >= self.minute_request_limit:
            wait_time = self._get_wait_time_ms()
            window_reset_time = f'{wait_time // 1000} seconds'
        else:
            window_reset_time = 'Available now'
        
        return {
            'size': len(self.cache),
            'current_minute_requests': len(self.request_timestamps),
            'api_calls_remaining': max(0, self.minute_request_limit - len(self.request_timestamps)),
            'window_reset_time': window_reset_time
        }
    
    def invalidate(self, key: str) -> None:
        """Clear a specific cache entry."""
        if key in self.cache:
            del self.cache[key]
            logging.debug(f'Cache entry invalidated: {key}')
    
    def invalidate_by_prefix(self, prefix: str) -> int:
        """Clear all entries matching a prefix."""
        count = 0
        for key in list(self.cache.keys()):
            if key.startswith(prefix):
                del self.cache[key]
                count += 1
        
        logging.debug(f'Invalidated {count} cache entries with prefix: {prefix}')
        return count
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        logging.info('TaoStats cache cleared')


# Create a synchronous version for easier integration with existing code
class SyncTaoStatsCacheService:
    """Synchronous wrapper around TaoStatsCacheService for non-async code."""
    
    def __init__(self, options: Dict[str, Any] = None):
        if options is None:
            options = {}
        
        # Configure cache path
        self.cache_path = options.get('cache_path') or os.path.join(
            os.getcwd(), '.cache', 'tao-cache.json')
        
        # Configure rate limits
        self.minute_request_limit = options.get('minute_request_limit', 5)
        
        # Enable/disable persistent cache
        self.persistent_cache_enabled = options.get('persistent_cache_enabled', True)
        
        # Initialize cache
        self.cache: Dict[str, CacheEntry] = {}
        self.pending_requests: Dict[str, bool] = {}
        self.request_timestamps: List[int] = []
        self.window_size_ms = 60 * 1000  # 1 minute window
        
        # Initialize cache from disk
        self._initialize_cache()
        
        # Handle shutdown properly
        import atexit
        atexit.register(self._persist_cache)
    
    def _initialize_cache(self) -> None:
        """Initialize cache from persistent storage."""
        if not self.persistent_cache_enabled:
            logging.info('TaoStats persistent cache is disabled')
            return
        
        try:
            # Check if cache directory exists
            cache_dir = os.path.dirname(self.cache_path)
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            
            # Try to load existing cache
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Restore request timestamps, but filter those too old
                if 'requestTimestamps' in cache_data and isinstance(cache_data['requestTimestamps'], list):
                    now = int(time.time() * 1000)
                    self.request_timestamps = [
                        ts for ts in cache_data['requestTimestamps']
                        if now - ts < self.window_size_ms
                    ]
                
                # Restore cache entries
                if 'entries' in cache_data and isinstance(cache_data['entries'], list):
                    for entry in cache_data['entries']:
                        if isinstance(entry, list) and len(entry) == 2:
                            key, value = entry
                            # Only restore non-expired entries
                            cache_entry = CacheEntry.from_dict(value)
                            if not cache_entry.is_expired():
                                self.cache[key] = cache_entry
                
                logging.info(f'Loaded TaoStats cache with {len(self.cache)} entries')
            
            except (FileNotFoundError, json.JSONDecodeError):
                logging.info('No valid TaoStats cache found, starting with empty cache')
        
        except Exception as e:
            logging.error(f'Error initializing TaoStats cache: {e}')
    
    def _persist_cache(self) -> None:
        """Save cache to persistent storage."""
        if not self.persistent_cache_enabled:
            return
        
        try:
            # Create cache structure
            cache_data = {
                "timestamp": int(time.time() * 1000),
                "requestTimestamps": self.request_timestamps,
                "entries": [[key, entry.to_dict()] for key, entry in self.cache.items()]
            }
            
            # Ensure directory exists
            cache_dir = os.path.dirname(self.cache_path)
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            
            # Write cache to file
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            
            logging.debug(f'TaoStats cache persisted with {len(self.cache)} entries')
        
        except Exception as e:
            logging.error(f'Failed to persist TaoStats cache: {e}')
    
    def _cleanup_expired_timestamps(self) -> None:
        """Clean up expired request timestamps (older than window)."""
        now = int(time.time() * 1000)
        self.request_timestamps = [
            ts for ts in self.request_timestamps
            if now - ts < self.window_size_ms
        ]
    
    def _has_reached_rate_limit(self) -> bool:
        """Check if we've reached the rate limit."""
        self._cleanup_expired_timestamps()
        return len(self.request_timestamps) >= self.minute_request_limit
    
    def _record_request(self) -> None:
        """Record a request timestamp."""
        self.request_timestamps.append(int(time.time() * 1000))
    
    def _get_wait_time_ms(self) -> int:
        """Calculate wait time before next request can be made."""
        if not self.request_timestamps:
            return 0
        
        now = int(time.time() * 1000)
        # Sort timestamps to get the oldest
        sorted_timestamps = sorted(self.request_timestamps)
        oldest_request = sorted_timestamps[0]
        
        # Calculate when we can make a new request
        time_until_window_frees = (oldest_request + self.window_size_ms) - now
        return max(0, time_until_window_frees)
    
    def with_cache(self, 
                   key: str,
                   fetch_fn: Callable[[], Any],
                   options: Dict[str, Any] = None) -> Any:
        """
        Execute a function with result caching
        
        Args:
            key: Unique cache key
            fetch_fn: Function that makes the actual API call
            options: Cache options
                ttl: Time-to-live in milliseconds
                force_refresh: Force refresh even if in cache
                fallback_to_cache: Use cache even if expired in case of error
                critical: Indicates if this request is critical (priority)
                fail_silently: Don't raise error if rate limit is reached
        
        Returns:
            Result from function or cache
        """
        if options is None:
            options = {}
        
        # Default options
        ttl = options.get('ttl', 3600000)  # 1 hour default
        force_refresh = options.get('force_refresh', False)
        fallback_to_cache = options.get('fallback_to_cache', True)  # Default True
        critical = options.get('critical', False)
        fail_silently = options.get('fail_silently', False)
        
        try:
            # Check if we already have a pending request for this key
            if key in self.pending_requests and not force_refresh:
                logging.debug(f'Using pending request for key: {key}')
                return None  # Can't wait for pending requests in sync mode
            
            # Check if we have a valid cache entry
            cached_entry = self.cache.get(key)
            if cached_entry and not force_refresh and not cached_entry.is_expired():
                logging.debug(f'Cache hit for key: {key}')
                return cached_entry.data
            
            # Check if we've reached the rate limit
            if self._has_reached_rate_limit() and not critical:
                # If we have a cache entry, even expired, use it
                if cached_entry and fallback_to_cache:
                    wait_time = self._get_wait_time_ms()
                    logging.warning(
                        f'API rate limit reached ({len(self.request_timestamps)}/{self.minute_request_limit} per minute), '
                        f'wait time: {wait_time // 1000}s, using expired cache for: {key}'
                    )
                    return cached_entry.data
                
                # Otherwise, raise an error or return None based on fail_silently
                wait_time = self._get_wait_time_ms()
                message = (
                    f'TaoStats API rate limit reached ({len(self.request_timestamps)}/{self.minute_request_limit} per minute), '
                    f'need to wait {wait_time // 1000} seconds'
                )
                
                if fail_silently:
                    logging.warning(f'{message}, returning None for: {key}')
                    return None
                else:
                    raise Exception(message)
            
            # Mark this key as pending
            self.pending_requests[key] = True
            
            try:
                # Record the request for rate tracking
                self._record_request()
                
                # Make the actual API request
                logging.info(
                    f'TaoStats API request ({len(self.request_timestamps)}/{self.minute_request_limit} per minute) for: {key}'
                )
                result = fetch_fn()
                
                # Update the cache
                self.cache[key] = CacheEntry(result, ttl)
                
                # Persist the cache after each new result
                self._persist_cache()
                
                return result
            except Exception as error:
                # If a cache entry exists, use it even if expired
                if fallback_to_cache and cached_entry:
                    logging.warning(f'Error fetching {key}, falling back to cache: {error}')
                    return cached_entry.data
                
                # Otherwise, propagate the error
                raise
            finally:
                # Clean up the pending request
                if key in self.pending_requests:
                    del self.pending_requests[key]
        
        except Exception as error:
            logging.error(f'Cache error for key {key}: {error}')
            raise
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the current cache state."""
        # Clean up expired timestamps first
        self._cleanup_expired_timestamps()
        
        # Calculate time until a request is possible again
        window_reset_time = 'N/A'
        if self.request_timestamps and len(self.request_timestamps) >= self.minute_request_limit:
            wait_time = self._get_wait_time_ms()
            window_reset_time = f'{wait_time // 1000} seconds'
        else:
            window_reset_time = 'Available now'
        
        return {
            'size': len(self.cache),
            'current_minute_requests': len(self.request_timestamps),
            'api_calls_remaining': max(0, self.minute_request_limit - len(self.request_timestamps)),
            'window_reset_time': window_reset_time
        }
    
    def invalidate(self, key: str) -> None:
        """Clear a specific cache entry."""
        if key in self.cache:
            del self.cache[key]
            logging.debug(f'Cache entry invalidated: {key}')
    
    def invalidate_by_prefix(self, prefix: str) -> int:
        """Clear all entries matching a prefix."""
        count = 0
        for key in list(self.cache.keys()):
            if key.startswith(prefix):
                del self.cache[key]
                count += 1
        
        logging.debug(f'Invalidated {count} cache entries with prefix: {prefix}')
        return count
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        logging.info('TaoStats cache cleared')

# Export a singleton instance
tao_stats_cache = SyncTaoStatsCacheService({
    'minute_request_limit': int(os.getenv('TAO_STAT_MINUTE_LIMIT', '5'))
}) 