# Multi-Tenancy Guide - JSONB Metadata Filtering

This guide explains how to use the multi-tenancy features with JSONB metadata filtering.

## Overview

The RAG service now supports flexible multi-tenancy through JSONB metadata columns. Instead of hardcoded tenant columns, you can use arbitrary metadata for filtering.

## Key Features

- **Flexible Metadata**: Store any JSON object as metadata
- **Efficient Filtering**: GIN indexes for fast JSONB queries
- **SQL-Level Filtering**: All filtering happens in PostgreSQL (not Python)
- **Backward Compatible**: Existing documents work with empty metadata `{}`

## Database Schema

### documents table
- `metadata JSONB NOT NULL DEFAULT '{}'` - Document-level metadata

### document_chunks table
- `metadata JSONB NOT NULL DEFAULT '{}'` - Chunk-level metadata (copied from document)

### Indexes
- `idx_chunks_metadata` - GIN index on `document_chunks.metadata` for fast filtering

## Usage Examples

### 1. Upload Document with Metadata

**cURL:**
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@document.pdf" \
  -F 'metadata={"community_id": "123", "organization_id": "456", "category": "meetings"}'
```

**Python:**
```python
import requests

files = {'file': open('document.pdf', 'rb')}
data = {
    'metadata': '{"community_id": "123", "organization_id": "456", "category": "meetings"}'
}
response = requests.post('http://localhost:8765/api/v1/upload', files=files, data=data)
```

**JavaScript:**
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('metadata', JSON.stringify({
  community_id: "123",
  organization_id: "456",
  category: "meetings"
}));

fetch('http://localhost:8765/api/v1/upload', {
  method: 'POST',
  body: formData
});
```

### 2. Query with Metadata Filters

**cURL:**
```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed in the meeting?",
    "filters": {
      "community_id": "123",
      "category": "meetings"
    },
    "top_k": 10
  }'
```

**Python:**
```python
import requests

response = requests.post('http://localhost:8765/api/v1/query', json={
    "question": "What was discussed?",
    "filters": {
        "community_id": "123",
        "category": "meetings"
    },
    "top_k": 10
})
```

### 3. Query Without Filters (Global Search)

```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed?",
    "top_k": 10
  }'
```

## Metadata Filtering

### How It Works

The filtering uses PostgreSQL's JSONB containment operator `@>`:

```sql
WHERE metadata @> :filters::jsonb
```

This means: "metadata contains all key-value pairs in filters"

### Filter Examples

**Exact match:**
```json
{"community_id": "123"}
```
Matches documents where `metadata.community_id = "123"`

**Multiple conditions (AND):**
```json
{
  "community_id": "123",
  "category": "meetings"
}
```
Matches documents where BOTH conditions are true

**Nested objects:**
```json
{
  "tenant": {
    "id": "123",
    "type": "enterprise"
  }
}
```

**Arrays:**
```json
{
  "tags": ["important", "q1-2024"]
}
```

### Important Notes

1. **Partial matches**: `@>` requires ALL keys in filters to exist in metadata
2. **Type matters**: `"123"` (string) ≠ `123` (number)
3. **Case sensitive**: Keys and string values are case-sensitive
4. **No schema enforcement**: You can use any JSON structure

## Common Use Cases

### Multi-Tenant SaaS

```json
{
  "tenant_id": "acme-corp",
  "workspace_id": "workspace-1",
  "user_id": "user-123"
}
```

### Community-Based

```json
{
  "community_id": "community-456",
  "organization_id": "org-789"
}
```

### Category/Tagging

```json
{
  "category": "technical-docs",
  "tags": ["api", "backend"],
  "version": "2.0"
}
```

### Time-Based

```json
{
  "year": 2024,
  "quarter": "Q1",
  "department": "engineering"
}
```

## Migration from Hardcoded Columns

If you previously used columns like `community_id`:

### Before (Old API)
```python
# Old way - not supported anymore
document.community_id = "123"
```

### After (New API)
```python
# New way - use metadata
metadata = {"community_id": "123"}
```

The old column data can be migrated:

```sql
-- Migrate old community_id to metadata
UPDATE documents 
SET metadata = jsonb_build_object('community_id', community_id::text)
WHERE community_id IS NOT NULL;
```

## Performance Considerations

### Index Usage

The GIN index on `metadata` makes filtering very fast:

```sql
EXPLAIN ANALYZE
SELECT * FROM document_chunks
WHERE metadata @> '{"community_id": "123"}'::jsonb;
```

Should show: `Index Scan using idx_chunks_metadata`

### Best Practices

1. **Use consistent keys**: Use the same metadata keys across documents
2. **Keep it simple**: Avoid deeply nested structures when possible
3. **Index what you filter**: The GIN index works on the entire JSONB, so all keys are indexed
4. **Limit metadata size**: Very large metadata objects may impact performance

## API Reference

### POST /api/v1/upload

**Request:**
- `file` (multipart/form-data): PDF or TXT file
- `metadata` (form-data, required): JSON string with metadata

**Response:**
```json
{
  "message": "Document uploaded and processed successfully",
  "document_id": "uuid",
  "filename": "document.pdf",
  "file_type": "pdf",
  "metadata": {"community_id": "123"},
  "uploaded_at": "2024-01-15T10:30:00Z"
}
```

### POST /api/v1/query

**Request:**
```json
{
  "question": "string (required)",
  "filters": {"key": "value"} (optional),
  "top_k": 10 (optional)
}
```

**Response:**
```json
{
  "answer": "Generated answer",
  "chunks": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "chunk_index": 0,
      "content_preview": "..."
    }
  ]
}
```

## Troubleshooting

### Issue: "Metadata must be a JSON object"

**Solution**: Ensure metadata is a valid JSON object, not an array or primitive:
```json
// ✅ Correct
{"key": "value"}

// ❌ Wrong
["array"]
"string"
123
```

### Issue: No results with filters

**Solution**: 
1. Check metadata keys match exactly (case-sensitive)
2. Verify metadata values match (type matters: "123" ≠ 123)
3. Check logs for filter application

### Issue: Filter not working

**Solution**: Verify the metadata was stored correctly:
```sql
SELECT metadata FROM document_chunks LIMIT 1;
```

## Security Considerations

1. **SQL Injection**: Filters are parameterized - safe from SQL injection
2. **Metadata Validation**: API validates metadata is a JSON object
3. **Access Control**: Implement application-level access control based on filters
4. **Data Isolation**: Ensure users can only query their own metadata

## Example: Complete Workflow

```bash
# 1. Upload document for tenant "acme-corp"
curl -X POST "http://localhost:8765/api/v1/upload" \
  -F "file=@meeting-notes.pdf" \
  -F 'metadata={"tenant_id": "acme-corp", "category": "meetings"}'

# 2. Query only acme-corp documents
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed?",
    "filters": {"tenant_id": "acme-corp"}
  }'

# 3. Query specific category
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed?",
    "filters": {
      "tenant_id": "acme-corp",
      "category": "meetings"
    }
  }'
```

## Next Steps

1. Update your ingestion code to include metadata
2. Update your query code to use filters
3. Monitor logs for filter application
4. Adjust metadata structure based on your needs
