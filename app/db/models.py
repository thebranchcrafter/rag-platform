from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid

from app.db.base import Base


class Document(Base):
    """Document model with JSONB metadata for multi-tenancy."""
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    # Use 'meta' as Python attribute name, but map to 'metadata' column in DB
    # Note: Cannot use 'metadata' as attribute name (SQLAlchemy reserved)
    meta = Column('metadata', JSONB, nullable=False, server_default='{}')  # JSONB for flexible filtering
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename})>"


class DocumentChunk(Base):
    """Document chunk model with vector embedding, full-text search, and JSONB metadata."""
    __tablename__ = "document_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=False)  # OpenAI text-embedding-3-small dimension
    content_tsv = Column(TSVECTOR, nullable=True)  # Full-text search vector
    # Use 'meta' as Python attribute name, but map to 'metadata' column in DB
    # Note: Cannot use 'metadata' as attribute name (SQLAlchemy reserved)
    meta = Column('metadata', JSONB, nullable=False, server_default='{}')  # JSONB for flexible filtering
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes for full-text search and metadata filtering
    __table_args__ = (
        Index('idx_content_tsv', 'content_tsv', postgresql_using='gin'),
        Index('idx_chunks_metadata', 'metadata', postgresql_using='gin'),
    )
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"
