from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional, Dict, Any
import logging

from app.db.models import Document, DocumentChunk
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import generate_embeddings_batch, prepare_texts_for_embedding
from sqlalchemy import text
from typing import List, Dict, Any

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
    
    async def create_document_with_chunks(
        self,
        filename: str,
        file_type: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any]
    ) -> Document:
        """
        Create a document with pre-chunked content (from new ingestion pipeline).
        
        Args:
            filename: Name of the file
            file_type: Type of file (e.g., 'pdf', 'txt')
            chunks: List of chunk dicts with 'content', 'tokens', 'section', 'metadata'
            metadata: JSONB metadata dict
            
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
        
        logger.info(f"Created document {document.id}, processing {len(chunks)} chunks")
        
        # Prepare texts for embedding (may split large chunks)
        chunk_texts = [chunk['content'] for chunk in chunks]
        processed_texts, original_indices = prepare_texts_for_embedding(chunk_texts)
        
        # Generate embeddings for processed texts
        embeddings = await generate_embeddings_batch(processed_texts)
        
        # Verify embeddings match processed texts
        if len(embeddings) != len(processed_texts):
            raise ValueError(f"Mismatch: {len(processed_texts)} processed texts but {len(embeddings)} embeddings")
        
        # Create document chunks, handling splits
        import tiktoken
        tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Track chunk indices to handle splits
        chunk_counter = 0
        
        for idx, (chunk_text, embedding, orig_idx) in enumerate(zip(processed_texts, embeddings, original_indices)):
            original_chunk = chunks[orig_idx]
            # Check if this original chunk was split
            split_count = sum(1 for i in original_indices if i == orig_idx)
            is_split = split_count > 1
            
            # Determine chunk index
            if is_split:
                # For splits, use a fractional index based on position
                split_position = sum(1 for i in range(idx) if original_indices[i] == orig_idx)
                # Use original chunk index * 1000 + split position to ensure uniqueness
                chunk_index = original_chunk.get('chunk_index', orig_idx) * 1000 + split_position
            else:
                chunk_index = original_chunk.get('chunk_index', orig_idx)
            
            # Merge chunk metadata with document metadata
            chunk_metadata = {
                **metadata,
                **original_chunk.get('metadata', {}),
                'section': original_chunk.get('section', ''),
                'tokens': len(tokenizer.encode(chunk_text)),
            }
            
            if is_split:
                chunk_metadata['is_split'] = True
                chunk_metadata['original_chunk_index'] = original_chunk.get('chunk_index', orig_idx)
                chunk_metadata['split_index'] = split_position
            
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=chunk_index,
                content=chunk_text,
                embedding=embedding,
                meta=chunk_metadata
            )
            self.db.add(chunk)
            await self.db.flush()  # Flush to get chunk ID
            
            # Populate tsvector using PostgreSQL to_tsvector (Spanish)
            await self.db.execute(
                text("""
                    UPDATE document_chunks 
                    SET content_tsv = to_tsvector('spanish', content)
                    WHERE id = :chunk_id
                """),
                {"chunk_id": chunk.id}
            )
            
            chunk_counter += 1
        
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
