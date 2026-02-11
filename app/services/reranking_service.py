from typing import List
import logging
from app.db.models import DocumentChunk
from app.core.openai_client import get_chat_completion

logger = logging.getLogger(__name__)


class RerankingService:
    """Service for re-ranking retrieved chunks using OpenAI."""
    
    async def rerank_chunks(
        self,
        chunks: List[DocumentChunk],
        question: str
    ) -> List[DocumentChunk]:
        """
        Re-rank chunks by relevance to the question using OpenAI.
        
        Args:
            chunks: List of DocumentChunk objects to re-rank
            question: The user's question
            
        Returns:
            Re-ordered list of DocumentChunk objects
        """
        if not chunks or len(chunks) <= 1:
            return chunks
        
        try:
            # Build prompt for ranking
            chunks_text = "\n\n".join([
                f"[Chunk {i}]: {chunk.content[:500]}..." if len(chunk.content) > 500 else f"[Chunk {i}]: {chunk.content}"
                for i, chunk in enumerate(chunks)
            ])
            
            prompt = f"""Rank the following text chunks by relevance to this question: "{question}"

Return ONLY a comma-separated list of chunk numbers (0-based indices) in order of relevance, most relevant first.

Chunks:
{chunks_text}

Return format: 3,1,0,2,4 (example)"""
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a ranking system. Return ONLY a comma-separated list of chunk indices (0-based) in order of relevance. No explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            response = await get_chat_completion(messages)
            
            # Parse response to get ranked indices
            ranked_indices = self._parse_ranking_response(response, len(chunks))
            
            if not ranked_indices:
                logger.warning("Failed to parse ranking response, returning original order")
                return chunks
            
            # Re-order chunks based on ranking
            reranked = [chunks[i] for i in ranked_indices if i < len(chunks)]
            
            # Add any chunks that weren't in the ranking (shouldn't happen, but safety check)
            ranked_set = set(ranked_indices)
            for i, chunk in enumerate(chunks):
                if i not in ranked_set:
                    reranked.append(chunk)
            
            logger.info(f"Re-ranked {len(reranked)} chunks")
            return reranked[:len(chunks)]  # Ensure we return same number
            
        except Exception as e:
            logger.error(f"Error during re-ranking: {str(e)}")
            return chunks  # Return original order on error
    
    def _parse_ranking_response(self, response: str, num_chunks: int) -> List[int]:
        """
        Parse the ranking response from OpenAI.
        
        Args:
            response: Response text from OpenAI
            num_chunks: Number of chunks to rank
            
        Returns:
            List of indices in ranked order
        """
        try:
            # Extract comma-separated numbers
            import re
            numbers = re.findall(r'\d+', response)
            indices = [int(n) for n in numbers if 0 <= int(n) < num_chunks]
            
            # Remove duplicates while preserving order
            seen = set()
            unique_indices = []
            for idx in indices:
                if idx not in seen:
                    seen.add(idx)
                    unique_indices.append(idx)
            
            # If we got all indices, return them
            if len(unique_indices) == num_chunks:
                return unique_indices
            
            # Otherwise, add missing indices at the end
            missing = [i for i in range(num_chunks) if i not in seen]
            unique_indices.extend(missing)
            
            return unique_indices[:num_chunks]
            
        except Exception as e:
            logger.error(f"Error parsing ranking response: {str(e)}")
            return list(range(num_chunks))  # Return original order
