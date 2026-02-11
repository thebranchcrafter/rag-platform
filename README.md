# RAG Service

A production-ready RAG (Retrieval-Augmented Generation) service built with FastAPI, PostgreSQL (pgvector), and OpenAI.

## Features

- **Document Upload**: Upload PDF and text files for processing
- **Automatic Chunking**: Intelligent text chunking with configurable size and overlap
- **Vector Embeddings**: Generate embeddings using OpenAI's embedding models
- **Vector Search**: Fast similarity search using PostgreSQL with pgvector
- **RAG Queries**: Ask questions and get answers based on uploaded documents
- **Async Architecture**: Fully async implementation for high performance
- **Docker Support**: Easy deployment with Docker Compose

## Tech Stack

- Python 3.11
- FastAPI
- PostgreSQL with pgvector extension
- SQLAlchemy (async)
- OpenAI API (embeddings & chat completions)
- Docker & Docker Compose
- Pydantic v2
- Uvicorn

## Project Structure

```
rag-service/
│
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── core/
│   │   ├── config.py           # Configuration management
│   │   └── openai_client.py    # OpenAI client wrapper
│   ├── db/
│   │   ├── base.py             # Database base and engine
│   │   ├── models.py           # SQLAlchemy models
│   │   └── session.py          # Database session management
│   ├── services/
│   │   ├── document_service.py # Document processing service
│   │   ├── embedding_service.py # Embedding generation service
│   │   └── retrieval_service.py # RAG retrieval service
│   ├── api/
│   │   ├── upload.py           # Document upload endpoint
│   │   └── query.py            # Query endpoint
│   └── utils/
│       └── chunking.py         # Text chunking utilities
│
├── migrations/                 # Database migration scripts
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker image definition
├── docker-compose.yml          # Docker Compose configuration
├── .env.example                # Environment variables template
└── README.md                   # This file
```

## Prerequisites

- Docker and Docker Compose
- OpenAI API key

## Docker Features

The application is fully dockerized with production-ready optimizations:

- **Multi-stage builds** for smaller image size
- **Non-root user** for enhanced security
- **Health checks** for both API and database
- **Separate dev/prod configurations**
- **Network isolation** with dedicated Docker network
- **Volume persistence** for database data

## Quick Start

### 1. Clone and Setup

```bash
cd rag-platform
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` and set your OpenAI API key:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Run with Docker Compose

**Using Makefile (recommended):**
```bash
make start
```

**Or using Docker Compose directly:**

**Using Makefile (recommended):**
```bash
make start
```

**Or using Docker Compose directly:**
```bash
docker-compose up --build
```

The service will be available at `http://localhost:8765`

### 4. Access API Documentation

- Swagger UI: http://localhost:8765/docs
- ReDoc: http://localhost:8765/redoc

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key (required) | - |
| `OPENAI_MODEL_EMBEDDING` | Embedding model to use | `text-embedding-3-small` |
| `OPENAI_MODEL_CHAT` | Chat completion model | `gpt-4o-mini` |
| `DATABASE_URL` | PostgreSQL connection string | Auto-configured for Docker |
| `CHUNK_SIZE` | Maximum tokens per chunk | `1200` |
| `CHUNK_OVERLAP` | Token overlap between chunks | `200` |
| `CHUNK_MAX_TOKENS` | Maximum tokens per chunk (hard limit) | `1200` |
| `TOP_K` | Number of top chunks to retrieve | `10` |
| `VECTOR_WEIGHT` | Weight for vector similarity in hybrid search | `0.7` |
| `BM25_WEIGHT` | Weight for full-text search in hybrid search | `0.3` |
| `ENABLE_RERANKING` | Enable OpenAI re-ranking (true/false) | `false` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |

## Quick cURL Examples

**Upload a document:**
```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -F "file=@document.pdf"
```

**Ask a question:**
```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic?"}'
```

**List documents:**
```bash
curl "http://localhost:8765/api/v1/documents"
```

For more examples, see [CURL_EXAMPLES.md](CURL_EXAMPLES.md).

## API Endpoints

### Upload Document

Upload a PDF or text file for processing.

