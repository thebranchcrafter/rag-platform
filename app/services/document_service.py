from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional, Dict, Any
import logging

from app.db.models import Document, DocumentChunk
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import generate_embeddings_batch
from sqlalchemy import text

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_document(
        self,
        filename: str,
        file_type: str,
        text_content: str,
        metadata: Dict[str, Any]
    ) -> Document:
        """
        Create a document and its chunks with embeddings and metadata.
        
        Args:
            filename: Name of the file
            file_type: Type of file (e.g., 'pdf', 'txt')
            text_content: Extracted text content
            metadata: JSONB metadata dict (required) - stored in both document and chunks
            
        Returns:
            Created Document object
        """
        # Validate metadata is a dict
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")
        
        # Create document with metadata
        document = Document(
            filename=filename,
            file_type=file_type,
            meta=metadata
        )
        self.db.add(document)
        await self.db.flush()  # Get the document ID
        
        # Chunk the text using structure-aware chunking
        chunking_service = ChunkingService()
        chunks = chunking_service.chunk_text(text_content)
        logger.info(f"Created {len(chunks)} chunks for document {document.id}")
        
        # Generate embeddings for all chunks
        chunk_texts = [chunk for chunk in chunks]
        embeddings = await generate_embeddings_batch(chunk_texts)
        
        # Verify embeddings match chunks
        if len(embeddings) != len(chunks):
            raise ValueError(f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings")
        
        # Create document chunks with tsvector and metadata
        # Store the same metadata in all chunks for filtering
        for idx, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                content=chunk_content,
                embedding=embedding,
                meta=metadata  # Same metadata as document
            )
            self.db.add(chunk)
            await self.db.flush()  # Flush to get chunk ID
            
            # Populate tsvector using PostgreSQL to_tsvector (Spanish for better Spanish text search)
            await self.db.execute(
                text("""
                    UPDATE document_chunks 
                    SET content_tsv = to_tsvector('spanish', content)
                    WHERE id = :chunk_id
                """),
                {"chunk_id": chunk.id}
            )
        
        await self.db.commit()
        await self.db.refresh(document)
        
        logger.info(f"Successfully created document {document.id} with {len(chunks)} chunks")
        return document
    
    async def get_document(self, document_id: UUID) -> Optional[Document]:
        """Get a document by ID."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
    
    async def list_documents(self, limit: int = 100, offset: int = 0) -> list[Document]:
        """List all documents."""
        result = await self.db.execute(
            select(Document)
            .order_by(Document.uploaded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def delete_document(self, document_id: UUID) -> bool:
        """Delete a document and its chunks (cascade)."""
        document = await self.get_document(document_id)
        if not document:
            return False
        
        await self.db.delete(document)
        await self.db.commit()
        logger.info(f"Deleted document {document_id}")
        return True
