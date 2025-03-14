# import time
# import threading
# import json
# from typing import Any, Dict, Optional, List, Union
# import redis
# from datetime import datetime, timedelta

# # Global lock for thread safety
# CACHE_LOCK = threading.Lock()

# # In-memory cache dictionary
# MEMORY_CACHE = {}

# class Cache:
#     """
#     Cache implementation supporting both in-memory and Redis backends
#     """
#     def __init__(self, redis_client=None, prefix="cache:"):
#         """
#         Initialize cache with optional Redis connection
        
#         Args:
#             redis_client: Optional Redis client
#             prefix: Key prefix for Redis keys
#         """
#         self.redis_client = redis_client
#         self.prefix = prefix
#         self.cache_dict = MEMORY_CACHE
    
#     def get(self, key: str, default=None) -> Any:
#         """
#         Get a value from the cache
        
#         Args:
#             key: Cache key
#             default: Default value if key not found
            
#         Returns:
#             Cached value or default
#         """
#         # Check memory cache first
#         with CACHE_LOCK:
#             if key in self.cache_dict:
#                 cache_entry = self.cache_dict[key]
                
#                 # Check if entry has expired
#                 if cache_entry["expiry"] and time.time() > cache_entry["expiry"]:
#                     del self.cache_dict[key]
#                     return default
                
#                 return cache_entry["value"]
        
#         # If not in memory and Redis is available, check Redis
#         if self.redis_client:
#             redis_key = f"{self.prefix}{key}"
#             cached_data = self.redis_client.get(redis_key)
            
#             if cached_data:
#                 try:
#                     return json.loads(cached_data)
#                 except (json.JSONDecodeError, TypeError):
#                     return cached_data
        
#         return default
    
#     def set(self, key: str, value: Any, expiry: Optional[int] = None, memory_only: bool = False) -> None:
#         """
#         Set a value in the cache
        
#         Args:
#             key: Cache key
#             value: Value to store
#             expiry: Expiry time in seconds
#             memory_only: Whether to store in memory only
#         """
#         # Calculate expiry timestamp if provided
#         expiry_ts = time.time() + expiry if expiry is not None else None
        
#         # Set in memory cache
#         with CACHE_LOCK:
#             self.cache_dict[key] = {
#                 "value": value,
#                 "expiry": expiry_ts
#             }
        
#         # Also set in Redis if available and not memory_only
#         if not memory_only and self.redis_client:
#             redis_key = f"{self.prefix}{key}"
#             try:
#                 serialized_value = json.dumps(value)
#                 if expiry:
#                     self.redis_client.setex(redis_key, expiry, serialized_value)
#                 else:
#                     self.redis_client.set(redis_key, serialized_value)
#             except (TypeError, json.JSONDecodeError):
#                 # If serialization fails, store as string if possible
#                 try:
#                     if expiry:
#                         self.redis_client.setex(redis_key, expiry, str(value))
#                     else:
#                         self.redis_client.set(redis_key, str(value))
#                 except Exception:
#                     # If all else fails, log or handle appropriately
#                     pass
    
#     def delete(self, key: str) -> None:
#         """
#         Delete a key from the cache
        
#         Args:
#             key: Cache key to delete
#         """
#         # Delete from memory
#         with CACHE_LOCK:
#             if key in self.cache_dict:
#                 del self.cache_dict[key]
        
#         # Delete from Redis if available
#         if self.redis_client:
#             redis_key = f"{self.prefix}{key}"
#             self.redis_client.delete(redis_key)
    
#     def clear(self) -> None:
#         """
#         Clear all cached items
#         """
#         # Clear memory cache
#         with CACHE_LOCK:
#             self.cache_dict.clear()
        
#         # Clear Redis cache if available
#         if self.redis_client and self.prefix:
#             keys = self.redis_client.keys(f"{self.prefix}*")
#             if keys:
#                 self.redis_client.delete(*keys)


# # Singleton instance
# _CACHE_INSTANCE = None

# def get_cache_instance() -> Cache:
#     """
#     Get or create the singleton cache instance
    
#     Returns:
#         Cache instance
#     """
#     global _CACHE_INSTANCE
    
#     if _CACHE_INSTANCE is None:
#         # Initialize Redis connection if needed
#         redis_client = None
#         try:
#             from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
#             redis_client = redis.Redis(
#                 host=REDIS_HOST,
#                 port=REDIS_PORT,
#                 db=REDIS_DB,
#                 password=REDIS_PASSWORD,
#                 decode_responses=True
#             )
#         except (ImportError, redis.RedisError):
#             # Failed to connect to Redis, use memory-only cache
#             pass
            
#         _CACHE_INSTANCE = Cache(redis_client=redis_client)
    
#     return _CACHE_INSTANCE


# def get_cache(key: str, default=None) -> Any:
#     """
#     Get a value from the cache
    
#     Args:
#         key: Cache key
#         default: Default value if key not found
        
#     Returns:
#         Cached value or default
#     """
#     cache = get_cache_instance()
#     return cache.get(key, default)


# def set_cache(key: str, value: Any, expiry: Optional[int] = None, memory_only: bool = False) -> None:
#     """
#     Set a value in the cache
    
