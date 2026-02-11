from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
import logging

from app.db.session import get_db
from app.db.models import Document, DocumentChunk
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter()


class DocumentResponse(BaseModel):
    """Document response model."""
    id: str
    filename: str
    file_type: str
    uploaded_at: str
    chunk_count: int
    metadata: dict = {}  # JSONB metadata


class DocumentsListResponse(BaseModel):
    """Documents list response model."""
    documents: List[DocumentResponse]
    total: int


@router.get("/documents", response_model=DocumentsListResponse)
async def list_documents(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    List all documents with their chunk counts.
    
    - **limit**: Maximum number of documents to return (1-1000)
    - **offset**: Number of documents to skip
    """
    try:
        document_service = DocumentService(db)
        documents = await document_service.list_documents(limit=limit, offset=offset)
        
        # Get total count
        total_result = await db.execute(select(func.count(Document.id)))
        total = total_result.scalar() or 0
        
        # Get chunk counts for each document
        document_responses = []
        for doc in documents:
            chunk_count_result = await db.execute(
                select(func.count(DocumentChunk.id))
                .where(DocumentChunk.document_id == doc.id)
            )
            chunk_count = chunk_count_result.scalar() or 0
            
            document_responses.append(DocumentResponse(
                id=str(doc.id),
                filename=doc.filename,
                file_type=doc.file_type,
                uploaded_at=doc.uploaded_at.isoformat(),
                chunk_count=chunk_count,
                metadata=doc.meta if hasattr(doc, 'meta') else {}
            ))
        
        return DocumentsListResponse(
            documents=document_responses,
            total=total
        )
    
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}"
        )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a document and all its chunks.
    
    - **document_id**: UUID of the document to delete
    """
    try:
        document_service = DocumentService(db)
        deleted = await document_service.delete_document(document_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        return {"message": "Document deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )
