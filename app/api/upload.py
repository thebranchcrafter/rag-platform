from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Dict, Any
import logging
import json
import os
import tempfile
from pathlib import Path

from app.db.session import get_db
from app.services.document_service import DocumentService
from app.services.ingestion.document_intelligence import (
    DocumentIntelligenceService,
    ExtractionStrategy
)
from app.services.ingestion.text_extractors.local_parser import LocalParserService
from app.services.ingestion.text_extractors.local_ocr import LocalOCRService
from app.services.ingestion.text_extractors.cloud_ocr import CloudOCRService
from app.services.ingestion.image_processor import ImageProcessor
from app.services.ingestion.normalizer import DocumentNormalizer
from app.services.ingestion.semantic_chunker import SemanticChunker
from app.core.config import settings

logger = logging.getLogger(__name__)

# OCR imports (optional - only if available)
try:
    from pdf2image import convert_from_bytes
    from pytesseract import image_to_string
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("OCR libraries not available. Install pdf2image and pytesseract for image text extraction.")

router = APIRouter()


def extract_text_from_pdf(file_content: bytes) -> str:
    """
    Extract text from PDF file with improved table extraction and OCR support.
    
    Uses pdfplumber for better table detection and extraction.
    Falls back to OCR for pages with images containing text.
    Tables are formatted as structured text for better searchability.
    Optimized to only extract tables when they exist.
    """
    try:
        pdf_file = io.BytesIO(file_content)
        text_parts = []
        pages_needing_ocr = []
        
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract regular text first
                page_text = page.extract_text()
                
                # Check if page has extractable text
                if page_text and page_text.strip():
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
                else:
                    # Page has no extractable text - might be an image, mark for OCR
                    pages_needing_ocr.append(page_num)
                    logger.debug(f"Page {page_num} has no extractable text, will try OCR")
                
                # Add page separator only if we have content
                if text_parts:
                    text_parts.append("\n")
        
        # If we have pages that need OCR and OCR is available, process them
        if pages_needing_ocr and OCR_AVAILABLE:
            logger.info(f"Attempting OCR on {len(pages_needing_ocr)} pages: {pages_needing_ocr}")
            ocr_text = extract_text_with_ocr(file_content, pages_needing_ocr)
            if ocr_text:
                text_parts.append(f"\n\n[Texto extraído con OCR de páginas {', '.join(map(str, pages_needing_ocr))}]\n{ocr_text}\n")
        
        full_text = "\n".join(text_parts).strip()
        
        if not full_text:
            logger.warning("No text extracted from PDF")
            # Final fallback: try OCR on all pages if available
            if OCR_AVAILABLE:
                logger.info("Attempting OCR on all pages as final fallback")
                ocr_text = extract_text_with_ocr(file_content, None)  # None = all pages
                if ocr_text:
                    return ocr_text.strip()
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


def extract_text_with_ocr(file_content: bytes, page_numbers: Optional[list] = None) -> str:
    """
    Extract text from PDF pages using OCR (Optical Character Recognition).
    
    Args:
        file_content: PDF file content as bytes
        page_numbers: Optional list of page numbers (1-indexed) to process. If None, processes all pages.
        
    Returns:
        Extracted text from OCR
    """
    if not OCR_AVAILABLE:
        logger.warning("OCR not available. Install pdf2image and pytesseract.")
        return ""
    
    try:
        # Convert PDF pages to images
        # first_page and last_page are 1-indexed
        first_page = min(page_numbers) if page_numbers else None
        last_page = max(page_numbers) if page_numbers else None
        
        # Convert PDF to images
        images = convert_from_bytes(
            file_content,
            first_page=first_page,
            last_page=last_page,
            dpi=300  # Higher DPI for better OCR accuracy
        )
        
        if not images:
            logger.warning("No images extracted from PDF for OCR")
            return ""
        
        # Extract text from each image using OCR
        ocr_texts = []
        for idx, image in enumerate(images):
            page_num = (first_page + idx) if first_page else (idx + 1)
            try:
                # Use Spanish language for better results with Spanish documents
                # You can add more languages: 'spa+eng' for Spanish and English
                text = image_to_string(image, lang='spa+eng')
                if text and text.strip():
                    ocr_texts.append(f"[Página {page_num} - OCR]\n{text.strip()}")
                    logger.debug(f"OCR extracted {len(text)} characters from page {page_num}")
            except Exception as e:
                logger.warning(f"Error during OCR on page {page_num}: {str(e)}")
                continue
        
        return "\n\n".join(ocr_texts)
    except Exception as e:
        logger.error(f"Error in OCR extraction: {str(e)}")
        return ""


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


