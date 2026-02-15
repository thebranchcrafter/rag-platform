# Implementation Guide: Next-Generation RAG Architecture

## Quick Start: Implementation Checklist

This guide provides concrete code structure and implementation steps for the architecture outlined in `ARCHITECTURE.md`.

---

## 1. Project Structure

```
app/
├── services/
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── document_receiver.py      # Phase 1: Reception
│   │   ├── document_intelligence.py  # Phase 2: Analysis & Routing
│   │   ├── text_extractors/
│   │   │   ├── __init__.py
│   │   │   ├── local_parser.py       # pdfplumber, docx, HTML
│   │   │   ├── local_ocr.py          # pytesseract
│   │   │   └── cloud_ocr.py          # AWS Textract, Azure DI
│   │   ├── image_processor.py        # Phase 3: Image extraction & vision
│   │   ├── normalizer.py             # Phase 4: Markdown conversion
│   │   ├── semantic_chunker.py       # Phase 5: Advanced chunking
│   │   └── embedder.py               # Phase 6: Embedding generation
│   ├── retrieval/
│   │   ├── multi_stage_retrieval.py  # Enhanced retrieval
│   │   └── reranking_service.py     # Cross-encoder reranking
│   └── observability/
│       ├── metrics.py                # Ingestion & retrieval metrics
│       └── quality_scorer.py         # Chunk quality scoring
├── api/
│   └── upload.py                     # Updated upload endpoint
└── core/
    ├── config.py                     # Configuration
    └── cloud_clients.py              # AWS, Azure clients
```

---

## 2. Core Implementation Files

### 2.1 Document Intelligence Service

**File: `app/services/ingestion/document_intelligence.py`**

```python
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ExtractionStrategy(str, Enum):
    LOCAL_PARSER = "local_parser"
    LOCAL_OCR = "local_ocr"
    CLOUD_OCR = "cloud_ocr"
    HYBRID = "hybrid"


@dataclass
class DocumentAnalysis:
    strategy: ExtractionStrategy
    confidence: float
    estimated_pages: int
    text_coverage: float  # Percentage of pages with extractable text
    layout_complexity: str  # "simple", "moderate", "complex"
    requires_ocr: bool
    requires_vision: bool


class DocumentIntelligenceService:
    """Analyzes documents and determines optimal extraction strategy."""
    
    def __init__(self):
        self.text_coverage_threshold = 0.5  # 50% of pages need text
        self.complex_layout_keywords = [
            "form", "table", "multi-column", "handwriting"
        ]
    
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
        # Quick text extraction test
        sample_analysis = await self._extract_sample_text(file_path, file_type)
        
        # Estimate page count
        estimated_pages = await self._estimate_page_count(file_path, file_type)
        
        # Detect layout complexity
        layout_complexity = await self._detect_layout_complexity(
            file_path, 
            file_type,
            sample_analysis
        )
        
        # Determine strategy
        strategy = self._determine_strategy(
            file_type=file_type,
            text_coverage=sample_analysis.coverage,
            estimated_pages=estimated_pages,
            layout_complexity=layout_complexity
        )
        
        return DocumentAnalysis(
            strategy=strategy,
            confidence=sample_analysis.confidence,
            estimated_pages=estimated_pages,
            text_coverage=sample_analysis.coverage,
            layout_complexity=layout_complexity,
            requires_ocr=strategy in [ExtractionStrategy.LOCAL_OCR, 
                                     ExtractionStrategy.CLOUD_OCR,
                                     ExtractionStrategy.HYBRID],
            requires_vision=file_type in ["image", "pdf"]  # Check for images
        )
    
    def _determine_strategy(
        self,
        file_type: str,
        text_coverage: float,
        estimated_pages: int,
        layout_complexity: str
    ) -> ExtractionStrategy:
        """Decision tree for extraction strategy."""
        
        # Native digital formats always use local parser
        if file_type in ["docx", "html", "txt"]:
            return ExtractionStrategy.LOCAL_PARSER
        
        # PDF with good text coverage
        if text_coverage >= self.text_coverage_threshold:
            return ExtractionStrategy.LOCAL_PARSER
        
        # Complex layouts → Cloud OCR
        if layout_complexity == "complex":
            return ExtractionStrategy.CLOUD_OCR
        
        # Low text coverage, small document → Local OCR
        if text_coverage < 0.1 and estimated_pages < 5:
            return ExtractionStrategy.LOCAL_OCR
        
        # Low text coverage, large document → Cloud OCR (cost-efficient)
        if text_coverage < 0.1 and estimated_pages >= 5:
            return ExtractionStrategy.CLOUD_OCR
        
        # Mixed coverage → Hybrid
        if 0.1 <= text_coverage < self.text_coverage_threshold:
            return ExtractionStrategy.HYBRID
        
        # Default to local parser
        return ExtractionStrategy.LOCAL_PARSER
    
    async def _extract_sample_text(
        self, 
        file_path: str, 
        file_type: str
    ) -> Dict[str, Any]:
        """Extract text from first page to assess document."""
        # Implementation: Extract first page only
        # Return: {coverage: float, confidence: float, text: str}
        pass
    
    async def _estimate_page_count(
        self, 
        file_path: str, 
        file_type: str
    ) -> int:
        """Estimate number of pages in document."""
        # Implementation: Quick page count
        pass
    
    async def _detect_layout_complexity(
        self,
        file_path: str,
        file_type: str,
        sample_analysis: Dict[str, Any]
    ) -> str:
        """Detect if document has complex layout."""
        # Check for forms, tables, multi-column layouts
        # Return: "simple", "moderate", "complex"
        pass
```

