import os
import time
import threading
from typing import Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from backend.api.routes import api_router
from backend.utils.session import ensure_safe_indices
# Update the import to use RequestLogMiddleware directly
from backend.utils.logging import setup_logger, RequestLogMiddleware
from backend.db.mongodb import create_indices
from backend.config import settings

# Setup logger
logger = setup_logger("main")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request logging middleware - use the class directly
app.add_middleware(RequestLogMiddleware)

# Mount API router
app.include_router(api_router, prefix=settings.API_PREFIX)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# In-memory store for rate limiting
RATE_LIMIT_STORE = {}
RATE_LIMIT_LOCK = threading.Lock()

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Simple IP-based rate limiting
    client_ip = request.client.host
    
    # Skip rate limiting for certain paths
    if request.url.path.startswith("/static/") or request.url.path == "/":
        return await call_next(request)
    
    # Rate limit key
    rate_limit_key = f"rate_limit:{client_ip}"
    
    # Get current timestamp
    current_time = time.time()
    
    # Thread-safe access to rate limit store
    with RATE_LIMIT_LOCK:
        # Get existing requests or empty list
        recent_requests = RATE_LIMIT_STORE.get(rate_limit_key, [])
        
        # Remove requests older than 1 minute
        recent_requests = [ts for ts in recent_requests if current_time - ts < 60]
        
        # Check if too many requests
        if len(recent_requests) >= 60:  # 60 requests per minute
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."}
            )
        
        # Add current request
        recent_requests.append(current_time)
        
        # Store updated list
        RATE_LIMIT_STORE[rate_limit_key] = recent_requests
        
        # Set expiry (cleanup old entries periodically)
        if len(RATE_LIMIT_STORE) > 1000:  # Simple cleanup to prevent memory leaks
            keys_to_delete = []
            for key, timestamps in RATE_LIMIT_STORE.items():
                if not timestamps or current_time - max(timestamps) > 600:  # 10 minutes
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del RATE_LIMIT_STORE[key]
    
    # Continue processing request
    return await call_next(request)

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # Create required directories
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    
    # Create MongoDB indices
    create_indices()
    
    # Initialize session indices
    ensure_safe_indices()
    
    logger.info("Application startup complete")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")
    
    # Close database connections
    from backend.db.mongodb import close_connections
    close_connections()

# Root path handler
@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "api_docs": "/api/docs"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    # Simple health check
    return {
        "status": "ok",
        "timestamp": time.time()
    }

# Add middleware to measure request time
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=settings.DEBUG
    )