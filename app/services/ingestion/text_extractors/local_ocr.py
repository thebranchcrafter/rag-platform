"""Local OCR using pytesseract."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import io

logger = logging.getLogger(__name__)

# Optional OCR imports
try:
    from pdf2image import convert_from_bytes
    from pytesseract import image_to_string
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("OCR libraries not available. Install pdf2image and pytesseract.")


@dataclass
class ExtractedContent:
    """Extracted content from OCR."""
    text: str
    tables: List[List[List[str]]]
    metadata: Dict[str, Any]
    confidence: float = 0.85  # OCR typically less confident
    pages_processed: int = 0


class LocalOCRService:
    """Extract text using local OCR (pytesseract)."""
    
    def __init__(self):
        if not OCR_AVAILABLE:
            raise RuntimeError("OCR libraries not available. Install pdf2image and pytesseract.")
        self.dpi = 300  # Higher DPI for better accuracy
    
    async def extract(
        self,
        file_path: str,
        file_type: str,
        pages: List[int] = None
    ) -> ExtractedContent:
        """Extract text using OCR."""
        if file_type == "pdf":
            return await self._extract_pdf_ocr(file_path, pages)
        elif file_type in ["png", "jpg", "jpeg", "tiff"]:
            return await self._extract_image_ocr(file_path)
        else:
            raise ValueError(f"Unsupported file type for OCR: {file_type}")
    
    async def _extract_pdf_ocr(
        self,
        file_path: str,
        pages: Optional[List[int]] = None
    ) -> ExtractedContent:
        """Extract text from PDF using OCR."""
        try:
            logger.debug(f"[Local OCR/PDF] Reading PDF file: {file_path}")
            with open(file_path, 'rb') as f:
                pdf_bytes = f.read()
            
            logger.debug(f"[Local OCR/PDF] Converting PDF to images at {self.dpi} DPI...")
            # Convert PDF to images
            if pages:
                first_page = min(pages)
                last_page = max(pages)
                logger.debug(f"[Local OCR/PDF] Processing pages {first_page} to {last_page}")
                images = convert_from_bytes(
                    pdf_bytes,
                    first_page=first_page,
                    last_page=last_page,
                    dpi=self.dpi
                )
            else:
                logger.debug("[Local OCR/PDF] Processing all pages")
                images = convert_from_bytes(pdf_bytes, dpi=self.dpi)
            
            logger.info(f"[Local OCR/PDF] Converted {len(images)} page(s) to images")
            
            # Extract text from each image
            text_parts = []
            successful_pages = 0
            total_chars = 0
            
            for idx, image in enumerate(images):
                page_num = (first_page + idx) if pages else (idx + 1)
                try:
                    logger.debug(f"[Local OCR/PDF] Running OCR on page {page_num} (image {idx + 1}/{len(images)})...")
                    # Use Spanish + English for better results
                    text = image_to_string(image, lang='spa+eng')
                    if text and text.strip():
                        text_parts.append(f"[Página {page_num}]\n{text.strip()}\n")
                        successful_pages += 1
                        total_chars += len(text)
                        logger.debug(f"[Local OCR/PDF] Page {page_num}: Extracted {len(text)} characters")
                    else:
                        logger.warning(f"[Local OCR/PDF] Page {page_num}: No text extracted")
                except Exception as e:
                    logger.warning(f"[Local OCR/PDF] Error during OCR on page {page_num}: {str(e)}")
                    continue
            
            full_text = "\n\n".join(text_parts).strip()
            
            logger.info(f"[Local OCR/PDF] OCR extraction complete:")
            logger.info(f"  - Pages processed: {successful_pages}/{len(images)}")
            logger.info(f"  - Total characters: {total_chars}")
            logger.info(f"  - Average chars/page: {total_chars // successful_pages if successful_pages > 0 else 0}")
            logger.info(f"  - Confidence: 0.85 (OCR default)")
            
            return ExtractedContent(
                text=full_text,
                tables=[],  # OCR doesn't extract tables well
                metadata={
                    "extraction_method": "pytesseract",
                    "dpi": self.dpi,
                    "pages_processed": len(images),
                    "successful_pages": successful_pages,
                    "total_characters": total_chars
                },
                confidence=0.85,  # OCR confidence
                pages_processed=len(images)
            )
        
        except Exception as e:
            logger.error(f"[Local OCR/PDF] Error in OCR extraction: {str(e)}", exc_info=True)
            raise
    
    async def _extract_image_ocr(self, file_path: str) -> ExtractedContent:
        """Extract text from image using OCR."""
        try:
            from PIL import Image
            
            image = Image.open(file_path)
            
            # Extract text
            text = image_to_string(image, lang='spa+eng')
            
            return ExtractedContent(
                text=text.strip(),
                tables=[],
                metadata={
                    "extraction_method": "pytesseract",
                    "dpi": self.dpi
                },
                confidence=0.85,
                pages_processed=1
            )
        
        except Exception as e:
            logger.error(f"Error in image OCR: {str(e)}")
            raise
