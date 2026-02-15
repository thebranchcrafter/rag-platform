# Next-Generation RAG Ingestion & Retrieval Architecture

## Executive Summary

This architecture transforms the current RAG system into a production-grade, document-intelligent platform that matches or exceeds SaaS RAG quality while maintaining on-premise data control and low-resource constraints.

**Key Principles:**
- **Intelligent Routing**: Local parsing for 80% of cases, cloud OCR for complex cases
- **Progressive Enhancement**: Start with text, add OCR/vision only when needed
- **Cost Efficiency**: Pay-per-use cloud services, not always-on infrastructure
- **Data Sovereignty**: Sensitive data stays on-premise unless cloud processing is essential

---

## 1. Complete Ingestion Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DOCUMENT INGESTION PIPELINE                      │
└─────────────────────────────────────────────────────────────────────────┘

[1] DOCUMENT RECEPTION
    │
    ├─> File Upload (PDF, DOCX, HTML, Images)
    ├─> Metadata Extraction (filename, size, MIME type)
    └─> Initial Validation (file integrity, size limits)

[2] DOCUMENT INTELLIGENCE LAYER
    │
    ├─> [2.1] Document Type Detection
    │   ├─> MIME type analysis
    │   ├─> File signature validation
    │   └─> Content sampling (first 1KB)
    │
    ├─> [2.2] Text Extraction Strategy Decision
    │   ├─> Decision Tree (see Section 2)
    │   ├─> Route to: Local Parser | Cloud OCR | Hybrid
    │   └─> Cost/Quality Trade-off Analysis
    │
    ├─> [2.3] Local Text Extraction (Primary Path)
    │   ├─> pdfplumber (text PDFs)
    │   ├─> python-docx (DOCX)
    │   ├─> BeautifulSoup (HTML)
    │   ├─> pytesseract (simple scanned PDFs, fallback)
    │   └─> Table extraction & structure preservation
    │
    ├─> [2.4] Cloud OCR (Conditional Path)
    │   ├─> AWS Textract (complex layouts, forms)
    │   ├─> Azure Document Intelligence (multilingual)
    │   └─> Google Document AI (alternative)
    │
    └─> [2.5] Image Extraction & Analysis
        ├─> Extract embedded images from documents
        ├─> Filter: diagrams, charts, photos (skip decorative)
        ├─> Vision API (OpenAI GPT-4 Vision) for captions
        └─> Inject captions into document context

[3] CANONICAL NORMALIZATION
    │
    ├─> [3.1] Structure Detection
    │   ├─> Heading hierarchy (H1-H6)
    │   ├─> Section boundaries
    │   ├─> Table identification
    │   ├─> List structures
    │   └─> Page/line references
    │
    ├─> [3.2] Markdown Conversion
    │   ├─> Preserve hierarchy with # headings
    │   ├─> Tables as markdown tables
    │   ├─> Lists as markdown lists
    │   ├─> Code blocks preserved
    │   └─> Metadata as frontmatter
    │
    └─> [3.3] Quality Validation
        ├─> Text coverage metrics
        ├─> Structure preservation score
        └─> OCR confidence scores (if applicable)

[4] SEMANTIC CHUNKING
    │
    ├─> [4.1] Boundary Detection
    │   ├─> Heading-based splitting
    │   ├─> Section boundaries
    │   ├─> Table integrity (never split tables)
    │   ├─> Paragraph boundaries
    │   └─> Semantic similarity thresholds
    │
    ├─> [4.2] Chunk Generation
    │   ├─> Target: 800-1200 tokens per chunk
    │   ├─> Overlap: 200-300 tokens
    │   ├─> Preserve: tables, code blocks, lists
    │   └─> Metadata: section, page, chunk_index
    │
    └─> [4.3] Chunk Quality Scoring
        ├─> Information density
        ├─> Completeness (no mid-sentence cuts)
        └─> Context preservation

[5] EMBEDDING GENERATION
    │
    ├─> [5.1] Batch Processing
    │   ├─> Batch size: 100 chunks
    │   ├─> Model: text-embedding-3-large (1536 dim)
    │   └─> Retry logic with exponential backoff
    │
    ├─> [5.2] Multilingual Support
    │   ├─> Language detection (langdetect)
    │   ├─> Language-specific preprocessing
    │   └─> Embedding model selection (if needed)
    │
    └─> [5.3] Embedding Storage
        ├─> pgvector (1536 dimensions)
        ├─> Index: HNSW (high-performance)
        └─> Metadata: chunk_id, document_id, language

