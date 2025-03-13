import os
import json
import time
import pickle
from typing import Any, Dict, Optional, List, Union, Set, Tuple
import threading
from datetime import datetime
import hashlib
from collections import OrderedDict

from backend.utils.logging import setup_logger
from backend.config import settings

logger = setup_logger("cache")

# In-memory cache using LRU (Least Recently Used) strategy
# For production, this would use Redis or a similar distributed cache
class LRUCache(OrderedDict):
    """Thread-safe LRU cache implementation"""
    
    def __init__(self, max_size=1000):
        super().__init__()
        self.max_size = max_size
        self._lock = threading.RLock()
    
    def get(self, key):
        """Get an item from the cache, moving it to the end of the LRU order"""
        with self._lock:
            if key not in self:
                return None
            self.move_to_end(key)
            return super().__getitem__(key)
    
    def set(self, key, value):
        """Add an item to the cache, evicting least recently used items if needed"""
        with self._lock:
            if key in self:
                self.move_to_end(key)
            super().__setitem__(key, value)
            if len(self) > self.max_size:
                # Remove oldest item (first item in ordered dict)
                oldest = next(iter(self))
                del self[oldest]
    
    def delete(self, key):
        """Remove an item from the cache"""
        with self._lock:
            if key in self:
                del self[key]
                return True
            return False

# Memory cache instances
_MEMORY_CACHE: Dict[str, Any] = {}
_CACHE_EXPIRY: Dict[str, float] = {}
_CACHE_LOCK = threading.RLock()

