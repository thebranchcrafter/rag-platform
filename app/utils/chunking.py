from typing import List
import tiktoken
from app.core.config import settings

# Initialize tokenizer
encoding = tiktoken.get_encoding("cl100k_base")


def chunk_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
    """
    Split text into chunks with token-based sizing and overlap.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum tokens per chunk (defaults to config)
        chunk_overlap: Token overlap between chunks (defaults to config)
        
    Returns:
        List of text chunks
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    
    # Tokenize the text
    tokens = encoding.encode(text)
    
    if len(tokens) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)
        
        # Move start position with overlap
        start = end - chunk_overlap
        
        # Prevent infinite loop if overlap is too large
        if start >= end:
            start = end
    
    return chunks