[6] INDEXING & STORAGE
    │
    ├─> [6.1] Full-Text Search Index
    │   ├─> PostgreSQL tsvector (Spanish/English)
    │   ├─> GIN index for fast search
    │   └─> Language-specific stemming
    │
    ├─> [6.2] Metadata Indexing
    │   ├─> JSONB indexes for filtering
    │   ├─> Document metadata
    │   └─> Chunk metadata (section, page, type)
    │
    └─> [6.3] Observability
        ├─> Ingestion metrics (Prometheus)
        ├─> Quality scores
        └─> Processing time tracking

[7] ASYNCHRONOUS PROCESSING QUEUE
    │
    ├─> Heavy operations queued:
    │   ├─> Cloud OCR requests
    │   ├─> Vision API calls
    │   └─> Large document processing
    │
    └─> Background workers (Celery/RQ)
        ├─> Process queue items
        ├─> Retry failed operations
        └─> Update document status
```

---

## 2. Decision Trees: Local vs Cloud OCR

### 2.1 Document Type Detection & Routing

```
START: Document Received
│
├─> Is MIME type PDF?
│   │
│   ├─> YES → Extract first page text with pdfplumber
│   │   │
│   │   ├─> Text extraction > 50 characters?
│   │   │   │
│   │   │   ├─> YES → [ROUTE: Local Parser]
│   │   │   │   └─> Use pdfplumber for full extraction
│   │   │   │
│   │   │   └─> NO → Check page count
│   │   │       │
│   │   │       ├─> Pages < 5 → [ROUTE: Local OCR (pytesseract)]
│   │   │       │   └─> Fast, free, good enough for small docs
│   │   │       │
│   │   │       └─> Pages >= 5 → [ROUTE: Cloud OCR]
│   │   │           └─> AWS Textract (better accuracy, cost-efficient)
│   │   │
│   │   └─> Check for complex layouts (forms, tables, multi-column)
│   │       │
│   │       ├─> Complex detected → [ROUTE: Cloud OCR]
│   │       │   └─> Azure Document Intelligence (best for structure)
│   │       │
│   │       └─> Simple layout → [ROUTE: Local Parser]
│   │
├─> Is MIME type DOCX?
│   │
│   └─> YES → [ROUTE: Local Parser]
│       └─> python-docx (always local, no OCR needed)
│
├─> Is MIME type HTML?
│   │
│   └─> YES → [ROUTE: Local Parser]
│       └─> BeautifulSoup (always local)
│
└─> Is MIME type Image (PNG, JPG, etc.)?
    │
    └─> YES → [ROUTE: Cloud OCR + Vision]
        ├─> AWS Textract (text extraction)
        └─> OpenAI Vision (caption generation)
