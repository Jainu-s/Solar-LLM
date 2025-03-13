from typing import List, Dict, Any, Optional
import json
import os
from datetime import datetime
from collections import Counter

from backend.db.mongodb import get_database
from backend.utils.cache import get_cache, set_cache
from backend.utils.logging import setup_logger

logger = setup_logger("suggestions")

class SuggestionEngine:
    """
    Provides intelligent query suggestions based on:
    - Common solar queries
    - User's past conversations
    - Trending topics
    - Context-aware follow-up questions
    """
    
    def __init__(self):
        self.db = get_database()
        self.user_collection = self.db["users"]
        self.conversation_collection = self.db["conversations"]
        self.query_collection = self.db["queries"]
        
        # Load default suggestions from JSON file
        self.default_suggestions = self._load_default_suggestions()
        
    def _load_default_suggestions(self) -> Dict[str, List[str]]:
        """Load default suggestions from JSON file"""
        try:
            suggestions_file = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "data", 
                "suggestions.json"
            )
            
            if not os.path.exists(suggestions_file):
                # Create default suggestions if file doesn't exist
                default_data = {
                    "general": [
                        "How do solar panels work?",
                        "What is the ROI on a residential solar system?",
                        "How many solar panels do I need?",
                        "What are solar incentives in my area?",
                        "What's the difference between monocrystalline and polycrystalline panels?"
                    ],
                    "technical": [
                        "How to calculate solar panel efficiency?",
                        "What is DC to AC ratio in solar design?",
                        "How does temperature affect solar panel output?",
                        "What is the lifespan of a solar inverter?",
                        "How to size a battery for solar storage?"
                    ],
                    "financial": [
                        "What tax credits are available for solar in 2025?",
                        "How does net metering work?",
                        "What financing options exist for solar projects?",
                        "How to calculate solar payback period?",
                        "What is the cost per watt for solar installation?"
                    ],
                    "maintenance": [
                        "How often should solar panels be cleaned?",
                        "What maintenance is required for solar systems?",
                        "How to troubleshoot common solar inverter issues?",
                        "Signs that your solar panels need replacement",
                        "How to monitor solar system performance?"
                    ]
                }
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(suggestions_file), exist_ok=True)
                
                # Write default suggestions
                with open(suggestions_file, 'w') as f:
                    json.dump(default_data, f, indent=2)
                
                return default_data
                
            with open(suggestions_file, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Error loading default suggestions: {str(e)}")
            # Return fallback default suggestions
            return {
                "general": [
                    "How do solar panels work?",
                    "What is the ROI on a residential solar system?",
                    "How many solar panels do I need?"
                ]
            }
    
    def get_suggestions(
        self, 
        user_id: Optional[str] = None, 
        current_context: Optional[List[Dict[str, str]]] = None,
        category: str = "general",
        count: int = 4
    ) -> List[str]:
        """
        Get query suggestions based on context and user history
        
        Args:
            user_id: Optional user ID for personalized suggestions
            current_context: Optional current conversation context
            category: Suggestion category (general, technical, financial, etc.)
            count: Number of suggestions to return
            
        Returns:
            List of suggested queries
        """
        suggestions = []
        
        # Try to get from cache first for better performance
        cache_key = f"suggestions:{user_id}:{category}" if user_id else f"suggestions:{category}"
        cached_suggestions = get_cache(cache_key)
        
        if cached_suggestions:
            return cached_suggestions[:count]
        
        # 1. Add category-specific default suggestions
        category_suggestions = self.default_suggestions.get(category, self.default_suggestions.get("general", []))
        suggestions.extend(category_suggestions)
        
        # 2. Add personalized suggestions if user_id provided
        if user_id:
            personal_suggestions = self._get_personalized_suggestions(user_id)
            suggestions.extend(personal_suggestions)
        
        # 3. Add context-aware suggestions if context provided
        if current_context and len(current_context) > 0:
            context_suggestions = self._get_context_aware_suggestions(current_context)
            suggestions.extend(context_suggestions)
        
        # 4. Add trending suggestions
        trending_suggestions = self._get_trending_suggestions()
        suggestions.extend(trending_suggestions)
        
        # Remove duplicates while preserving order
        unique_suggestions = []
        seen = set()
        for suggestion in suggestions:
            if suggestion not in seen:
                unique_suggestions.append(suggestion)
                seen.add(suggestion)
        
        # Cache the results for 30 minutes
        if user_id:
            set_cache(cache_key, unique_suggestions, expiry=1800)
        
        return unique_suggestions[:count]
    
    def _get_personalized_suggestions(self, user_id: str) -> List[str]:
        """Get personalized suggestions based on user's past conversations"""
        try:
            # Get user's recent conversations
            conversations = list(self.conversation_collection.find(
                {"user_id": user_id},
                {"messages": 1}
            ).sort("updated_at", -1).limit(5))
            
            # Extract user queries from conversations
            user_queries = []
            for conversation in conversations:
                for message in conversation.get("messages", []):
                    if message.get("role") == "user":
                        user_queries.append(message.get("content", ""))
            
            # Generate follow-up suggestions based on past queries
            # In a real system, this could use an LLM to generate better follow-ups
            follow_ups = [
                f"Tell me more about {query.split()[0:3]}" 
                for query in user_queries if len(query.split()) >= 3
            ][:2]
            
            return follow_ups
            
        except Exception as e:
            logger.error(f"Error getting personalized suggestions: {str(e)}")
            return []
    
    def _get_context_aware_suggestions(self, context: List[Dict[str, str]]) -> List[str]:
        """Generate context-aware suggestions based on conversation history"""
        try:
            # Extract the last user message
            user_messages = [msg for msg in context if msg.get("role") == "user"]
            if not user_messages:
                return []
                
            last_user_message = user_messages[-1].get("content", "")
            
            # Simple rule-based follow-up suggestions
            # In a real system, this would use an LLM to generate better follow-ups
            
            # Keywords to follow-up suggestions mapping
            keyword_suggestions = {
                "cost": ["What's the installation cost for a typical home?", 
                         "How do financing options affect total system cost?"],
                "efficiency": ["How does weather affect solar panel efficiency?",
                             "Which solar panel brands have the highest efficiency?"],
                "battery": ["How long do solar batteries typically last?",
                          "What's the ROI for adding battery storage to solar?"],
                "install": ["What's involved in a typical solar installation?",
                         "How long does a solar installation usually take?"],
                "incentive": ["What federal tax credits are available for solar?",
                           "What local incentives exist for solar in my area?"],
                "maintenance": ["What regular maintenance do solar panels need?",
                             "How often should solar panels be cleaned?"]
            }
            
            suggestions = []
            for keyword, keyword_suggestions in keyword_suggestions.items():
                if keyword in last_user_message.lower():
                    suggestions.extend(keyword_suggestions)
            
            return suggestions[:3]  # Limit to 3 context-aware suggestions
            
        except Exception as e:
            logger.error(f"Error getting context-aware suggestions: {str(e)}")
            return []
    
    def _get_trending_suggestions(self) -> List[str]:
        """Get trending suggestions based on popular queries"""
        try:
            # Get queries from the last 7 days
            one_week_ago = datetime.utcnow().timestamp() - (7 * 24 * 60 * 60)
            recent_queries = list(self.query_collection.find(
                {"timestamp": {"$gte": one_week_ago}},
                {"query": 1}
            ).limit(100))
            
            # Count query frequencies
            query_counter = Counter([q.get("query") for q in recent_queries])
            
            # Get top 3 trending queries
            trending = [query for query, _ in query_counter.most_common(3)]
            
            return trending
            
        except Exception as e:
            logger.error(f"Error getting trending suggestions: {str(e)}")
            return []
    
    def log_query(self, query: str, user_id: Optional[str] = None) -> None:
        """Log a query for analytics and improving suggestions"""
        try:
            self.query_collection.insert_one({
                "query": query,
                "user_id": user_id,
                "timestamp": datetime.utcnow().timestamp()
            })
        except Exception as e:
            logger.error(f"Error logging query: {str(e)}")
    
    def generate_follow_up_questions(
        self, 
        conversation_context: List[Dict[str, str]],
        count: int = 3
    ) -> List[str]:
        """
        Generate follow-up questions based on the conversation context
        
        Args:
            conversation_context: List of messages in the conversation
            count: Number of follow-up questions to generate
            
        Returns:
            List of follow-up questions
        """
        # In a production system, this would use an LLM to generate 
        # intelligent follow-up questions based on the conversation
        
        # Extract the last assistant response
        assistant_messages = [msg for msg in conversation_context if msg.get("role") == "assistant"]
        if not assistant_messages:
            return self.get_suggestions(count=count)
            
        last_assistant_message = assistant_messages[-1].get("content", "")
        
        # For now, use a simple rule-based approach
        # This would be replaced with an LLM call in production
        
        follow_ups = []
        
        # Check for key solar topics in the last response
        topics = {
            "efficiency": ["What factors affect solar panel efficiency?",
                         "How can I maximize my solar system's efficiency?"],
            "cost": ["What's the typical ROI for solar installations?",
                   "How do financing options affect total system cost?"],
            "installation": ["What's the installation process like?",
                          "How long does a typical installation take?"],
            "maintenance": ["What maintenance is required for solar panels?",
                         "How often should solar panels be cleaned?"],
            "technology": ["What are the latest solar panel technologies?",
                        "How is solar technology likely to evolve?"]
        }
        
        for topic, questions in topics.items():
            if topic in last_assistant_message.lower():
                follow_ups.extend(questions)
        
        # If we couldn't generate specific follow-ups, fall back to defaults
        if not follow_ups:
            follow_ups = [
                "Can you explain that in more detail?",
                "How does that compare to conventional options?",
                "What are the environmental benefits of this approach?",
                "What are the financial implications of this?"
            ]
        
        return follow_ups[:count]