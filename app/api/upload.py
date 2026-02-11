from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Dict, Any
import logging
import json
import PyPDF2
import io

from app.db.session import get_db
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter()


def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file."""
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract text from PDF: {str(e)}"
        )


def extract_text_from_txt(file_content: bytes) -> str:
    """Extract text from plain text file."""
    try:
        return file_content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return file_content.decode("latin-1")
        except Exception as e:
            logger.error(f"Error decoding text file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to decode text file. Please ensure it's UTF-8 encoded."
            )


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(default="{}", description="JSON metadata object (defaults to {})"),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document (PDF or text file) and process it for RAG.
    
    - **file**: PDF or text file to upload
    - **metadata**: JSON object with metadata for multi-tenancy filtering (defaults to {})
    
    Example metadata:
    ```json
    {
      "community_id": "123",
      "organization_id": "456",
      "category": "meetings",
      "tags": ["important", "q1-2024"]
    }
    ```
    """
    # Ensure metadata has a default value if not provided
    if not metadata or metadata.strip() == '':
        metadata = '{}'
        logger.warning("Metadata was empty or not provided, using default: {}")
    
    logger.info(f"Upload request received - filename: {file.filename if file else 'None'}, metadata: {metadata}")
    
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    file_type = file.filename.split(".")[-1].lower()
    
    if file_type not in ["pdf", "txt"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and TXT files are supported"
        )
    
    try:
        # Parse and validate metadata
        try:
            metadata_dict = json.loads(metadata)
            if not isinstance(metadata_dict, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Metadata must be a JSON object"
                )
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON in metadata: {str(e)}"
            )
        
        # Read file content
        file_content = await file.read()
        
        # Extract text based on file type
        if file_type == "pdf":
            text_content = extract_text_from_pdf(file_content)
        else:
            text_content = extract_text_from_txt(file_content)
        
        if not text_content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File appears to be empty or contains no extractable text"
            )
        
        # Process document with metadata
        document_service = DocumentService(db)
        document = await document_service.create_document(
            filename=file.filename,
            file_type=file_type,
            text_content=text_content,
            metadata=metadata_dict
        )
        
        logger.info(f"Document uploaded with metadata: {metadata_dict}")
        
        return {
            "message": "Document uploaded and processed successfully",
            "document_id": str(document.id),
            "filename": document.filename,
            "file_type": document.file_type,
            "metadata": document.meta,
            "uploaded_at": document.uploaded_at.isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )
