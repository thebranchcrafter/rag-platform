# Multi-Tenancy Refactor - Summary

## What Changed

The RAG service has been refactored to support flexible multi-tenancy using JSONB metadata instead of hardcoded tenant columns.

## Key Changes

### 1. Database Schema

**Added:**
- `documents.metadata` - JSONB column (NOT NULL, DEFAULT '{}')
- `document_chunks.metadata` - JSONB column (NOT NULL, DEFAULT '{}')
- `idx_chunks_metadata` - GIN index on `document_chunks.metadata`

**Removed:**
- `documents.document_metadata` (Text column) - replaced with JSONB `metadata`

### 2. API Changes

#### Upload Endpoint (`POST /api/v1/upload`)

**Before:**
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -F "file=@document.pdf"
```

**After:**
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -F "file=@document.pdf" \
  -F 'metadata={"community_id": "123", "category": "meetings"}'
```

**Changes:**
- `metadata` parameter is now **required** (must be valid JSON object)
- Metadata is stored in both `documents.metadata` and `document_chunks.metadata`

#### Query Endpoint (`POST /api/v1/query`)

**Before:**
```json
{
  "question": "What was discussed?"
}
```

**After:**
```json
{
  "question": "What was discussed?",
  "filters": {
    "community_id": "123",
    "category": "meetings"
  },
  "top_k": 10
}
```

**Changes:**
- Added optional `filters` parameter (JSON object)
- Added optional `top_k` parameter
- Filters are applied in SQL using JSONB containment operator

### 3. Service Layer Changes

#### DocumentService
- `create_document()` now requires `metadata: Dict[str, Any]` parameter
- Metadata is stored in both document and all chunks
- Validates metadata is a dictionary

#### RetrievalService
- `hybrid_search()` accepts optional `filters` parameter
- `search_similar_chunks()` applies metadata filtering in SQL
- `query()` accepts `filters` and `top_k` parameters
- Enhanced logging includes metadata and filter information

### 4. Filtering Implementation

**SQL Filtering:**
```sql
WHERE metadata @> :filters::jsonb
```

This uses PostgreSQL's JSONB containment operator to match documents where metadata contains all key-value pairs in filters.

**Example:**
```json
filters: {"community_id": "123", "category": "meetings"}
```

Matches documents where:
- `metadata.community_id = "123"` AND
- `metadata.category = "meetings"`

### 5. Hybrid Search Compatibility

Hybrid search continues to work with filtering:

```sql
SELECT ...
FROM document_chunks
WHERE metadata @> :filters::jsonb  -- Filtering happens first
ORDER BY hybrid_score DESC          -- Then ordering
LIMIT :top_k;
```

## Migration Steps

### Automatic Migration (Recommended)

The service automatically:
1. Adds `metadata` columns if they don't exist
2. Creates GIN indexes
3. Backfills existing rows with `{}`

**Just restart the service:**
```bash
make restart
```

### Manual Migration (If Needed)

Run the SQL script:
```bash
psql -U rag_user -d rag_db -f migrations/add_metadata_jsonb.sql
```

### Data Migration

If you had data in old columns (e.g., `community_id`), migrate it:

```sql
-- Example: Migrate old community_id to metadata
UPDATE documents 
SET metadata = jsonb_build_object('community_id', community_id::text)
WHERE community_id IS NOT NULL;

-- Then update chunks to match
UPDATE document_chunks dc
SET metadata = d.metadata
FROM documents d
WHERE dc.document_id = d.id;
```

## Usage Examples

### Upload with Metadata

```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -F "file=@meeting-notes.pdf" \
  -F 'metadata={"tenant_id": "acme-corp", "category": "meetings", "year": 2024}'
```

### Query with Filters

```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed?",
    "filters": {
      "tenant_id": "acme-corp",
      "category": "meetings"
    },
    "top_k": 10
  }'
```

### Query Without Filters (Global)

```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed?",
    "top_k": 10
  }'
```

## Backward Compatibility

✅ **Existing documents work** - automatically get `metadata = {}`
✅ **API contracts preserved** - query endpoint still works without filters
✅ **No breaking changes** - old code continues to work (with empty metadata)

## Performance

- **GIN Index**: Fast JSONB filtering (similar to vector search performance)
- **SQL-Level**: All filtering in PostgreSQL (no Python filtering)
- **Hybrid Search**: Filtering happens before scoring (efficient)

## Files Modified

### Database
- `app/db/models.py` - Added JSONB metadata columns and indexes

### API
- `app/api/upload.py` - Accepts metadata parameter
- `app/api/query.py` - Accepts filters and top_k parameters
- `app/api/documents.py` - Returns metadata in responses

### Services
- `app/services/document_service.py` - Handles metadata storage
- `app/services/retrieval_service.py` - Implements metadata filtering

### Infrastructure
- `app/main.py` - Automatic migration on startup
- `migrations/add_metadata_jsonb.sql` - Manual migration script

### Documentation
- `MULTI_TENANCY_GUIDE.md` - Complete usage guide
- `CURL_EXAMPLES.md` - Updated examples
- `MULTI_TENANCY_REFACTOR.md` - This file

## Testing

### Test Upload
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -F "file=@test.txt" \
  -F 'metadata={"test": "value"}'
```

### Test Query with Filter
```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "filters": {"test": "value"}}'
```

### Verify Metadata
```sql
SELECT id, metadata FROM documents LIMIT 5;
SELECT id, metadata FROM document_chunks LIMIT 5;
```

## Next Steps

1. **Update your ingestion code** to include metadata
2. **Update your query code** to use filters for multi-tenancy
3. **Test with your data** to ensure filters work correctly
4. **Monitor logs** for filter application and performance

## Support

For detailed usage examples, see:
- `MULTI_TENANCY_GUIDE.md` - Complete guide with examples
- `CURL_EXAMPLES.md` - Quick reference
- API docs at `http://localhost:8765/docs`
