import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from backend.db.mongodb import get_database
from backend.schemas.chat import Message, Conversation
from backend.utils.cache import get_cache, set_cache
from backend.utils.logging import setup_logger

logger = setup_logger("context_manager")

class ConversationContextManager:
    """
    Manages conversation context across multiple turns, including:
    - Message history tracking
    - Context window management
    - Conversation persistence
    - Context summarization for long conversations
    """

    def __init__(
        self, 
        user_id: str, 
        conversation_id: Optional[str] = None,
        max_context_length: int = 10,
        context_window_size: int = 4096
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.max_context_length = max_context_length
        self.context_window_size = context_window_size
        self.db = get_database()
        self.conversation_collection = self.db["conversations"]
        self.messages: List[Dict[str, Any]] = []
        
        # Initialize conversation or load existing
        if conversation_id:
            self._load_conversation()
        else:
            self._create_conversation()
    
    def _create_conversation(self):
        """Create a new conversation"""
        conversation = {
            "user_id": self.user_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "title": "New Conversation",
            "messages": [],
            "summary": "",
            "metadata": {
                "total_tokens": 0,
                "topics": [],
                "sources": []
            }
        }
        
        result = self.conversation_collection.insert_one(conversation)
        self.conversation_id = str(result.inserted_id)
        logger.info(f"Created new conversation with ID: {self.conversation_id}")
    
    def _load_conversation(self):
        """Load an existing conversation from database or cache"""
        # Try to get from cache first
        cache_key = f"conversation:{self.conversation_id}"
        cached_conversation = get_cache(cache_key)
        
        if cached_conversation:
            self.messages = cached_conversation.get("messages", [])
            logger.info(f"Loaded conversation {self.conversation_id} from cache")
            return
            
        # If not in cache, load from database
        conversation = self.conversation_collection.find_one({"_id": self.conversation_id})
        if conversation:
            self.messages = conversation.get("messages", [])
            # Update cache for faster retrieval next time
            set_cache(cache_key, {"messages": self.messages}, expiry=3600)
            logger.info(f"Loaded conversation {self.conversation_id} from database")
        else:
            logger.warning(f"Conversation {self.conversation_id} not found, creating new")
            self._create_conversation()
    
    def add_message(self, message: Message) -> None:
        """
        Add a new message to the conversation context
        """
        message_dict = {
            "role": message.role,
            "content": message.content,
            "timestamp": datetime.utcnow(),
            "metadata": message.metadata
        }
        
        self.messages.append(message_dict)
        
        # Update the conversation in database
        self.conversation_collection.update_one(
            {"_id": self.conversation_id},
            {
                "$push": {"messages": message_dict},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Update cache
        cache_key = f"conversation:{self.conversation_id}"
        set_cache(cache_key, {"messages": self.messages}, expiry=3600)
        
        logger.info(f"Added message to conversation {self.conversation_id}")
        
        # Check if context needs pruning
        if len(self.messages) > self.max_context_length:
            self._prune_context()
    
    def _prune_context(self) -> None:
        """
        Prune the conversation context when it exceeds max length
        This implementation summarizes older messages to maintain conversation flow
        while staying within token limits
        """
        if len(self.messages) <= self.max_context_length:
            return
            
        # For now, simple pruning by keeping most recent messages
        # In a real implementation, we would summarize older messages
        excess_messages = len(self.messages) - self.max_context_length
        summary = self._generate_summary(self.messages[:excess_messages + 2])
        
        # Keep system messages, summary, and recent messages
        new_messages = [
            msg for msg in self.messages if msg["role"] == "system"
        ]
        
        # Add summary message
        summary_message = {
            "role": "system",
            "content": f"Earlier conversation summary: {summary}",
            "timestamp": datetime.utcnow(),
            "metadata": {"is_summary": True}
        }
        new_messages.append(summary_message)
        
        # Add recent messages
        new_messages.extend(self.messages[-self.max_context_length:])
        
        # Update in memory and database
        self.messages = new_messages
        
        self.conversation_collection.update_one(
            {"_id": self.conversation_id},
            {
                "$set": {
                    "messages": new_messages,
                    "summary": summary,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Update cache
        cache_key = f"conversation:{self.conversation_id}"
        set_cache(cache_key, {"messages": self.messages}, expiry=3600)
        
        logger.info(f"Pruned conversation {self.conversation_id} context")
    
    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Generate a summary of older messages
        In a production system, this would use an LLM to generate a good summary
        """
        # Placeholder for actual summarization logic
        # In a real implementation, we would call the LLM here
        message_count = len(messages)
        summary = f"This conversation has {message_count} earlier messages discussing solar energy topics."
        
        # Implement more sophisticated summarization using the LLM
        # This would be integrated with model_loader.py
        
        return summary
    
    def get_formatted_context(self, include_system_context: bool = True) -> List[Dict[str, str]]:
        """
        Get the conversation context formatted for LLM input
        """
        formatted_messages = []
        
        # Add system context if requested
        if include_system_context:
            system_context = {
                "role": "system",
                "content": "You are a helpful assistant specializing in solar energy systems and technology."
            }
            formatted_messages.append(system_context)
        
        # Add conversation messages in chronological order
        for message in self.messages:
            formatted_message = {
                "role": message["role"],
                "content": message["content"]
            }
            formatted_messages.append(formatted_message)
            
        return formatted_messages
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current conversation, including metadata
        """
        conversation = self.conversation_collection.find_one({"_id": self.conversation_id})
        if not conversation:
            return {
                "id": self.conversation_id,
                "message_count": len(self.messages),
                "error": "Conversation not found in database"
            }
            
        return {
            "id": self.conversation_id,
            "title": conversation.get("title", "Untitled Conversation"),
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "message_count": len(self.messages),
            "summary": conversation.get("summary", ""),
            "metadata": conversation.get("metadata", {})
        }
    
    def update_conversation_title(self, title: str) -> None:
        """
        Update the conversation title
        """
        self.conversation_collection.update_one(
            {"_id": self.conversation_id},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}}
        )
        logger.info(f"Updated conversation {self.conversation_id} title to: {title}")
    
    def update_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Update conversation metadata
        """
        self.conversation_collection.update_one(
            {"_id": self.conversation_id},
            {
                "$set": {
                    "metadata": metadata,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        logger.info(f"Updated conversation {self.conversation_id} metadata")
    
    def get_conversation_by_id(conversation_id: str) -> Optional[Conversation]:
        """
        Static method to retrieve a conversation by ID
        """
        db = get_database()
        conversation = db["conversations"].find_one({"_id": conversation_id})
        if not conversation:
            return None
            
        return Conversation(
            id=str(conversation["_id"]),
            user_id=conversation["user_id"],
            title=conversation.get("title", "Untitled"),
            created_at=conversation.get("created_at"),
            updated_at=conversation.get("updated_at"),
            messages=[
                Message(
                    role=msg["role"],
                    content=msg["content"],
                    metadata=msg.get("metadata", {})
                )
                for msg in conversation.get("messages", [])
            ],
            metadata=conversation.get("metadata", {})
        )