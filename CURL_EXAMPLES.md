# RAG Service - cURL Examples

Quick reference for using the RAG Service API with cURL commands.

## Base URL
All endpoints are available at: `http://localhost:8765`

---

## 1. Health Check

Check if the service is running:

```bash
curl http://localhost:8765/health
```

**Expected Response:**
```json
{"status":"healthy"}
```

---

## 2. Upload a Document

Upload a PDF or text file to the system with metadata:

### Upload a PDF file with metadata:
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@/path/to/your/document.pdf" \
  -F 'metadata={"community_id": "123", "category": "meetings"}'
```

### Upload without metadata (uses empty {}):
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@/path/to/your/document.pdf" \
  -F 'metadata={}'
```

### Upload a text file:
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@/path/to/your/document.txt"
```

**Example with a local file:**
```bash
# Create a test file
echo "Artificial Intelligence (AI) is transforming the way we work and live. Machine learning algorithms can process vast amounts of data to identify patterns and make predictions. Natural language processing enables computers to understand and generate human language." > test_doc.txt

# Upload it
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@test_doc.txt"
```

**Expected Response:**
```json
{
  "message": "Document uploaded and processed successfully",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "file_type": "pdf",
  "uploaded_at": "2024-01-15T10:30:00Z"
}
```

---

## 3. Ask Questions (Query the RAG System)

Ask questions based on uploaded documents:

### Basic query (no filters):
```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is artificial intelligence?"
  }'
```

### Query with metadata filters:
```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was discussed?",
    "filters": {
      "community_id": "123",
      "category": "meetings"
    },
    "top_k": 10
  }'
```

### More examples:
```bash
# Ask about specific topics
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is machine learning?"}'

# Ask for explanations
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "How does natural language processing work?"}'

# Ask for summaries
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize the main points from the documents"}'
```

**Expected Response:**
```json
{
  "answer": "Based on the provided context, artificial intelligence (AI) is transforming the way we work and live...",
  "chunks": [
    {
      "chunk_id": "660e8400-e29b-41d4-a716-446655440001",
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "chunk_index": 0,
      "content_preview": "Artificial Intelligence (AI) is transforming..."
    }
  ]
}
```

---

## 4. List All Documents

Get a list of all uploaded documents:

```bash
curl -X GET "http://localhost:8765/api/v1/documents" \
  -H "accept: application/json"
```

**With pagination:**
```bash
# Get first 10 documents
curl "http://localhost:8765/api/v1/documents?limit=10&offset=0"

# Get next 10 documents
curl "http://localhost:8765/api/v1/documents?limit=10&offset=10"
```

**Expected Response:**
```json
{
  "documents": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "document.pdf",
      "file_type": "pdf",
      "uploaded_at": "2024-01-15T10:30:00Z",
      "chunk_count": 15,
      "metadata": null
    }
  ],
  "total": 1
}
```

---

## 5. Delete a Document

Delete a document by its ID:

```bash
curl -X DELETE "http://localhost:8765/api/v1/documents/550e8400-e29b-41d4-a716-446655440000" \
  -H "accept: application/json"
```

**Expected Response:**
```json
{
  "message": "Document deleted successfully"
}
```

---

## Complete Workflow Example

Here's a complete example workflow:

```bash
# 1. Check service health
curl http://localhost:8765/health

# 2. Create and upload a test document
cat > test_ai.txt << EOF
Artificial Intelligence (AI) is a branch of computer science that aims to create 
intelligent machines capable of performing tasks that typically require human intelligence. 
These tasks include learning, reasoning, problem-solving, perception, and language understanding.

Machine Learning is a subset of AI that enables systems to learn and improve from 
experience without being explicitly programmed. It uses algorithms to analyze data, 
identify patterns, and make decisions.

Deep Learning is a subset of machine learning that uses neural networks with multiple 
layers to process complex data. It has been particularly successful in image recognition, 
natural language processing, and speech recognition.
EOF

# 3. Upload the document
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@test_ai.txt"

# 4. Ask questions about the uploaded content
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is artificial intelligence?"}'

curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the difference between machine learning and deep learning?"}'

curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are some applications of deep learning?"}'

# 5. List all documents
curl "http://localhost:8765/api/v1/documents"
```

---

## Pretty Print JSON Responses

For better readability, pipe responses through `jq`:

```bash
# Install jq if needed: brew install jq (macOS) or apt-get install jq (Linux)

curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AI?"}' | jq
```

---

## Troubleshooting

### Check if service is running:
```bash
curl http://localhost:8765/health
```

### View API documentation:
Open in browser: http://localhost:8765/docs

### Check service logs:
```bash
make logs
# or
docker-compose logs -f api
```

---

## Notes

- Make sure the service is running: `make up` or `docker-compose up`
- Ensure `OPENAI_API_KEY` is set in your `.env` file
- The service processes documents asynchronously - large files may take a moment
- Questions are answered based on the content of uploaded documents only
