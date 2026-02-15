from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import logging

from app.core.config import settings
from app.api import upload, query, documents
from app.db.base import engine, Base
# Import models to ensure they're registered with Base.metadata
from app.db.models import Document, DocumentChunk  # noqa: F401
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Service",
    description="Production-ready RAG (Retrieval-Augmented Generation) service",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(query.router, prefix="/api/v1", tags=["query"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])

# Serve static files for UI
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve UI at root
@app.get("/")
async def serve_ui():
    """Serve the documents UI."""
    ui_path = static_dir / "index.html"
    if ui_path.exists():
        return FileResponse(str(ui_path))
    return JSONResponse({
        "message": "RAG Service API",
        "version": "1.0.0",
        "docs": "/docs"
    })


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Starting up RAG service...")
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        
        # Add content_tsv column if it doesn't exist
        try:
            await conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'document_chunks' 
                        AND column_name = 'content_tsv'
                    ) THEN
                        ALTER TABLE document_chunks 
                        ADD COLUMN content_tsv tsvector;
                    END IF;
                END $$;
            """))
            logger.info("Added content_tsv column if needed")
        except Exception as e:
            logger.warning(f"Could not add content_tsv column (may already exist): {e}")
        
        # Create GIN index for tsvector if it doesn't exist
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_content_tsv 
                ON document_chunks USING gin(content_tsv)
            """))
            logger.info("Created tsvector index if needed")
        except Exception as e:
            logger.warning(f"Could not create tsvector index (may already exist): {e}")
        
        # Update existing chunks to populate tsvector if needed (Spanish for better Spanish text search)
        try:
            result = await conn.execute(text("""
                UPDATE document_chunks 
                SET content_tsv = to_tsvector('spanish', content)
                WHERE content_tsv IS NULL AND content IS NOT NULL
            """))
            rows_updated = result.rowcount
            if rows_updated > 0:
                logger.info(f"Populated tsvector for {rows_updated} existing chunks")
        except Exception as e:
            logger.warning(f"Could not populate tsvector for existing chunks: {e}")
        
        # Add metadata JSONB column to documents if it doesn't exist
        try:
            await conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'documents' 
                        AND column_name = 'metadata'
                    ) THEN
                        ALTER TABLE documents 
                        ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';
                    END IF;
                END $$;
            """))
            logger.info("Added metadata column to documents if needed")
        except Exception as e:
            logger.warning(f"Could not add metadata column to documents (may already exist): {e}")
        
        # Add metadata JSONB column to document_chunks if it doesn't exist
        try:
            await conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'document_chunks' 
                        AND column_name = 'metadata'
                    ) THEN
                        ALTER TABLE document_chunks 
                        ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';
                    END IF;
                END $$;
            """))
            logger.info("Added metadata column to document_chunks if needed")
        except Exception as e:
            logger.warning(f"Could not add metadata column to document_chunks (may already exist): {e}")
        
        # Create GIN index for metadata filtering if it doesn't exist
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chunks_metadata 
                ON document_chunks USING gin(metadata)
            """))
            logger.info("Created metadata GIN index if needed")
        except Exception as e:
            logger.warning(f"Could not create metadata index (may already exist): {e}")
        
        # Backfill metadata for existing rows (set to empty object if NULL)
        try:
            result = await conn.execute(text("""
                UPDATE documents 
                SET metadata = '{}'::jsonb
                WHERE metadata IS NULL
            """))
            rows_updated = result.rowcount
            if rows_updated > 0:
                logger.info(f"Backfilled metadata for {rows_updated} existing documents")
        except Exception as e:
            logger.warning(f"Could not backfill documents metadata: {e}")
        
        try:
            result = await conn.execute(text("""
                UPDATE document_chunks 
                SET metadata = '{}'::jsonb
                WHERE metadata IS NULL
            """))
            rows_updated = result.rowcount
            if rows_updated > 0:
                logger.info(f"Backfilled metadata for {rows_updated} existing chunks")
        except Exception as e:
            logger.warning(f"Could not backfill chunks metadata: {e}")
    
    logger.info("Database initialized")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