#     Args:
#         key: Cache key
#         value: Value to store
#         expiry: Expiry time in seconds
#         memory_only: Whether to store in memory only
#     """
#     cache = get_cache_instance()
#     cache.set(key, value, expiry, memory_only)


# def delete_cache(key: str) -> None:
#     """
#     Delete a key from the cache
    
#     Args:
#         key: Cache key to delete
#     """
#     cache = get_cache_instance()
#     cache.delete(key)


# def clear_cache() -> None:
#     """
#     Clear all cached items
#     """
#     cache = get_cache_instance()
#     cache.clear()


# def cache_decorator(expiry: Optional[int] = None, key_prefix: str = "cache:"):
#     """
#     Decorator to cache function results
    
#     Args:
#         expiry: Cache expiry time in seconds
#         key_prefix: Cache key prefix
    
#     Returns:
#         Decorated function
#     """
#     def decorator(func):
#         def wrapper(*args, **kwargs):
#             # Generate cache key from function name and arguments
#             key_parts = [key_prefix, func.__name__]
            
#             # Add positional args to key
#             for arg in args:
#                 key_parts.append(str(arg))
            
#             # Add keyword args to key (sorted for consistency)
#             for k, v in sorted(kwargs.items()):
#                 key_parts.append(f"{k}:{v}")
            
#             cache_key = ":".join(key_parts)
            
#             # Try to get from cache first
#             cached_result = get_cache(cache_key)
#             if cached_result is not None:
#                 return cached_result
            
#             # Not in cache, call the function
#             result = func(*args, **kwargs)
            
#             # Cache the result
#             set_cache(cache_key, result, expiry)
            
#             return result
        
#         return wrapper
    
#     return decorator










"""
Complete cache implementation that provides all the required functionality
for the application, avoiding class-based method errors.
"""

import time
import threading
import logging
from typing import Any, Dict, Optional, List, Union, Callable

# Setup logger
logger = logging.getLogger("cache")

# Global variables
MEMORY_CACHE = {}  # The actual cache storage
CACHE_LOCK = threading.Lock()  # Lock for thread safety

# Cache manager implementation
class CacheManager:
    """
    Cache manager that provides methods for managing the cache.
    """
    def __init__(self):
        pass
        
    def get(self, key, default=None):
        """Wrapper for get_cache"""
        return get_cache(key, default)
        
    def set(self, key, value, expiry=None, memory_only=False):
        """Wrapper for set_cache"""
        set_cache(key, value, expiry, memory_only)
        
    def delete(self, key):
        """Wrapper for delete_cache"""
        delete_cache(key)
        
    def clear(self):
        """Wrapper for clear_cache"""
        clear_cache()
        
    def invalidate_prefix(self, prefix):
        """Wrapper for invalidate_cache_prefix"""
        invalidate_cache_prefix(prefix)

# Create the cache_manager instance
cache_manager = CacheManager()

def get_cache(key, default=None):
    """
    Get a value from the cache
    
    Args:
        key: Cache key
        default: Default value if key not found
    
    Returns:
        Cached value or default
    """
    with CACHE_LOCK:
        if key in MEMORY_CACHE:
            entry = MEMORY_CACHE[key]
            expiry = entry.get("expiry")
            
            # Check if expired
            if expiry and time.time() > expiry:
                del MEMORY_CACHE[key]
                return default
                
            return entry.get("value")
    
    return default

def set_cache(key, value, expiry=None, memory_only=False):
    """
    Set a value in the cache
    
    Args:
        key: Cache key
        value: Value to store
        expiry: Expiry time in seconds
        memory_only: Ignored (for compatibility)
    """
    with CACHE_LOCK:
        MEMORY_CACHE[key] = {
            "value": value,
            "expiry": time.time() + expiry if expiry else None
        }

def delete_cache(key):
    """
    Delete a key from the cache
    
    Args:
        key: Cache key to delete
    """
    with CACHE_LOCK:
        if key in MEMORY_CACHE:
            del MEMORY_CACHE[key]

def clear_cache():
    """
    Clear all cached items
    """
    with CACHE_LOCK:
        MEMORY_CACHE.clear()

def invalidate_cache_prefix(prefix):
    """
    Invalidate all cache keys that start with the given prefix
    
    Args:
        prefix: Prefix to match against cache keys
    """
    with CACHE_LOCK:
        keys_to_delete = [key for key in MEMORY_CACHE if key.startswith(prefix)]
        for key in keys_to_delete:
            del MEMORY_CACHE[key]

# For compatibility with existing code
def get_cache_instance():
    """
    This function exists only for compatibility.
    Returns the cache_manager for backward compatibility.
    """
    return cache_manager

# Cache decorator for function results
def cache_decorator(expiry=None, key_prefix="cache:"):
    """
    Decorator to cache function results
    
    Args:
        expiry: Cache expiry time in seconds
        key_prefix: Cache key prefix
    
    Returns:
        Decorated function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [key_prefix, func.__name__]
            
            # Add args to key
            for arg in args:
                key_parts.append(str(arg))
            
            # Add kwargs to key
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}:{v}")
            
            cache_key = ":".join(key_parts)
            
            # Check cache
            result = get_cache(cache_key)
            if result is not None:
                return result
            
            # Call function
            result = func(*args, **kwargs)
            
            # Cache result
            set_cache(cache_key, result, expiry)
            
            return result
        
        return wrapper
    
    return decorator