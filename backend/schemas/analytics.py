from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field

class EventBase(BaseModel):
    """Base event model"""
    event_type: str = Field(..., description="Type of event")
    user_id: Optional[str] = Field(default=None, description="User ID")
    timestamp: datetime = Field(..., description="Event timestamp")

class QueryEvent(EventBase):
    """Query event model"""
    query: str = Field(..., description="User query")
    response_length: int = Field(..., description="Response length in characters")
    model: Optional[str] = Field(default=None, description="Model used")
    processing_time: Optional[float] = Field(default=None, description="Processing time in seconds")
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional metadata")

class FeedbackEvent(EventBase):
    """Feedback event model"""
    query: str = Field(..., description="Original query")
    feedback: str = Field(..., description="Feedback text")
    rating: Optional[int] = Field(default=None, description="Rating (1-5)")
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID")

class ErrorEvent(EventBase):
    """Error event model"""
    error: str = Field(..., description="Error message")
    context: Dict[str, Any] = Field(..., description="Error context")
    stack_trace: Optional[str] = Field(default=None, description="Stack trace")

class PerformanceMetric(BaseModel):
    """Performance metric model"""
    operation: str = Field(..., description="Operation name")
    duration: float = Field(..., description="Duration in seconds")
    timestamp: datetime = Field(..., description="Measurement timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Additional metadata")

class DailyStats(BaseModel):
    """Daily statistics model"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    queries: int = Field(..., description="Number of queries")
    users: int = Field(..., description="Number of unique users")
    errors: int = Field(..., description="Number of errors")
    avg_response_time: float = Field(..., description="Average response time in seconds")

class UsageStats(BaseModel):
    """Usage statistics model"""
    days: List[str] = Field(..., description="List of days (YYYY-MM-DD)")
    queries: List[int] = Field(..., description="Number of queries per day")
    errors: List[int] = Field(..., description="Number of errors per day")
    document_views: List[int] = Field(..., description="Number of document views per day")
    users: List[int] = Field(..., description="Number of active users per day")

class PerformanceStats(BaseModel):
    """Performance statistics model"""
    days: List[str] = Field(..., description="List of days (YYYY-MM-DD)")
    operations: Dict[str, Dict[str, Any]] = Field(..., description="Statistics by operation")
    top_operations: List[str] = Field(..., description="Top operations by count")
    daily_data: Dict[str, List[float]] = Field(..., description="Daily average duration by operation")

class TopQuery(BaseModel):
    """Top query model"""
    query: str = Field(..., description="Query text")
    count: int = Field(..., description="Number of occurrences")
    last_seen: str = Field(..., description="Last seen timestamp")

class ErrorSummary(BaseModel):
    """Error summary model"""
    total_count: int = Field(..., description="Total number of errors")
    top_errors: List[Dict[str, Any]] = Field(..., description="Top errors by count")

class SystemHealth(BaseModel):
    """System health model"""
    status: str = Field(..., description="Overall status (good, warning, critical)")
    cpu_percent: float = Field(..., description="CPU usage percentage")
    memory_percent: float = Field(..., description="Memory usage percentage")
    disk_percent: float = Field(..., description="Disk usage percentage")
    log_sizes_mb: Dict[str, float] = Field(..., description="Log file sizes in MB")
    recent_errors: int = Field(..., description="Number of errors in the last hour")
    response_times: Dict[str, Any] = Field(..., description="Response time metrics")
    timestamp: str = Field(..., description="Timestamp of health check")

class AnalyticsDashboard(BaseModel):
    """Analytics dashboard model"""
    daily_stats: UsageStats = Field(..., description="Daily usage statistics")
    performance_stats: PerformanceStats = Field(..., description="Performance statistics")
    top_queries: List[TopQuery] = Field(..., description="Top queries")
    error_summary: ErrorSummary = Field(..., description="Error summary")
    system_health: SystemHealth = Field(..., description="System health")

class ExportRequest(BaseModel):
    """Export request model"""
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    event_types: Optional[List[str]] = Field(default=None, description="Event types to include")