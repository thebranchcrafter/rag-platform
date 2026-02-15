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
    
    # Cloud OCR Configuration
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: str = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    AZURE_DOCUMENT_INTELLIGENCE_KEY: str = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    
    # OCR Settings
    ENABLE_OCR: bool = os.getenv("ENABLE_OCR", "false").lower() == "true"  # Master switch for all OCR
    ENABLE_CLOUD_OCR: bool = os.getenv("ENABLE_CLOUD_OCR", "false").lower() == "true"
    CLOUD_OCR_PROVIDER: str = os.getenv("CLOUD_OCR_PROVIDER", "aws")  # "aws" or "azure"
    MAX_CLOUD_OCR_PAGES: int = int(os.getenv("MAX_CLOUD_OCR_PAGES", "100"))
    CLOUD_OCR_MONTHLY_BUDGET: float = float(os.getenv("CLOUD_OCR_MONTHLY_BUDGET", "50.0"))
    
    # Vision API Settings
    ENABLE_IMAGE_CAPTIONS: bool = os.getenv("ENABLE_IMAGE_CAPTIONS", "true").lower() == "true"
    MAX_IMAGES_PER_DOCUMENT: int = int(os.getenv("MAX_IMAGES_PER_DOCUMENT", "20"))
    IMAGE_CAPTION_MODEL: str = os.getenv("IMAGE_CAPTION_MODEL", "gpt-4o")
    
    # Advanced Chunking
    PRESERVE_TABLES: bool = os.getenv("PRESERVE_TABLES", "true").lower() == "true"
    PRESERVE_CODE_BLOCKS: bool = os.getenv("PRESERVE_CODE_BLOCKS", "true").lower() == "true"
    
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
