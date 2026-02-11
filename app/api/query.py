from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging

from app.db.session import get_db
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter()


class QueryRequest(BaseModel):
    """Query request model with optional metadata filters and system prompt."""
    question: str = Field(..., min_length=1, max_length=1000, description="The question to ask")
    filters: Optional[Dict[str, Any]] = Field(None, description="JSONB metadata filters for multi-tenancy")
    top_k: Optional[int] = Field(None, ge=1, le=100, description="Number of chunks to retrieve (overrides default)")
    system_prompt: Optional[str] = Field(None, max_length=2000, description="Custom system prompt to override the default")


class QueryResponse(BaseModel):
    """Query response model."""
    answer: str
    chunks: list[dict]


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Query the RAG system with a question and optional metadata filters.
    
    - **question**: The question to ask based on uploaded documents
    - **filters**: Optional JSON object for metadata filtering (e.g., {"community_id": "123"})
    - **top_k**: Optional number of chunks to retrieve
    - **system_prompt**: Optional custom system prompt to override the default
    
    Example with filters and custom prompt:
    ```json
    {
      "question": "What was discussed?",
      "filters": {
        "community_id": "123",
        "category": "meetings"
      },
      "system_prompt": "You are a helpful assistant specialized in meeting summaries."
    }
    ```
    """
    try:
        # Validate filters if provided
        if request.filters is not None and not isinstance(request.filters, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filters must be a JSON object"
            )
        
        logger.info(f"Query received - question: '{request.question[:50]}...', filters: {request.filters}, top_k: {request.top_k}, custom_prompt: {bool(request.system_prompt)}")
        
        retrieval_service = RetrievalService(db)
        result = await retrieval_service.query(
            question=request.question,
            filters=request.filters,
            top_k=request.top_k,
            system_prompt=request.system_prompt
        )
        
        return QueryResponse(**result)
    
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )
