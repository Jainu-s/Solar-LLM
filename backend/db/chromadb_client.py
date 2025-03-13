import os
import time
from typing import Optional, Dict, Any

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from backend.utils.logging import setup_logger
from backend.config import settings

logger = setup_logger("chromadb_client")

# Global client instance
_client = None

def get_chroma_client(
    persist_directory: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None
) -> chromadb.Client:
    """
    Get a ChromaDB client instance
    
    Args:
        persist_directory: Directory for persistent storage
        host: Optional host for using HTTP client
        port: Optional port for using HTTP client
        
    Returns:
        ChromaDB client instance
    """
    global _client
    
    if _client is not None:
        return _client
    
    # Default settings
    persist_directory = persist_directory or settings.VECTOR_DB_PATH
    
    # Create directory if it doesn't exist
    if persist_directory:
        os.makedirs(persist_directory, exist_ok=True)
    
    try:
        start_time = time.time()
        
        # Use HTTP client if host is provided, otherwise use persistent client
        if host:
            logger.info(f"Connecting to ChromaDB via HTTP at {host}:{port}")
            _client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=Settings(
                    anonymized_telemetry=False
                )
            )
        else:
            logger.info(f"Creating persistent ChromaDB client at {persist_directory}")
            _client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        
        logger.info(f"ChromaDB client initialized in {time.time() - start_time:.2f}s")
        return _client
        
    except Exception as e:
        logger.error(f"Error initializing ChromaDB client: {str(e)}")
        raise

def reset_client() -> None:
    """Reset the global client instance"""
    global _client
    _client = None

def list_collections() -> list:
    """
    List all collections in the database
    
    Returns:
        List of collection names
    """
    client = get_chroma_client()
    return client.list_collections()

def create_collection(
    name: str, 
    embedding_function: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> chromadb.Collection:
    """
    Create a new collection
    
    Args:
        name: Collection name
        embedding_function: Optional embedding function
        metadata: Optional collection metadata
        
    Returns:
        Created collection
    """
    client = get_chroma_client()
    
    try:
        logger.info(f"Creating collection: {name}")
        
        # Create collection
        collection = client.create_collection(
            name=name,
            embedding_function=embedding_function,
            metadata=metadata
        )
        
        return collection
        
    except Exception as e:
        logger.error(f"Error creating collection: {str(e)}")
        raise

def get_collection(
    name: str, 
    embedding_function: Optional[Any] = None
) -> Optional[chromadb.Collection]:
    """
    Get a collection by name
    
    Args:
        name: Collection name
        embedding_function: Optional embedding function
        
    Returns:
        Collection or None if not found
    """
    client = get_chroma_client()
    
    try:
        return client.get_collection(
            name=name,
            embedding_function=embedding_function
        )
    except Exception as e:
        logger.error(f"Error getting collection {name}: {str(e)}")
        return None

def get_or_create_collection(
    name: str, 
    embedding_function: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> chromadb.Collection:
    """
    Get a collection by name or create it if it doesn't exist
    
    Args:
        name: Collection name
        embedding_function: Optional embedding function
        metadata: Optional collection metadata
        
    Returns:
        Existing or newly created collection
    """
    client = get_chroma_client()
    
    try:
        # Try to get existing collection
        collection = get_collection(name, embedding_function)
        
        if collection:
            return collection
        
        # Create new collection
        return create_collection(name, embedding_function, metadata)
        
    except Exception as e:
        logger.error(f"Error getting or creating collection {name}: {str(e)}")
        raise

def delete_collection(name: str) -> bool:
    """
    Delete a collection by name
    
    Args:
        name: Collection name
        
    Returns:
        True if deleted, False otherwise
    """
    client = get_chroma_client()
    
    try:
        logger.info(f"Deleting collection: {name}")
        client.delete_collection(name)
        return True
    except Exception as e:
        logger.error(f"Error deleting collection {name}: {str(e)}")
        return False

def optimize_database() -> bool:
    """
    Optimize the database (if supported by backend)
    
    Returns:
        True if optimization was successful, False otherwise
    """
    client = get_chroma_client()
    
    try:
        # For PersistentClient, we can call persist() to ensure all data is written to disk
        if hasattr(client, "persist"):
            client.persist()
            logger.info("Database optimized")
            return True
        
        logger.info("Database optimization not supported by this client type")
        return False
        
    except Exception as e:
        logger.error(f"Error optimizing database: {str(e)}")
        return False

def get_default_embedding_function() -> Any:
    """
    Get the default embedding function
    
    Returns:
        Default embedding function
    """
    # Use a default embedding function based on settings
    embedding_model = settings.DEFAULT_EMBEDDING_MODEL
    
    if embedding_model == "all-MiniLM-L6-v2":
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    if embedding_model == "openai":
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            logger.warning("OpenAI API key not set, falling back to all-MiniLM-L6-v2")
            return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-ada-002"
        )
    
    # Default to SentenceTransformer
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

def get_collection_count(name: str) -> int:
    """
    Get the number of items in a collection
    
    Args:
        name: Collection name
        
    Returns:
        Number of items in collection
    """
    collection = get_collection(name)
    
    if collection:
        return collection.count()
    
    return 0

def create_index(name: str) -> bool:
    """
    Create an index for a collection
    
    Args:
        name: Collection name
        
    Returns:
        True if index was created, False otherwise
    """
    collection = get_collection(name)
    
    if not collection:
        return False
    
    try:
        # Note: ChromaDB automatically creates and maintains indices,
        # so this is just a placeholder for potential future optimizations
        logger.info(f"Index already exists for collection: {name}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating index for collection {name}: {str(e)}")
        return False