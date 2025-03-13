import os
import time
from typing import Optional, Dict, Any, List, Union
import threading

import pymongo
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.utils.logging import setup_logger
from backend.config import settings

logger = setup_logger("mongodb_client")

# Connection pool
_clients = {}
_db_instances = {}
_lock = threading.RLock()

def get_client(
    uri: Optional[str] = None,
    max_pool_size: int = 10
) -> MongoClient:
    """
    Get a MongoDB client instance
    
    Args:
        uri: MongoDB connection URI
        max_pool_size: Maximum connection pool size
        
    Returns:
        MongoDB client instance
    """
    uri = uri or settings.MONGODB_URI
    
    with _lock:
        if uri in _clients:
            return _clients[uri]
        
        try:
            start_time = time.time()
            
            # Create client
            client = MongoClient(
                uri,
                maxPoolSize=max_pool_size,
                connectTimeoutMS=5000,
                socketTimeoutMS=30000,
                serverSelectionTimeoutMS=5000,
                retryWrites=True
            )
            
            # Test connection
            client.admin.command("ping")
            
            logger.info(f"MongoDB client connected in {time.time() - start_time:.2f}s")
            
            # Store client
            _clients[uri] = client
            
            return client
            
        except (ConnectionFailure, OperationFailure) as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {str(e)}")
            raise

def get_database(
    db_name: Optional[str] = None,
    uri: Optional[str] = None
) -> Database:
    """
    Get a MongoDB database instance
    
    Args:
        db_name: Database name
        uri: MongoDB connection URI
        
    Returns:
        MongoDB database instance
    """
    db_name = db_name or settings.MONGODB_DB
    uri = uri or settings.MONGODB_URI
    
    with _lock:
        cache_key = f"{uri}:{db_name}"
        
        if cache_key in _db_instances:
            return _db_instances[cache_key]
        
        try:
            # Get client
            client = get_client(uri)
            
            # Get database
            db = client[db_name]
            
            # Store database instance
            _db_instances[cache_key] = db
            
            return db
            
        except Exception as e:
            logger.error(f"Error getting MongoDB database: {str(e)}")
            raise

def close_connections() -> None:
    """Close all MongoDB client connections"""
    with _lock:
        for uri, client in _clients.items():
            try:
                client.close()
                logger.info(f"Closed MongoDB connection for {uri}")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")
        
        _clients.clear()
        _db_instances.clear()

