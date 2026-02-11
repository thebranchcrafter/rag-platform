from typing import List
import tiktoken
import re
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize tokenizer
encoding = tiktoken.get_encoding("cl100k_base")


class ChunkingService:
    """Service for structure-aware text chunking."""
    
    def __init__(self):
        self.max_tokens = settings.CHUNK_MAX_TOKENS
        self.overlap_tokens = settings.CHUNK_OVERLAP
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(encoding.encode(text))
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Chunk text with structure-aware strategy.
        
        Strategy:
        1. Identify and preserve tables (marked with [Tabla X])
        2. Split by double newline (paragraphs)
        3. Preserve paragraph integrity
        4. Don't cut sentences in half
        5. If chunk too long, apply token-based split with overlap
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        if not text.strip():
            return []
        
        # Step 1: Identify and preserve tables
        # Tables are marked with [Tabla X] pattern
        # Split text preserving table blocks
        parts = []
        current_part = []
        lines = text.split('\n')
        in_table = False
        table_lines = []
        
        for line in lines:
            # Detect table start
            if re.match(r'\[Tabla\s+\d+\]', line, re.IGNORECASE):
                # Save current part if exists
                if current_part:
                    parts.append('\n'.join(current_part))
                    current_part = []
                # Start collecting table
                in_table = True
                table_lines = [line]
            elif in_table:
                table_lines.append(line)
                # Check if we've reached end of table (empty line or new section)
                if line.strip() == '' and len(table_lines) > 3:
                    # End of table detected
                    parts.append('\n'.join(table_lines))
                    table_lines = []
                    in_table = False
                elif re.match(r'\[Tabla\s+\d+\]', line, re.IGNORECASE):
                    # New table starts, save previous one
                    if len(table_lines) > 1:
                        parts.append('\n'.join(table_lines[:-1]))
                    table_lines = [line]
            else:
                current_part.append(line)
        
        # Handle remaining content
        if table_lines:
            parts.append('\n'.join(table_lines))
        if current_part:
            parts.append('\n'.join(current_part))
        
        # If no tables found, use original paragraph splitting
        if len(parts) == 1 and not re.search(r'\[Tabla\s+\d+\]', parts[0], re.IGNORECASE):
            # Step 2: Split by double newline to preserve paragraphs
            paragraphs = re.split(r'\n\s*\n', text)
            paragraphs = [p.strip() for p in paragraphs if p.strip()]
        else:
            # Use the parts we identified (may include tables and paragraphs)
            paragraphs = [p.strip() for p in parts if p.strip()]
        
        if not paragraphs:
            # Fallback: treat entire text as one paragraph
            paragraphs = [text]
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = self.count_tokens(para)
            
            # If paragraph itself is too large, split it by sentences
            if para_tokens > self.max_tokens:
                # First, add current chunk if exists
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Split large paragraph by sentences
                sentence_chunks = self._split_by_sentences(para)
                chunks.extend(sentence_chunks)
                continue
            
            # Check if adding this paragraph would exceed max tokens
            if current_tokens + para_tokens > self.max_tokens and current_chunk:
                # Save current chunk
                chunks.append("\n\n".join(current_chunk))
                
                # Start new chunk with overlap if possible
                if chunks and self.overlap_tokens > 0:
                    overlap_text = self._get_overlap_text(chunks[-1], self.overlap_tokens)
                    if overlap_text:
                        current_chunk = [overlap_text, para]
                        current_tokens = self.count_tokens("\n\n".join(current_chunk))
                    else:
                        current_chunk = [para]
                        current_tokens = para_tokens
                else:
                    current_chunk = [para]
                    current_tokens = para_tokens
            else:
                # Add paragraph to current chunk
                current_chunk.append(para)
                current_tokens += para_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        # Ensure we have at least one chunk
        if not chunks:
            chunks = [text]
        
        logger.info(f"Created {len(chunks)} chunks from text (max_tokens={self.max_tokens})")
        return chunks
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """
        Split text by sentences, respecting max_tokens.
        
        Args:
            text: Text to split
            
        Returns:
            List of chunks
        """
        # Simple sentence splitting (can be improved with nltk if needed)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            sent_tokens = self.count_tokens(sentence)
            
            # If single sentence is too large, force split by tokens
            if sent_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Force token-based split
                token_chunks = self._split_by_tokens(sentence)
                chunks.extend(token_chunks)
                continue
            
            # Check if adding sentence would exceed limit
            if current_tokens + sent_tokens > self.max_tokens and current_chunk:
                chunks.append(" ".join(current_chunk))
                
                # Start new chunk with overlap
                if chunks and self.overlap_tokens > 0:
                    overlap_text = self._get_overlap_text(chunks[-1], self.overlap_tokens)
                    if overlap_text:
                        current_chunk = [overlap_text, sentence]
                        current_tokens = self.count_tokens(" ".join(current_chunk))
                    else:
                        current_chunk = [sentence]
                        current_tokens = sent_tokens
                else:
                    current_chunk = [sentence]
                    current_tokens = sent_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sent_tokens
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks if chunks else [text]
    
    def _split_by_tokens(self, text: str) -> List[str]:
        """
        Force split text by tokens when structure-aware splitting fails.
        
        Args:
            text: Text to split
            
        Returns:
            List of chunks
        """
        tokens = encoding.encode(text)
        
        if len(tokens) <= self.max_tokens:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(tokens):
            end = start + self.max_tokens
            chunk_tokens = tokens[start:end]
            chunk_text = encoding.decode(chunk_tokens)
            chunks.append(chunk_text)
            
            # Move start with overlap
            start = end - self.overlap_tokens
            
            # Prevent infinite loop
            if start >= end:
                start = end
        
        return chunks
    
    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """
        Get the last N tokens from text for overlap.
        
        Args:
            text: Source text
            overlap_tokens: Number of tokens to extract
            
        Returns:
            Overlap text
        """
        tokens = encoding.encode(text)
        if len(tokens) <= overlap_tokens:
            return text
        
        overlap_tokens_list = tokens[-overlap_tokens:]
        return encoding.decode(overlap_tokens_list)
