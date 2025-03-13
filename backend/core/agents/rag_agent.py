import os
import time
from typing import List, Dict, Any, Optional, Tuple, Union
import asyncio
from datetime import datetime

from backend.db.chromadb_client import get_chroma_client
from backend.utils.cache import get_cache, set_cache
from backend.utils.logging import setup_logger
from backend.config import settings
from backend.models.model_loader import model_loader
from backend.retrieval.rag_pipeline import retrieve_relevant_chunks
from backend.core.context_manager import ConversationContextManager

logger = setup_logger("rag_agent")

class RAGAgent:
    """
    Agent that implements Retrieval Augmented Generation (RAG) for the solar energy domain.
    
    Features:
    - Multi-document context retrieval
    - Relevance scoring and reranking
    - Document chunk optimization
    - Citation and source tracking
    - Enhanced prompt engineering
    - Response validation
    """
    
    def __init__(self):
        self.vector_db_client = get_chroma_client()
        self.collection_name = settings.VECTOR_DB_COLLECTION
        self.max_chunks = settings.MAX_CHUNKS_PER_QUERY
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD
        self.response_cache_ttl = settings.RESPONSE_CACHE_TTL
        
        # Rate limiting
        self.last_query_time = 0
        self.min_query_interval = settings.MIN_QUERY_INTERVAL
    
    async def generate_response(
        self,
        query: str,
        context_manager: ConversationContextManager,
        user_id: str,
        model_name: Optional[str] = None,
        use_cache: bool = True,
        max_new_tokens: int = 512,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Generate a response using the RAG pipeline
        
        Args:
            query: User query
            context_manager: Conversation context manager
            user_id: User ID
            model_name: Name of the model to use
            use_cache: Whether to use cached responses
            max_new_tokens: Maximum number of tokens in response
            temperature: Sampling temperature
            
        Returns:
            Dict containing response text and metadata
        """
        start_time = time.time()
        query_hash = f"{hash(query)}_{user_id}_{model_name}_{max_new_tokens}_{temperature}"
        
        # Check cache if enabled
        if use_cache:
            cache_key = f"rag_response:{query_hash}"
            cached_response = get_cache(cache_key)
            
            if cached_response:
                logger.info(f"Using cached response for query hash: {query_hash}")
                return cached_response
        
        # Apply rate limiting
        current_time = time.time()
        time_since_last_query = current_time - self.last_query_time
        
        if time_since_last_query < self.min_query_interval:
            sleep_time = self.min_query_interval - time_since_last_query
            logger.info(f"Rate limiting: waiting {sleep_time:.2f} seconds before query")
            await asyncio.sleep(sleep_time)
        
        self.last_query_time = time.time()
        
        try:
            # Get conversation context
            conversation_context = context_manager.get_formatted_context()
            
            # Retrieve relevant documents
            retrieval_start_time = time.time()
            retrieval_results = await retrieve_relevant_chunks(
                query,
                self.collection_name,
                max_chunks=self.max_chunks,
                similarity_threshold=self.similarity_threshold
            )
            retrieval_time = time.time() - retrieval_start_time
            
            # Extract chunks and metadata
            chunks = [result["text"] for result in retrieval_results]
            sources = []
            
            for result in retrieval_results:
                metadata = result.get("metadata", {})
                source = metadata.get("source", "Unknown")
                page = metadata.get("page", None)
                
                source_info = {
                    "source": source,
                    "page": page,
                    "similarity": result.get("similarity", 0)
                }
                
                if source_info not in sources:
                    sources.append(source_info)
            
            # Build prompt with context and retrieved information
            prompt = self._build_prompt(query, chunks, conversation_context)
            
            # Generate response
            generation_start_time = time.time()
            response = model_loader.generate_response(
                prompt,
                model_name=model_name,
                max_length=max_new_tokens,
                temperature=temperature
            )
            generation_time = time.time() - generation_start_time
            
            # Extract citations
            response_with_citations = self._format_response_with_citations(response, sources)
            
            # Prepare final response
            final_response = {
                "query": query,
                "response": response_with_citations,
                "sources": sources,
                "metadata": {
                    "retrieval_time": retrieval_time,
                    "generation_time": generation_time,
                    "total_time": time.time() - start_time,
                    "chunk_count": len(chunks),
                    "model": model_name or settings.DEFAULT_MODEL_NAME
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Cache response if enabled
            if use_cache:
                cache_key = f"rag_response:{query_hash}"
                set_cache(cache_key, final_response, expiry=self.response_cache_ttl)
            
            # Log query for analytics
            self._log_query(query, user_id, final_response["metadata"])
            
            return final_response
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            
            return {
                "query": query,
                "response": "I'm sorry, I encountered an error while processing your request. Please try again.",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _build_prompt(
        self,
        query: str,
        chunks: List[str],
        conversation_context: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Build a prompt for the LLM using the query, retrieved chunks, and conversation context
        
        Args:
            query: User query
            chunks: Retrieved document chunks
            conversation_context: Conversation context
            
        Returns:
            Formatted prompt for the LLM
        """
        # Start with conversation context
        prompt = conversation_context.copy()
        
        # Add system context about retrieved information
        context_str = "I've retrieved the following information that might help answer the query:\n\n"
        
        # Add retrieved chunks
        for i, chunk in enumerate(chunks, 1):
            context_str += f"[CHUNK {i}]:\n{chunk}\n\n"
        
        # Add instructions for the model
        context_str += (
            "Based on the above information and your knowledge, please provide a detailed "
            "and accurate response to the user's query. If the information doesn't fully "
            "answer the query, be honest about limitations. Include specific details from "
            "the retrieved information where relevant.\n\n"
            "When referring to specific information from the chunks, use 'According to the "
            "provided information' or similar phrases. For contradictions between chunks, "
            "acknowledge these differences."
        )
        
        # Add system message with context
        prompt.append({
            "role": "system",
            "content": context_str
        })
        
        # Add user query if not already in conversation context
        if not any(msg.get("role") == "user" and msg.get("content") == query for msg in prompt):
            prompt.append({
                "role": "user",
                "content": query
            })
        
        return prompt
    
    def _format_response_with_citations(
        self,
        response: str,
        sources: List[Dict[str, Any]]
    ) -> str:
        """
        Format the response with citations
        
        Args:
            response: Generated response
            sources: List of sources
            
        Returns:
            Response with formatted citations
        """
        if not sources:
            return response
        
        # Add citation section
        response += "\n\n**Sources:**\n"
        
        for i, source in enumerate(sources, 1):
            source_name = os.path.basename(source["source"]) if source["source"] != "Unknown" else "Unknown"
            page_info = f" (page {source['page']})" if source.get("page") is not None else ""
            
            response += f"{i}. {source_name}{page_info}\n"
        
        return response
    
    def _log_query(
        self,
        query: str,
        user_id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Log a query for analytics
        
        Args:
            query: User query
            user_id: User ID
            metadata: Query metadata
        """
        try:
            # In a production system, this would log to a database or analytics service
            logger.info(f"Query: {query}, User: {user_id}, Metadata: {metadata}")
        except Exception as e:
            logger.error(f"Error logging query: {str(e)}")
    
    async def feedback_response(
        self,
        query: str,
        response: str,
        user_id: str,
        feedback: str,
        rating: Optional[int] = None,
        conversation_id: Optional[str] = None
    ) -> None:
        """
        Process user feedback on a response
        
        Args:
            query: Original user query
            response: Generated response
            user_id: User ID
            feedback: User feedback text
            rating: Optional rating (1-5)
            conversation_id: Optional conversation ID
        """
        try:
            # In a production system, this would store feedback in a database
            feedback_data = {
                "query": query,
                "response": response,
                "user_id": user_id,
                "feedback": feedback,
                "rating": rating,
                "conversation_id": conversation_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Received feedback: {feedback_data}")
            
        except Exception as e:
            logger.error(f"Error processing feedback: {str(e)}")

# Singleton instance
rag_agent = RAGAgent()