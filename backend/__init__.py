"""
Solar IntelliBot Backend

This package contains the backend implementation of the Solar IntelliBot,
an intelligent chatbot for solar energy information and analytics.

The backend is built with FastAPI and uses a RAG (Retrieval Augmented Generation)
architecture to provide accurate and context-aware responses about solar energy topics.

Key components:
- Multi-agent system for handling different query types
- Security features including JWT authentication
- Vector database integration for semantic search
- MongoDB integration for structured data queries
- Advanced analytics and monitoring capabilities
"""

__version__ = "2.0.0"
__author__ = "NeoSilica Team"
__license__ = "Proprietary"

# Import config for easier access
from backend.config import get_settings, settings

# Setup global logging
from backend.utils.logging import setup_global_logging
setup_global_logging(settings.LOG_DIR)