### 2.2 Cloud OCR Integration

**File: `app/services/ingestion/text_extractors/cloud_ocr.py`**

```python
import boto3
from typing import List, Dict, Any
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class CloudOCRService:
    """Handles cloud OCR using AWS Textract or Azure Document Intelligence."""
    
    def __init__(self):
        self.textract_client = None
        self.azure_client = None
        
        # Initialize AWS Textract if credentials available
        if settings.AWS_ACCESS_KEY_ID:
            self.textract_client = boto3.client(
                'textract',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
    
    async def extract_with_textract(
        self,
        file_path: str,
        pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Extract text using AWS Textract.
        
        Cost: ~$1.50 per 1,000 pages
        Best for: Forms, tables, handwriting
        """
        if not self.textract_client:
            raise ValueError("AWS Textract not configured")
        
        try:
            # Read file
            with open(file_path, 'rb') as file:
                document_bytes = file.read()
            
            # Call Textract
            if pages:
                # Process specific pages
                response = self.textract_client.analyze_document(
                    Document={'Bytes': document_bytes},
                    FeatureTypes=['TABLES', 'FORMS', 'SIGNATURES']
                )
            else:
                # Process all pages
                response = self.textract_client.detect_document_text(
                    Document={'Bytes': document_bytes}
                )
            
            # Extract text and structure
            extracted_text = self._parse_textract_response(response)
            
            return {
                'text': extracted_text['text'],
                'tables': extracted_text['tables'],
                'forms': extracted_text['forms'],
                'confidence': extracted_text['confidence'],
                'pages_processed': len(response.get('Blocks', []))
            }
        
        except Exception as e:
            logger.error(f"Textract extraction failed: {str(e)}")
            raise
    
    def _parse_textract_response(self, response: Dict) -> Dict[str, Any]:
        """Parse Textract response into structured format."""
        # Implementation: Parse blocks, extract text, tables, forms
        pass
```

### 2.3 Image Processor with Vision API

**File: `app/services/ingestion/image_processor.py`**