```bash
curl -X POST "http://localhost:8765/api/v1/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

**Response:**
```json
{
  "message": "Document uploaded and processed successfully",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "file_type": "pdf",
  "uploaded_at": "2024-01-15T10:30:00Z"
}
```

### Query

Ask a question based on uploaded documents.

```bash
curl -X POST "http://localhost:8765/api/v1/query" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the main topic of the document?"
  }'
```

**Response:**
```json
{
  "answer": "Based on the provided context, the main topic is...",
  "chunks": [
    {
      "chunk_id": "660e8400-e29b-41d4-a716-446655440001",
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "chunk_index": 0,
      "content_preview": "The document discusses..."
    }
  ]
}
```

### Health Check

```bash
curl http://localhost:8765/health
```

## Running Locally (Without Docker)

### 1. Install Dependencies

```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Setup PostgreSQL with pgvector

Make sure you have PostgreSQL with pgvector extension installed:

```bash
# Using Homebrew on macOS
brew install postgresql
brew install pgvector

# Or use Docker for just the database
docker run -d \
  --name rag_postgres \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=rag_password \
  -e POSTGRES_DB=rag_db \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 3. Configure Environment

Create `.env` file with your settings:

```bash
DATABASE_URL=postgresql+asyncpg://rag_user:rag_password@localhost:5432/rag_db
OPENAI_API_KEY=your_openai_api_key_here
```

### 4. Initialize Database

The database tables and pgvector extension are automatically created on startup.

### 5. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Makefile Commands

The project includes a Makefile for common operations:

```bash
make help        # Show all available commands
make build       # Build Docker images
make up          # Start all services
make down        # Stop all services
make restart     # Restart all services
make logs        # View logs from all services
make logs-api    # View API logs only
make logs-db     # View database logs only
make shell       # Access API container shell
make db-shell    # Access PostgreSQL shell
make clean       # Remove containers, volumes, and images
make start       # Build and start services (quick start)
make stop        # Stop services
make install     # Install Python dependencies locally
make run         # Run API locally (requires local PostgreSQL)
make prod-build  # Build production images
make prod-up     # Start services in production mode
```

## Production Deployment

For production deployment, use the production configuration:

```bash
# Build production images
make prod-build

# Start in production mode
make prod-up

# Or manually
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Production features:**
- Multiple workers (4) for better performance
- No hot reload (code is baked into image)
- Optimized for production workloads
- Smaller image size with multi-stage builds

## Development

### Project Structure

The codebase follows a clean architecture pattern:

- **API Layer** (`app/api/`): FastAPI route handlers
- **Service Layer** (`app/services/`): Business logic
- **Database Layer** (`app/db/`): Models and session management
- **Core** (`app/core/`): Configuration and external clients
- **Utils** (`app/utils/`): Utility functions

### Adding New Features

The codebase is designed to be easily extensible:

1. **Multi-tenant support**: Add `tenant_id` column to models and filter queries
2. **Additional file types: Extend** `upload.py` with new file type handlers
3. **Different embedding models**: Update `openai_client.py` or create new client
4. **Alternative vector stores**: Implement new retrieval service with same interface

## Database Schema

### documents

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| filename | String | Original filename |
| file_type | String | File type (pdf, txt) |
| uploaded_at | DateTime | Upload timestamp |
| metadata | Text | Additional metadata (JSON) |

### document_chunks

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| document_id | UUID | Foreign key to documents |
| chunk_index | Integer | Chunk position in document |
| content | Text | Chunk text content |
| embedding | Vector(1536) | Embedding vector |
| created_at | DateTime | Creation timestamp |

## Error Handling

The service includes comprehensive error handling:

- Validation errors return 400 Bad Request
- File processing errors return 400 with descriptive messages
- Database errors return 500 Internal Server Error
- OpenAI API errors are logged and returned as 500

## Logging

Structured logging is configured throughout the application. Logs include:

- Document upload and processing
- Embedding generation
- Query processing
- Error details

## Performance Considerations

- **Async operations**: All I/O operations are async for better concurrency
- **Batch embeddings**: Embeddings are generated in batches to optimize API calls
- **Vector indexing**: Consider adding HNSW index on embedding column for large datasets:

```sql
CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops);
```

## Security

- Environment variables for sensitive data
- CORS configuration for API access control
- Input validation using Pydantic
- SQL injection protection via SQLAlchemy

## License

This project is provided as-is for internal use.

## Support

For issues or questions, please refer to the API documentation at `/docs` or check the logs.
