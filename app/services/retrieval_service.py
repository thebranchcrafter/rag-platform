from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, bindparam
from typing import List, Dict, Tuple, Optional, Any
import logging
import json
import tiktoken

from app.db.models import DocumentChunk
from app.core.openai_client import get_embedding, get_chat_completion
from app.core.config import settings
from app.services.reranking_service import RerankingService

logger = logging.getLogger(__name__)

# Initialize tokenizer once (reused for performance)
_tokenizer = None

def _get_tokenizer():
    """Get or initialize tokenizer (lazy initialization)."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


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
        
        # Build optimized query SQL - conditionally include WHERE clause
        if filters:
            # Convert filters dict to JSON string for JSONB containment operator
            # Escape single quotes in JSON for safe SQL insertion
            filters_json = json.dumps(filters).replace("'", "''")
            logger.debug(f"Applying metadata filters: {filters}")
            
            # Optimized SQL with filters - use parameterized query for better performance
            # Only select needed columns to reduce data transfer
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
                                ({bm25_weight_val} * COALESCE(ts_rank(dc.content_tsv, plainto_tsquery('spanish', :query_text)), 0))
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
            # Optimized SQL without filters - only select needed columns
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
                                ({bm25_weight_val} * COALESCE(ts_rank(dc.content_tsv, plainto_tsquery('spanish', :query_text)), 0))
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
        """Log retrieval details for debugging (optimized - less verbose)."""
        # Only log summary, not every chunk detail (for performance)
        logger.debug(f"Retrieved {len(chunks_with_scores)} chunks for query: '{query[:50]}...'")
        
        # Only log top chunk details if in debug mode
        if logger.isEnabledFor(logging.DEBUG) and chunks_with_scores:
            top_chunk, top_score = chunks_with_scores[0]
            logger.debug(f"Top chunk score: {top_score:.4f}, index: {top_chunk.chunk_index}")
    
    async def query(
        self,
        question: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> dict:
        """
        Perform RAG query: retrieve relevant chunks and generate answer.
        Optimized for performance with parallel operations and context limits.
        
        Args:
            question: User's question
            filters: Optional metadata filters for multi-tenancy
            top_k: Optional number of chunks to retrieve
            system_prompt: Optional custom system prompt to override the default
            
        Returns:
            Dictionary with answer and used chunks
        """
        # Generate embedding for the question
        query_embedding = await get_embedding(question)
        
        # Hybrid search for similar chunks with optional filtering
        # Increase top_k slightly for queries about specific points/sections to ensure we get relevant chunks
        effective_top_k = top_k or settings.TOP_K
        # Expand query text for point-specific queries to improve retrieval
        expanded_query_text = question
        
        # If query mentions numbered points/sections, retrieve more chunks and expand query
        if any(keyword in question.lower() for keyword in ['punto', 'puntos', 'sección', 'apartado', 'tema']):
            effective_top_k = max(effective_top_k, 15)  # Retrieve at least 15 chunks for point-specific queries
            # Expand query to include variations that might appear in the document
            # This helps with full-text search (BM25) to find "PUNTO 3", "Punto 3", etc.
            expanded_query_text = f"{question} PUNTO punto"
            logger.debug(f"Increased top_k to {effective_top_k} and expanded query for point-specific query")
        
        similar_chunks = await self.search_similar_chunks(
            query_embedding,
            query_text=expanded_query_text,
            filters=filters,
            top_k=effective_top_k
        )
        
        if not similar_chunks:
            return {
                "answer": "No pude encontrar información relevante en la base de conocimientos para responder tu pregunta.",
                "chunks": []
            }
        
        # Optional re-ranking (only if enabled and we have multiple chunks)
        if settings.ENABLE_RERANKING and len(similar_chunks) > 1:
            similar_chunks = await self.reranking_service.rerank_chunks(
                similar_chunks,
                question
            )
        
        # Build optimized context from chunks (no metadata in context, just content)
        # Limit context size to avoid very long prompts (max ~8000 tokens for context)
        encoding = _get_tokenizer()
        max_context_tokens = 8000
        context_parts = []
        current_tokens = 0
        
        for chunk in similar_chunks:
            chunk_text = chunk.content
            chunk_tokens = len(encoding.encode(chunk_text))
            
            if current_tokens + chunk_tokens > max_context_tokens:
                # Log if we're truncating
                if current_tokens > 0:
                    logger.debug(f"Context truncated at {current_tokens} tokens (limit: {max_context_tokens})")
                break
            
            context_parts.append(chunk_text)
            current_tokens += chunk_tokens
        
        context = "\n\n".join(context_parts)
        
        # Build optimized RAG prompt (shorter for faster processing)
        # Use custom system prompt if provided, otherwise use default
        default_system_prompt = """Responde basándote ÚNICAMENTE en el contexto proporcionado. 

INSTRUCCIONES:
- Si el contexto contiene información sobre el tema preguntado, responde con esa información
- Si el contexto menciona puntos numerados (PUNTO 1, PUNTO 2, PUNTO 3, etc.), busca específicamente el punto mencionado en la pregunta
- Si hay tablas o datos estructurados, presérvalos en tu respuesta
- Si el contexto NO contiene la información solicitada, di explícitamente que no hay información disponible en el contexto
- Responde en el mismo idioma de la pregunta
- Sé específico y cita detalles del contexto cuando sea relevante"""
        
        system_prompt_content = system_prompt if system_prompt else default_system_prompt
        
        # Optimized prompt format with explicit instruction to search for numbered points
        user_content = f"Contexto del documento:\n{context}\n\nPregunta: {question}\n\nIMPORTANTE: Si la pregunta menciona un punto numerado (ej: 'punto 3', 'PUNTO 3'), busca específicamente ese punto en el contexto. Responde con la información encontrada o indica claramente si no está disponible en el contexto.\n\nRespuesta:"
        
        messages = [
            {
                "role": "system",
                "content": system_prompt_content
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        # Generate answer with token limit for faster responses
        # Limit to 2000 tokens max for faster generation (adjust based on needs)
        answer = await get_chat_completion(messages, max_tokens=2000)
        
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