```

### 2.2 OCR Strategy Decision Matrix

| Document Type | Text Coverage | Page Count | Layout Complexity | Recommended Strategy | Cost |
|--------------|---------------|------------|-------------------|---------------------|------|
| PDF (text) | High (>90%) | Any | Simple | Local (pdfplumber) | $0 |
| PDF (scanned) | Low (<10%) | <5 | Simple | Local OCR (pytesseract) | $0 |
| PDF (scanned) | Low (<10%) | >=5 | Simple | Cloud OCR (Textract) | ~$1.50/1000 pages |
| PDF (scanned) | Low (<10%) | Any | Complex | Cloud OCR (Azure DI) | ~$1.00/1000 pages |
| PDF (mixed) | Medium (10-90%) | Any | Any | Hybrid (local + cloud) | Variable |
| Image | N/A | N/A | Any | Cloud OCR + Vision | ~$0.001/image |

### 2.3 Cost-Efficiency Rules

**Always use local parsing when:**
- Text extraction yields >50 characters per page
- Document is native digital (DOCX, HTML, text PDF)
- Simple layout, no forms or complex tables

**Use local OCR when:**
- Document is <5 pages
- Simple layout
- Cost sensitivity is high
- Acceptable accuracy: 85-90%

**Use cloud OCR when:**
- Document is >=5 pages (cost-efficient at scale)
- Complex layouts (forms, multi-column, tables)
- High accuracy required (>95%)
- Multilingual content (Azure DI excels)

**Use cloud Vision API when:**
- Images contain diagrams, charts, or complex visuals
- Contextual understanding needed
- Caption generation required

---

## 3. Recommended Libraries & Services

### 3.1 Open-Source Libraries (Local Processing)

**Document Parsing:**
- `pdfplumber` (0.11.0) - Text PDFs, table extraction
- `python-docx` (1.1.0) - DOCX parsing
- `beautifulsoup4` (4.12.0) - HTML parsing
- `pytesseract` (0.3.10) - Local OCR (fallback)
- `pdf2image` (1.16.3) - PDF to image conversion
- `Pillow` (10.1.0) - Image processing

**Structure Detection:**
- `markdownify` (0.11.6) - HTML to Markdown
- `pymupdf` (1.23.0) - Advanced PDF parsing (alternative)
- `unstructured` (0.11.0) - Document structure detection (optional)

**Language Processing:**
- `langdetect` (1.0.9) - Language detection
- `spacy` (3.7.0) - NLP (optional, for advanced chunking)

**Chunking:**
- `tiktoken` (0.5.1) - Token counting
- Custom semantic chunker (implemented)

**Async Processing:**
- `celery` (5.3.4) - Task queue (recommended)
- `redis` (5.0.0) - Message broker for Celery

### 3.2 Cloud Services (Conditional Use)

**OCR Services:**
1. **AWS Textract** (Recommended for most cases)
   - Cost: $1.50 per 1,000 pages
   - Strengths: Forms, tables, handwriting
   - API: `boto3` (AWS SDK)

2. **Azure Document Intelligence** (Best for structure)
   - Cost: ~$1.00 per 1,000 pages
   - Strengths: Layout analysis, multilingual
   - API: `azure-ai-documentintelligence`

3. **Google Document AI** (Alternative)
   - Cost: Similar to AWS
   - Strengths: General purpose
   - API: `google-cloud-documentai`

**Vision Services:**
1. **OpenAI GPT-4 Vision** (Recommended)
   - Cost: $0.01 per image (low-res), $0.03 (high-res)
   - Strengths: Contextual understanding, captions
   - API: Already integrated

2. **AWS Rekognition** (Alternative)
   - Cost: $1.00 per 1,000 images
   - Strengths: Text in images, object detection

**Storage & Queue:**
- **AWS S3** - Temporary storage for cloud processing
- **AWS SQS** - Queue for async processing (alternative to Celery)

---

## 4. Step-by-Step Ingestion Flow (Implementation Ready)

### Phase 1: Document Reception & Validation

```python
# app/services/ingestion/document_receiver.py

async def receive_document(file: UploadFile, metadata: dict) -> DocumentMetadata:
    """
    Step 1: Receive and validate document
    """
    # Validate file
    file_type = detect_file_type(file.filename, file.content)
    file_size = len(await file.read())
    
    # Store original file (S3 or local)
    file_path = await store_original_file(file)
    
    return DocumentMetadata(
        filename=file.filename,
        file_type=file_type,
        file_size=file_size,
        file_path=file_path,
        metadata=metadata
    )
```

### Phase 2: Document Intelligence

```python
# app/services/ingestion/document_intelligence.py

async def analyze_document(metadata: DocumentMetadata) -> DocumentAnalysis:
    """
    Step 2: Analyze document and decide extraction strategy
    """
    # Quick text extraction test (first page only)
    sample_text = await extract_sample_text(metadata.file_path)
    
    # Decision tree
    strategy = decide_extraction_strategy(
        file_type=metadata.file_type,
        sample_text=sample_text,
        file_size=metadata.file_size
    )
    
    return DocumentAnalysis(
        strategy=strategy,
        confidence=sample_text.confidence,
        estimated_pages=estimate_page_count(metadata.file_path)
    )

