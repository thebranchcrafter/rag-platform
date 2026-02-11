from typing import List
import asyncio
import logging

from app.core.openai_client import get_embedding

logger = logging.getLogger(__name__)

# Batch size for embedding generation
EMBEDDING_BATCH_SIZE = 100


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts.
    
    Args:
        texts: List of texts to embed
        
    Returns:
        List of embedding vectors
    """
    if not texts:
        return []
    
    # Process in batches to avoid rate limits
    all_embeddings = []
    
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]
        
        # Generate embeddings concurrently for the batch
        tasks = [get_embedding(text) for text in batch]
        batch_embeddings = await asyncio.gather(*tasks)
        
        all_embeddings.extend(batch_embeddings)
        
        logger.info(f"Generated embeddings for batch {i // EMBEDDING_BATCH_SIZE + 1}")
    
    return all_embeddings