```python
from typing import List, Dict, Any
import logging
from app.core.openai_client import client as openai_client

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Extracts images from documents and generates captions."""
    
    def __init__(self):
        self.min_image_size = (100, 100)  # Skip tiny images
        self.max_images_per_page = 5  # Limit processing
    
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
            'image_type': str  # 'diagram', 'chart', 'photo', 'decorative'
        }
        """
        # Extract images from document
        images = await self._extract_images(document_path, document_type)
        
        # Filter relevant images
        relevant_images = self._filter_relevant_images(images)
        
        # Generate captions
        captions = []
        for image in relevant_images:
            caption = await self._generate_caption(image)
            captions.append({
                'image_id': image['id'],
                'page': image['page'],
                'caption': caption['text'],
                'confidence': caption['confidence'],
                'image_type': image['type']
            })
        
        return captions
    
    async def _generate_caption(self, image: Dict) -> Dict[str, Any]:
        """Generate caption using OpenAI Vision API."""
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",  # or gpt-4-vision-preview
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this image in detail, focusing on any text, data, diagrams, or important visual elements. Be factual and concise."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image['base64']}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300
            )
            
            caption_text = response.choices[0].message.content
            
            return {
                'text': caption_text,
                'confidence': 0.95  # OpenAI Vision is highly reliable
            }
        
        except Exception as e:
            logger.error(f"Caption generation failed: {str(e)}")
            return {
                'text': f"[Image on page {image['page']}]",
                'confidence': 0.0
            }
    
    def _filter_relevant_images(self, images: List[Dict]) -> List[Dict]:
        """Filter out decorative images (logos, watermarks)."""
        relevant = []
        for image in images:
            # Skip if too small
            if (image['width'] < self.min_image_size[0] or 
                image['height'] < self.min_image_size[1]):
                continue
            
            # Skip if likely decorative (heuristic)
            if self._is_decorative(image):
                continue
            
            relevant.append(image)
        
        return relevant
    
    def _is_decorative(self, image: Dict) -> bool:
        """Heuristic to detect decorative images."""
        # Check aspect ratio (logos are often square)
        # Check position (watermarks are often in corners)
        # Check size relative to page
        # This is a simple heuristic; can be improved with ML
        return False
```

### 2.4 Semantic Chunker

**File: `app/services/ingestion/semantic_chunker.py`**

