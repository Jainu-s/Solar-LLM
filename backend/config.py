import os
from typing import Dict, Any, Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """
    Application settings and configuration
    
    Includes:
    - Database settings
    - Security configuration
    - LLM model settings
    - API keys
    - File storage
    - Analytics configuration
    - Rate limits
    """
    
    # Application settings
    APP_NAME: str = "Solar LLM"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "Solar energy domain-specific LLM assistant"
    DEBUG: bool = Field(False, env="DEBUG")
    
    # Path settings
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    LOGS_DIR: str = os.path.join(BASE_DIR, "logs")
    UPLOADS_DIR: str = os.path.join(BASE_DIR, "uploads")
    
    # API settings
    API_PREFIX: str = "/api"
    ALLOWED_HOSTS: List[str] = ["*"]
    CORS_ORIGINS: List[str] = ["*"]
    
    # Added missing API settings
    API_HOST: str = Field("localhost", env="API_HOST")
    API_PORT: str = Field("8000", env="API_PORT")
    API_URL: str = Field("http://localhost:8000/ask", env="API_URL")
    API_KEY: str = Field("your-admin-api-key-change-this-in-production", env="API_KEY")
    ALLOWED_ORIGINS: str = Field("http://localhost:8501,http://localhost:8000", env="ALLOWED_ORIGINS")
    
    # Database settings
    MONGODB_URI: str = Field("mongodb://localhost:27017/solar_llm", env="MONGODB_URI")
    MONGODB_DB: str = Field("solar_llm", env="MONGODB_DB")
    
    # Added missing MongoDB settings
    MONGO_USER: str = Field("", env="MONGO_USER")
    MONGO_PASSWORD: str = Field("", env="MONGO_PASSWORD")
    MONGO_HOST: str = Field("localhost", env="MONGO_HOST")
    MONGO_PORT: str = Field("27017", env="MONGO_PORT")
    MONGO_AUTH_SOURCE: str = Field("admin", env="MONGO_AUTH_SOURCE")
    MONGO_URI: str = Field("", env="MONGO_URI")
    
    # Vector database settings
    VECTOR_DB_PATH: str = os.path.join(DATA_DIR, "vector_db")
    VECTOR_DB_COLLECTION: str = "solar_docs"
    
    # Added ChromaDB and Meta Index settings
    CHROMA_DB_PATH: str = Field("backend/vector_db/chromadb", env="CHROMA_DB_PATH")
    META_INDEX_PATH: str = Field("backend/vector_db/meta_index.json", env="META_INDEX_PATH")
    
    # Security settings
    SECRET_KEY: str = Field("your-secret-key", env="SECRET_KEY")
    JWT_SECRET_KEY: str = Field("your-jwt-secret-key", env="JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    PASSWORD_RESET_EXPIRE_MINUTES: int = Field(15, env="PASSWORD_RESET_EXPIRE_MINUTES")
    
    # Added JWT Secret
    JWT_SECRET: str = Field("your-secure-jwt-secret-key-change-this-in-production", env="JWT_SECRET")
    
    # LLM model settings
    DEFAULT_MODEL_NAME: str = Field("mistralai/Mistral-7B-Instruct-v0.1", env="DEFAULT_MODEL_NAME")
    EMBEDDING_MODEL_NAME: str = Field("sentence-transformers/all-MiniLM-L6-v2", env="EMBEDDING_MODEL_NAME")
    MODEL_CACHE_TTL: int = Field(3600, env="MODEL_CACHE_TTL")  # 1 hour
    DEFAULT_EMBEDDING_MODEL: str = Field("all-MiniLM-L6-v2", env="DEFAULT_EMBEDDING_MODEL")
    MAX_MEMORY_USAGE: int = Field(85, env="MAX_MEMORY_USAGE")  # percent
    
    # Added missing model cache size
    MODEL_CACHE_SIZE: str = Field("100", env="MODEL_CACHE_SIZE")
    
    # Document processing settings
    CHUNK_SIZE: int = Field(1000, env="CHUNK_SIZE")
    CHUNK_OVERLAP: int = Field(200, env="CHUNK_OVERLAP")
    
    # RAG settings
    MAX_CHUNKS_PER_QUERY: int = Field(5, env="MAX_CHUNKS_PER_QUERY")
    SIMILARITY_THRESHOLD: float = Field(0.7, env="SIMILARITY_THRESHOLD")
    
    # External API keys
    OPENAI_API_KEY: Optional[str] = Field(None, env="OPENAI_API_KEY")
    SERPAPI_KEY: Optional[str] = Field(None, env="SERPAPI_KEY")
    SEARCHAPI_KEY: Optional[str] = Field(None, env="SEARCHAPI_KEY")
    
    # Added Gemini API key
    GEMINI_API_KEY: str = Field("", env="GEMINI_API_KEY")
    
    # Search settings
    DEFAULT_SEARCH_PROVIDER: str = Field("duckduckgo", env="DEFAULT_SEARCH_PROVIDER")
    SEARCH_CACHE_TTL: int = Field(3600, env="SEARCH_CACHE_TTL")  # 1 hour
    MAX_SEARCH_RESULTS: int = Field(5, env="MAX_SEARCH_RESULTS")
    
    # Caching settings
    RESPONSE_CACHE_TTL: int = Field(3600, env="RESPONSE_CACHE_TTL")  # 1 hour
    
    # Rate limiting
    MIN_QUERY_INTERVAL: float = Field(0.1, env="MIN_QUERY_INTERVAL")  # seconds
    MIN_SEARCH_INTERVAL: float = Field(1.0, env="MIN_SEARCH_INTERVAL")  # seconds
    
    # Added missing rate limit settings
    REQUEST_TIMEOUT: str = Field("30", env="REQUEST_TIMEOUT")
    MAX_REQUESTS_PER_MINUTE: str = Field("60", env="MAX_REQUESTS_PER_MINUTE")
    
    # Added session settings
    SESSION_EXPIRY: str = Field("86400", env="SESSION_EXPIRY")
    
    # Added environment type
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    
    # Logging
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    
    # Analytics
    ANALYTICS_BUFFER_SIZE: int = Field(100, env="ANALYTICS_BUFFER_SIZE")
    ANALYTICS_FLUSH_INTERVAL: int = Field(60, env="ANALYTICS_FLUSH_INTERVAL")  # seconds
    
    # Frontend settings
    THEME_COLOR: str = Field("#2563EB", env="THEME_COLOR")  # Blue
    
    # Updated Config class to match Pydantic V2 structure
    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }
    
    @validator("BASE_DIR", "DATA_DIR", "LOGS_DIR", "UPLOADS_DIR", "VECTOR_DB_PATH", pre=True)
    def create_dirs(cls, v):
        """Create directories if they don't exist"""
        os.makedirs(v, exist_ok=True)
        return v
    
    def get_database_uri(self) -> str:
        """Get database URI with fallback to local SQLite for testing"""
        if self.MONGODB_URI:
            return self.MONGODB_URI
        
        # Fallback to SQLite for testing
        sqlite_path = os.path.join(self.DATA_DIR, "solar_llm.db")
        return f"sqlite:///{sqlite_path}"
    
    def get_model_path(self, model_name: str) -> str:
        """Get local path for a model"""
        model_dir = os.path.join(self.BASE_DIR, "models")
        os.makedirs(model_dir, exist_ok=True)
        
        # Create a safe directory name from model name
        safe_name = model_name.replace("/", "_").replace("\\", "_")
        
        return os.path.join(model_dir, safe_name)

    @property
    def LOG_DIR(self) -> str:
        """Alias for LOGS_DIR for backward compatibility"""
        return self.LOGS_DIR

        

# Create settings instance
settings = Settings()

# Create required directories
os.makedirs(settings.DATA_DIR, exist_ok=True)
os.makedirs(settings.LOGS_DIR, exist_ok=True)
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
os.makedirs(os.path.join(settings.DATA_DIR, "documents"), exist_ok=True)
os.makedirs(os.path.join(settings.DATA_DIR, "conversations"), exist_ok=True)
os.makedirs(os.path.join(settings.DATA_DIR, "analytics"), exist_ok=True)

# Function for getting settings (for compatibility)
def get_settings():
    return settings