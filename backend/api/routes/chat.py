from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from pydantic import BaseModel

from backend.models.chat import Message, Conversation, ChatRequest, ChatResponse
from backend.core.agents.rag_agent import rag_agent
from backend.core.agents.web_agent import web_search_agent
from backend.core.agents.viz_agent import viz_agent
from backend.core.context_manager import ConversationContextManager
from backend.core.suggestions import SuggestionEngine
from backend.utils.session import session_manager
from backend.utils.analytics import analytics_service
from backend.utils.logging import setup_logger, PerformanceMonitor
from backend.utils.cache import get_cache, set_cache

logger = setup_logger("chat_routes")
suggestion_engine = SuggestionEngine()

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)

class FeedbackRequest(BaseModel):
    """Feedback request schema"""
    query: str
    response: str
    conversation_id: str
    feedback: str
    rating: Optional[int] = None

class ConversationRequest(BaseModel):
    """Conversation creation request schema"""
    title: Optional[str] = "New Conversation"

class SuggestionRequest(BaseModel):
    """Suggestion request schema"""
    conversation_id: Optional[str] = None
    category: Optional[str] = "general"
    count: Optional[int] = 4

@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Process a chat query and generate a response
    """
    try:
        user_id = current_user["_id"]
        
        # Create or get conversation context
        conversation_id = request.conversation_id
        context_manager = ConversationContextManager(
            user_id, 
            conversation_id=conversation_id
        )
        
        # Track query (async in background)
        background_tasks.add_task(
            analytics_service.track_query,
            request.query,
            "",  # Response will be added later
            user_id
        )
        
        # Log query for suggestions
        suggestion_engine.log_query(request.query, user_id)
        
        # Create performance monitor
        with PerformanceMonitor("chat_query") as monitor:
            # Add user query to context
            user_message = Message(
                role="user",
                content=request.query,
                metadata={"ip": req.client.host}
            )
            context_manager.add_message(user_message)
            
            # Generate response based on the selected agent
            if request.web_search and request.query.strip().endswith("?"):
                # Use web search for questions
                search_results = await web_search_agent.search_and_summarize(
                    request.query,
                    max_results=3,
                    use_cache=True
                )
                
                response_text = search_results["summary"]
                sources = search_results.get("results", [])
                
                # Add source information
                if sources:
                    response_text += "\n\n**Sources:**\n"
                    for i, source in enumerate(sources[:3], 1):
                        response_text += f"{i}. [{source['title']}]({source['link']})\n"
                
                metadata = {
                    "agent": "web_search",
                    "sources": sources,
                    "web_search": True
                }
                
            else:
                # Use RAG agent for normal queries
                rag_response = await rag_agent.generate_response(
                    request.query,
                    context_manager,
                    user_id,
                    model_name=request.model,
                    use_cache=not request.no_cache,
                    max_new_tokens=request.max_tokens,
                    temperature=request.temperature
                )
                
                response_text = rag_response["response"]
                metadata = {
                    "agent": "rag",
                    "sources": rag_response.get("sources", []),
                    "retrieval_time": rag_response.get("metadata", {}).get("retrieval_time"),
                    "generation_time": rag_response.get("metadata", {}).get("generation_time")
                }
            
            # Add assistant response to context
            assistant_message = Message(
                role="assistant",
                content=response_text,
                metadata=metadata
            )
            context_manager.add_message(assistant_message)
            
            # Get follow-up suggestions
            follow_ups = suggestion_engine.generate_follow_up_questions(
                context_manager.get_formatted_context(),
                count=3
            )
            
            # Update conversation title if it's a new conversation
            if not request.conversation_id and context_manager.conversation_id:
                # Use first query as title (truncated)
                title = request.query[:50] + ("..." if len(request.query) > 50 else "")
                context_manager.update_conversation_title(title)
            
            # Update performance metadata
            metadata["processing_time"] = monitor.stop()
            
            # Update the tracked query with the response (async)
            background_tasks.add_task(
                analytics_service.track_query,
                request.query,
                response_text,
                user_id,
                metadata
            )
            
            # Create response
            response = ChatResponse(
                conversation_id=context_manager.conversation_id,
                message=assistant_message,
                suggestions=follow_ups
            )
            
            return response
            
    except Exception as e:
        logger.error(f"Error processing chat query: {str(e)}")
        # Track error
        background_tasks.add_task(
            analytics_service.track_error,
            str(e),
            {"query": request.query, "conversation_id": request.conversation_id},
            user_id if 'user_id' in locals() else None
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}"
        )

@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(
    feedback: FeedbackRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Submit feedback for a conversation
    """
    try:
        user_id = current_user["_id"]
        
        # Process feedback in the background
        background_tasks.add_task(
            rag_agent.feedback_response,
            feedback.query,
            feedback.response,
            user_id,
            feedback.feedback,
            feedback.rating,
            feedback.conversation_id
        )
        
        # Track feedback event
        background_tasks.add_task(
            analytics_service.track_event,
            "feedback",
            {
                "query": feedback.query,
                "feedback": feedback.feedback,
                "rating": feedback.rating,
                "conversation_id": feedback.conversation_id
            },
            user_id
        )
        
        return {"status": "Feedback received"}
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting feedback: {str(e)}"
        )