```python
from typing import List, Dict, Any
import tiktoken
import re
import logging

logger = logging.getLogger(__name__)


class SemanticChunker:
    """
    Advanced chunking that preserves document structure.
    
    Features:
    - Heading-based splitting
    - Table preservation (never split)
    - Paragraph boundaries
    - Semantic overlap
    """
    
    def __init__(
        self,
        max_tokens: int = 1200,
        overlap_tokens: int = 200,
        preserve_tables: bool = True,
        preserve_code_blocks: bool = True
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.preserve_tables = preserve_tables
        self.preserve_code_blocks = preserve_code_blocks
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def chunk(self, text: str, structure: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create semantic chunks from markdown text.
        
        Returns list of chunks with metadata:
        {
            'content': str,
            'tokens': int,
            'section': str,
            'page': int,
            'chunk_index': int,
            'metadata': dict
        }
        """
        # Detect document structure
        sections = self._detect_sections(text, structure)
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        
        for section in sections:
            section_tokens = self._count_tokens(section['content'])
            
            # If section is a table and preserve_tables is True
            if section['type'] == 'table' and self.preserve_tables:
                # Table must stay together
                if current_tokens + section_tokens > self.max_tokens and current_chunk:
                    # Save current chunk
                    chunks.append(self._create_chunk(
                        current_chunk,
                        chunk_index,
                        structure
                    ))
                    chunk_index += 1
                    current_chunk = []
                    current_tokens = 0
                
                # Add table (even if it exceeds max_tokens)
                current_chunk.append(section)
                current_tokens += section_tokens
                continue
            
            # Regular section handling
            if current_tokens + section_tokens > self.max_tokens and current_chunk:
                # Save current chunk with overlap
                chunks.append(self._create_chunk(
                    current_chunk,
                    chunk_index,
                    structure
                ))
                chunk_index += 1
                
                # Start new chunk with overlap
                overlap = self._get_overlap(current_chunk)
                current_chunk = [overlap, section] if overlap else [section]
                current_tokens = self._count_tokens(
                    self._chunk_to_text(current_chunk)
                )
            else:
                current_chunk.append(section)
                current_tokens += section_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append(self._create_chunk(
                current_chunk,
                chunk_index,
                structure
            ))
        
        return chunks
    
    def _detect_sections(self, text: str, structure: Dict) -> List[Dict]:
        """Detect sections, headings, tables, etc."""
        sections = []
        
        # Split by headings (markdown #)
        heading_pattern = r'^(#{1,6})\s+(.+)$'
        lines = text.split('\n')
        
        current_section = {'type': 'text', 'content': [], 'level': 0}
        
        for line in lines:
            heading_match = re.match(heading_pattern, line)
            
            if heading_match:
                # Save previous section
                if current_section['content']:
                    sections.append(current_section)
                
                # Start new section
                level = len(heading_match.group(1))
                current_section = {
                    'type': 'heading',
                    'content': [line],
                    'level': level,
                    'heading': heading_match.group(2)
                }
            else:
                # Check if line is a table
                if self._is_table_line(line):
                    if current_section['type'] != 'table':
                        if current_section['content']:
                            sections.append(current_section)
                        current_section = {'type': 'table', 'content': []}
                    current_section['content'].append(line)
                else:
                    current_section['content'].append(line)
        
        # Add final section
        if current_section['content']:
            sections.append(current_section)
        
        # Convert to text
        for section in sections:
            section['content'] = '\n'.join(section['content'])
        
        return sections
    
    def _is_table_line(self, line: str) -> bool:
        """Detect if line is part of a markdown table."""
        return '|' in line and line.count('|') >= 2
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def _get_overlap(self, chunk: List[Dict]) -> Optional[Dict]:
        """Get overlap text from end of chunk."""
        if not chunk:
            return None
        
        # Get last section
        last_section = chunk[-1]
        last_text = last_section['content']
        
        # Get last N tokens
        tokens = self.tokenizer.encode(last_text)
        if len(tokens) <= self.overlap_tokens:
            return last_section
        
        overlap_tokens = tokens[-self.overlap_tokens:]
        overlap_text = self.tokenizer.decode(overlap_tokens)
        
        return {
            'type': 'text',
            'content': overlap_text,
            'level': 0
        }
    
    def _chunk_to_text(self, chunk: List[Dict]) -> str:
        """Convert chunk list to text."""
        return '\n\n'.join(s['content'] for s in chunk)
    
    def _create_chunk(
        self,
        chunk_sections: List[Dict],
        chunk_index: int,
        structure: Dict
    ) -> Dict[str, Any]:
        """Create final chunk object."""
        content = self._chunk_to_text(chunk_sections)
        
        return {
            'content': content,
            'tokens': self._count_tokens(content),
            'chunk_index': chunk_index,
            'section': chunk_sections[0].get('heading', ''),
            'metadata': {
                'sections': len(chunk_sections),
                'has_table': any(s['type'] == 'table' for s in chunk_sections)
            }
        }
```

### 2.5 Updated Upload Endpoint

**File: `app/api/upload.py` (Updated)**

