import os
import json
import time
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import glob

from backend.db.mongodb import get_database
from backend.utils.cache import get_cache, set_cache
from backend.utils.logging import setup_logger
from backend.config import settings

logger = setup_logger("analytics")

class AnalyticsService:
    """
    Service for collecting and analyzing usage data
    
    Features:
    - Event tracking
    - Usage statistics
    - Performance metrics
    - User behavior analysis
    - System health monitoring
    """
    
    def __init__(self):
        self.db = get_database()
        self.collection = self.db["analytics"]
        self.events_collection = self.db["events"]
        self.performance_collection = self.db["performance"]
        
        # Ensure indices
        self._ensure_indices()
        
        # Create data directory
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "analytics")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize event buffer for batch processing
        self.event_buffer = []
        self.buffer_lock = threading.Lock()
        self.buffer_size = settings.ANALYTICS_BUFFER_SIZE
        self.buffer_flush_interval = settings.ANALYTICS_FLUSH_INTERVAL
        
        # Start buffer flush thread
        self._start_buffer_flush_thread()
    
    def _ensure_indices(self) -> None:
        """Ensure database indices exist"""
        try:
            # Analytics collection indices
            self.collection.create_index("timestamp")
            self.collection.create_index("type")
            self.collection.create_index("user_id")
            
            # Events collection indices
            self.events_collection.create_index("timestamp")
            self.events_collection.create_index("event_type")
            self.events_collection.create_index("user_id")
            
            # Performance collection indices
            self.performance_collection.create_index("timestamp")
            self.performance_collection.create_index("operation")
            
        except Exception as e:
            logger.error(f"Error ensuring indices: {str(e)}")
    
    def _start_buffer_flush_thread(self) -> None:
        """Start a thread to periodically flush the event buffer"""
        def flush_thread():
            while True:
                try:
                    time.sleep(self.buffer_flush_interval)
                    self.flush_event_buffer()
                except Exception as e:
                    logger.error(f"Error in buffer flush thread: {str(e)}")
        
        thread = threading.Thread(target=flush_thread, daemon=True)
        thread.start()
    
    def track_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """
        Track an event
        
        Args:
            event_type: Type of event
            data: Event data
            user_id: Optional user ID
        """
        event = {
            "event_type": event_type,
            "user_id": user_id,
            "data": data,
            "timestamp": datetime.utcnow()
        }
        
        # Add to buffer for batch processing
        with self.buffer_lock:
            self.event_buffer.append(event)
            
            # Flush buffer if it reaches the size threshold
            if len(self.event_buffer) >= self.buffer_size:
                self.flush_event_buffer()
    
    def flush_event_buffer(self) -> None:
        """Flush the event buffer to the database"""
        with self.buffer_lock:
            if not self.event_buffer:
                return
            
            try:
                # Insert events in batch
                self.events_collection.insert_many(self.event_buffer)
                logger.info(f"Flushed {len(self.event_buffer)} events to database")
                
                # Clear buffer
                self.event_buffer = []
                
            except Exception as e:
                logger.error(f"Error flushing event buffer: {str(e)}")
    
    def track_query(
        self,
        query: str,
        response: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track a user query
        
        Args:
            query: User query
            response: Generated response
            user_id: Optional user ID
            metadata: Optional metadata
        """
        metadata = metadata or {}
        
        event_data = {
            "query": query,
            "response_length": len(response),
            "metadata": metadata
        }
        
        self.track_event("query", event_data, user_id)
    
    def track_document_view(
        self,
        document_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track a document view
        
        Args:
            document_id: Document ID
            user_id: Optional user ID
            metadata: Optional metadata
        """
        metadata = metadata or {}
        
        event_data = {
            "document_id": document_id,
            "metadata": metadata
        }
        
        self.track_event("document_view", event_data, user_id)
    
    def track_error(
        self,
        error: str,
        context: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """
        Track an error
        
        Args:
            error: Error message
            context: Error context
            user_id: Optional user ID
        """
        event_data = {
            "error": error,
            "context": context
        }
        
        self.track_event("error", event_data, user_id)
    
    def track_performance(
        self,
        operation: str,
        duration: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Track a performance metric
        
        Args:
            operation: Operation name
            duration: Duration in seconds
            metadata: Optional metadata
        """
        metadata = metadata or {}
        
        # Log directly to performance collection
        try:
            self.performance_collection.insert_one({
                "operation": operation,
                "duration": duration,
                "metadata": metadata,
                "timestamp": datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Error tracking performance: {str(e)}")
    
    async def get_daily_stats(
        self,
        days: int = 7,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get daily usage statistics
        
        Args:
            days: Number of days to include
            use_cache: Whether to use cached results
            
        Returns:
            Dictionary with daily statistics
        """
        # Check cache if enabled
        if use_cache:
            cache_key = f"analytics:daily_stats:{days}"
            cached_stats = get_cache(cache_key)
            
            if cached_stats:
                logger.info(f"Using cached daily stats for {days} days")
                return cached_stats
        
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Aggregate query stats by day
            query_pipeline = [
                {"$match": {"event_type": "query", "timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1},
                    "users": {"$addToSet": "$user_id"}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            query_results = list(self.events_collection.aggregate(query_pipeline))
            
            # Aggregate error stats by day
            error_pipeline = [
                {"$match": {"event_type": "error", "timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            error_results = list(self.events_collection.aggregate(error_pipeline))
            
            # Aggregate document view stats by day
            doc_view_pipeline = [
                {"$match": {"event_type": "document_view", "timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            doc_view_results = list(self.events_collection.aggregate(doc_view_pipeline))
            
            # Format results
            days_list = [(end_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
            
            # Initialize results with zeros
            queries_by_day = {day: 0 for day in days_list}
            errors_by_day = {day: 0 for day in days_list}
            doc_views_by_day = {day: 0 for day in days_list}
            users_by_day = {day: 0 for day in days_list}
            
            # Fill in query data
            for day_data in query_results:
                day = day_data["_id"]
                if day in queries_by_day:
                    queries_by_day[day] = day_data["count"]
                    users_by_day[day] = len([u for u in day_data["users"] if u])
            
            # Fill in error data
            for day_data in error_results:
                day = day_data["_id"]
                if day in errors_by_day:
                    errors_by_day[day] = day_data["count"]
            
            # Fill in document view data
            for day_data in doc_view_results:
                day = day_data["_id"]
                if day in doc_views_by_day:
                    doc_views_by_day[day] = day_data["count"]
            
            # Prepare final results
            result = {
                "days": days_list,
                "queries": [queries_by_day[day] for day in days_list],
                "errors": [errors_by_day[day] for day in days_list],
                "document_views": [doc_views_by_day[day] for day in days_list],
                "users": [users_by_day[day] for day in days_list]
            }
            
            # Cache results
            if use_cache:
                cache_key = f"analytics:daily_stats:{days}"
                set_cache(cache_key, result, expiry=3600)  # 1 hour
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting daily stats: {str(e)}")
            return {
                "error": str(e),
                "days": [],
                "queries": [],
                "errors": [],
                "document_views": [],
                "users": []
            }
    
    async def get_performance_stats(
        self,
        days: int = 7,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Args:
            days: Number of days to include
            use_cache: Whether to use cached results
            
        Returns:
            Dictionary with performance statistics
        """
        # Check cache if enabled
        if use_cache:
            cache_key = f"analytics:performance_stats:{days}"
            cached_stats = get_cache(cache_key)
            
            if cached_stats:
                logger.info(f"Using cached performance stats for {days} days")
                return cached_stats
        
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Aggregate performance by operation
            pipeline = [
                {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": "$operation",
                    "count": {"$sum": 1},
                    "avg_duration": {"$avg": "$duration"},
                    "max_duration": {"$max": "$duration"},
                    "min_duration": {"$min": "$duration"}
                }},
                {"$sort": {"count": -1}}
            ]
            
            operation_results = list(self.performance_collection.aggregate(pipeline))
            
            # Aggregate daily average performance
            daily_pipeline = [
                {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                        "operation": "$operation"
                    },
                    "avg_duration": {"$avg": "$duration"}
                }},
                {"$sort": {"_id.date": 1}}
            ]
            
            daily_results = list(self.performance_collection.aggregate(daily_pipeline))
            
            # Format results
            operations = {op["_id"]: {
                "count": op["count"],
                "avg_duration": op["avg_duration"],
                "max_duration": op["max_duration"],
                "min_duration": op["min_duration"]
            } for op in operation_results}
            
            # Get top operations
            top_operations = sorted(operations.keys(), key=lambda x: operations[x]["count"], reverse=True)[:5]
            
            # Format daily results
            days_list = [(end_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
            
            # Initialize daily data
            daily_data = {op: {day: 0 for day in days_list} for op in top_operations}
            
            # Fill in daily data
            for day_data in daily_results:
                day = day_data["_id"]["date"]
                operation = day_data["_id"]["operation"]
                
                if operation in top_operations and day in days_list:
                    daily_data[operation][day] = day_data["avg_duration"]
            
            # Prepare final results
            result = {
                "days": days_list,
                "operations": operations,
                "top_operations": top_operations,
                "daily_data": {
                    op: [daily_data[op][day] for day in days_list]
                    for op in top_operations
                }
            }
            
            # Cache results
            if use_cache:
                cache_key = f"analytics:performance_stats:{days}"
                set_cache(cache_key, result, expiry=3600)  # 1 hour
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting performance stats: {str(e)}")
            return {
                "error": str(e),
                "days": [],
                "operations": {},
                "top_operations": [],
                "daily_data": {}
            }
    
    async def get_top_queries(
        self,
        days: int = 7,
        limit: int = 10,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get top user queries
        
        Args:
            days: Number of days to include
            limit: Maximum number of queries to return
            use_cache: Whether to use cached results
            
        Returns:
            List of top queries
        """
        # Check cache if enabled
        if use_cache:
            cache_key = f"analytics:top_queries:{days}:{limit}"
            cached_queries = get_cache(cache_key)
            
            if cached_queries:
                logger.info(f"Using cached top queries for {days} days")
                return cached_queries
        
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Aggregate queries
            pipeline = [
                {"$match": {"event_type": "query", "timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": "$data.query",
                    "count": {"$sum": 1},
                    "last_seen": {"$max": "$timestamp"}
                }},
                {"$sort": {"count": -1}},
                {"$limit": limit}
            ]
            
            results = list(self.events_collection.aggregate(pipeline))
            
            # Format results
            top_queries = [{
                "query": item["_id"],
                "count": item["count"],
                "last_seen": item["last_seen"].isoformat()
            } for item in results]
            
            # Cache results
            if use_cache:
                cache_key = f"analytics:top_queries:{days}:{limit}"
                set_cache(cache_key, top_queries, expiry=3600)  # 1 hour
            
            return top_queries
            
        except Exception as e:
            logger.error(f"Error getting top queries: {str(e)}")
            return []
    
    async def get_error_summary(
        self,
        days: int = 7,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get error summary
        
        Args:
            days: Number of days to include
            use_cache: Whether to use cached results
            
        Returns:
            Dictionary with error summary
        """
        # Check cache if enabled
        if use_cache:
            cache_key = f"analytics:error_summary:{days}"
            cached_summary = get_cache(cache_key)
            
            if cached_summary:
                logger.info(f"Using cached error summary for {days} days")
                return cached_summary
        
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Aggregate errors by type
            pipeline = [
                {"$match": {"event_type": "error", "timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$group": {
                    "_id": "$data.error",
                    "count": {"$sum": 1},
                    "last_seen": {"$max": "$timestamp"},
                    "contexts": {"$push": "$data.context"}
                }},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]
            
            results = list(self.events_collection.aggregate(pipeline))
            
            # Get total error count
            total_pipeline = [
                {"$match": {"event_type": "error", "timestamp": {"$gte": start_date, "$lte": end_date}}},
                {"$count": "total"}
            ]
            
            total_result = list(self.events_collection.aggregate(total_pipeline))
            total_count = total_result[0]["total"] if total_result else 0
            
            # Format results
            top_errors = [{
                "error": item["_id"],
                "count": item["count"],
                "last_seen": item["last_seen"].isoformat(),
                "contexts": item["contexts"][:5]  # Limit contexts to 5
            } for item in results]
            
            result = {
                "total_count": total_count,
                "top_errors": top_errors
            }
            
            # Cache results
            if use_cache:
                cache_key = f"analytics:error_summary:{days}"
                set_cache(cache_key, result, expiry=3600)  # 1 hour
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting error summary: {str(e)}")
            return {
                "error": str(e),
                "total_count": 0,
                "top_errors": []
            }
    
    async def get_system_health(self) -> Dict[str, Any]:
        """
        Get system health metrics
        
        Returns:
            Dictionary with system health metrics
        """
        try:
            import psutil
            
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Get disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Get log file sizes
            log_files = glob.glob(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "*.log"))
            log_sizes = {os.path.basename(f): os.path.getsize(f) / (1024 * 1024) for f in log_files}  # Size in MB
            
            # Check recent errors
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(hours=1)
            
            recent_errors = self.events_collection.count_documents({
                "event_type": "error",
                "timestamp": {"$gte": start_date, "$lte": end_date}
            })
            
            # Get response time metrics
            response_time_pipeline = [
                {"$match": {
                    "operation": "generate_response",
                    "timestamp": {"$gte": start_date, "$lte": end_date}
                }},
                {"$group": {
                    "_id": None,
                    "avg_duration": {"$avg": "$duration"},
                    "max_duration": {"$max": "$duration"},
                    "count": {"$sum": 1}
                }}
            ]
            
            response_time_results = list(self.performance_collection.aggregate(response_time_pipeline))
            
            response_times = response_time_results[0] if response_time_results else {
                "avg_duration": 0,
                "max_duration": 0,
                "count": 0
            }
            
            # Determine overall health status
            health_status = "good"
            
            if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
                health_status = "critical"
            elif cpu_percent > 75 or memory_percent > 75 or disk_percent > 75 or recent_errors > 10:
                health_status = "warning"
            
            return {
                "status": health_status,
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
                "log_sizes_mb": log_sizes,
                "recent_errors": recent_errors,
                "response_times": {
                    "avg_seconds": response_times.get("avg_duration", 0),
                    "max_seconds": response_times.get("max_duration", 0),
                    "count": response_times.get("count", 0)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system health: {str(e)}")
            return {
                "status": "unknown",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def export_analytics(
        self,
        start_date: datetime,
        end_date: datetime,
        event_types: Optional[List[str]] = None
    ) -> str:
        """
        Export analytics data to a JSON file
        
        Args:
            start_date: Start date
            end_date: End date
            event_types: Optional list of event types to include
            
        Returns:
            Path to the export file
        """
        try:
            # Build query
            query = {"timestamp": {"$gte": start_date, "$lte": end_date}}
            
            if event_types:
                query["event_type"] = {"$in": event_types}
            
            # Get events
            events = list(self.events_collection.find(query, {"_id": 0}))
            
            # Convert datetime objects to strings
            for event in events:
                event["timestamp"] = event["timestamp"].isoformat()
            
            # Create export file
            file_name = f"analytics_export_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
            file_path = os.path.join(self.data_dir, file_name)
            
            # Write to file
            with open(file_path, 'w') as f:
                json.dump(events, f, indent=2)
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error exporting analytics: {str(e)}")
            raise

# Create singleton instance
analytics_service = AnalyticsService()