async def extract_text(analysis: DocumentAnalysis) -> ExtractedContent:
    """
    Step 3: Extract text based on strategy
    """
    if analysis.strategy == "local_parser":
        return await extract_with_local_parser(analysis)
    
    elif analysis.strategy == "local_ocr":
        return await extract_with_local_ocr(analysis)
    
    elif analysis.strategy == "cloud_ocr":
        # Queue for async processing
        task_id = await queue_cloud_ocr(analysis)
        return ExtractedContent(status="queued", task_id=task_id)
    
    elif analysis.strategy == "hybrid":
        local_text = await extract_with_local_parser(analysis)
        # Only OCR pages with low text coverage
        ocr_pages = identify_pages_needing_ocr(local_text)
        cloud_text = await extract_with_cloud_ocr(analysis, pages=ocr_pages)
        return merge_extracted_content(local_text, cloud_text)
```

### Phase 3: Image Extraction & Vision

```python
# app/services/ingestion/image_processor.py

async def extract_and_analyze_images(document_path: str) -> List[ImageCaption]:
    """
    Step 4: Extract images and generate captions
    """
    # Extract images from document
    images = await extract_images_from_document(document_path)
    
    # Filter: skip decorative images (logos, watermarks)
    relevant_images = filter_relevant_images(images)
    
    # Generate captions with OpenAI Vision
    captions = []
    for image in relevant_images:
        caption = await generate_image_caption(image)
        captions.append(ImageCaption(
            image_id=image.id,
            caption=caption.text,
            page=image.page,
            confidence=caption.confidence
        ))
    
    return captions
```

### Phase 4: Canonical Normalization

```python
# app/services/ingestion/normalizer.py

async def normalize_to_markdown(
    extracted_content: ExtractedContent,
    image_captions: List[ImageCaption]
) -> NormalizedDocument:
    """
    Step 5: Convert to canonical Markdown format
    """
    # Detect structure
    structure = detect_document_structure(extracted_content.text)
    
    # Inject image captions at appropriate locations
    text_with_captions = inject_image_captions(
        extracted_content.text,
        image_captions,
        structure
    )
    
    # Convert to Markdown
    markdown = convert_to_markdown(
        text=text_with_captions,
        structure=structure,
        preserve_tables=True,
        preserve_lists=True
    )
    
    # Validate quality
    quality_score = validate_normalization_quality(markdown)
    
    return NormalizedDocument(
        markdown=markdown,
        structure=structure,
        quality_score=quality_score,
        metadata=extracted_content.metadata
    )
```

### Phase 5: Semantic Chunking

```python
# app/services/ingestion/semantic_chunker.py

async def chunk_semantically(document: NormalizedDocument) -> List[Chunk]:
    """
    Step 6: Create semantic chunks
    """
    chunker = SemanticChunker(
        max_tokens=1200,
        overlap_tokens=200,
        preserve_tables=True,
        preserve_code_blocks=True
    )
    
    chunks = chunker.chunk(
        text=document.markdown,
        structure=document.structure
    )
    
    # Score chunk quality
    for chunk in chunks:
        chunk.quality_score = score_chunk_quality(chunk)
    
    return chunks
```

### Phase 6: Embedding & Indexing

```python
# app/services/ingestion/embedder.py

async def embed_and_index(chunks: List[Chunk], document_id: UUID):
    """
    Step 7: Generate embeddings and index
    """
    # Batch embeddings
    embeddings = await generate_embeddings_batch(
        texts=[chunk.content for chunk in chunks],
        model="text-embedding-3-large"
    )
    
    # Store in database
    for chunk, embedding in zip(chunks, embeddings):
        await store_chunk(
            document_id=document_id,
            chunk=chunk,
            embedding=embedding,
            full_text_index=chunk.content  # For BM25
        )
