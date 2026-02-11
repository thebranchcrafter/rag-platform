# RAG Pipeline Improvements - Migration Guide

This document describes the migration steps required for the improved RAG retrieval pipeline.

## Overview of Changes

The RAG system has been upgraded with:
1. **Hybrid Search**: Combines vector similarity (pgvector) with full-text search (PostgreSQL tsvector)
2. **Structure-Aware Chunking**: Preserves paragraphs and sentences
3. **Optional Re-ranking**: Uses OpenAI to re-rank results
4. **Improved Prompts**: Better handling of structured data

## Database Migration

### Automatic Migration (Recommended)

The system will automatically:
- Create the `content_tsv` column on `document_chunks` table
- Create a GIN index on `content_tsv`
- Populate `content_tsv` for existing chunks

**No manual migration needed** - just restart the service.

### Manual Migration (If Needed)

If you need to run migrations manually:

```sql
-- Add tsvector column
ALTER TABLE document_chunks 
ADD COLUMN IF NOT EXISTS content_tsv tsvector;

-- Create GIN index
CREATE INDEX IF NOT EXISTS idx_content_tsv 
ON document_chunks USING gin(content_tsv);

-- Populate tsvector for existing chunks
UPDATE document_chunks 
SET content_tsv = to_tsvector('english', content)
WHERE content_tsv IS NULL AND content IS NOT NULL;
```

## Configuration Changes

### New Environment Variables

Add these to your `.env` file:

```bash
# Hybrid search weights (must sum to ~1.0)
VECTOR_WEIGHT=0.7      # Weight for vector similarity
BM25_WEIGHT=0.3        # Weight for full-text search

# Retrieval settings
TOP_K=10               # Increased from 5 to 10

# Chunking settings
CHUNK_MAX_TOKENS=1200  # Maximum tokens per chunk
CHUNK_OVERLAP=200      # Overlap tokens (unchanged)

# Optional re-ranking
ENABLE_RERANKING=false # Set to true to enable OpenAI re-ranking
```

### Default Values

If not set, defaults are:
- `VECTOR_WEIGHT=0.7`
- `BM25_WEIGHT=0.3`
- `TOP_K=10`
- `CHUNK_MAX_TOKENS=1200`
- `ENABLE_RERANKING=false`

## Backward Compatibility

✅ **All existing endpoints remain unchanged**
✅ **API contracts are preserved**
✅ **Existing documents will work** (tsvector populated automatically)

## Re-indexing Existing Documents

Existing documents will have their `content_tsv` populated automatically on startup.

However, for best results with the new chunking strategy, you may want to:

1. **Delete and re-upload documents** (recommended for best quality)
   - Old chunks used fixed token-based chunking
   - New chunks use structure-aware chunking
   - This ensures optimal chunk boundaries

2. **Or keep existing documents** (works but suboptimal)
   - Existing chunks will work with hybrid search
   - But chunk boundaries may not be optimal

## Testing the Improvements

### 1. Test Hybrid Search

```bash
# Query with specific terms
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the key metrics from the meeting?"}'
```

Check logs for retrieval debug information showing hybrid scores.

### 2. Test Structure-Aware Chunking

Upload a document with structured content (tables, lists):

```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -F "file=@structured_document.pdf"
```

The new chunking should preserve paragraph boundaries better.

### 3. Test Re-ranking (Optional)

Enable re-ranking:

```bash
# In .env
ENABLE_RERANKING=true
```

Restart and query - results should be better ordered.

## Performance Considerations

### Index Performance

- The GIN index on `content_tsv` improves full-text search performance
- Vector index (HNSW) improves vector search performance
- Hybrid queries use both indexes

### Re-ranking Cost

- Re-ranking adds one OpenAI API call per query
- Only enable if retrieval quality is more important than cost
- Recommended for production with high-quality requirements

## Troubleshooting

### Issue: tsvector column not created

**Solution**: Check PostgreSQL logs. Ensure you have permissions to create columns and indexes.

### Issue: Hybrid search returns no results

**Solution**: 
1. Check that `content_tsv` is populated: `SELECT COUNT(*) FROM document_chunks WHERE content_tsv IS NOT NULL;`
2. Verify query text is not empty
3. Check logs for retrieval debug information

### Issue: Poor chunk quality

**Solution**: Re-upload documents to use new structure-aware chunking.

## Rollback

If you need to rollback:

1. Remove new environment variables
2. The system will fall back to vector-only search if `content_tsv` is NULL
3. Old chunking function still exists in `app/utils/chunking.py` (not used by default)

## Next Steps

1. Update your `.env` file with new configuration
2. Restart the service: `make restart`
3. Monitor logs for retrieval debug information
4. Optionally re-upload documents for optimal chunking
5. Test queries and adjust weights if needed
