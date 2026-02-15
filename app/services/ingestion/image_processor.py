"""Image extraction and caption generation using Vision API."""

from typing import List, Dict, Any, Optional
import logging
import base64
import io
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional imports
try:
    from pdf2image import convert_from_bytes
    from PIL import Image
    IMAGE_PROCESSING_AVAILABLE = True
except ImportError:
    IMAGE_PROCESSING_AVAILABLE = False
    logger.warning("Image processing libraries not available.")

from app.core.openai_client import client as openai_client
from app.core.config import settings


class ImageProcessor:
    """Extracts images from documents and generates captions."""
    
    def __init__(self):
        self.min_image_size = (100, 100)  # Skip tiny images
        self.max_images_per_page = 5
        self.max_images_per_document = settings.MAX_IMAGES_PER_DOCUMENT
        
        logger.info(f"[Image Processor] Initializing image processor")
        logger.debug(f"[Image Processor] Image captions enabled: {settings.ENABLE_IMAGE_CAPTIONS}")
        logger.debug(f"[Image Processor] Max images per document: {self.max_images_per_document}")
        logger.debug(f"[Image Processor] Image processing available: {IMAGE_PROCESSING_AVAILABLE}")
        logger.debug(f"[Image Processor] Caption model: {settings.IMAGE_CAPTION_MODEL}")
    
    async def extract_and_caption_images(
        self,
        document_path: str,
        document_type: str
    ) -> List[Dict[str, Any]]:
        """
        Extract images and generate captions.
        
        Returns list of:
        {
            'image_id': str,
            'page': int,
            'caption': str,
            'confidence': float,
            'image_type': str
        }
        """
        logger.info(f"[Image Processor] Starting image extraction for {document_type} file: {document_path}")
        
        if not IMAGE_PROCESSING_AVAILABLE:
            logger.warning("[Image Processor] Image processing not available, skipping image extraction")
            return []
        
        if not settings.ENABLE_IMAGE_CAPTIONS:
            logger.debug("[Image Processor] Image captions disabled in config")
            return []
        
        # Extract images from document
        logger.debug("[Image Processor] Extracting images from document...")
        images = await self._extract_images(document_path, document_type)
        logger.info(f"[Image Processor] Extracted {len(images)} image(s) from document")
        
        # Filter relevant images
        logger.debug("[Image Processor] Filtering relevant images...")
        relevant_images = self._filter_relevant_images(images)
        logger.info(f"[Image Processor] {len(relevant_images)} relevant image(s) after filtering (from {len(images)} total)")
        
        # Limit number of images (but prioritize full pages)
        # Separate full pages from embedded images
        full_pages = [img for img in relevant_images if img.get('type') == 'full_page']
        embedded = [img for img in relevant_images if img.get('type') != 'full_page']
        
        # Always process all full pages (they contain document content)
        # Only limit embedded images if needed
        if len(relevant_images) > self.max_images_per_document:
            # Keep all full pages, limit embedded images
            remaining_slots = self.max_images_per_document - len(full_pages)
            if remaining_slots > 0:
                embedded = embedded[:remaining_slots]
            else:
                embedded = []  # No slots for embedded images
            relevant_images = full_pages + embedded
            logger.info(f"[Image Processor] Limited to {len(relevant_images)} image(s): {len(full_pages)} full pages + {len(embedded)} embedded")
        
        # Generate captions for ALL relevant images
        logger.info(f"[Image Processor] Generating captions for {len(relevant_images)} image(s) using {settings.IMAGE_CAPTION_MODEL}...")
        captions = []
        for idx, image in enumerate(relevant_images, 1):
            try:
                page_num = image.get('page', 'unknown')
                image_type = image.get('type', 'unknown')
                logger.debug(f"[Image Processor] Processing image {idx}/{len(relevant_images)}: {image['id']} (page {page_num}, type: {image_type})")
                
                # For full page images, use a more specific prompt to extract text and structure
                if image_type == 'full_page':
                    caption = await self._generate_caption_for_page(image, page_num)
                else:
                    caption = await self._generate_caption(image)
                
                captions.append({
                    'image_id': image['id'],
                    'page': page_num,
                    'caption': caption['text'],
                    'confidence': caption['confidence'],
                    'image_type': image_type
                })
                logger.info(f"[Image Processor] Generated caption for page {page_num}: {len(caption['text'])} chars")
                logger.debug(f"[Image Processor] Caption preview: {caption['text'][:200]}...")
            except Exception as e:
                logger.warning(f"[Image Processor] Failed to generate caption for image {image['id']}: {str(e)}", exc_info=True)
                continue
        
        logger.info(f"[Image Processor] Successfully generated {len(captions)} caption(s)")
        return captions
    
    async def _extract_images(
        self,
        document_path: str,
        document_type: str
    ) -> List[Dict[str, Any]]:
        """Extract images from document."""
        images = []
        
        if document_type == "pdf":
            images = await self._extract_images_from_pdf(document_path)
        elif document_type in ["png", "jpg", "jpeg", "tiff"]:
            # Document itself is an image
            images = [{
                'id': f"img_0",
                'page': 1,
                'path': document_path,
                'type': 'photo'
            }]
        
        return images
    
    async def _extract_images_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract images from PDF - both embedded images and full pages with images."""
        try:
            import pdfplumber
            from PIL import Image as PILImage
            
            images = []
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            # First, try to extract embedded images from PDF
            logger.debug("[Image Processor] Attempting to extract embedded images from PDF...")
            embedded_images = await self._extract_embedded_images(pdf_path)
            logger.info(f"[Image Processor] Found {len(embedded_images)} embedded image(s)")
            images.extend(embedded_images)
            
            # Also convert ALL pages to images for Vision API analysis
            # This is important because some pages might have images or content that wasn't extracted as text
            logger.debug("[Image Processor] Converting ALL PDF pages to images for Vision API analysis...")
            pdf_images = convert_from_bytes(pdf_bytes, dpi=200)
            logger.info(f"[Image Processor] Converted {len(pdf_images)} page(s) to images")
            
            for page_num, pil_image in enumerate(pdf_images, 1):
                # Convert each page to base64 for Vision API
                buffered = io.BytesIO()
                pil_image.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                
                images.append({
                    'id': f"page_{page_num}",
                    'page': page_num,
                    'base64': img_base64,
                    'width': pil_image.width,
                    'height': pil_image.height,
                    'type': 'full_page',  # Full page image for Vision API
                    'is_embedded': False
                })
                logger.debug(f"[Image Processor] Added page {page_num} image ({pil_image.width}x{pil_image.height})")
            
            logger.info(f"[Image Processor] Total images extracted: {len(images)} ({len(embedded_images)} embedded + {len(pdf_images)} full pages)")
            return images
        
        except Exception as e:
            logger.error(f"[Image Processor] Error extracting images from PDF: {str(e)}", exc_info=True)
            return []
    
    async def _extract_embedded_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract embedded images from PDF using pdfplumber."""
        try:
            import pdfplumber
            
            embedded_images = []
            with open(pdf_path, 'rb') as f:
                pdf_file = io.BytesIO(f.read())
            
            with pdfplumber.open(pdf_file) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract images from page
                    page_images = page.images
                    
                    for img_idx, img in enumerate(page_images):
                        try:
                            # Get image object
                            if hasattr(page, 'get_image') or hasattr(page, 'images'):
                                # Try to extract image data
                                # pdfplumber doesn't directly extract image bytes, so we'll use the page image
                                # For now, we'll process full pages, but mark embedded ones
                                embedded_images.append({
                                    'id': f"embedded_p{page_num}_i{img_idx}",
                                    'page': page_num,
                                    'x0': img.get('x0', 0),
                                    'y0': img.get('y0', 0),
                                    'x1': img.get('x1', 0),
                                    'y1': img.get('y1', 0),
                                    'width': img.get('width', 0),
                                    'height': img.get('height', 0),
                                    'type': 'embedded',
                                    'is_embedded': True
                                })
                                logger.debug(f"[Image Processor] Found embedded image on page {page_num}: {img.get('width', 0)}x{img.get('height', 0)}")
                        except Exception as e:
                            logger.debug(f"[Image Processor] Error processing embedded image on page {page_num}: {str(e)}")
                            continue
            
            return embedded_images
        
        except Exception as e:
            logger.warning(f"[Image Processor] Error extracting embedded images: {str(e)}")
            return []
    
    async def _generate_caption(self, image: Dict) -> Dict[str, Any]:
        """Generate caption using OpenAI Vision API."""
        if not openai_client:
            return {
                'text': f"[Image on page {image.get('page', 'unknown')}]",
                'confidence': 0.0
            }
        
        try:
            # Get image data
            if 'base64' in image:
                image_url = f"data:image/png;base64,{image['base64']}"
            elif 'path' in image:
                # Read image file
                with open(image['path'], 'rb') as f:
                    img_bytes = f.read()
                    img_base64 = base64.b64encode(img_bytes).decode()
                    image_url = f"data:image/png;base64,{img_base64}"
            else:
                return {
                    'text': f"[Image on page {image.get('page', 'unknown')}]",
                    'confidence': 0.0
                }
            
            # Enhanced prompt specifically for tables and structured data
            prompt_text = """Extract ALL text from this image verbatim, especially from tables, lists, and structured data. 

For tables:
- Include ALL column headers exactly as shown
- Include ALL row data exactly as shown
- Preserve the table structure with clear row and column separators
- Include row numbers, codes (like V1, V2, etc.), and all text content

For any text in the image:
- Copy it EXACTLY as it appears, including:
  - Numbers, codes, identifiers
  - Technical terms, descriptions
  - Any labels, headers, or captions
- Do not summarize or paraphrase
- Include punctuation and formatting marks

If this is a table or structured list, format it as a markdown table or structured list. Include every piece of text visible in the image."""

            response = await openai_client.chat.completions.create(
                model=settings.IMAGE_CAPTION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt_text
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000  # Increased significantly for tables with lots of text
            )
            
            caption_text = response.choices[0].message.content
            
            return {
                'text': caption_text,
                'confidence': 0.95  # OpenAI Vision is highly reliable
            }
        
        except Exception as e:
            logger.error(f"[Image Processor] Caption generation failed: {str(e)}", exc_info=True)
            return {
                'text': f"[Image on page {image.get('page', 'unknown')}]",
                'confidence': 0.0
            }
    
    async def _generate_caption_for_page(self, image: Dict, page_num: int) -> Dict[str, Any]:
        """Generate detailed caption for a full page image, focusing on extracting all text and structure."""
        if not openai_client:
            return {
                'text': f"[Page {page_num} content]",
                'confidence': 0.0
            }
        
        try:
            image_url = f"data:image/png;base64,{image['base64']}"
            
            # More detailed prompt for full page images
            prompt = f"""You are analyzing page {page_num} of a Spanish document (acta de junta de propietarios).

CRITICAL INSTRUCTIONS - Extract EVERYTHING:

1. SECTION HEADINGS: If you see "PUNTO 7", "PUNTO 7.2", "PUNTO 8", etc., include the COMPLETE section number and ALL content under it.

2. TABLES: Extract ALL tables COMPLETELY:
   - Include ALL column headers (N°, DEFICIENCIA, SOLUCIÓN, etc.)
   - Include ALL row data (V1, V2, H1, H2, etc. and their descriptions)
   - Include ALL text in each cell verbatim
   - Preserve table structure with clear row/column separation
   - Example: If you see "V1 | Grietas y fisuras en pavimentos..." extract it EXACTLY

3. STRUCTURED DATA: Extract all:
   - Lists with bullet points or numbers
   - Any codes, identifiers (like V1, V2, H1, H2)
   - Technical terms, descriptions
   - Numerical data, percentages, amounts

4. FORMAT: Structure your response as:
   - If there's a section: "PUNTO X.Y: [all content]"
   - For tables: Format as markdown table or structured list with ALL data
   - Include EVERY piece of text visible

5. BE EXHAUSTIVE: The text extraction may have missed content. Extract EVERYTHING you can see, especially:
   - Text in tables
   - Section content
   - Any structured information

DO NOT summarize. Copy text EXACTLY as it appears."""

            response = await openai_client.chat.completions.create(
                model=settings.IMAGE_CAPTION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000  # Increased for full page analysis with tables and structured data
            )
            
            caption_text = response.choices[0].message.content
            
            logger.debug(f"[Image Processor] Generated detailed caption for page {page_num}: {len(caption_text)} chars")
            
            return {
                'text': caption_text,
                'confidence': 0.95
            }
        
        except Exception as e:
            logger.error(f"[Image Processor] Failed to generate page caption: {str(e)}", exc_info=True)
            return {
                'text': f"[Page {page_num} content - extraction failed]",
                'confidence': 0.0
            }
    
    def _filter_relevant_images(self, images: List[Dict]) -> List[Dict]:
        """Filter out decorative images (logos, watermarks)."""
        relevant = []
        full_pages = []
        embedded = []
        
        for image in images:
            # Full page images should always be processed (they might contain important content)
            if image.get('type') == 'full_page':
                full_pages.append(image)
                logger.debug(f"[Image Processor] Including full page image: {image['id']} (page {image.get('page')})")
            else:
                embedded.append(image)
        
        # Process all full pages (they contain document content)
        relevant.extend(full_pages)
        logger.info(f"[Image Processor] Processing {len(full_pages)} full page image(s) for Vision API")
        
        # For embedded images, apply filtering
        for image in embedded:
            width = image.get('width', 0)
            height = image.get('height', 0)
            
            # Skip if too small
            if width < self.min_image_size[0] or height < self.min_image_size[1]:
                logger.debug(f"[Image Processor] Skipping small embedded image: {image['id']} ({width}x{height})")
                continue
            
            # Skip if likely decorative (heuristic)
            if self._is_decorative(image):
                logger.debug(f"[Image Processor] Skipping decorative embedded image: {image['id']}")
                continue
            
            relevant.append(image)
            logger.debug(f"[Image Processor] Including relevant embedded image: {image['id']}")
        
        logger.info(f"[Image Processor] Total relevant images: {len(relevant)} ({len(full_pages)} full pages + {len(relevant) - len(full_pages)} embedded)")
        return relevant
    
    def _is_decorative(self, image: Dict) -> bool:
        """Heuristic to detect decorative images."""
        # Don't filter full page images
        if image.get('type') == 'full_page':
            return False
        
        # Simple heuristics - can be improved with ML
        width = image.get('width', 0)
        height = image.get('height', 0)
        
        # Very small images are likely decorative
        if width < 200 or height < 200:
            return True
        
        # Square images might be logos (but not always)
        aspect_ratio = width / height if height > 0 else 1
        if 0.9 < aspect_ratio < 1.1 and width < 300:
            return True
        
        return False
