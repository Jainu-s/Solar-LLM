import os
import logging
import sys
import json
from typing import Dict, Any, Optional
from datetime import datetime
import traceback
import logging.handlers
import time

from backend.config import settings

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
os.makedirs(logs_dir, exist_ok=True)

# Configure loggers
_loggers = {}

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs log records as JSON
    """
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields
        if hasattr(record, "extras"):
            log_data.update(record.extras)
        
        return json.dumps(log_data)

def setup_logger(name: str, log_level: Optional[str] = None) -> logging.Logger:
    """
    Set up a logger with file and console handlers
    
    Args:
        name: Logger name
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Returns:
        Configured logger
    """
    # Check if logger already exists
    if name in _loggers:
        return _loggers[name]
    
    # Create logger
    logger = logging.getLogger(name)
    
    # Set log level
    log_level = log_level or settings.LOG_LEVEL or "INFO"
    logger.setLevel(getattr(logging, log_level))
    
    # Prevent logs from being passed to the root logger
    logger.propagate = False
    
    # Create handlers if they don't exist
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(console_handler)
        
        # File handler for regular logs
        log_file = os.path.join(logs_dir, f"{name}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(file_handler)
        
        # JSON file handler for analytics
        analytics_file = os.path.join(logs_dir, f"{name}_analytics.json")
        json_handler = logging.handlers.RotatingFileHandler(
            analytics_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        json_handler.setFormatter(JSONFormatter())
        json_handler.setLevel(logging.INFO)  # Only log INFO and above for analytics
        logger.addHandler(json_handler)
        
        # Error handler for aggregated errors
        error_file = os.path.join(logs_dir, "error.log")
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        error_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        error_handler.setLevel(logging.ERROR)  # Only log errors and critical
        logger.addHandler(error_handler)
    
    # Store logger
    _loggers[name] = logger
    
    return logger

def log_with_extras(
    logger: logging.Logger,
    level: str,
    message: str,
    extras: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log a message with extra data fields for structured logging
    
    Args:
        logger: Logger to use
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        extras: Extra data fields
    """
    extras = extras or {}
    
    # Create log record
    record = logging.LogRecord(
        name=logger.name,
        level=getattr(logging, level.upper()),
        pathname=__file__,
        lineno=0,
        msg=message,
        args=(),
        exc_info=None
    )
    
    # Add extras
    record.extras = extras
    
    # Log record
    logger.handle(record)

class RequestLogger:
    """
    Logger for HTTP requests
    """
    
    def __init__(self):
        self.logger = setup_logger("api")
    
    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        response_time: float,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        query_params: Optional[Dict[str, Any]] = None,
        extras: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an HTTP request
        
        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            response_time: Response time in seconds
            user_id: Optional user ID
            client_ip: Optional client IP address
            user_agent: Optional user agent string
            query_params: Optional query parameters
            extras: Optional extra data fields
        """
        # Create extras
        log_extras = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "response_time": response_time,
            "user_id": user_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "query_params": query_params
        }
        
        # Add any additional extras
        if extras:
            log_extras.update(extras)
        
        # Determine log level based on status code
        if status_code >= 500:
            level = "error"
        elif status_code >= 400:
            level = "warning"
        else:
            level = "info"
        
        # Create log message
        message = f"{method} {path} {status_code} in {response_time:.3f}s"
        
        # Log request
        log_with_extras(self.logger, level, message, log_extras)

class RequestLogMiddleware:
    """
    Middleware for logging HTTP requests
    """
    
    def __init__(self):
        self.logger = RequestLogger()
    
    async def __call__(self, request, call_next):
        # Record start time
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Record end time
            end_time = time.time()
            
            # Log request
            self.logger.log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                response_time=end_time - start_time,
                user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
                client_ip=request.client.host,
                user_agent=request.headers.get("user-agent"),
                query_params=dict(request.query_params)
            )
            
            return response
            
        except Exception as e:
            # Record end time
            end_time = time.time()
            
            # Log error
            self.logger.log_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                response_time=end_time - start_time,
                user_id=request.state.user_id if hasattr(request.state, "user_id") else None,
                client_ip=request.client.host,
                user_agent=request.headers.get("user-agent"),
                query_params=dict(request.query_params),
                extras={"error": str(e), "traceback": traceback.format_exc()}
            )
            
            # Re-raise exception
            raise

class PerformanceMonitor:
    """
    Monitor for tracking performance metrics
    """
    
    def __init__(self, name: str):
        self.name = name
        self.logger = setup_logger("performance")
        self.start_time = None
    
    def start(self) -> None:
        """Start timing"""
        self.start_time = time.time()
    
    def stop(self, extras: Optional[Dict[str, Any]] = None) -> float:
        """
        Stop timing and log performance
        
        Args:
            extras: Extra data fields
            
        Returns:
            Elapsed time in seconds
        """
        if self.start_time is None:
            return 0
        
        # Calculate elapsed time
        elapsed_time = time.time() - self.start_time
        
        # Create extras
        log_extras = {
            "name": self.name,
            "elapsed_time": elapsed_time
        }
        
        # Add any additional extras
        if extras:
            log_extras.update(extras)
        
        # Log performance
        log_with_extras(
            self.logger,
            "info",
            f"{self.name} completed in {elapsed_time:.3f}s",
            log_extras
        )
        
        return elapsed_time
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        extras = None
        
        if exc_type:
            extras = {
                "error": str(exc_val),
                "traceback": traceback.format_exc()
            }
        
        self.stop(extras)

def setup_global_logging(logs_dir):
    """
    Set up global logging configuration for the application
    
    Args:
        logs_dir: Directory for log files
    """
    # Ensure the logs directory exists
    os.makedirs(logs_dir, exist_ok=True)
    
    # Set up the main application logger
    app_logger = setup_logger("app")
    
    # Set up specific loggers for different components
    setup_logger("api")
    setup_logger("db")
    setup_logger("models")
    setup_logger("security")
    setup_logger("performance")
    
    # Log application startup
    app_logger.info(f"Application started with environment: {settings.ENVIRONMENT}")
    app_logger.info(f"Logging to directory: {logs_dir}")
    
    return app_logger

# Initialize request logger
request_logger = RequestLogger()