"""Document intelligence service for analyzing documents and determining extraction strategy."""

from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging
import pdfplumber
import io
from pathlib import Path

logger = logging.getLogger(__name__)


class ExtractionStrategy(str, Enum):
    """Extraction strategy types."""
    LOCAL_PARSER = "local_parser"
    LOCAL_OCR = "local_ocr"
    CLOUD_OCR = "cloud_ocr"
    HYBRID = "hybrid"


@dataclass
class DocumentAnalysis:
    """Analysis result for a document."""
    strategy: ExtractionStrategy
    confidence: float
    estimated_pages: int
    text_coverage: float  # Percentage of pages with extractable text
    layout_complexity: str  # "simple", "moderate", "complex"
    requires_ocr: bool
    requires_vision: bool
    file_type: str


@dataclass
class SampleTextResult:
    """Result of sampling text from document."""
    text: str
    coverage: float  # Percentage of pages with text
    confidence: float
    page_count: int


class DocumentIntelligenceService:
    """Analyzes documents and determines optimal extraction strategy."""
    
    def __init__(self):
        self.text_coverage_threshold = 0.5  # 50% of pages need text
        self.complex_layout_keywords = [
            "form", "table", "multi-column", "handwriting", "signature"
        ]
        self.min_text_per_page = 50  # Minimum characters to consider page as having text
    
    async def analyze_document(
        self,
        file_path: str,
        file_type: str,
        file_size: int
    ) -> DocumentAnalysis:
        """
        Analyze document and determine extraction strategy.
        
        Decision Tree:
        1. Try local text extraction (first page)
        2. If text coverage > 50% → Local Parser
        3. If text coverage < 10% and pages < 5 → Local OCR
        4. If text coverage < 10% and pages >= 5 → Cloud OCR
        5. If complex layout detected → Cloud OCR
        6. If mixed (10-50%) → Hybrid
        """
        logger.info(f"[Document Intelligence] Starting analysis for file: {file_path}")
        logger.debug(f"[Document Intelligence] File type: {file_type}, Size: {file_size} bytes")
        
        # Quick text extraction test
        logger.debug("[Document Intelligence] Extracting sample text for analysis...")
        sample_analysis = await self._extract_sample_text(file_path, file_type)
        
        logger.info(f"[Document Intelligence] Sample analysis results:")
        logger.info(f"  - Text coverage: {sample_analysis.coverage:.2%}")
        logger.info(f"  - Confidence: {sample_analysis.confidence:.2%}")
        logger.info(f"  - Estimated pages: {sample_analysis.page_count}")
        logger.debug(f"  - Sample text length: {len(sample_analysis.text)} chars")
        
        # Estimate page count
        estimated_pages = sample_analysis.page_count
        
        # Detect layout complexity
        logger.debug("[Document Intelligence] Detecting layout complexity...")
        layout_complexity = await self._detect_layout_complexity(
            file_path,
            file_type,
            sample_analysis
        )
        logger.info(f"[Document Intelligence] Layout complexity: {layout_complexity}")
        
        # Determine strategy
        logger.debug("[Document Intelligence] Determining extraction strategy...")
        strategy = self._determine_strategy(
            file_type=file_type,
            text_coverage=sample_analysis.coverage,
            estimated_pages=estimated_pages,
            layout_complexity=layout_complexity
        )
        
        logger.info(f"[Document Intelligence] Selected strategy: {strategy.value}")
        logger.debug(f"[Document Intelligence] Strategy decision factors:")
        logger.debug(f"  - File type: {file_type}")
        logger.debug(f"  - Text coverage: {sample_analysis.coverage:.2%} (threshold: {self.text_coverage_threshold:.2%})")
        logger.debug(f"  - Pages: {estimated_pages}")
        logger.debug(f"  - Layout: {layout_complexity}")
        
        analysis = DocumentAnalysis(
            strategy=strategy,
            confidence=sample_analysis.confidence,
            estimated_pages=estimated_pages,
            text_coverage=sample_analysis.coverage,
            layout_complexity=layout_complexity,
            requires_ocr=strategy in [
                ExtractionStrategy.LOCAL_OCR,
                ExtractionStrategy.CLOUD_OCR,
                ExtractionStrategy.HYBRID
            ],
            requires_vision=file_type in ["image", "pdf"],
            file_type=file_type
        )
        
        logger.info(f"[Document Intelligence] Analysis complete:")
        logger.info(f"  - Strategy: {analysis.strategy.value}")
        logger.info(f"  - Requires OCR: {analysis.requires_ocr}")
        logger.info(f"  - Requires Vision: {analysis.requires_vision}")
        
        return analysis
    
    def _determine_strategy(
        self,
        file_type: str,
        text_coverage: float,
        estimated_pages: int,
        layout_complexity: str
    ) -> ExtractionStrategy:
        """Decision tree for extraction strategy."""
        
        from app.core.config import settings
        
        logger.debug(f"[Strategy Decision] Evaluating strategy for file_type={file_type}, "
                    f"coverage={text_coverage:.2%}, pages={estimated_pages}, layout={layout_complexity}")
        logger.debug(f"[Strategy Decision] Cloud OCR enabled: {settings.ENABLE_CLOUD_OCR}, provider: {settings.CLOUD_OCR_PROVIDER}")
        
        # Check if Cloud OCR is available and properly configured
        cloud_ocr_available = False
        if settings.ENABLE_CLOUD_OCR:
            # Check if credentials are configured
            if settings.CLOUD_OCR_PROVIDER.lower() == "aws":
                cloud_ocr_available = bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY)
            elif settings.CLOUD_OCR_PROVIDER.lower() == "azure":
                cloud_ocr_available = bool(settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and settings.AZURE_DOCUMENT_INTELLIGENCE_KEY)
            
            if not cloud_ocr_available:
                logger.warning(f"[Strategy Decision] Cloud OCR enabled but credentials not configured for provider: {settings.CLOUD_OCR_PROVIDER}")
        
        # Native digital formats always use local parser
        if file_type in ["docx", "html", "txt"]:
            logger.debug(f"[Strategy Decision] Native digital format → LOCAL_PARSER")
            return ExtractionStrategy.LOCAL_PARSER
        
        # If Cloud OCR is available, prioritize it for:
        # 1. Complex layouts (tables, multi-column)
        # 2. Documents with moderate/complex layouts that might have images
        # 3. Large documents (more cost-efficient than local processing)
        if cloud_ocr_available:
            if layout_complexity in ["complex", "moderate"]:
                logger.debug(f"[Strategy Decision] Cloud OCR available + {layout_complexity} layout → CLOUD_OCR (better table extraction)")
                return ExtractionStrategy.CLOUD_OCR
            
            if estimated_pages >= 5:
                logger.debug(f"[Strategy Decision] Cloud OCR available + large doc ({estimated_pages} pages) → CLOUD_OCR (more efficient)")
                return ExtractionStrategy.CLOUD_OCR
        
        # PDF with good text coverage → Local parser
        if text_coverage >= self.text_coverage_threshold:
            logger.debug(f"[Strategy Decision] High text coverage ({text_coverage:.2%} >= {self.text_coverage_threshold:.2%}) → LOCAL_PARSER")
            return ExtractionStrategy.LOCAL_PARSER
        
        # Complex layouts → Cloud OCR (if available) or Local OCR
        if layout_complexity == "complex":
            if cloud_ocr_available:
                logger.debug(f"[Strategy Decision] Complex layout → CLOUD_OCR")
                return ExtractionStrategy.CLOUD_OCR
            else:
                logger.debug(f"[Strategy Decision] Complex layout → LOCAL_OCR (Cloud OCR not available)")
                return ExtractionStrategy.LOCAL_OCR
        
        # Low text coverage, small document → Local OCR
        if text_coverage < 0.1 and estimated_pages < 5:
            logger.debug(f"[Strategy Decision] Low coverage ({text_coverage:.2%}) + small doc ({estimated_pages} pages) → LOCAL_OCR")
            return ExtractionStrategy.LOCAL_OCR
        
        # Low text coverage, large document → Cloud OCR (cost-efficient) or Local OCR
        if text_coverage < 0.1 and estimated_pages >= 5:
            if cloud_ocr_available:
                logger.debug(f"[Strategy Decision] Low coverage ({text_coverage:.2%}) + large doc ({estimated_pages} pages) → CLOUD_OCR")
                return ExtractionStrategy.CLOUD_OCR
            else:
                logger.debug(f"[Strategy Decision] Low coverage ({text_coverage:.2%}) + large doc ({estimated_pages} pages) → LOCAL_OCR")
                return ExtractionStrategy.LOCAL_OCR
        
        # Mixed coverage → Hybrid or Cloud OCR
        if 0.1 <= text_coverage < self.text_coverage_threshold:
            if cloud_ocr_available and layout_complexity != "simple":
                logger.debug(f"[Strategy Decision] Mixed coverage ({text_coverage:.2%}) + {layout_complexity} layout → CLOUD_OCR")
                return ExtractionStrategy.CLOUD_OCR
            else:
                logger.debug(f"[Strategy Decision] Mixed coverage ({text_coverage:.2%}) → HYBRID")
                return ExtractionStrategy.HYBRID
        
        # Default to local parser
        logger.debug(f"[Strategy Decision] Default fallback → LOCAL_PARSER")
        return ExtractionStrategy.LOCAL_PARSER
    
    async def _extract_sample_text(
        self,
        file_path: str,
        file_type: str
    ) -> SampleTextResult:
        """Extract text from first few pages to assess document."""
        try:
            if file_type == "pdf":
                return await self._sample_pdf_text(file_path)
            elif file_type == "docx":
                # DOCX always has text, return high coverage
                return SampleTextResult(
                    text="",
                    coverage=1.0,
                    confidence=1.0,
                    page_count=1  # Will be updated
                )
            elif file_type in ["png", "jpg", "jpeg", "tiff"]:
                # Images have no text
                return SampleTextResult(
                    text="",
                    coverage=0.0,
                    confidence=1.0,
                    page_count=1
                )
            else:
                # Unknown type, assume no text
                return SampleTextResult(
                    text="",
                    coverage=0.0,
                    confidence=0.5,
                    page_count=1
                )
        except Exception as e:
            logger.error(f"Error sampling text: {str(e)}")
            return SampleTextResult(
                text="",
                coverage=0.0,
                confidence=0.0,
                page_count=1
            )
    
    async def _sample_pdf_text(self, file_path: str) -> SampleTextResult:
        """Sample text from first 3 pages of PDF."""
        try:
            with open(file_path, 'rb') as f:
                pdf_file = io.BytesIO(f.read())
            
            with pdfplumber.open(pdf_file) as pdf:
                total_pages = len(pdf.pages)
                sample_pages = min(3, total_pages)
                
                pages_with_text = 0
                total_text = ""
                
                for i in range(sample_pages):
                    page = pdf.pages[i]
                    page_text = page.extract_text() or ""
                    
                    if len(page_text.strip()) >= self.min_text_per_page:
                        pages_with_text += 1
                        total_text += page_text + "\n"
                
                # Calculate coverage
                coverage = pages_with_text / sample_pages if sample_pages > 0 else 0.0
                
                # Confidence based on sample size
                confidence = min(1.0, sample_pages / 3.0)
                
                return SampleTextResult(
                    text=total_text,
                    coverage=coverage,
                    confidence=confidence,
                    page_count=total_pages
                )
        except Exception as e:
            logger.error(f"Error sampling PDF text: {str(e)}")
            return SampleTextResult(
                text="",
                coverage=0.0,
                confidence=0.0,
                page_count=1
            )
    
    async def _detect_layout_complexity(
        self,
        file_path: str,
        file_type: str,
        sample_analysis: SampleTextResult
    ) -> str:
        """Detect if document has complex layout."""
        if file_type != "pdf":
            return "simple"
        
        # Check sample text for complex layout indicators
        text_lower = sample_analysis.text.lower()
        
        complex_indicators = sum(
            1 for keyword in self.complex_layout_keywords
            if keyword in text_lower
        )
        
        # Check for tables (multiple pipe characters or tabs)
        has_tables = "|" in sample_analysis.text or "\t" in sample_analysis.text
        
        # Check for multi-column (multiple newlines in short space)
        lines = sample_analysis.text.split('\n')
        short_lines = sum(1 for line in lines if 0 < len(line.strip()) < 30)
        likely_multi_column = short_lines > len(lines) * 0.3
        
        if complex_indicators >= 2 or (has_tables and likely_multi_column):
            return "complex"
        elif complex_indicators >= 1 or has_tables:
            return "moderate"
        else:
            return "simple"