```

---

## 5. Strategies to Surpass SaaS RAG Quality

### 5.1 Advanced Chunking Strategies

**Hierarchical Chunking:**
- Create chunks at multiple granularities (section, paragraph, sentence)
- Store parent-child relationships
- Retrieve at appropriate level based on query

**Table-Aware Chunking:**
- Never split tables across chunks
- Include table context (surrounding text) in chunk
- Store table structure separately for reconstruction

**Cross-Reference Preservation:**
- Detect and preserve document references (e.g., "see Section 3.2")
- Link chunks that reference each other
- Use graph structure for related chunk retrieval

### 5.2 Enhanced Retrieval

**Multi-Stage Retrieval:**
1. **Coarse Retrieval**: Vector search (top 50)
2. **Re-ranking**: Cross-encoder (top 10)
3. **Expansion**: Retrieve related chunks (parent/child, references)
4. **Deduplication**: Remove overlapping content

**Query Understanding:**
- Detect query type (factual, analytical, comparative)
- Adjust retrieval strategy based on type
- Use query expansion for better recall

**Contextual Retrieval:**
- Consider document structure in scoring
- Boost chunks from relevant sections
- Penalize chunks from irrelevant sections

### 5.3 Quality Metrics & Continuous Improvement

**Ingestion Metrics:**
- OCR coverage percentage
- Text extraction confidence
- Chunk quality scores
- Structure preservation score

**Retrieval Metrics:**
- Recall@k (k=5, 10, 20)
- Precision@k
- MRR (Mean Reciprocal Rank)
- NDCG (Normalized Discounted Cumulative Gain)

**Generation Metrics:**
- Answer relevance (human evaluation)
- Factual accuracy
- Citation quality

**Feedback Loop:**
- Collect user feedback on answers
- Identify low-quality chunks
- Re-process problematic documents
- Continuously improve chunking strategy

### 5.4 Advanced Features

**Multi-Document Reasoning:**
- Retrieve from multiple documents
- Cross-reference information
- Synthesize answers from multiple sources

**Temporal Awareness:**
- Track document versions
- Handle temporal queries ("latest", "as of date X")
- Version-aware retrieval

**Domain Adaptation:**
- Fine-tune embeddings on domain corpus
- Custom chunking rules per document type
- Domain-specific vocabulary handling

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Implement document type detection
- [ ] Add local OCR (pytesseract) as fallback
- [ ] Implement decision tree for routing
- [ ] Add basic structure detection

### Phase 2: Cloud Integration (Weeks 3-4)
- [ ] Integrate AWS Textract
- [ ] Implement async queue for cloud processing
- [ ] Add cost tracking and limits
- [ ] Implement hybrid extraction

### Phase 3: Vision & Images (Weeks 5-6)
- [ ] Extract images from documents
- [ ] Integrate OpenAI Vision API
- [ ] Generate and inject captions
- [ ] Filter irrelevant images

### Phase 4: Advanced Chunking (Weeks 7-8)
- [ ] Implement semantic chunker
- [ ] Add table preservation
- [ ] Implement hierarchical chunking
- [ ] Add chunk quality scoring

### Phase 5: Enhanced Retrieval (Weeks 9-10)
- [ ] Implement cross-encoder reranking
- [ ] Add multi-stage retrieval
- [ ] Implement query understanding
- [ ] Add related chunk expansion

### Phase 6: Observability & Quality (Weeks 11-12)
- [ ] Add ingestion metrics
- [ ] Implement retrieval evaluation
- [ ] Add feedback collection
- [ ] Create quality dashboard

---

## 7. Cost Optimization

**Local Processing (Free):**
- Text PDFs: 100% local
- DOCX/HTML: 100% local
- Simple scanned PDFs (<5 pages): Local OCR

**Cloud Processing (Pay-per-use):**
- Complex PDFs: ~$0.0015/page
- Images with captions: ~$0.01/image
- Average document: $0.10-0.50

**Cost Controls:**
- Set monthly budget limits
- Alert on unusual usage
- Cache OCR results for duplicate documents
- Batch processing to reduce API calls

---

## 8. Security & Data Governance

**On-Premise Processing:**
- All text extraction (when possible)
- All embedding generation
- All storage and indexing

**Cloud Processing (Conditional):**
- Only when local processing insufficient
- Encrypt data in transit (TLS)
- Use temporary storage (auto-delete)
- No persistent cloud storage
- Audit all cloud API calls

**Compliance:**
- Document processing logs
- Data retention policies
- User access controls
- Encryption at rest

---

## Conclusion

This architecture provides:
- **Intelligence**: Document-aware processing
- **Efficiency**: Cost-optimized cloud usage
- **Quality**: Surpasses basic RAG systems
- **Control**: On-premise data sovereignty
- **Scalability**: Handles growth without infrastructure changes

The key is **intelligent routing**: use local processing for 80% of cases, cloud services only when necessary, and always preserve document structure and context.