```python
from app.services.ingestion.document_intelligence import DocumentIntelligenceService
from app.services.ingestion.text_extractors.local_parser import LocalParserService
from app.services.ingestion.text_extractors.cloud_ocr import CloudOCRService
from app.services.ingestion.image_processor import ImageProcessor
from app.services.ingestion.normalizer import DocumentNormalizer
from app.services.ingestion.semantic_chunker import SemanticChunker

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(default="{}"),
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced upload with document intelligence.
    """
    # Phase 1: Receive document
    file_content = await file.read()
    file_type = detect_file_type(file.filename)
    
    # Store original file
    file_path = await store_file(file_content, file.filename)
    
    # Phase 2: Analyze document
    intelligence_service = DocumentIntelligenceService()
    analysis = await intelligence_service.analyze_document(
        file_path=file_path,
        file_type=file_type,
        file_size=len(file_content)
    )
    
    # Phase 3: Extract text based on strategy
    if analysis.strategy == ExtractionStrategy.LOCAL_PARSER:
        extractor = LocalParserService()
        extracted = await extractor.extract(file_path, file_type)
    
    elif analysis.strategy == ExtractionStrategy.CLOUD_OCR:
        # Queue for async processing
        extractor = CloudOCRService()
        task_id = await queue_ocr_task(file_path, analysis)
        return {"status": "queued", "task_id": task_id}
    
    # Phase 4: Extract and caption images
    if analysis.requires_vision:
        image_processor = ImageProcessor()
        image_captions = await image_processor.extract_and_caption_images(
            file_path, file_type
        )
    else:
        image_captions = []
    
    # Phase 5: Normalize to Markdown
    normalizer = DocumentNormalizer()
    normalized = await normalizer.normalize(
        extracted_content=extracted,
        image_captions=image_captions
    )
    
    # Phase 6: Semantic chunking
    chunker = SemanticChunker()
    chunks = chunker.chunk(
        text=normalized.markdown,
        structure=normalized.structure
    )
    
    # Phase 7: Embed and index
    document_service = DocumentService(db)
    document = await document_service.create_document_with_chunks(
        filename=file.filename,
        file_type=file_type,
        chunks=chunks,
        metadata=metadata_dict
    )
    
    return {
        "message": "Document processed successfully",
        "document_id": str(document.id),
        "strategy": analysis.strategy.value,
        "chunks_created": len(chunks)
    }
```

---

## 3. Configuration

**File: `app/core/config.py` (Additions)**

```python
# Cloud OCR Configuration
AWS_ACCESS_KEY_ID: Optional[str] = None
AWS_SECRET_ACCESS_KEY: Optional[str] = None
AWS_REGION: str = "us-east-1"
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: Optional[str] = None
AZURE_DOCUMENT_INTELLIGENCE_KEY: Optional[str] = None

# OCR Settings
ENABLE_CLOUD_OCR: bool = True
CLOUD_OCR_PROVIDER: str = "aws"  # "aws" or "azure"
MAX_CLOUD_OCR_PAGES: int = 100  # Limit per document
CLOUD_OCR_MONTHLY_BUDGET: float = 50.0  # USD

# Vision API Settings
ENABLE_IMAGE_CAPTIONS: bool = True
MAX_IMAGES_PER_DOCUMENT: int = 20
IMAGE_CAPTION_MODEL: str = "gpt-4o"

# Chunking Settings
CHUNK_MAX_TOKENS: int = 1200
CHUNK_OVERLAP_TOKENS: int = 200
PRESERVE_TABLES: bool = True
PRESERVE_CODE_BLOCKS: bool = True
```

---

## 4. Async Processing Queue

**File: `app/services/ingestion/queue.py`**

```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    'rag_ingestion',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

@celery_app.task
async def process_cloud_ocr(file_path: str, analysis: DocumentAnalysis):
    """Async task for cloud OCR processing."""
    ocr_service = CloudOCRService()
    result = await ocr_service.extract_with_textract(file_path)
    
    # Continue with normalization and chunking
    # Update document status in database
    pass
```

---

## 5. Next Steps

1. **Install dependencies:**
   ```bash
   pip install boto3 azure-ai-documentintelligence celery redis
   ```

2. **Set up AWS credentials** (if using Textract)

3. **Implement core services** in order:
   - DocumentIntelligenceService
   - CloudOCRService
   - ImageProcessor
   - SemanticChunker

4. **Test with sample documents**

5. **Add observability** (metrics, logging)

6. **Deploy and monitor**

---

This implementation guide provides the concrete structure needed to build the next-generation RAG system. Each component is designed to be modular, testable, and production-ready.
