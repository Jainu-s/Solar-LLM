from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field

class Message(BaseModel):
    """Chat message model"""
    role: str = Field(..., description="Role of the message sender (user, assistant, system)")
    content: str = Field(..., description="Message content")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Optional message metadata")

class Conversation(BaseModel):
    """Conversation model"""
    id: str = Field(..., description="Conversation ID")
    user_id: str = Field(..., description="User ID")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    messages: Optional[List[Message]] = Field(default=[], description="List of messages in the conversation")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Optional conversation metadata")

class ConversationSummary(BaseModel):
    """Conversation summary model"""
    id: str = Field(..., description="Conversation ID")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    message_count: int = Field(..., description="Number of messages")
    summary: Optional[str] = Field(default=None, description="Conversation summary")
    last_message: Optional[str] = Field(default=None, description="Last message preview")

class ChatRequest(BaseModel):
    """Chat request model"""
    query: str = Field(..., description="User query")
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID (optional)")
    model: Optional[str] = Field(default=None, description="Model to use for generation")
    max_tokens: Optional[int] = Field(default=512, description="Maximum number of tokens to generate")
    temperature: Optional[float] = Field(default=0.7, description="Sampling temperature")
    web_search: Optional[bool] = Field(default=False, description="Whether to include web search results")
    no_cache: Optional[bool] = Field(default=False, description="Whether to skip caching")
    streaming: Optional[bool] = Field(default=False, description="Whether to stream the response")

class ChatResponse(BaseModel):
    """Chat response model"""
    conversation_id: str = Field(..., description="Conversation ID")
    message: Message = Field(..., description="Assistant response message")
    suggestions: Optional[List[str]] = Field(default=[], description="Suggested follow-up queries")

class StreamChatResponse(BaseModel):
    """Streaming chat response model"""
    conversation_id: str = Field(..., description="Conversation ID")
    content: str = Field(..., description="Message content chunk")
    done: bool = Field(..., description="Whether this is the last chunk")
    suggestions: Optional[List[str]] = Field(default=None, description="Suggested follow-up queries (only in last chunk)")

class FeedbackRequest(BaseModel):
    """Feedback request model"""
    query: str = Field(..., description="Original query")
    response: str = Field(..., description="Assistant response")
    conversation_id: str = Field(..., description="Conversation ID")
    feedback: str = Field(..., description="Feedback text")
    rating: Optional[int] = Field(default=None, description="Rating (1-5)")

class ConversationRequest(BaseModel):
    """Conversation creation request model"""
    title: Optional[str] = Field(default="New Conversation", description="Conversation title")

class SuggestionRequest(BaseModel):
    """Suggestion request model"""
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID")
    category: Optional[str] = Field(default="general", description="Suggestion category")
    count: Optional[int] = Field(default=4, description="Number of suggestions to return")