@router.post("/conversations", response_model=Conversation)
async def create_conversation(
    request: ConversationRequest,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Create a new conversation
    """
    try:
        user_id = current_user["_id"]
        
        # Create conversation context
        context_manager = ConversationContextManager(user_id)
        
        # Update conversation title
        context_manager.update_conversation_title(request.title)
        
        # Get conversation summary
        conversation = context_manager.get_conversation_summary()
        
        return conversation
        
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating conversation: {str(e)}"
        )

@router.get("/conversations", response_model=List[Conversation])
async def get_conversations(
    current_user = Depends(session_manager.get_current_user),
    limit: int = 10,
    skip: int = 0
):
    """
    Get user conversations
    """
    try:
        user_id = current_user["_id"]
        
        # Get conversations from database
        db = session_manager.db
        conversations = list(db["conversations"].find(
            {"user_id": user_id},
            {"messages": 0}  # Exclude messages for performance
        ).sort("updated_at", -1).skip(skip).limit(limit))
        
        # Format conversations
        result = []
        for conv in conversations:
            # Convert ObjectId to string
            conv["id"] = str(conv.pop("_id"))
            result.append(conv)
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting conversations: {str(e)}"
        )

@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Get a conversation by ID
    """
    try:
        user_id = current_user["_id"]
        
        # Get conversation from database
        db = session_manager.db
        conversation = db["conversations"].find_one({
            "_id": conversation_id,
            "user_id": user_id
        })
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Convert ObjectId to string
        conversation["id"] = str(conversation.pop("_id"))
        
        return conversation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting conversation: {str(e)}"
        )

@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Delete a conversation
    """
    try:
        user_id = current_user["_id"]
        
        # Delete conversation from database
        db = session_manager.db
        result = db["conversations"].delete_one({
            "_id": conversation_id,
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting conversation: {str(e)}"
        )

@router.get("/suggestions", response_model=List[str])
async def get_suggestions(
    request: SuggestionRequest = SuggestionRequest(),
    current_user = Depends(session_manager.get_current_user)
):
    """
    Get query suggestions
    """
    try:
        user_id = current_user["_id"]
        
        # Get conversation context if conversation_id is provided
        context = None
        if request.conversation_id:
            context_manager = ConversationContextManager(
                user_id, 
                conversation_id=request.conversation_id
            )
            context = context_manager.get_formatted_context()
        
        # Get suggestions
        suggestions = suggestion_engine.get_suggestions(
            user_id=user_id,
            current_context=context,
            category=request.category,
            count=request.count
        )
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Error getting suggestions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting suggestions: {str(e)}"
        )