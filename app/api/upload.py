from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Dict, Any
import logging
import json
import pdfplumber
import io

from app.db.session import get_db
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter()


def extract_text_from_pdf(file_content: bytes) -> str:
    """
    Extract text from PDF file with improved table extraction.
    
    Uses pdfplumber for better table detection and extraction.
    Tables are formatted as structured text for better searchability.
    Optimized to only extract tables when they exist.
    """
    try:
        pdf_file = io.BytesIO(file_content)
        text_parts = []
        
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract regular text first
                page_text = page.extract_text()
                
                # Only extract tables if page has text (optimization)
                # This avoids expensive table extraction on pages without tables
                if page_text:
                    text_parts.append(page_text)
                    
                    # Check if page likely contains tables (heuristic: look for table-like patterns in text)
                    # Only extract tables if we detect potential table indicators
                    has_table_indicators = any(
                        keyword in page_text for keyword in 
                        ['|', '\t', 'CH ', 'COEF', 'CUOTA', 'Tabla', 'CHALET']
                    )
                    
                    if has_table_indicators:
                        # Extract tables and format them
                        tables = page.extract_tables()
                        if tables:
                            for table_num, table in enumerate(tables, 1):
                                if table and len(table) > 0:
                                    # Format table as structured text
                                    table_text = format_table_as_text(table)
                                    if table_text:
                                        text_parts.append(f"\n\n[Tabla {table_num}]\n{table_text}\n")
                
                # Add page separator only if we have content
                if text_parts:
                    text_parts.append("\n")
        
        full_text = "\n".join(text_parts).strip()
        
        if not full_text:
            logger.warning("No text extracted from PDF")
            # Fallback: try to extract at least something
            pdf_file.seek(0)
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
        
        return full_text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract text from PDF: {str(e)}"
        )


def format_table_as_text(table: list) -> str:
    """
    Format a table (list of lists) as readable text.
    
    Args:
        table: List of rows, where each row is a list of cells
        
    Returns:
        Formatted table as string optimized for searchability
    """
    if not table or len(table) == 0:
        return ""
    
    # Filter out empty rows
    table = [row for row in table if any(cell and str(cell).strip() for cell in row)]
    
    if not table:
        return ""
    
    # Normalize table: ensure all rows have the same number of columns
    max_cols = max(len(row) for row in table) if table else 0
    normalized_table = []
    for row in table:
        normalized_row = [str(cell).strip() if cell else "" for cell in row]
        # Pad row to max_cols
        while len(normalized_row) < max_cols:
            normalized_row.append("")
        normalized_table.append(normalized_row)
    
    if not normalized_table:
        return ""
    
    formatted_lines = []
    
    # Single optimized format: row-by-row with pipe separator
    # This format is both structured and searchable
    for row in normalized_table:
        if any(cell.strip() for cell in row):
            row_text = " | ".join(cell if cell else "" for cell in row)
            formatted_lines.append(row_text)
    
    return "\n".join(formatted_lines)


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
