import os
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from datetime import datetime

from backend.db.chromadb_client import get_chroma_client
from backend.utils.cache import get_cache, set_cache
from backend.utils.logging import setup_logger
from backend.config import settings
from backend.models.model_loader import model_loader

logger = setup_logger("rag_pipeline")

async def retrieve_relevant_chunks(
    query: str,
    collection_name: str,
    max_chunks: int = 5,
    similarity_threshold: float = 0.7,
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant document chunks based on the query
    
    Args:
        query: User query
        collection_name: Name of the vector database collection
        max_chunks: Maximum number of chunks to retrieve
        similarity_threshold: Minimum similarity score for chunks
        use_cache: Whether to use cached results
        
    Returns:
        List of relevant chunks with metadata
    """
    start_time = time.time()
    
    # Check cache if enabled
    if use_cache:
        cache_key = f"query_chunks:{query}:{collection_name}:{max_chunks}:{similarity_threshold}"
        cached_results = get_cache(cache_key)
        
        if cached_results:
            logger.info(f"Using cached chunks for query: {query}")
            return cached_results
    
    try:
        # Get embeddings model
        model_dict = model_loader.get_embedding_model()
        embedding_function = model_dict["model"].encode
        
        # Get vector database client
        chroma_client = get_chroma_client()
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Generate query embedding
        query_embedding = embedding_function([query])[0].tolist()
        
        # Retrieve chunks using vector similarity search
        # This is a two-stage retrieval process:
        # 1. First, retrieve more chunks than needed (2x) to ensure good coverage
        # 2. Then, re-rank them using a more sophisticated approach
        initial_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=max_chunks * 2,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format initial results
        chunks = []
        if (
            initial_results 
            and "documents" in initial_results 
            and len(initial_results["documents"]) > 0
        ):
            documents = initial_results["documents"][0]
            metadatas = initial_results["metadatas"][0]
            distances = initial_results["distances"][0]
            
            # Normalize distances to similarity scores (1 is most similar)
            # ChromaDB returns L2 distances, so we need to convert
            max_distance = max(distances) if distances else 1
            similarities = [1 - (dist / max_distance) for dist in distances]
            
            # Combine results
            for i, (doc, meta, sim) in enumerate(zip(documents, metadatas, similarities)):
                if sim >= similarity_threshold:
                    chunks.append({
                        "text": doc,
                        "metadata": meta,
                        "similarity": sim,
                        "rank": i + 1
                    })
        
        # If we didn't get any results or not enough results, try semantic search
        if len(chunks) < max_chunks:
            logger.info(f"Not enough chunks from vector search, trying semantic search")
            semantic_results = await semantic_search(query, collection_name, max_chunks)
            
            # Add semantic results if they're not already in chunks
            existing_texts = {chunk["text"] for chunk in chunks}
            for result in semantic_results:
                if result["text"] not in existing_texts:
                    chunks.append(result)
                    existing_texts.add(result["text"])
        
        # Re-rank chunks using more sophisticated approach
        ranked_chunks = await rerank_chunks(query, chunks, max_chunks)
        
        # Cache results
        if use_cache and ranked_chunks:
            cache_key = f"query_chunks:{query}:{collection_name}:{max_chunks}:{similarity_threshold}"
            set_cache(cache_key, ranked_chunks, expiry=300)  # 5 minutes
        
        logger.info(f"Retrieved {len(ranked_chunks)} chunks in {time.time() - start_time:.2f}s")
        return ranked_chunks
        
    except Exception as e:
        logger.error(f"Error retrieving chunks: {str(e)}")
        return []

async def semantic_search(
    query: str,
    collection_name: str,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Perform a semantic search on document chunks
    
    Args:
        query: User query
        collection_name: Name of the vector database collection
        max_results: Maximum number of results to return
        
    Returns:
        List of relevant chunks with metadata
    """
    try:
        # Get vector database client
        chroma_client = get_chroma_client()
        collection = chroma_client.get_collection(name=collection_name)
        
        # Get total documents to search
        collection_count = collection.count()
        if collection_count == 0:
            return []
        
        # For smaller collections, get all documents
        if collection_count <= 1000:
            all_results = collection.get(
                include=["documents", "metadatas"]
            )
            
            documents = all_results["documents"]
            metadatas = all_results["metadatas"]
            
            # Simple keyword matching for now
            # In a production system, this would use a more sophisticated approach
            query_keywords = set(query.lower().split())
            scored_results = []
            
            for i, (doc, meta) in enumerate(zip(documents, metadatas)):
                doc_text = doc.lower()
                keyword_hits = sum(1 for kw in query_keywords if kw in doc_text)
                similarity = keyword_hits / len(query_keywords) if query_keywords else 0
                
                if similarity > 0:
                    scored_results.append({
                        "text": doc,
                        "metadata": meta,
                        "similarity": similarity,
                        "rank": len(scored_results) + 1
                    })
            
            # Sort by similarity (highest first)
            scored_results.sort(key=lambda x: x["similarity"], reverse=True)
            
            return scored_results[:max_results]
            
        else:
            # For larger collections, we need a more efficient approach
            # This would typically involve a text search index
            # For now, we'll return an empty list
            logger.warning(f"Collection too large for semantic search: {collection_count} documents")
            return []
            
    except Exception as e:
        logger.error(f"Error in semantic search: {str(e)}")
        return []

async def rerank_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    max_chunks: int = 5
) -> List[Dict[str, Any]]:
    """
    Re-rank chunks based on query relevance
    
    Args:
        query: User query
        chunks: List of chunks to re-rank
        max_chunks: Maximum number of chunks to return
        
    Returns:
        Re-ranked list of chunks
    """
    if not chunks:
        return []
    
    try:
        # In a production system, this would use a trained reranker model
        # For simplicity, we'll use a combination of:
        # 1. Original similarity score
        # 2. Keyword matching
        # 3. Chunk length (prefer slightly longer chunks)
        
        query_keywords = set(query.lower().split())
        
        for chunk in chunks:
            text = chunk["text"].lower()
            
            # Calculate keyword score
            keyword_hits = sum(1 for kw in query_keywords if kw in text)
            keyword_score = keyword_hits / len(query_keywords) if query_keywords else 0
            
            # Calculate length score (normalize between 0-1, prefer medium length)
            text_length = len(text)
            length_score = min(text_length / 1000, 1.0) if text_length < 1000 else (2000 - text_length) / 1000 if text_length < 2000 else 0
            
            # Combine scores (with weights)
            original_score = chunk["similarity"]
            combined_score = (original_score * 0.6) + (keyword_score * 0.3) + (length_score * 0.1)
            
            # Update chunk with new score
            chunk["rerank_score"] = combined_score
        
        # Sort by combined score (highest first)
        chunks.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        
        # Take top chunks
        return chunks[:max_chunks]
        
    except Exception as e:
        logger.error(f"Error re-ranking chunks: {str(e)}")
        return chunks[:max_chunks]  # Fall back to original ordering

