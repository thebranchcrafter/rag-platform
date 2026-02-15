from typing import List, Tuple
import asyncio
import logging
import tiktoken

from app.core.openai_client import get_embedding
from app.core.config import settings

logger = logging.getLogger(__name__)

# Batch size for embedding generation
EMBEDDING_BATCH_SIZE = 100

# Maximum tokens for embedding models (text-embedding-3-small has 8192 limit)
EMBEDDING_MAX_TOKENS = 8000  # Leave some margin below 8192

# Initialize tokenizer
_tokenizer = None

def _get_tokenizer():
    """Get or create tokenizer instance."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


def _split_large_chunk(text: str, max_tokens: int = EMBEDDING_MAX_TOKENS) -> List[str]:
    """
    Split a chunk that exceeds the token limit into smaller chunks.
    
    Args:
        text: Text to split
        max_tokens: Maximum tokens per chunk
        
    Returns:
        List of text chunks
    """
    tokenizer = _get_tokenizer()
    tokens = tokenizer.encode(text)
    
    if len(tokens) <= max_tokens:
        return [text]
    
    logger.warning(f"Chunk exceeds token limit ({len(tokens)} > {max_tokens}), splitting...")
    
    # Split by sentences first to preserve meaning
    sentences = text.split('. ')
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = len(tokenizer.encode(sentence))
        
        if current_tokens + sentence_tokens > max_tokens and current_chunk:
            # Save current chunk
            chunks.append('. '.join(current_chunk) + '.')
            current_chunk = [sentence]
            current_tokens = sentence_tokens
        else:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
    
    # Add final chunk
    if current_chunk:
        chunks.append('. '.join(current_chunk))
    
    # If still too large, split by paragraphs
    final_chunks = []
    for chunk in chunks:
        chunk_tokens = len(tokenizer.encode(chunk))
        if chunk_tokens <= max_tokens:
            final_chunks.append(chunk)
        else:
            # Split by paragraphs
            paragraphs = chunk.split('\n\n')
            current_para_chunk = []
            current_para_tokens = 0
            
            for para in paragraphs:
                para_tokens = len(tokenizer.encode(para))
                if current_para_tokens + para_tokens > max_tokens and current_para_chunk:
                    final_chunks.append('\n\n'.join(current_para_chunk))
                    current_para_chunk = [para]
                    current_para_tokens = para_tokens
                else:
                    current_para_chunk.append(para)
                    current_para_tokens += para_tokens
            
            if current_para_chunk:
                final_chunks.append('\n\n'.join(current_para_chunk))
    
    logger.info(f"Split chunk into {len(final_chunks)} sub-chunks")
    return final_chunks


def prepare_texts_for_embedding(texts: List[str]) -> Tuple[List[str], List[int]]:
    """
    Prepare texts for embedding by splitting large chunks.
    
    Args:
        texts: List of texts to embed
        
    Returns:
        Tuple of (processed_texts, original_indices)
        - processed_texts: List of texts ready for embedding (may be longer than input)
        - original_indices: List mapping each processed text to its original index
    """
    if not texts:
        return [], []
    
    processed_texts = []
    original_indices = []
    
    for idx, text in enumerate(texts):
        tokenizer = _get_tokenizer()
        tokens = len(tokenizer.encode(text))
        
        if tokens > EMBEDDING_MAX_TOKENS:
            logger.warning(f"Chunk {idx} has {tokens} tokens, exceeding limit of {EMBEDDING_MAX_TOKENS}, splitting...")
            split_chunks = _split_large_chunk(text, EMBEDDING_MAX_TOKENS)
            processed_texts.extend(split_chunks)
            # Map all splits back to original index
            original_indices.extend([idx] * len(split_chunks))
        else:
            processed_texts.append(text)
            original_indices.append(idx)
    
    if len(processed_texts) != len(texts):
        logger.info(f"Split {len(texts)} chunks into {len(processed_texts)} chunks for embedding")
    
    return processed_texts, original_indices


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts.
    Automatically splits chunks that exceed the token limit.
    
    Args:
        texts: List of texts to embed
        
    Returns:
        List of embedding vectors (may be longer than input if chunks were split)
    """
    if not texts:
        return []
    
    processed_texts, _ = prepare_texts_for_embedding(texts)
    
    # Process in batches to avoid rate limits
    all_embeddings = []
    
    for i in range(0, len(processed_texts), EMBEDDING_BATCH_SIZE):
        batch = processed_texts[i:i + EMBEDDING_BATCH_SIZE]
        
        # Generate embeddings concurrently for the batch
        tasks = [get_embedding(text) for text in batch]
        batch_embeddings = await asyncio.gather(*tasks)
        
        all_embeddings.extend(batch_embeddings)
        
        logger.info(f"Generated embeddings for batch {i // EMBEDDING_BATCH_SIZE + 1}")
    
    return all_embeddings