def detect_file_type(filename: str, content: bytes = None) -> str:
    """Detect file type from filename and optionally content."""
    if not filename:
        return "unknown"
    
    extension = filename.split(".")[-1].lower()
    
    # Map extensions to types
    type_map = {
        "pdf": "pdf",
        "docx": "docx",
        "doc": "docx",  # Treat old .doc as docx
        "html": "html",
        "htm": "html",
        "txt": "txt",
        "png": "png",
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "tiff": "tiff",
        "tif": "tiff"
    }
    
    return type_map.get(extension, "unknown")


async def store_file_temporarily(file_content: bytes, filename: str) -> str:
    """Store file temporarily and return path."""
    # Create temp directory if it doesn't exist
    temp_dir = Path(tempfile.gettempdir()) / "rag_uploads"
    temp_dir.mkdir(exist_ok=True)
    
    # Create unique filename
    import uuid
    unique_id = str(uuid.uuid4())
    file_path = temp_dir / f"{unique_id}_{filename}"
    
    # Write file
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    return str(file_path)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(default="{}", description="JSON metadata object (defaults to {})"),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document with next-generation ingestion pipeline.
    
    Supports: PDF (text and scanned), DOCX, HTML, TXT, Images (PNG, JPG, TIFF)
    
    - **file**: Document file to upload
    - **metadata**: JSON object with metadata for multi-tenancy filtering (defaults to {})
    """
    # Ensure metadata has a default value if not provided
    if not metadata or metadata.strip() == '':
        metadata = '{}'
    
    logger.info(f"Upload request received - filename: {file.filename if file else 'None'}")
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Detect file type
    file_type = detect_file_type(file.filename)
    
    if file_type == "unknown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Supported: PDF, DOCX, HTML, TXT, PNG, JPG, TIFF"
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
        
        # Store file temporarily
        file_path = await store_file_temporarily(file_content, file.filename)
        
        try:
            # Log configuration status
            logger.info("=" * 80)
            logger.info("[Upload Pipeline] Starting document ingestion pipeline")
            logger.info("=" * 80)
            logger.info(f"[Upload Pipeline] File: {file.filename}")
            logger.info(f"[Upload Pipeline] File type: {file_type}")
            logger.info(f"[Upload Pipeline] File size: {file_size:,} bytes")
            logger.info(f"[Upload Pipeline] Configuration:")
            logger.info(f"  - Cloud OCR enabled: {settings.ENABLE_CLOUD_OCR}")
            logger.info(f"  - Cloud OCR provider: {settings.CLOUD_OCR_PROVIDER}")
            logger.info(f"  - Image captions enabled: {settings.ENABLE_IMAGE_CAPTIONS}")
            logger.info(f"  - Max images per document: {settings.MAX_IMAGES_PER_DOCUMENT}")
            logger.info(f"  - Preserve tables: {settings.PRESERVE_TABLES}")
            logger.info(f"  - Preserve code blocks: {settings.PRESERVE_CODE_BLOCKS}")
            logger.info(f"  - Chunk max tokens: {settings.CHUNK_MAX_TOKENS}")
            logger.info(f"  - Chunk overlap: {settings.CHUNK_OVERLAP}")
            
            # Phase 1: Document Intelligence - Analyze and decide strategy
            logger.info("")
            logger.info("[Upload Pipeline] Phase 1: Document Intelligence")
            intelligence_service = DocumentIntelligenceService()
            analysis = await intelligence_service.analyze_document(
                file_path=file_path,
                file_type=file_type,
                file_size=file_size
            )
            
            logger.info("")
            logger.info("[Upload Pipeline] Phase 1 complete:")
            logger.info(f"  - Strategy: {analysis.strategy.value}")
            logger.info(f"  - Confidence: {analysis.confidence:.2%}")
            logger.info(f"  - Estimated pages: {analysis.estimated_pages}")
            logger.info(f"  - Text coverage: {analysis.text_coverage:.2%}")
            logger.info(f"  - Layout complexity: {analysis.layout_complexity}")
            logger.info(f"  - Requires OCR: {analysis.requires_ocr}")
            logger.info(f"  - Requires Vision: {analysis.requires_vision}")
            
            # Phase 2: Extract text based on strategy
            logger.info("")
            logger.info("[Upload Pipeline] Phase 2: Text Extraction")
            extracted_content = None
            
            if analysis.strategy == ExtractionStrategy.LOCAL_PARSER:
                logger.info("[Upload Pipeline] Using Local Parser service")
                extractor = LocalParserService()
                extracted_content = await extractor.extract(file_path, file_type)
            
            elif analysis.strategy == ExtractionStrategy.LOCAL_OCR:
                logger.info("[Upload Pipeline] Using Local OCR service")
                extractor = LocalOCRService()
                extracted_content = await extractor.extract(file_path, file_type)
            
            elif analysis.strategy == ExtractionStrategy.CLOUD_OCR:
                if not settings.ENABLE_CLOUD_OCR:
                    logger.warning("[Upload Pipeline] Cloud OCR disabled in config, falling back to local OCR")
                    extractor = LocalOCRService()
                    extracted_content = await extractor.extract(file_path, file_type)
                else:
                    logger.info("[Upload Pipeline] Using Cloud OCR service")
                    try:
                        extractor = CloudOCRService()
                        extracted_content = await extractor.extract(file_path, file_type)
                        logger.info("[Upload Pipeline] Cloud OCR extraction successful")
                    except Exception as e:
                        logger.warning(f"[Upload Pipeline] Cloud OCR failed: {str(e)}, falling back to local OCR")
                        extractor = LocalOCRService()
                        extracted_content = await extractor.extract(file_path, file_type)
            
            elif analysis.strategy == ExtractionStrategy.HYBRID:
                logger.info("[Upload Pipeline] Using Hybrid extraction (local parser + OCR)")
                # Extract with local parser first
                local_extractor = LocalParserService()
                local_content = await local_extractor.extract(file_path, file_type)
                
                # Identify pages needing OCR (simplified - would need page-level analysis)
                # For now, use local content
                extracted_content = local_content
            
            if not extracted_content or not extracted_content.text.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to extract text from document"
                )
            
            logger.info("[Upload Pipeline] Phase 2 complete:")
            logger.info(f"  - Text length: {len(extracted_content.text):,} characters")
            logger.info(f"  - Pages processed: {extracted_content.pages_processed}")
            logger.info(f"  - Tables found: {len(extracted_content.tables)}")
            logger.info(f"  - Confidence: {extracted_content.confidence:.2%}")
            
            # Phase 3: Extract and caption images
            logger.info("")
            logger.info("[Upload Pipeline] Phase 3: Image Processing")
            image_captions = []
            
            # Skip image processing if we used Cloud OCR (it already extracts text from images)
            used_cloud_ocr = (analysis.strategy == ExtractionStrategy.CLOUD_OCR and 
                            settings.ENABLE_CLOUD_OCR)
            
            if used_cloud_ocr:
                logger.info("[Upload Pipeline] Phase 3 skipped: Cloud OCR already extracted text from images")
            elif file_type == "pdf" or analysis.requires_vision:
                # Only process images if not using Cloud OCR (which handles images automatically)
                try:
                    logger.info(f"[Upload Pipeline] Processing images (file_type={file_type}, requires_vision={analysis.requires_vision})")
                    logger.info("[Upload Pipeline] Note: Consider using Cloud OCR (AWS Textract/Azure) for better performance on low-resource servers")
                    image_processor = ImageProcessor()
                    image_captions = await image_processor.extract_and_caption_images(
                        file_path, file_type
                    )
                    logger.info(f"[Upload Pipeline] Phase 3 complete: {len(image_captions)} image caption(s) generated")
                    if image_captions:
                        logger.info(f"[Upload Pipeline] Captions generated for pages: {sorted(set(c['page'] for c in image_captions))}")
                except Exception as e:
                    logger.warning(f"[Upload Pipeline] Image processing failed: {str(e)}", exc_info=True)
                    image_captions = []
            else:
                logger.info("[Upload Pipeline] Phase 3 skipped: Vision not required for this file type")
            
            # Phase 4: Normalize to Markdown
            logger.info("")
            logger.info("[Upload Pipeline] Phase 4: Normalization")
            normalizer = DocumentNormalizer()
            normalized = await normalizer.normalize(
                extracted_content=extracted_content,
                image_captions=image_captions
            )
            
            logger.info("[Upload Pipeline] Phase 4 complete:")
            logger.info(f"  - Markdown length: {len(normalized.markdown):,} characters")
            logger.info(f"  - Quality score: {normalized.quality_score:.2%}")
            logger.info(f"  - Headings: {len(normalized.structure.headings)}")
            logger.info(f"  - Sections: {len(normalized.structure.sections)}")
            logger.info(f"  - Tables: {len(normalized.structure.tables)}")
            
            # Phase 5: Semantic chunking
            logger.info("")
            logger.info("[Upload Pipeline] Phase 5: Semantic Chunking")
            chunker = SemanticChunker(
                max_tokens=settings.CHUNK_MAX_TOKENS,
                overlap_tokens=settings.CHUNK_OVERLAP,
                preserve_tables=settings.PRESERVE_TABLES,
                preserve_code_blocks=settings.PRESERVE_CODE_BLOCKS
            )
            chunks = chunker.chunk(
                text=normalized.markdown,
                structure=normalized.structure
            )
            
            logger.info("[Upload Pipeline] Phase 5 complete:")
            logger.info(f"  - Chunks created: {len(chunks)}")
            
            # Phase 6: Create document with chunks
            logger.info("")
            logger.info("[Upload Pipeline] Phase 6: Embedding & Storage")
            document_service = DocumentService(db)
            document = await document_service.create_document_with_chunks(
                filename=file.filename,
                file_type=file_type,
                chunks=chunks,
                metadata={
                    **metadata_dict,
                    "extraction_strategy": analysis.strategy.value,
                    "quality_score": normalized.quality_score,
                    "pages_processed": extracted_content.pages_processed,
                    "image_captions_count": len(image_captions)
                }
            )
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("[Upload Pipeline] Pipeline complete - Document stored successfully")
            logger.info("=" * 80)
            logger.info(f"[Upload Pipeline] Document ID: {document.id}")
            logger.info(f"[Upload Pipeline] Final summary:")
            logger.info(f"  - Strategy used: {analysis.strategy.value}")
            logger.info(f"  - Chunks created: {len(chunks)}")
            logger.info(f"  - Quality score: {normalized.quality_score:.2%}")
            logger.info(f"  - Image captions: {len(image_captions)}")
            logger.info("=" * 80)
            
            return {
                "message": "Document uploaded and processed successfully",
                "document_id": str(document.id),
                "filename": document.filename,
                "file_type": document.file_type,
                "metadata": document.meta,
                "uploaded_at": document.uploaded_at.isoformat(),
                "processing_info": {
                    "strategy": analysis.strategy.value,
                    "chunks_created": len(chunks),
                    "quality_score": normalized.quality_score,
                    "image_captions": len(image_captions)
                }
            }
        
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp file {file_path}: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(e)}"
        )