def create_indices() -> None:
    """Create indices for commonly used collections"""
    try:
        db = get_database()
        
        # Users collection
        db.users.create_index("email", unique=True)
        db.users.create_index("username", unique=True)
        db.users.create_index("created_at")
        
        # Conversations collection
        db.conversations.create_index("user_id")
        db.conversations.create_index("created_at")
        db.conversations.create_index([("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
        
        # Documents collection
        db.documents.create_index("user_id")
        db.documents.create_index("file_path", unique=True)
        db.documents.create_index("status")
        db.documents.create_index("ingestion_time")
        
        # Analytics collection
        db.analytics.create_index("timestamp")
        db.analytics.create_index("type")
        db.analytics.create_index("user_id")
        
        # Events collection
        db.events.create_index("timestamp")
        db.events.create_index("event_type")
        db.events.create_index("user_id")
        db.events.create_index([("event_type", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)])
        
        # Performance collection
        db.performance.create_index("timestamp")
        db.performance.create_index("operation")
        db.performance.create_index([("operation", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)])
        
        # Feedback collection
        db.feedback.create_index("user_id")
        db.feedback.create_index("timestamp")
        db.feedback.create_index("conversation_id")
        
        # Sessions collection
        db.sessions.create_index("user_id")
        db.sessions.create_index("expires_at", expireAfterSeconds=0)  # TTL index
        
        logger.info("Created MongoDB indices")
        
    except Exception as e:
        logger.error(f"Error creating MongoDB indices: {str(e)}")
        raise

def check_health() -> Dict[str, Any]:
    """
    Check the health of the MongoDB connection
    
    Returns:
        Dictionary with health status
    """
    try:
        start_time = time.time()
        
        # Get client
        client = get_client()
        
        # Execute ping command
        client.admin.command("ping")
        
        # Get server status
        server_status = client.admin.command("serverStatus")
        
        latency = time.time() - start_time
        
        return {
            "status": "ok",
            "latency": latency,
            "connections": server_status.get("connections", {}).get("current", 0),
            "version": server_status.get("version", "unknown")
        }
        
    except Exception as e:
        logger.error(f"MongoDB health check failed: {str(e)}")
        
        return {
            "status": "error",
            "error": str(e)
        }

def get_collection_stats(collection_name: str) -> Dict[str, Any]:
    """
    Get statistics for a collection
    
    Args:
        collection_name: Collection name
        
    Returns:
        Dictionary with collection statistics
    """
    try:
        db = get_database()
        
        # Execute collStats command
        stats = db.command("collStats", collection_name)
        
        return {
            "name": collection_name,
            "count": stats.get("count", 0),
            "size_bytes": stats.get("size", 0),
            "avg_doc_size_bytes": stats.get("avgObjSize", 0),
            "storage_size_bytes": stats.get("storageSize", 0),
            "num_indices": len(stats.get("indexSizes", {})),
            "indices_size_bytes": stats.get("totalIndexSize", 0)
        }
        
    except Exception as e:
        logger.error(f"Error getting collection stats for {collection_name}: {str(e)}")
        
        return {
            "name": collection_name,
            "error": str(e)
        }

def add_with_retry(
    collection_name: str,
    document: Dict[str, Any],
    max_retries: int = 3
) -> Optional[str]:
    """
    Add a document to a collection with retry logic
    
    Args:
        collection_name: Collection name
        document: Document to add
        max_retries: Maximum number of retries
        
    Returns:
        Inserted document ID or None if failed
    """
    db = get_database()
    collection = db[collection_name]
    
    for attempt in range(max_retries):
        try:
            result = collection.insert_one(document)
            return str(result.inserted_id)
            
        except pymongo.errors.AutoReconnect:
            if attempt < max_retries - 1:
                sleep_time = (2 ** attempt) * 0.1  # Exponential backoff
                logger.warning(f"MongoDB connection lost, retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
            else:
                logger.error(f"Failed to add document after {max_retries} retries")
                return None
                
        except Exception as e:
            logger.error(f"Error adding document to {collection_name}: {str(e)}")
            return None

def backup_collection(
    collection_name: str,
    output_dir: Optional[str] = None
) -> Optional[str]:
    """
    Backup a collection to a JSON file
    
    Args:
        collection_name: Collection name
        output_dir: Output directory (defaults to data/backups)
        
    Returns:
        Path to backup file or None if failed
    """
    import json
    from datetime import datetime
    
    # Set default output directory
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "backups")
    
    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate backup filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(output_dir, f"{collection_name}_{timestamp}.json")
    
    try:
        # Get all documents from collection
        db = get_database()
        collection = db[collection_name]
        documents = list(collection.find({}, {"_id": 0}))
        
        # Handle date/datetime objects for JSON serialization
        for doc in documents:
            for key, value in doc.items():
                if isinstance(value, (datetime)):
                    doc[key] = value.isoformat()
        
        # Write to file
        with open(backup_path, 'w') as f:
            json.dump(documents, f, indent=2)
        
        logger.info(f"Backed up {len(documents)} documents from {collection_name} to {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"Error backing up collection {collection_name}: {str(e)}")
        return None

def restore_collection(
    backup_path: str,
    collection_name: Optional[str] = None,
    drop_existing: bool = False
) -> Dict[str, Any]:
    """
    Restore a collection from a backup file
    
    Args:
        backup_path: Path to backup file
        collection_name: Collection name (defaults to filename without timestamp)
        drop_existing: Whether to drop existing collection
        
    Returns:
        Dictionary with restoration results
    """
    import json
    
    try:
        # Determine collection name from filename if not provided
        if not collection_name:
            filename = os.path.basename(backup_path)
            parts = filename.split("_")
            collection_name = parts[0]
        
        # Read backup file
        with open(backup_path, 'r') as f:
            documents = json.load(f)
        
        # Get database and collection
        db = get_database()
        collection = db[collection_name]
        
        # Drop existing collection if requested
        if drop_existing:
            collection.drop()
        
        # Insert documents
        if documents:
            result = collection.insert_many(documents)
            inserted_count = len(result.inserted_ids)
        else:
            inserted_count = 0
        
        logger.info(f"Restored {inserted_count} documents to {collection_name} from {backup_path}")
        
        return {
            "collection_name": collection_name,
            "documents_count": len(documents),
            "inserted_count": inserted_count,
            "backup_path": backup_path
        }
        
    except Exception as e:
        logger.error(f"Error restoring collection from {backup_path}: {str(e)}")
        
        return {
            "error": str(e),
            "backup_path": backup_path
        }

def optimize_collection(collection_name: str) -> Dict[str, Any]:
    """
    Optimize a collection with potential improvements
    
    Args:
        collection_name: Collection name
        
    Returns:
        Dictionary with optimization results
    """
    try:
        db = get_database()
        
        # Run compact command
        result = db.command("compact", collection_name)
        
        # Reindex collection
        db[collection_name].reindex()
        
        return {
            "collection_name": collection_name,
            "compact_result": result,
            "status": "optimized"
        }
        
    except Exception as e:
        logger.error(f"Error optimizing collection {collection_name}: {str(e)}")
        
        return {
            "collection_name": collection_name,
            "error": str(e)
        }