from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os
import json


class Settings(BaseSettings):
    """Application settings."""
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    # Store CORS_ORIGINS as string to avoid JSON parsing issues
    # Use Field with validation_alias to map from CORS_ORIGINS env var
    CORS_ORIGINS_STR: str = Field(default="*", validation_alias="CORS_ORIGINS")
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://rag_user:rag_password@postgres:5432/rag_db"
    )
    
    # OpenAI
    OPENAI_API_KEY: str = ""  # Will be read from environment variable
    OPENAI_MODEL_EMBEDDING: str = "text-embedding-3-small"
    OPENAI_MODEL_CHAT: str = "gpt-4o-mini"
    
    # Chunking
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    CHUNK_MAX_TOKENS: int = int(os.getenv("CHUNK_MAX_TOKENS", "1200"))
    
    # Retrieval
    TOP_K: int = int(os.getenv("TOP_K", "10"))
    VECTOR_WEIGHT: float = float(os.getenv("VECTOR_WEIGHT", "0.7"))
    BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.3"))
    ENABLE_RERANKING: bool = os.getenv("ENABLE_RERANKING", "false").lower() == "true"
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Parse CORS_ORIGINS from string to list."""
        v = getattr(self, 'CORS_ORIGINS_STR', '*')
        if v == "*":
            return ["*"]
        # Try JSON first
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Fall back to comma-separated
        origins = [origin.strip() for origin in v.split(",") if origin.strip()]
        return origins if origins else ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
