from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from pydantic import BaseModel

from backend.utils.session import session_manager
from backend.utils.analytics import analytics_service
from backend.utils.logging import setup_logger
from backend.db.mongodb import get_database, check_health, optimize_collection
from backend.db.chromadb_client import get_chroma_client, optimize_database
from backend.retrieval.document_ingestion import document_ingestion_manager
from backend.utils.cache import cache_manager
from backend.config import settings

logger = setup_logger("admin_routes")

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={404: {"description": "Not found"}},
)

class SystemStatusResponse(BaseModel):
    """System status response schema"""
    status: str
    components: Dict[str, Dict[str, Any]]
    resources: Dict[str, Any]
    uptime: float

class OptimizationRequest(BaseModel):
    """Optimization request schema"""
    components: List[str]

# Admin check middleware
async def admin_check(current_user = Depends(session_manager.get_current_user)):
    """Check if the current user is an admin"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

@router.get("/status", response_model=SystemStatusResponse)
async def system_status(
    admin_user = Depends(admin_check)
):
    """
    Get system status
    """
    try:
        # Get database health
        db_health = check_health()
        
        # Get system health from analytics service
        system_health = await analytics_service.get_system_health()
        
        # Get cache stats
        cache_stats = cache_manager.get_stats()
        
        # Get vector database stats
        vector_db_stats = {
            "status": "ok",
            "collections": len(get_chroma_client().list_collections())
        }
        
        # Get document ingestion stats
        documents = await document_ingestion_manager.get_all_documents()
        document_stats = {
            "status": "ok",
            "total_documents": len(documents),
            "completed": sum(1 for doc in documents if doc.get("status") == "completed"),
            "processing": sum(1 for doc in documents if doc.get("status") == "processing"),
            "error": sum(1 for doc in documents if doc.get("status") == "error")
        }
        
        # Combine all stats
        status = "ok"
        if (
            db_health.get("status") != "ok" or
            system_health.get("status") != "good"
        ):
            status = "degraded"
        
        if (
            db_health.get("status") == "error" or
            system_health.get("status") == "critical"
        ):
            status = "critical"
        
        # Calculate uptime (placeholder)
        uptime = 0
        
        return {
            "status": status,
            "components": {
                "database": db_health,
                "vector_db": vector_db_stats,
                "document_ingestion": document_stats,
                "cache": cache_stats
            },
            "resources": {
                "cpu_percent": system_health.get("cpu_percent", 0),
                "memory_percent": system_health.get("memory_percent", 0),
                "disk_percent": system_health.get("disk_percent", 0)
            },
            "uptime": uptime
        }
        
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting system status: {str(e)}"
        )

@router.post("/optimize")
async def optimize_system(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks,
    admin_user = Depends(admin_check)
):
    """
    Optimize system components
    """
    try:
        results = {}
        
        # Optimize cache if requested
        if "cache" in request.components:
            cleaned_items = cache_manager.cleanup()
            results["cache"] = {
                "status": "optimized",
                "cleaned_items": cleaned_items
            }
        
        # Optimize vector database if requested
        if "vector_db" in request.components:
            optimize_result = optimize_database()
            results["vector_db"] = {
                "status": "optimized" if optimize_result else "failed"
            }
        
        # Optimize database collections if requested
        if "database" in request.components:
            db_results = {}
            collections = ["users", "conversations", "documents", "events", "analytics"]
            
            for collection in collections:
                try:
                    result = optimize_collection(collection)
                    db_results[collection] = {
                        "status": result.get("status", "error")
                    }
                except Exception as e:
                    logger.error(f"Error optimizing collection {collection}: {str(e)}")
                    db_results[collection] = {
                        "status": "error",
                        "error": str(e)
                    }
            
            results["database"] = db_results
        
        # Prune expired sessions if requested
        if "sessions" in request.components:
            cleaned = session_manager.cleanup_expired_sessions()
            results["sessions"] = {
                "status": "optimized",
                "cleaned_sessions": cleaned
            }
        
        return {
            "status": "completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error optimizing system: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error optimizing system: {str(e)}"
        )

@router.get("/analytics/dashboard")
async def analytics_dashboard(
    days: int = 7,
    admin_user = Depends(admin_check)
):
    """
    Get analytics dashboard data
    """
    try:
        # Get stats from analytics service
        daily_stats = await analytics_service.get_daily_stats(days)
        performance_stats = await analytics_service.get_performance_stats(days)
        top_queries = await analytics_service.get_top_queries(days)
        error_summary = await analytics_service.get_error_summary(days)
        
        return {
            "daily_stats": daily_stats,
            "performance_stats": performance_stats,
            "top_queries": top_queries,
            "error_summary": error_summary
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting analytics dashboard: {str(e)}"
        )

@router.get("/users", response_model=List[Dict[str, Any]])
async def list_users(
    admin_user = Depends(admin_check),
    limit: int = 100,
    skip: int = 0,
    sort: str = "created_at",
    sort_dir: int = -1
):
    """
    List all users
    """
    try:
        # Get database
        db = get_database()
        
        # Build sort dictionary
        sort_field = sort if sort else "created_at"
        sort_direction = sort_dir if sort_dir in [-1, 1] else -1
        
        # Query users
        users = list(db["users"].find(
            {},
            {"password": 0}  # Exclude password
        ).sort(sort_field, sort_direction).skip(skip).limit(limit))
        
        # Format users
        result = []
        for user in users:
            # Convert ObjectId to string
            user["id"] = str(user.pop("_id"))
            result.append(user)
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing users: {str(e)}"
        )

@router.get("/documents", response_model=List[Dict[str, Any]])
async def admin_list_documents(
    admin_user = Depends(admin_check)
):
    """
    List all documents
    """
    try:
        # Get all documents
        documents = await document_ingestion_manager.get_all_documents()
        
        # Get document details
        db = get_database()
        for doc in documents:
            if doc.get("file_path"):
                # Get file info
                file = db["files"].find_one({"file_path": doc["file_path"]})
                if file:
                    doc["file_id"] = str(file["_id"])
                    doc["user_id"] = file.get("user_id")
                    doc["title"] = file.get("title")
        
        return documents
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing documents: {str(e)}"
        )

@router.post("/export-analytics")
async def export_analytics(
    start_date: str,
    end_date: str,
    event_types: Optional[List[str]] = None,
    admin_user = Depends(admin_check)
):
    """
    Export analytics data
    """
    try:
        # Parse dates
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        # Export analytics
        export_path = await analytics_service.export_analytics(
            start,
            end,
            event_types
        )
        
        return {
            "status": "success",
            "export_path": export_path
        }
        
    except Exception as e:
        logger.error(f"Error exporting analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting analytics: {str(e)}"
        )

@router.post("/cleanup")
async def system_cleanup(
    background_tasks: BackgroundTasks,
    admin_user = Depends(admin_check)
):
    """
    Clean up system resources
    """
    try:
        results = {}
        
        # Clean up cache
        cache_items = cache_manager.cleanup()
        results["cache"] = {
            "cleaned_items": cache_items
        }
        
        # Clean up expired sessions
        cleaned_sessions = session_manager.cleanup_expired_sessions()
        results["sessions"] = {
            "cleaned_sessions": cleaned_sessions
        }
        
        # Clean up temporary files
        import os
        import glob
        import time
        
        temp_files = glob.glob(os.path.join(settings.UPLOADS_DIR, "temp_*"))
        old_files = [f for f in temp_files if os.path.getmtime(f) < time.time() - 24*60*60]
        
        for file in old_files:
            try:
                os.remove(file)
            except:
                pass
        
        results["temp_files"] = {
            "cleaned_files": len(old_files)
        }
        
        return {
            "status": "completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up system: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cleaning up system: {str(e)}"
        )

@router.post("/user/{user_id}/activate")
async def activate_user(
    user_id: str,
    admin_user = Depends(admin_check)
):
    """
    Activate a user account
    """
    try:
        # Get database
        db = get_database()
        
        # Update user
        result = db["users"].update_one(
            {"_id": user_id},
            {"$set": {"active": True}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {"status": "User activated"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error activating user: {str(e)}"
        )

@router.post("/user/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    admin_user = Depends(admin_check)
):
    """
    Deactivate a user account
    """
    try:
        # Get database
        db = get_database()
        
        # Update user
        result = db["users"].update_one(
            {"_id": user_id},
            {"$set": {"active": False}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Revoke all sessions
        session_manager.revoke_all_user_sessions(user_id)
        
        return {"status": "User deactivated"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating user: {str(e)}"
        )