class CacheManager:
    """
    Cache manager for storing and retrieving cached data
    
    Features:
    - In-memory caching with TTL
    - File-based cache for persistence
    - Cache invalidation by key or prefix
    - Automatic cache cleanup
    - LRU (Least Recently Used) eviction policy
    """
    
    def __init__(self):
        self.memory_cache_enabled = True
        self.file_cache_enabled = True
        self.file_cache_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
        self.max_memory_items = settings.CACHE_MAX_ITEMS
        self.cleanup_interval = 300  # 5 minutes
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.file_cache_dir, exist_ok=True)
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self) -> None:
        """Start a thread to periodically clean up expired cache items"""
        def cleanup_thread():
            while True:
                try:
                    time.sleep(self.cleanup_interval)
                    self.cleanup()
                except Exception as e:
                    logger.error(f"Error in cache cleanup thread: {str(e)}")
        
        thread = threading.Thread(target=cleanup_thread, daemon=True)
        thread.start()
    
    def get(self, key: str) -> Any:
        """
        Get a value from the cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        # First try memory cache
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                # Check if expired
                if key in _CACHE_EXPIRY and time.time() > _CACHE_EXPIRY[key]:
                    self._remove_from_memory(key)
                else:
                    value = _MEMORY_CACHE.get(key)
                    if value is not None:
                        logger.debug(f"Cache hit (memory): {key}")
                        return value
        
        # Then try file cache
        if self.file_cache_enabled:
            file_path = self._get_file_path(key)
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        cache_data = pickle.load(f)
                        
                        # Check if expired
                        if "expiry" in cache_data and time.time() > cache_data["expiry"]:
                            os.unlink(file_path)
                        else:
                            value = cache_data["value"]
                            
                            # Add to memory cache for faster access next time
                            if self.memory_cache_enabled:
                                with _CACHE_LOCK:
                                    # _MEMORY_CACHE.set(key, value)
                                    _MEMORY_CACHE[key] = value
                                    if "expiry" in cache_data:
                                        _CACHE_EXPIRY[key] = cache_data["expiry"]
                            
                            logger.debug(f"Cache hit (file): {key}")
                            return value
                except Exception as e:
                    logger.error(f"Error reading from file cache: {str(e)}")
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(
        self,
        key: str,
        value: Any,
        expiry: Optional[int] = None,
        memory_only: bool = False
    ) -> None:
        """
        Set a value in the cache
        
        Args:
            key: Cache key
            value: Value to cache
            expiry: Optional expiry time in seconds
            memory_only: Whether to store in memory only
        """
        # Calculate expiry timestamp
        expiry_time = time.time() + expiry if expiry else None
        
        # Set in memory cache
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                # _MEMORY_CACHE.set(key, value)
                _MEMORY_CACHE[key] = value
                
                if expiry_time:
                    _CACHE_EXPIRY[key] = expiry_time
        
        # Set in file cache if enabled and not memory-only
        if self.file_cache_enabled and not memory_only:
            file_path = self._get_file_path(key)
            
            try:
                cache_data = {
                    "value": value,
                    "timestamp": time.time()
                }
                
                if expiry_time:
                    cache_data["expiry"] = expiry_time
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                with open(file_path, 'wb') as f:
                    pickle.dump(cache_data, f)
                    
            except Exception as e:
                logger.error(f"Error writing to file cache: {str(e)}")
        
        logger.debug(f"Cache set: {key}")
    
    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache
        
        Args:
            key: Cache key
            
        Returns:
            True if the key was found and deleted, False otherwise
        """
        found = False
        
        # Remove from memory cache
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                if _MEMORY_CACHE.delete(key):
                    if key in _CACHE_EXPIRY:
                        del _CACHE_EXPIRY[key]
                    found = True
        
        # Remove from file cache
        if self.file_cache_enabled:
            file_path = self._get_file_path(key)
            
            if os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                    found = True
                except Exception as e:
                    logger.error(f"Error deleting from file cache: {str(e)}")
        
        logger.debug(f"Cache delete: {key} (found: {found})")
        return found
    
    def invalidate_prefix(self, prefix: str) -> int:
        """
        Invalidate all cache keys with a given prefix
        
        Args:
            prefix: Key prefix to invalidate
            
        Returns:
            Number of invalidated keys
        """
        count = 0
        
        # Invalidate in memory cache
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                # Get a copy of keys to avoid modification during iteration
                all_keys = list(_MEMORY_CACHE.keys())
                
                for key in all_keys:
                    if key.startswith(prefix):
                        _MEMORY_CACHE.delete(key)
                        if key in _CACHE_EXPIRY:
                            del _CACHE_EXPIRY[key]
                        count += 1
        
        # Invalidate in file cache
        if self.file_cache_enabled:
            try:
                prefix_hash = hashlib.md5(prefix.encode()).hexdigest()[:8]
                matching_files = []
                
                # Find files matching the prefix
                for root, _, files in os.walk(self.file_cache_dir):
                    for file in files:
                        if file.startswith(prefix_hash):
                            file_path = os.path.join(root, file)
                            matching_files.append(file_path)
                
                # Delete matching files
                for file_path in matching_files:
                    try:
                        os.unlink(file_path)
                        count += 1
                    except Exception as e:
                        logger.error(f"Error deleting file: {str(e)}")
                        
            except Exception as e:
                logger.error(f"Error invalidating prefix: {str(e)}")
        
        logger.info(f"Cache invalidated prefix: {prefix} (count: {count})")
        return count
    
    def cleanup(self) -> int:
        """
        Clean up expired cache items
        
        Returns:
            Number of cleaned up items
        """
        count = 0
        
        # Clean up memory cache
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                current_time = time.time()
                
                # Get a copy of the keys and expiry times to avoid modification during iteration
                expiry_items = list(_CACHE_EXPIRY.items())
                
                for key, expiry in expiry_items:
                    if current_time > expiry:
                        self._remove_from_memory(key)
                        count += 1
        
        # Clean up file cache
        if self.file_cache_enabled:
            try:
                for root, _, files in os.walk(self.file_cache_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        
                        try:
                            with open(file_path, 'rb') as f:
                                cache_data = pickle.load(f)
                                
                                # Check if expired
                                if (
                                    "expiry" in cache_data 
                                    and time.time() > cache_data["expiry"]
                                ):
                                    os.unlink(file_path)
                                    count += 1
                        except Exception as e:
                            # If we can't read the file, consider it corrupted and delete it
                            try:
                                logger.warning(f"Removing corrupted cache file: {file_path}")
                                os.unlink(file_path)
                                count += 1
                            except:
                                pass
                            
            except Exception as e:
                logger.error(f"Error cleaning up file cache: {str(e)}")
        
        logger.info(f"Cache cleanup completed (count: {count})")
        return count
    
    def clear(self) -> int:
        """
        Clear all cache items
        
        Returns:
            Number of cleared items
        """
        count = 0
        
        # Clear memory cache
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                count = len(_MEMORY_CACHE)
                _MEMORY_CACHE = LRUCache(self.max_memory_items)
                _CACHE_EXPIRY.clear()
        
        # Clear file cache
        if self.file_cache_enabled:
            try:
                for root, _, files in os.walk(self.file_cache_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        
                        try:
                            os.unlink(file_path)
                            count += 1
                        except Exception as e:
                            logger.error(f"Error deleting file: {str(e)}")
                            
            except Exception as e:
                logger.error(f"Error clearing file cache: {str(e)}")
        
        logger.info(f"Cache cleared (count: {count})")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "memory_cache": {
                "enabled": self.memory_cache_enabled,
                "items": 0,
                "expired_items": 0,
                "max_items": self.max_memory_items
            },
            "file_cache": {
                "enabled": self.file_cache_enabled,
                "items": 0,
                "size_bytes": 0
            }
        }
        
        # Memory cache stats
        if self.memory_cache_enabled:
            with _CACHE_LOCK:
                stats["memory_cache"]["items"] = len(_MEMORY_CACHE)
                
                current_time = time.time()
                expired_items = sum(
                    1 for expiry in _CACHE_EXPIRY.values()
                    if current_time > expiry
                )
                
                stats["memory_cache"]["expired_items"] = expired_items
        
        # File cache stats
        if self.file_cache_enabled:
            try:
                file_count = 0
                total_size = 0
                
                for root, _, files in os.walk(self.file_cache_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_count += 1
                        total_size += os.path.getsize(file_path)
                
                stats["file_cache"]["items"] = file_count
                stats["file_cache"]["size_bytes"] = total_size
                
            except Exception as e:
                logger.error(f"Error getting file cache stats: {str(e)}")
        
        return stats
    
    def _get_file_path(self, key: str) -> str:
        """
        Get the file path for a cache key
        
        Args:
            key: Cache key
            
        Returns:
            File path
        """
        # Use a hash to shorten the key and avoid invalid filenames
        key_hash = hashlib.md5(key.encode()).hexdigest()
        
        # Use the first 4 characters as a directory and the rest as the filename
        dir_name = key_hash[:4]
        file_name = key_hash[4:]
        
        return os.path.join(self.file_cache_dir, dir_name, file_name)
    
    def _remove_from_memory(self, key: str) -> None:
        """
        Remove a key from memory cache
        
        Args:
            key: Cache key
        """
        with _CACHE_LOCK:
            _MEMORY_CACHE.delete(key)
            if key in _CACHE_EXPIRY:
                del _CACHE_EXPIRY[key]

# Create singleton instance
cache_manager = CacheManager()

# Convenience functions
def get_cache(key: str) -> Any:
    """
    Get a value from the cache
    
    Args:
        key: Cache key
        
    Returns:
        Cached value or None if not found
    """
    return cache_manager.get(key)

def set_cache(
    key: str,
    value: Any,
    expiry: Optional[int] = None,
    memory_only: bool = False
) -> None:
    """
    Set a value in the cache
    
    Args:
        key: Cache key
        value: Value to cache
        expiry: Optional expiry time in seconds
        memory_only: Whether to store in memory only
    """
    cache_manager.set(key, value, expiry, memory_only)

def delete_cache(key: str) -> bool:
    """
    Delete a value from the cache
    
    Args:
        key: Cache key
        
    Returns:
        True if the key was found and deleted, False otherwise
    """
    return cache_manager.delete(key)

def invalidate_cache_prefix(prefix: str) -> int:
    """
    Invalidate all cache keys with a given prefix
    
    Args:
        prefix: Key prefix to invalidate
        
    Returns:
        Number of invalidated keys
    """
    return cache_manager.invalidate_prefix(prefix)