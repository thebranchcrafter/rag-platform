from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, bindparam
from typing import List, Dict, Tuple, Optional, Any
import logging
import json

from app.db.models import DocumentChunk
from app.core.openai_client import get_embedding, get_chat_completion
from app.core.config import settings
from app.services.reranking_service import RerankingService

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for RAG retrieval and generation with hybrid search."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.reranking_service = RerankingService()
    
    async def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = None
    ) -> List[Tuple[DocumentChunk, float]]:
        """
        Hybrid search combining vector similarity and full-text search (BM25) with metadata filtering.
        
        Score = (vector_weight * (1 - cosine_distance)) + (bm25_weight * ts_rank)
        Filtering: WHERE metadata @> :filters::jsonb
        
        Args:
            query_embedding: Embedding vector of the query
            query_text: Original query text for full-text search
            filters: Optional metadata filters (JSONB object)
            top_k: Number of top results to return
            
        Returns:
            List of tuples (DocumentChunk, score) ordered by score DESC
        """
        top_k = top_k or settings.TOP_K
        
        # Convert embedding to PostgreSQL array format string
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        # Build WHERE clause for metadata filtering
        vector_weight_val = settings.VECTOR_WEIGHT
        bm25_weight_val = settings.BM25_WEIGHT
        
        # Build query SQL - conditionally include WHERE clause
        if filters:
            # Convert filters dict to JSON string for JSONB containment operator
            # Escape single quotes in JSON for safe SQL insertion
            filters_json = json.dumps(filters).replace("'", "''")
            logger.info(f"Applying metadata filters: {filters}")
            
            # Build SQL with filters - insert JSON directly (already validated as dict)
            query_sql = f"""
                SELECT 
                    dc.id,
                    dc.document_id,
                    dc.chunk_index,
                    dc.content,
                    dc.embedding,
                    dc.content_tsv,
                    dc.metadata,
                    dc.created_at,
                    CASE 
                        WHEN dc.content_tsv IS NOT NULL THEN
                            (
                                ({vector_weight_val} * (1 - (dc.embedding <-> '{embedding_str}'::vector))) +
                                ({bm25_weight_val} * COALESCE(ts_rank(dc.content_tsv, plainto_tsquery('english', :query_text)), 0))
                            )
                        ELSE
                            ({vector_weight_val} * (1 - (dc.embedding <-> '{embedding_str}'::vector)))
                    END AS hybrid_score
                FROM document_chunks dc
                WHERE dc.metadata @> '{filters_json}'::jsonb
                ORDER BY hybrid_score DESC
                LIMIT :top_k
            """
            
            # Use bindparam for user-provided text only (filters_json is in SQL string)
            query = text(query_sql).bindparams(
                query_text=query_text,
                top_k=top_k
            )
        else:
            query_sql = f"""
                SELECT 
                    dc.id,
                    dc.document_id,
                    dc.chunk_index,
                    dc.content,
                    dc.embedding,
                    dc.content_tsv,
                    dc.metadata,
                    dc.created_at,
                    CASE 
                        WHEN dc.content_tsv IS NOT NULL THEN
                            (
                                ({vector_weight_val} * (1 - (dc.embedding <-> '{embedding_str}'::vector))) +
                                ({bm25_weight_val} * COALESCE(ts_rank(dc.content_tsv, plainto_tsquery('english', :query_text)), 0))
                            )
                        ELSE
                            ({vector_weight_val} * (1 - (dc.embedding <-> '{embedding_str}'::vector)))
                    END AS hybrid_score
                FROM document_chunks dc
                ORDER BY hybrid_score DESC
                LIMIT :top_k
            """
            
            query = text(query_sql).bindparams(
                query_text=query_text,
                top_k=top_k
            )
        
        result = await self.db.execute(query)
        
        rows = result.fetchall()
        chunks_with_scores = []
        
        for row in rows:
            # Extract chunk and score
            # Row is a Row object, access by index
            chunk = DocumentChunk(
                id=row[0],  # id
                document_id=row[1],  # document_id
                chunk_index=row[2],  # chunk_index
                content=row[3],  # content
                embedding=row[4],  # embedding
                content_tsv=row[5],  # content_tsv
                meta=row[6],  # metadata (stored as meta attribute)
                created_at=row[7]  # created_at
            )
            score = float(row[8])  # hybrid_score
            chunks_with_scores.append((chunk, score))
        
        return chunks_with_scores
    
    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        query_text: str = "",
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = None
    ) -> List[DocumentChunk]:
        """
        Search for similar chunks using hybrid search with optional metadata filtering.
        
        Args:
            query_embedding: Embedding vector of the query
            query_text: Original query text for full-text search
            filters: Optional metadata filters (JSONB object)
            top_k: Number of top results to return
            
        Returns:
            List of DocumentChunk objects ordered by hybrid score
        """
        top_k = top_k or settings.TOP_K
        
        if not query_text:
            # Fallback to pure vector search if no query text
            logger.warning("No query text provided, using vector-only search")
            query = select(DocumentChunk)
            
            # Apply metadata filtering if provided
            if filters:
                filters_json = json.dumps(filters)
                query = query.where(
                    text("metadata @> :filters_json::jsonb")
                ).params(filters_json=filters_json)
                logger.info(f"Applying metadata filters to vector search: {filters}")
            
            result = await self.db.execute(
                query.order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
                .limit(top_k)
            )
            chunks = list(result.scalars().all())
            logger.info(f"Retrieved {len(chunks)} chunks with vector search (filters: {filters})")
            return chunks
        
        # Use hybrid search with filters
        chunks_with_scores = await self.hybrid_search(
            query_embedding, 
            query_text, 
            filters=filters,
            top_k=top_k
        )
        
        # Log retrieval details for debugging
        self._log_retrieval_details(query_text, chunks_with_scores, top_k, filters)
        
        return [chunk for chunk, score in chunks_with_scores]
    
    def _log_retrieval_details(
        self,
        query: str,
        chunks_with_scores: List[Tuple[DocumentChunk, float]],
        top_k: int,
        filters: Optional[Dict[str, Any]] = None
    ):
        """Log retrieval details for debugging."""
        logger.info(f"Retrieval Debug - Query: '{query}'")
        logger.info(f"Retrieval Debug - Filters: {filters}")
        logger.info(f"Retrieval Debug - Top K: {top_k}")
        logger.info(f"Retrieval Debug - Retrieved: {len(chunks_with_scores)} chunks")
        
        for i, (chunk, score) in enumerate(chunks_with_scores[:5]):  # Log top 5
            logger.info(
                f"Retrieval Debug - Chunk {i+1}: "
                f"id={chunk.id}, "
                f"score={score:.4f}, "
                f"index={chunk.chunk_index}, "
                f"metadata={chunk.meta}, "
                f"preview={chunk.content[:100]}..."
            )
    
    async def query(
        self,
        question: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> dict:
        """
        Perform RAG query: retrieve relevant chunks and generate answer.
        
        Args:
            question: User's question
            filters: Optional metadata filters for multi-tenancy
            top_k: Optional number of chunks to retrieve
            system_prompt: Optional custom system prompt to override the default
            
        Returns:
            Dictionary with answer and used chunks
        """
        # Generate embedding for the question
        logger.info(f"Generating embedding for question: {question[:50]}...")
        query_embedding = await get_embedding(question)
        
        # Hybrid search for similar chunks with optional filtering
        similar_chunks = await self.search_similar_chunks(
            query_embedding,
            query_text=question,
            filters=filters,
            top_k=top_k or settings.TOP_K
        )
        
        logger.info(f"Retrieved {len(similar_chunks)} chunks (filters: {filters}, top_k: {top_k or settings.TOP_K})")
        
        if not similar_chunks:
            return {
                "answer": "I couldn't find any relevant information in the knowledge base to answer your question.",
                "chunks": []
            }
        
        # Optional re-ranking
        if settings.ENABLE_RERANKING and len(similar_chunks) > 1:
            logger.info("Applying re-ranking to retrieved chunks")
            similar_chunks = await self.reranking_service.rerank_chunks(
                similar_chunks,
                question
            )
        
        # Build context from chunks
        context = "\n\n".join([
            f"[Chunk {chunk.chunk_index} from {chunk.document_id}]:\n{chunk.content}"
            for chunk in similar_chunks
        ])
        
        # Build improved RAG prompt
        # Use custom system prompt if provided, otherwise use default
        default_system_prompt = """You are a helpful assistant that answers questions based on the provided context.

IMPORTANT INSTRUCTIONS:
- The context may include structured data such as tables, lists, meeting minutes, or numeric data
- When data is presented in lists or sections, infer relationships between items
- Answer precisely and extract numeric values if present
- If the context contains tables or structured formats, preserve that structure in your answer
- Use only the information from the context to answer
- If the context doesn't contain enough information to answer the question, say so explicitly
- Be specific and cite relevant details from the context"""
        
        system_prompt_content = system_prompt if system_prompt else default_system_prompt
        
        messages = [
            {
                "role": "system",
                "content": system_prompt_content
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
            }
        ]
        
        if system_prompt:
            logger.info(f"Using custom system prompt (length: {len(system_prompt)} chars)")
        
        # Generate answer
        logger.info("Generating answer using OpenAI...")
        answer = await get_chat_completion(messages)
        
        # Prepare chunk metadata for response
        chunks_metadata = [
            {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "chunk_index": chunk.chunk_index,
                "content_preview": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content
            }
            for chunk in similar_chunks
        ]
        
        return {
            "answer": answer,
            "chunks": chunks_metadata
        }