async def preprocess_query(query: str) -> str:
    """
    Preprocess the query to improve retrieval
    
    Args:
        query: Original user query
        
    Returns:
        Preprocessed query
    """
    # Expand acronyms and abbreviations
    expansions = {
        "roi": "return on investment",
        "pv": "photovoltaic",
        "solar pv": "solar photovoltaic",
        "kwh": "kilowatt hour",
        "kw": "kilowatt",
        "mw": "megawatt",
        "ac": "alternating current",
        "dc": "direct current"
    }
    
    # Case-insensitive replacement
    processed_query = query.lower()
    
    for abbr, expansion in expansions.items():
        # Only replace whole words
        processed_query = processed_query.replace(f" {abbr} ", f" {expansion} ")
        # Check start of string
        if processed_query.startswith(f"{abbr} "):
            processed_query = f"{expansion} " + processed_query[len(abbr)+1:]
        # Check end of string
        if processed_query.endswith(f" {abbr}"):
            processed_query = processed_query[:-len(abbr)-1] + f" {expansion}"
    
    # If the query is very short, try to expand it
    if len(processed_query.split()) <= 3:
        # In a production system, this would use an LLM to expand the query
        # For simplicity, we'll just add some solar-related terms
        if "cost" in processed_query or "price" in processed_query:
            processed_query += " solar panel system cost pricing installation"
        elif "efficiency" in processed_query:
            processed_query += " solar panel efficiency performance output"
        elif "install" in processed_query:
            processed_query += " solar panel installation process requirements"
    
    return processed_query

async def process_query_for_retrieval(
    query: str,
    user_context: Optional[Dict[str, Any]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Process a query for optimal retrieval, considering user context
    
    Args:
        query: Original user query
        user_context: Optional user context information
        
    Returns:
        Processed query and retrieval parameters
    """
    # Default retrieval parameters
    params = {
        "max_chunks": settings.MAX_CHUNKS_PER_QUERY,
        "similarity_threshold": settings.SIMILARITY_THRESHOLD
    }
    
    # Preprocess the query
    processed_query = await preprocess_query(query)
    
    # Adjust parameters based on query characteristics
    query_length = len(query.split())
    
    if query_length > 15:
        # Complex query, increase chunks
        params["max_chunks"] = min(params["max_chunks"] + 2, 10)
        
    elif query_length < 5:
        # Simple query, slightly lower threshold to get more diverse results
        params["similarity_threshold"] = max(params["similarity_threshold"] - 0.05, 0.6)
    
    # If user context is provided, consider it
    if user_context:
        expertise_level = user_context.get("expertise_level", "beginner")
        
        if expertise_level == "expert":
            # Experts likely want more detailed information
            params["max_chunks"] = min(params["max_chunks"] + 1, 10)
        elif expertise_level == "beginner":
            # Beginners benefit from clearer, focused information
            params["max_chunks"] = max(params["max_chunks"] - 1, 3)
    
    return processed_query, params

async def optimize_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Optimize retrieved chunks for better response generation
    
    Args:
        chunks: Original chunks
        
    Returns:
        Optimized chunks
    """
    if not chunks:
        return []
    
    # Remove duplicate content
    unique_chunks = []
    seen_content = set()
    
    for chunk in chunks:
        # Create a content signature (simplified for demonstration)
        content = chunk["text"]
        content_sig = " ".join(content.lower().split()[:50])
        
        if content_sig not in seen_content:
            seen_content.add(content_sig)
            unique_chunks.append(chunk)
    
    # Sort by original rank
    unique_chunks.sort(key=lambda x: x.get("rank", float("inf")))
    
    # Merge very short, consecutive chunks from the same source
    merged_chunks = []
    current_chunk = None
    
    for chunk in unique_chunks:
        if current_chunk is None:
            current_chunk = chunk.copy()
        elif (
            len(current_chunk["text"]) < 300 
            and chunk.get("metadata", {}).get("source") == current_chunk.get("metadata", {}).get("source")
        ):
            # Merge with previous chunk
            current_chunk["text"] += "\n\n" + chunk["text"]
            # Keep the higher similarity score
            current_chunk["similarity"] = max(
                current_chunk.get("similarity", 0),
                chunk.get("similarity", 0)
            )
        else:
            merged_chunks.append(current_chunk)
            current_chunk = chunk.copy()
    
    if current_chunk:
        merged_chunks.append(current_chunk)
    
    return merged_chunks