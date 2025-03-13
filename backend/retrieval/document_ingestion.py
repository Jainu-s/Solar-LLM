import os
import time
import asyncio
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from datetime import datetime
import traceback

import aiofiles
from tqdm import tqdm
import numpy as np

from backend.db.chromadb_client import get_chroma_client
from backend.db.mongodb import get_database
from backend.retrieval.pdf_processor import extract_text_from_pdf, split_text_into_chunks
from backend.utils.logging import setup_logger
from backend.utils.cache import get_cache, set_cache, invalidate_cache_prefix
from backend.config import settings
from backend.models.model_loader import model_loader

logger = setup_logger("document_ingestion")

class DocumentIngestionManager:
    """
    Manages the ingestion process for documents into the vector database
    
    Features:
    - Optimized document chunking
    - Multi-format support (PDF, TXT, DOCX)
    - Metadata extraction and storage
    - Duplicate detection
    - Progress tracking
    - Error handling and recovery
    """
    
    def __init__(self):
        self.chroma_client = get_chroma_client()
        self.mongodb = get_database()
        self.collection_name = settings.VECTOR_DB_COLLECTION
        self.documents_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "documents")
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        
        # Create documents directory if it doesn't exist
        os.makedirs(self.documents_dir, exist_ok=True)
        
        # Create a collection to store document metadata
        self.doc_collection = self.mongodb["documents"]
        
        # Initialize vector database collection
        self._initialize_collection()
    
    def _initialize_collection(self) -> None:
        """Initialize the vector database collection"""
        try:
            # Check if collection exists
            collections = self.chroma_client.list_collections()
            
            if self.collection_name not in [c.name for c in collections]:
                logger.info(f"Creating collection: {self.collection_name}")
                self.chroma_client.create_collection(name=self.collection_name)
            
            # Ensure index on document collection
            self.doc_collection.create_index("file_path", unique=True)
            self.doc_collection.create_index("ingestion_time")
            self.doc_collection.create_index("status")
            
        except Exception as e:
            logger.error(f"Error initializing collection: {str(e)}")
            raise
    
    async def ingest_document(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        force_reindex: bool = False
    ) -> Dict[str, Any]:
        """
        Ingest a document into the vector database
        
        Args:
            file_path: Path to the document file
            metadata: Additional metadata for the document
            force_reindex: Whether to force reindexing if document already exists
            
        Returns:
            Dictionary with ingestion results
        """
        start_time = time.time()
        metadata = metadata or {}
        
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Check file format
            file_ext = os.path.splitext(file_path)[1].lower()
            supported_extensions = {".pdf", ".txt", ".docx"}
            
            if file_ext not in supported_extensions:
                raise ValueError(f"Unsupported file format: {file_ext}. Supported formats: {supported_extensions}")
            
            # Check if document already exists
            existing_doc = self.doc_collection.find_one({"file_path": file_path})
            
            if existing_doc and existing_doc.get("status") == "completed" and not force_reindex:
                logger.info(f"Document already indexed: {file_path}")
                return {
                    "file_path": file_path,
                    "status": "exists",
                    "document_id": existing_doc.get("document_id"),
                    "message": "Document already indexed"
                }
            
            # Generate document ID
            document_id = str(uuid.uuid4())
            
            # Update document status in database
            self.doc_collection.update_one(
                {"file_path": file_path},
                {
                    "$set": {
                        "document_id": document_id,
                        "file_path": file_path,
                        "file_name": os.path.basename(file_path),
                        "file_extension": file_ext,
                        "status": "processing",
                        "ingestion_time": datetime.utcnow(),
                        "metadata": metadata
                    }
                },
                upsert=True
            )
            
            # Extract text based on file format
            if file_ext == ".pdf":
                text, page_map = await extract_text_from_pdf(file_path)
            elif file_ext == ".txt":
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    text = await f.read()
                page_map = None
            elif file_ext == ".docx":
                # For simplicity, we'll just use basic text extraction for DOCX
                # In a production system, use specialized libraries like python-docx
                from docx import Document
                doc = Document(file_path)
                text = "\n\n".join([para.text for para in doc.paragraphs])
                page_map = None
            
            # Split text into chunks
            chunks = await self._create_optimized_chunks(text, page_map)
            
            if not chunks:
                logger.warning(f"No chunks created from document: {file_path}")
                self.doc_collection.update_one(
                    {"file_path": file_path},
                    {"$set": {"status": "error", "error": "No text extracted from document"}}
                )
                return {
                    "file_path": file_path,
                    "status": "error",
                    "message": "No text extracted from document"
                }
            
            # Generate embeddings and store in vector database
            result = await self._index_chunks(chunks, document_id, file_path, metadata)
            
            # Update document status
            self.doc_collection.update_one(
                {"file_path": file_path},
                {
                    "$set": {
                        "status": "completed",
                        "chunks_count": len(chunks),
                        "completion_time": datetime.utcnow(),
                        "processing_time": time.time() - start_time
                    }
                }
            )
            
            # Invalidate related caches
            invalidate_cache_prefix("query_chunks:")
            
            return {
                "file_path": file_path,
                "document_id": document_id,
                "status": "completed",
                "chunks_count": len(chunks),
                "processing_time": time.time() - start_time
            }
            
        except Exception as e:
            logger.error(f"Error ingesting document {file_path}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Update document status
            self.doc_collection.update_one(
                {"file_path": file_path},
                {"$set": {"status": "error", "error": str(e)}}
            )
            
            return {
                "file_path": file_path,
                "status": "error",
                "error": str(e)
            }
    
    async def _create_optimized_chunks(
        self,
        text: str,
        page_map: Optional[Dict[int, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Create optimized chunks from document text
        
        Args:
            text: Document text
            page_map: Mapping of text positions to page numbers
            
        Returns:
            List of chunk dictionaries
        """
        # Split text into initial chunks
        raw_chunks = split_text_into_chunks(
            text, 
            chunk_size=self.chunk_size, 
            chunk_overlap=self.chunk_overlap
        )
        
        # Process chunks with optimizations
        optimized_chunks = []
        
        for i, chunk_text in enumerate(raw_chunks):
            # Skip empty chunks
            if not chunk_text.strip():
                continue
            
            # Determine page number if page map is available
            page_num = None
            if page_map:
                chunk_start = sum(len(c) for c in raw_chunks[:i])
                if chunk_start in page_map:
                    page_num = page_map[chunk_start]
                else:
                    # Find closest position
                    positions = list(page_map.keys())
                    closest_pos = min(positions, key=lambda x: abs(x - chunk_start))
                    page_num = page_map[closest_pos]
            
            # Create chunk dictionary
            chunk = {
                "text": chunk_text,
                "metadata": {
                    "chunk_id": str(uuid.uuid4()),
                    "chunk_index": i,
                    "page": page_num
                }
            }
            
            optimized_chunks.append(chunk)
        
        # Apply additional optimizations:
        
        # 1. Merge very short chunks with their neighbors
        merged_chunks = []
        skip_next = False
        
        for i in range(len(optimized_chunks)):
            if skip_next:
                skip_next = False
                continue
            
            chunk = optimized_chunks[i]
            
            # If this is a very short chunk and not the last one, try to merge
            if len(chunk["text"]) < 100 and i < len(optimized_chunks) - 1:
                next_chunk = optimized_chunks[i + 1]
                
                # If pages match (or both are None), merge chunks
                if chunk["metadata"]["page"] == next_chunk["metadata"]["page"]:
                    merged_text = chunk["text"] + " " + next_chunk["text"]
                    new_chunk = {
                        "text": merged_text,
                        "metadata": {
                            "chunk_id": chunk["metadata"]["chunk_id"],
                            "chunk_index": chunk["metadata"]["chunk_index"],
                            "page": chunk["metadata"]["page"],
                            "merged": True
                        }
                    }
                    merged_chunks.append(new_chunk)
                    skip_next = True
                else:
                    merged_chunks.append(chunk)
            else:
                merged_chunks.append(chunk)
        
        # 2. Split overly long chunks at logical boundaries
        final_chunks = []
        
        for chunk in merged_chunks:
            if len(chunk["text"]) > self.chunk_size * 1.5:
                # Split at paragraph or sentence boundaries
                paragraphs = chunk["text"].split("\n\n")
                
                if len(paragraphs) > 1:
                    # Split at paragraph boundaries
                    current_text = ""
                    for para in paragraphs:
                        if len(current_text) + len(para) < self.chunk_size:
                            if current_text:
                                current_text += "\n\n" + para
                            else:
                                current_text = para
                        else:
                            # Add current chunk
                            if current_text:
                                final_chunks.append({
                                    "text": current_text,
                                    "metadata": {
                                        "chunk_id": str(uuid.uuid4()),
                                        "chunk_index": len(final_chunks),
                                        "page": chunk["metadata"]["page"],
                                        "parent_chunk_id": chunk["metadata"]["chunk_id"]
                                    }
                                })
                            
                            current_text = para
                    
                    # Add the last chunk
                    if current_text:
                        final_chunks.append({
                            "text": current_text,
                            "metadata": {
                                "chunk_id": str(uuid.uuid4()),
                                "chunk_index": len(final_chunks),
                                "page": chunk["metadata"]["page"],
                                "parent_chunk_id": chunk["metadata"]["chunk_id"]
                            }
                        })
                else:
                    # If no paragraph breaks, split at sentence boundaries
                    sentences = chunk["text"].replace(". ", ".\n").split("\n")
                    
                    current_text = ""
                    for sentence in sentences:
                        if len(current_text) + len(sentence) < self.chunk_size:
                            if current_text:
                                current_text += " " + sentence
                            else:
                                current_text = sentence
                        else:
                            # Add current chunk
                            if current_text:
                                final_chunks.append({
                                    "text": current_text,
                                    "metadata": {
                                        "chunk_id": str(uuid.uuid4()),
                                        "chunk_index": len(final_chunks),
                                        "page": chunk["metadata"]["page"],
                                        "parent_chunk_id": chunk["metadata"]["chunk_id"]
                                    }
                                })
                            
                            current_text = sentence
                    
                    # Add the last chunk
                    if current_text:
                        final_chunks.append({
                            "text": current_text,
                            "metadata": {
                                "chunk_id": str(uuid.uuid4()),
                                "chunk_index": len(final_chunks),
                                "page": chunk["metadata"]["page"],
                                "parent_chunk_id": chunk["metadata"]["chunk_id"]
                            }
                        })
            else:
                final_chunks.append(chunk)
        
        return final_chunks
    
    async def _index_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_id: str,
        file_path: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Index chunks in the vector database
        
        Args:
            chunks: List of chunk dictionaries
            document_id: Document ID
            file_path: Path to the document file
            metadata: Additional metadata
            
        Returns:
            Dictionary with indexing results
        """
        try:
            # Get embedding model
            model_dict = model_loader.get_embedding_model()
            embedding_function = model_dict["model"].encode
            
            # Get or create collection
            collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=embedding_function
            )
            
            # Prepare data for batch insertion
            ids = []
            texts = []
            metadatas = []
            
            for chunk in chunks:
                chunk_id = chunk["metadata"]["chunk_id"]
                ids.append(chunk_id)
                texts.append(chunk["text"])
                
                # Create metadata
                chunk_metadata = {
                    "document_id": document_id,
                    "source": file_path,
                    "page": chunk["metadata"].get("page"),
                    "chunk_index": chunk["metadata"]["chunk_index"]
                }
                
                # Add any additional metadata
                chunk_metadata.update(metadata)
                
                metadatas.append(chunk_metadata)
            
            # Add documents to collection
            collection.add(
                ids=ids,
                documents=texts,
                metadatas=metadatas
            )
            
            return {
                "indexed_chunks": len(chunks),
                "document_id": document_id
            }
            
        except Exception as e:
            logger.error(f"Error indexing chunks: {str(e)}")
            raise
    
    async def ingest_directory(
        self,
        directory_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        force_reindex: bool = False,
        file_extensions: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Ingest all documents in a directory
        
        Args:
            directory_path: Path to the directory
            metadata: Additional metadata for all documents
            force_reindex: Whether to force reindexing
            file_extensions: Set of file extensions to include
            
        Returns:
            Dictionary with ingestion results
        """
        start_time = time.time()
        metadata = metadata or {}
        file_extensions = file_extensions or {".pdf", ".txt", ".docx"}
        
        try:
            # Check if directory exists
            if not os.path.isdir(directory_path):
                raise NotADirectoryError(f"Directory not found: {directory_path}")
            
            # Get all files with supported extensions
            files = []
            for root, _, filenames in os.walk(directory_path):
                for filename in filenames:
                    if os.path.splitext(filename)[1].lower() in file_extensions:
                        files.append(os.path.join(root, filename))
            
            if not files:
                logger.warning(f"No supported files found in directory: {directory_path}")
                return {
                    "directory_path": directory_path,
                    "status": "completed",
                    "files_processed": 0,
                    "message": "No supported files found"
                }
            
            # Process files
            results = []
            for file_path in tqdm(files, desc="Processing files"):
                try:
                    # Add base directory to metadata
                    file_metadata = metadata.copy()
                    file_metadata["base_directory"] = directory_path
                    
                    result = await self.ingest_document(
                        file_path,
                        metadata=file_metadata,
                        force_reindex=force_reindex
                    )
                    
                    results.append(result)
                    
                    # Sleep briefly to avoid overloading the system
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {str(e)}")
                    results.append({
                        "file_path": file_path,
                        "status": "error",
                        "error": str(e)
                    })
            
            # Summarize results
            success_count = sum(1 for r in results if r.get("status") in ["completed", "exists"])
            error_count = len(results) - success_count
            
            return {
                "directory_path": directory_path,
                "status": "completed",
                "files_processed": len(results),
                "successful": success_count,
                "errors": error_count,
                "processing_time": time.time() - start_time,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error ingesting directory {directory_path}: {str(e)}")
            return {
                "directory_path": directory_path,
                "status": "error",
                "error": str(e)
            }
    
    async def get_document_status(self, document_id: str) -> Dict[str, Any]:
        """
        Get the status of a document
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with document status
        """
        try:
            doc = self.doc_collection.find_one({"document_id": document_id})
            
            if not doc:
                return {
                    "document_id": document_id,
                    "status": "not_found",
                    "message": "Document not found"
                }
            
            return {
                "document_id": document_id,
                "file_path": doc.get("file_path"),
                "file_name": doc.get("file_name"),
                "status": doc.get("status"),
                "ingestion_time": doc.get("ingestion_time"),
                "completion_time": doc.get("completion_time"),
                "chunks_count": doc.get("chunks_count"),
                "error": doc.get("error")
            }
            
        except Exception as e:
            logger.error(f"Error getting document status: {str(e)}")
            return {
                "document_id": document_id,
                "status": "error",
                "error": str(e)
            }
    
    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        Delete a document from the vector database
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with deletion result
        """
        try:
            # Get document from database
            doc = self.doc_collection.find_one({"document_id": document_id})
            
            if not doc:
                return {
                    "document_id": document_id,
                    "status": "not_found",
                    "message": "Document not found"
                }
            
            # Get collection
            collection = self.chroma_client.get_collection(name=self.collection_name)
            
            # Get all chunks for this document
            result = collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas", "embeddings"]
            )
            
            if not result or not result["ids"]:
                logger.warning(f"No chunks found for document: {document_id}")
            else:
                # Delete chunks from collection
                collection.delete(ids=result["ids"])
            
            # Delete document from database
            self.doc_collection.delete_one({"document_id": document_id})
            
            # Invalidate related caches
            invalidate_cache_prefix("query_chunks:")
            
            return {
                "document_id": document_id,
                "status": "deleted",
                "chunks_deleted": len(result["ids"]) if result and "ids" in result else 0
            }
            
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return {
                "document_id": document_id,
                "status": "error",
                "error": str(e)
            }
    
    async def get_all_documents(self) -> List[Dict[str, Any]]:
        """
        Get all documents in the system
        
        Returns:
            List of document dictionaries
        """
        try:
            docs = list(self.doc_collection.find(
                {}, 
                {
                    "_id": 0,
                    "document_id": 1,
                    "file_path": 1,
                    "file_name": 1,
                    "status": 1,
                    "ingestion_time": 1,
                    "completion_time": 1,
                    "chunks_count": 1,
                    "metadata": 1
                }
            ))
            
            return docs
            
        except Exception as e:
            logger.error(f"Error getting all documents: {str(e)}")
            return []
    
    async def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a document
        
        Args:
            document_id: Document ID
            
        Returns:
            List of chunk dictionaries
        """
        try:
            # Get collection
            collection = self.chroma_client.get_collection(name=self.collection_name)
            
            # Get all chunks for this document
            result = collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"]
            )
            
            if not result or not result["ids"]:
                return []
            
            # Format chunks
            chunks = []
            
            for i, chunk_id in enumerate(result["ids"]):
                chunks.append({
                    "chunk_id": chunk_id,
                    "text": result["documents"][i],
                    "metadata": result["metadatas"][i]
                })
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error getting document chunks: {str(e)}")
            return []

# Create singleton instance
document_ingestion_manager = DocumentIngestionManager()