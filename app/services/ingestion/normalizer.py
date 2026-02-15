"""Document normalization to canonical Markdown format."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class DocumentStructure:
    """Detected document structure."""
    headings: List[Dict[str, Any]]  # {level: int, text: str, line: int}
    sections: List[Dict[str, Any]]  # {start: int, end: int, level: int}
    tables: List[Dict[str, Any]]  # {start: int, end: int, rows: int}
    lists: List[Dict[str, Any]]  # {start: int, end: int, type: str}


@dataclass
class NormalizedDocument:
    """Normalized document in Markdown format."""
    markdown: str
    structure: DocumentStructure
    quality_score: float
    metadata: Dict[str, Any]


class DocumentNormalizer:
    """Converts extracted content to canonical Markdown format."""
    
    def __init__(self):
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.table_pattern = re.compile(r'^\|.+\|$', re.MULTILINE)
    
    async def normalize(
        self,
        extracted_content: Any,  # ExtractedContent from extractors
        image_captions: List[Dict[str, Any]] = None
    ) -> NormalizedDocument:
        """
        Normalize extracted content to Markdown.
        
        Args:
            extracted_content: ExtractedContent object with text and tables
            image_captions: List of image captions to inject
        """
        logger.info("[Normalizer] Starting document normalization")
        logger.debug(f"[Normalizer] Extraction method: {extracted_content.metadata.get('extraction_method', 'unknown')}")
        logger.debug(f"[Normalizer] Original text length: {len(extracted_content.text)} chars")
        logger.debug(f"[Normalizer] Image captions to inject: {len(image_captions) if image_captions else 0}")
        
        if image_captions is None:
            image_captions = []
        
        # Start with extracted text
        text = extracted_content.text
        
        # Inject image captions at appropriate locations
        if image_captions:
            logger.debug("[Normalizer] Injecting image captions into document...")
            text = self._inject_image_captions(text, image_captions)
            logger.debug(f"[Normalizer] Text length after caption injection: {len(text)} chars")
        
        # Detect structure
        logger.debug("[Normalizer] Detecting document structure...")
        structure = self._detect_structure(text)
        logger.info(f"[Normalizer] Structure detected:")
        logger.info(f"  - Headings: {len(structure.headings)}")
        logger.info(f"  - Sections: {len(structure.sections)}")
        logger.info(f"  - Tables: {len(structure.tables)}")
        logger.info(f"  - Lists: {len(structure.lists)}")
        
        # Convert to Markdown (already mostly Markdown if from pdfplumber)
        logger.debug("[Normalizer] Converting to Markdown format...")
        markdown = self._convert_to_markdown(text, structure, extracted_content.tables)
        
        # Validate quality
        logger.debug("[Normalizer] Validating normalization quality...")
        quality_score = self._validate_quality(markdown, structure)
        logger.info(f"[Normalizer] Normalization complete - Quality score: {quality_score:.2f}")
        
        return NormalizedDocument(
            markdown=markdown,
            structure=structure,
            quality_score=quality_score,
            metadata={
                "extraction_method": extracted_content.metadata.get("extraction_method", "unknown"),
                "confidence": extracted_content.confidence,
                "pages_processed": extracted_content.pages_processed
            }
        )
    
    def _inject_image_captions(
        self,
        text: str,
        image_captions: List[Dict[str, Any]]
    ) -> str:
        """Inject image captions into text at appropriate locations."""
        if not image_captions:
            return text
        
        logger.debug(f"[Normalizer] Injecting {len(image_captions)} image caption(s) into document")
        
        # Group captions by page
        captions_by_page = {}
        for caption in image_captions:
            page = caption.get('page', 1)
            if page not in captions_by_page:
                captions_by_page[page] = []
            captions_by_page[page].append(caption)
            logger.debug(f"[Normalizer] Caption for page {page}: {caption['caption'][:100]}...")
        
        # Split text into lines for processing
        lines = text.split('\n')
        result_lines = []
        current_page = 1
        pages_processed = set()
        
        # Build a map of section numbers to page numbers (approximate)
        # This helps us associate images with sections
        section_to_pages = {}
        page_to_sections = {}
        
        # First pass: map sections to pages
        for i, line in enumerate(lines):
            # Detect page markers
            page_match = re.search(r'[Pp]ágina\s+(\d+)', line)
            if page_match:
                current_page = int(page_match.group(1))
            
            # Detect section markers (including sub-sections like 7.2, 7.3, etc.)
            section_match = re.search(r'(PUNTO|Punto|punto)\s+(\d+(?:\.\d+)?)', line, re.IGNORECASE)
            if section_match:
                section_num = section_match.group(2)
                if section_num not in section_to_pages:
                    section_to_pages[section_num] = []
                section_to_pages[section_num].append(current_page)
                if current_page not in page_to_sections:
                    page_to_sections[current_page] = []
                page_to_sections[current_page].append(section_num)
                logger.debug(f"[Normalizer] Mapped section {section_num} to page {current_page}")
        
        # Second pass: inject captions
        current_page = 1
        for i, line in enumerate(lines):
            result_lines.append(line)
            
            # Detect page markers
            page_match = re.search(r'[Pp]ágina\s+(\d+)', line)
            if page_match:
                current_page = int(page_match.group(1))
            
            # Detect section markers and inject captions after them (including sub-sections like 7.2)
            section_match = re.search(r'(PUNTO|Punto|punto)\s+(\d+(?:\.\d+)?)', line, re.IGNORECASE)
            if section_match:
                section_num = section_match.group(2)
                logger.debug(f"[Normalizer] Found section {section_num} at line {i}, injecting associated captions...")
                
                # Inject captions for pages associated with this section
                if section_num in section_to_pages:
                    for page in section_to_pages[section_num]:
                        if page in captions_by_page and page not in pages_processed:
                            # Inject immediately after section header
                            for caption in captions_by_page[page]:
                                # Format caption to include section context
                                caption_text = f"[Contenido de la página {page} - PUNTO {section_num}]: {caption['caption']}"
                                result_lines.append(f"\n{caption_text}\n")
                                logger.info(f"[Normalizer] ✓ Injected caption for page {page} (section {section_num})")
                            pages_processed.add(page)
                
                # Also check current page and nearby pages (sections might span multiple pages)
                pages_to_check = [current_page, current_page + 1, current_page - 1]
                for nearby_page in pages_to_check:
                    if nearby_page in captions_by_page and nearby_page not in pages_processed:
                        for caption in captions_by_page[nearby_page]:
                            # Check if caption mentions this section or parent section
                            caption_lower = caption['caption'].lower()
                            section_base = section_num.split('.')[0]  # Get base section (e.g., "7" from "7.2")
                            
                            # Check for exact match or parent section match
                            if (f"punto {section_num}" in caption_lower or 
                                f"punto{section_num}" in caption_lower or
                                f"punto {section_base}" in caption_lower or
                                f"punto{section_base}" in caption_lower):
                                caption_text = f"[Contenido de la página {nearby_page} - PUNTO {section_num}]: {caption['caption']}"
                                result_lines.append(f"\n{caption_text}\n")
                                logger.info(f"[Normalizer] ✓ Injected caption for page {nearby_page} (matches section {section_num})")
                            else:
                                # Inject anyway if it's on the same page as the section
                                caption_text = f"[Contenido de la página {nearby_page} - PUNTO {section_num}]: {caption['caption']}"
                                result_lines.append(f"\n{caption_text}\n")
                                logger.debug(f"[Normalizer] Injected caption for nearby page {nearby_page} (section {section_num})")
                        pages_processed.add(nearby_page)
            
            # Inject captions after page markers (if not already processed)
            if current_page in captions_by_page and current_page not in pages_processed:
                # Check if this page is associated with a section we've seen
                if current_page in page_to_sections:
                    # Already handled by section injection
                    pages_processed.add(current_page)
                else:
                    # Inject after page marker
                    for caption in captions_by_page[current_page]:
                        result_lines.append(f"\n[Contenido visual de la página {current_page}]: {caption['caption']}\n")
                        logger.debug(f"[Normalizer] Injected caption for page {current_page} after page marker")
                    pages_processed.add(current_page)
        
        # Add any remaining captions at the end
        for page, captions in captions_by_page.items():
            if page not in pages_processed:
                for caption in captions:
                    result_lines.append(f"\n[Contenido visual de la página {page}]: {caption['caption']}\n")
                    logger.debug(f"[Normalizer] Injected remaining caption for page {page} at end")
        
        result = '\n'.join(result_lines)
        logger.info(f"[Normalizer] Successfully injected {len(image_captions)} caption(s) into document")
        return result
    
    def _detect_structure(self, text: str) -> DocumentStructure:
        """Detect document structure (headings, sections, tables, lists)."""
        lines = text.split('\n')
        
        headings = []
        sections = []
        tables = []
        lists = []
        
        current_section_start = 0
        current_table_start = None
        in_table = False
        
        for i, line in enumerate(lines):
            # Detect headings
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if heading_match:
                level = len(heading_match.group(1))
                headings.append({
                    'level': level,
                    'text': heading_match.group(2),
                    'line': i
                })
                
                # End previous section
                if current_section_start < i:
                    sections.append({
                        'start': current_section_start,
                        'end': i - 1,
                        'level': headings[-2]['level'] if len(headings) > 1 else 1
                    })
                
                current_section_start = i
            
            # Detect tables
            if '|' in line and line.count('|') >= 2:
                if not in_table:
                    current_table_start = i
                    in_table = True
            else:
                if in_table and current_table_start is not None:
                    tables.append({
                        'start': current_table_start,
                        'end': i - 1,
                        'rows': i - current_table_start
                    })
                    in_table = False
                    current_table_start = None
            
            # Detect lists (simple heuristic)
            if re.match(r'^[\*\-\+]\s+', line.strip()) or re.match(r'^\d+\.\s+', line.strip()):
                if not lists or lists[-1]['end'] < i - 1:
                    lists.append({
                        'start': i,
                        'end': i,
                        'type': 'unordered' if re.match(r'^[\*\-\+]', line.strip()) else 'ordered'
                    })
                else:
                    lists[-1]['end'] = i
        
        # Close final section
        if current_section_start < len(lines):
            sections.append({
                'start': current_section_start,
                'end': len(lines) - 1,
                'level': headings[-1]['level'] if headings else 1
            })
        
        return DocumentStructure(
            headings=headings,
            sections=sections,
            tables=tables,
            lists=lists
        )
    
    def _convert_to_markdown(
        self,
        text: str,
        structure: DocumentStructure,
        tables: List[List[List[str]]]
    ) -> str:
        """Convert text to proper Markdown format."""
        # Text is likely already in Markdown-like format
        # Just ensure proper formatting
        
        # Ensure tables are properly formatted
        lines = text.split('\n')
        result_lines = []
        
        for line in lines:
            # Ensure table rows are properly formatted
            if '|' in line and line.count('|') >= 2:
                # Clean up table row
                line = '| ' + ' | '.join(cell.strip() for cell in line.split('|')[1:-1]) + ' |'
            
            result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    def _validate_quality(
        self,
        markdown: str,
        structure: DocumentStructure
    ) -> float:
        """Validate normalization quality."""
        score = 1.0
        
        # Check if text is not empty
        if not markdown.strip():
            score *= 0.0
        
        # Check structure preservation
        if structure.headings:
            score *= 1.0  # Good structure
        else:
            score *= 0.9  # No headings but still valid
        
        # Check table preservation
        if structure.tables or markdown.count('|') > 10:
            score *= 1.0  # Tables preserved
        else:
            score *= 0.95  # No tables, but that's OK
        
        return score
