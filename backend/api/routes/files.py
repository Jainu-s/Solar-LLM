import os
import uuid
import shutil
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Form, Query
from fastapi.responses import FileResponse

from backend.utils.session import session_manager
from backend.utils.analytics import analytics_service
from backend.utils.logging import setup_logger, PerformanceMonitor
from backend.retrieval.document_ingestion import document_ingestion_manager
from backend.config import settings

logger = setup_logger("file_routes")

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses={404: {"description": "Not found"}},
)

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    add_to_index: bool = Form(True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user = Depends(session_manager.get_current_user)
):
    """
    Upload a file
    """
    try:
        user_id = current_user["_id"]
        
        # Check file size (limit to 50MB)
        file_size = 0
        for chunk in file.file:
            file_size += len(chunk)
            if file_size > 50 * 1024 * 1024:  # 50MB
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File too large (max 50MB)"
                )
        
        # Reset file position
        file.file.seek(0)
        
        # Create documents directory for user if it doesn't exist
        user_docs_dir = os.path.join(settings.DATA_DIR, "documents", user_id)
        os.makedirs(user_docs_dir, exist_ok=True)
        
        # Generate unique filename
        filename = file.filename
        file_extension = os.path.splitext(filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(user_docs_dir, unique_filename)
        
        # Check if file extension is allowed
        allowed_extensions = [".pdf", ".txt", ".docx", ".csv", ".json", ".xlsx"]
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Write file to disk
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        # Create file metadata
        file_metadata = {
            "user_id": user_id,
            "original_filename": filename,
            "filename": unique_filename,
            "file_path": file_path,
            "file_type": file_extension,
            "file_size": file_size,
            "title": title or filename,
            "description": description,
            "category": category,
            "tags": tags.split(",") if tags else [],
            "upload_time": "now"  # MongoDB will convert this to the current time
        }
        
        # Store file metadata in database
        db = session_manager.db
        result = db["files"].insert_one(file_metadata)
        file_id = str(result.inserted_id)
        
        # Add file to vector index if requested
        if add_to_index and file_extension in [".pdf", ".txt", ".docx"]:
            # Process document in the background
            background_tasks.add_task(
                document_ingestion_manager.ingest_document,
                file_path,
                {
                    "user_id": user_id,
                    "file_id": file_id,
                    "title": title or filename,
                    "description": description,
                    "category": category,
                    "tags": tags.split(",") if tags else []
                }
            )
        
        # Track file upload
        background_tasks.add_task(
            analytics_service.track_event,
            "file_upload",
            {
                "file_id": file_id,
                "file_type": file_extension,
                "file_size": file_size,
                "add_to_index": add_to_index
            },
            user_id
        )
        
        return {
            "id": file_id,
            "filename": filename,
            "size": file_size,
            "status": "uploaded",
            "indexing": add_to_index
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file: {str(e)}"
        )
    finally:
        file.file.close()

@router.get("/list", response_model=List[Dict[str, Any]])
async def list_files(
    current_user = Depends(session_manager.get_current_user),
    category: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """
    List user files
    """
    try:
        user_id = current_user["_id"]
        
        # Build query
        query = {"user_id": user_id}
        
        if category:
            query["category"] = category
            
        if file_type:
            query["file_type"] = file_type
        
        # Get files from database
        db = session_manager.db
        files = list(db["files"].find(query).sort("upload_time", -1).skip(skip).limit(limit))
        
        # Format files
        result = []
        for file in files:
            # Convert ObjectId to string
            file["id"] = str(file.pop("_id"))
            result.append(file)
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing files: {str(e)}"
        )

@router.get("/{file_id}")
async def get_file(
    file_id: str,
    current_user = Depends(session_manager.get_current_user),
    download: bool = False
):
    """
    Get file details or download file
    """
    try:
        user_id = current_user["_id"]
        
        # Get file from database
        db = session_manager.db
        file = db["files"].find_one({
            "_id": file_id,
            "user_id": user_id
        })
        
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # If download requested, return file
        if download:
            file_path = file["file_path"]
            
            if not os.path.exists(file_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found on disk"
                )
            
            # Track download
            analytics_service.track_event(
                "file_download",
                {"file_id": file_id},
                user_id
            )
            
            return FileResponse(
                file_path,
                filename=file["original_filename"],
                media_type="application/octet-stream"
            )
        
        # Otherwise, return file details
        file["id"] = str(file.pop("_id"))
        return file
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting file: {str(e)}"
        )

@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: str,
    current_user = Depends(session_manager.get_current_user),
    remove_from_index: bool = True,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Delete a file
    """
    try:
        user_id = current_user["_id"]
        
        # Get file from database
        db = session_manager.db
        file = db["files"].find_one({
            "_id": file_id,
            "user_id": user_id
        })
        
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Get file path
        file_path = file["file_path"]
        
        # Delete file from database
        db["files"].delete_one({"_id": file_id})
        
        # Delete file from disk if it exists
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Remove from vector index if requested
        if remove_from_index:
            # Get document ID from vector database
            documents = list(db["documents"].find({"file_path": file_path}))
            
            for doc in documents:
                document_id = doc.get("document_id")
                if document_id:
                    # Delete document in the background
                    background_tasks.add_task(
                        document_ingestion_manager.delete_document,
                        document_id
                    )
        
        # Track deletion
        background_tasks.add_task(
            analytics_service.track_event,
            "file_delete",
            {
                "file_id": file_id,
                "remove_from_index": remove_from_index
            },
            user_id
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting file: {str(e)}"
        )

@router.get("/documents/status/{document_id}")
async def get_document_status(
    document_id: str,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Get document processing status
    """
    try:
        user_id = current_user["_id"]
        
        # Get document status
        status = await document_ingestion_manager.get_document_status(document_id)
        
        # Check if document belongs to user
        if status.get("file_path"):
            # Get file from database
            db = session_manager.db
            file = db["files"].find_one({
                "file_path": status["file_path"],
                "user_id": user_id
            })
            
            if not file:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting document status: {str(e)}"
        )

@router.get("/documents/list")
async def list_documents(
    current_user = Depends(session_manager.get_current_user)
):
    """
    List indexed documents
    """
    try:
        user_id = current_user["_id"]
        
        # Get all documents
        all_documents = await document_ingestion_manager.get_all_documents()
        
        # Filter documents by user
        user_documents = []
        for doc in all_documents:
            # Get file from database to check ownership
            db = session_manager.db
            file = db["files"].find_one({
                "file_path": doc.get("file_path"),
                "user_id": user_id
            })
            
            if file:
                doc["file_id"] = str(file["_id"])
                doc["title"] = file.get("title")
                user_documents.append(doc)
        
        return user_documents
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing documents: {str(e)}"
        )