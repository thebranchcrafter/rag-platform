# RAG Pipeline Improvements - Summary

## Overview

The RAG retrieval pipeline has been significantly improved to handle structured documents (meeting minutes, tables, numeric data) better. All improvements maintain backward compatibility.

## Key Improvements

### 1. Hybrid Search (Vector + BM25) ✅

**What Changed:**
- Added `content_tsv` (tsvector) column to `document_chunks` table
- Created GIN index for fast full-text search
- Combined vector similarity (70%) with BM25 full-text search (30%)
- Configurable weights via `VECTOR_WEIGHT` and `BM25_WEIGHT`

**Benefits:**
- Better retrieval for keyword-heavy queries
- Improved handling of structured data
- More accurate relevance scoring

**Files Modified:**
- `app/db/models.py` - Added tsvector column and index
- `app/services/retrieval_service.py` - Hybrid search implementation
- `app/services/document_service.py` - Populates tsvector on insert

### 2. Structure-Aware Chunking ✅

**What Changed:**
- Replaced fixed token chunking with intelligent structure-aware chunking
- Preserves paragraph boundaries (splits on double newline)
- Preserves sentence integrity (doesn't cut sentences)
- Falls back to token-based splitting only when necessary

**Benefits:**
- Better chunk boundaries for structured content
- Preserves context within paragraphs
- More meaningful chunks for retrieval

**Files Created:**
- `app/services/chunking_service.py` - New chunking service

**Files Modified:**
- `app/services/document_service.py` - Uses new chunking service

### 3. Retrieval Debug Logging ✅

**What Changed:**
- Added structured logging for retrieval operations
- Logs query, chunk IDs, similarity scores, hybrid scores, and top_k

**Benefits:**
- Easy debugging of retrieval quality
- Visibility into why certain chunks were retrieved
- Performance monitoring

**Files Modified:**
- `app/services/retrieval_service.py` - Added `_log_retrieval_details()`

### 4. Optional Re-ranking ✅

**What Changed:**
- Added optional OpenAI-based re-ranking
- Re-ranks top 10 chunks by relevance to question
- Toggleable via `ENABLE_RERANKING` config

**Benefits:**
- Improved result ordering
- Better answer quality
- Optional (can be disabled for cost savings)

**Files Created:**
- `app/services/reranking_service.py` - Re-ranking service

**Files Modified:**
- `app/services/retrieval_service.py` - Integrates re-ranking

### 5. Improved Prompt Construction ✅

**What Changed:**
- Enhanced system prompt with explicit instructions for structured data
- Instructs model to infer relationships in lists/sections
- Emphasizes precise answers and numeric extraction

**Benefits:**
- Better handling of tables and structured formats
- More accurate answers from structured data
- Preserves data relationships

**Files Modified:**
- `app/services/retrieval_service.py` - Updated prompt in `query()`

### 6. Configuration Updates ✅

**New Settings:**
- `VECTOR_WEIGHT=0.7` - Weight for vector similarity
- `BM25_WEIGHT=0.3` - Weight for full-text search
- `TOP_K=10` - Increased from 5
- `CHUNK_MAX_TOKENS=1200` - Maximum chunk size
- `ENABLE_RERANKING=false` - Toggle re-ranking

**Files Modified:**
- `app/core/config.py` - Added new configuration options
- `docker-compose.yml` - Added environment variables

## Architecture

### Service Layer

```
DocumentService
  └── Uses ChunkingService for structure-aware chunking
  └── Populates tsvector on chunk creation

RetrievalService
  └── Hybrid search (vector + BM25)
  └── Optional RerankingService integration
  └── Debug logging

ChunkingService
  └── Structure-aware chunking
  └── Paragraph and sentence preservation

RerankingService
  └── OpenAI-based re-ranking
  └── Optional feature
```

### Database Schema

```sql
document_chunks
  ├── id (UUID)
  ├── document_id (UUID, FK)
  ├── chunk_index (INT)
  ├── content (TEXT)
  ├── embedding (VECTOR(1536))  -- Vector similarity
  ├── content_tsv (TSVECTOR)     -- Full-text search (NEW)
  └── created_at (TIMESTAMP)

Indexes:
  ├── idx_content_tsv (GIN)      -- Full-text search index (NEW)
  └── (vector index via pgvector)
```

## Migration Steps

1. **Update Configuration**
   ```bash
   # Add to .env
   VECTOR_WEIGHT=0.7
   BM25_WEIGHT=0.3
   TOP_K=10
   CHUNK_MAX_TOKENS=1200
   ENABLE_RERANKING=false
   ```

2. **Restart Service**
   ```bash
   make restart
   # or
   make down && make build && make up
   ```

3. **Automatic Migration**
   - Database schema updated automatically
   - Existing chunks get tsvector populated
   - No manual SQL needed

4. **Optional: Re-upload Documents**
   - For optimal chunking, re-upload documents
   - New chunking preserves structure better

## Backward Compatibility

✅ **All API endpoints unchanged**
✅ **Existing documents work** (tsvector auto-populated)
✅ **Falls back to vector-only** if tsvector missing
✅ **Old chunking function preserved** (not used by default)

## Performance Impact

### Positive
- Better retrieval quality → fewer irrelevant chunks
- Hybrid search uses both indexes efficiently
- Structure-aware chunking → better context preservation

### Considerations
- Re-ranking adds one OpenAI API call per query (optional)
- GIN index uses additional storage (~20% overhead)
- Hybrid query slightly more complex (negligible impact)

## Testing Recommendations

1. **Test with structured documents**
   - Upload meeting minutes, tables, lists
   - Query for specific data points
   - Verify answers preserve structure

2. **Compare retrieval quality**
   - Check logs for hybrid scores
   - Compare with/without re-ranking
   - Adjust weights if needed

3. **Monitor performance**
   - Check query response times
   - Monitor OpenAI API usage
   - Review retrieval debug logs

## Next Steps

1. Update `.env` with new configuration
2. Restart service
3. Test with your documents
4. Adjust weights based on results
5. Enable re-ranking if quality is priority

## Files Changed

### New Files
- `app/services/chunking_service.py`
- `app/services/reranking_service.py`
- `MIGRATION.md`
- `IMPROVEMENTS_SUMMARY.md`

### Modified Files
- `app/db/models.py`
- `app/core/config.py`
- `app/services/document_service.py`
- `app/services/retrieval_service.py`
- `app/main.py`
- `docker-compose.yml`
- `README.md`

### Unchanged (Backward Compatible)
- `app/api/upload.py`
- `app/api/query.py`
- `app/api/documents.py`
- All API contracts
