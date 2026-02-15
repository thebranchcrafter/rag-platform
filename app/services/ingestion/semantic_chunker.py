"""Advanced semantic chunking that preserves document structure."""

from typing import List, Dict, Any, Optional
import logging
import tiktoken
import re

logger = logging.getLogger(__name__)


class SemanticChunker:
    """
    Advanced chunking that preserves document structure.
    
    Features:
    - Heading-based splitting
    - Table preservation (never split)
    - Paragraph boundaries
    - Semantic overlap
    """
    
    def __init__(
        self,
        max_tokens: int = 1200,
        overlap_tokens: int = 200,
        preserve_tables: bool = True,
        preserve_code_blocks: bool = True
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.preserve_tables = preserve_tables
        self.preserve_code_blocks = preserve_code_blocks
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def chunk(
        self,
        text: str,
        structure: Any = None  # DocumentStructure from normalizer
    ) -> List[Dict[str, Any]]:
        """
        Create semantic chunks from markdown text.
        
        Returns list of chunks with metadata:
        {
            'content': str,
            'tokens': int,
            'section': str,
            'chunk_index': int,
            'metadata': dict
        }
        """
        logger.info("[Semantic Chunker] Starting semantic chunking")
        logger.debug(f"[Semantic Chunker] Input text length: {len(text)} chars")
        logger.debug(f"[Semantic Chunker] Config:")
        logger.debug(f"  - Max tokens: {self.max_tokens}")
        logger.debug(f"  - Overlap tokens: {self.overlap_tokens}")
        logger.debug(f"  - Preserve tables: {self.preserve_tables}")
        logger.debug(f"  - Preserve code blocks: {self.preserve_code_blocks}")
        
        # Detect document structure
        logger.debug("[Semantic Chunker] Detecting sections...")
        sections = self._detect_sections(text, structure)
        logger.info(f"[Semantic Chunker] Detected {len(sections)} section(s)")
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        
        for section in sections:
            section_tokens = self._count_tokens(section['content'])
            
            # If section is a table and preserve_tables is True
            if section['type'] == 'table' and self.preserve_tables:
                # Table must stay together, but check embedding limit (8000 tokens)
                EMBEDDING_MAX_TOKENS = 8000
                
                if current_tokens + section_tokens > self.max_tokens and current_chunk:
                    # Save current chunk
                    chunks.append(self._create_chunk(
                        current_chunk,
                        chunk_index,
                        structure
                    ))
                    chunk_index += 1
                    current_chunk = []
                    current_tokens = 0
                
                # If table alone exceeds embedding limit, we'll need to split it later
                # For now, add it and let the embedding service handle splitting
                if section_tokens > EMBEDDING_MAX_TOKENS:
                    logger.warning(f"Table section has {section_tokens} tokens, exceeds embedding limit. Will be split during embedding.")
                
                current_chunk.append(section)
                current_tokens += section_tokens
                continue
            
            # Regular section handling
            if current_tokens + section_tokens > self.max_tokens and current_chunk:
                # Save current chunk with overlap
                chunks.append(self._create_chunk(
                    current_chunk,
                    chunk_index,
                    structure
                ))
                chunk_index += 1
                
                # Start new chunk with overlap
                overlap = self._get_overlap(current_chunk)
                current_chunk = [overlap, section] if overlap else [section]
                current_tokens = self._count_tokens(
                    self._chunk_to_text(current_chunk)
                )
            else:
                current_chunk.append(section)
                current_tokens += section_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append(self._create_chunk(
                current_chunk,
                chunk_index,
                structure
            ))
        
        logger.info(f"[Semantic Chunker] Chunking complete:")
        logger.info(f"  - Total chunks created: {len(chunks)}")
        if chunks:
            avg_tokens = sum(c['tokens'] for c in chunks) / len(chunks)
            logger.info(f"  - Average tokens per chunk: {avg_tokens:.0f}")
            logger.info(f"  - Chunks with tables: {sum(1 for c in chunks if c['metadata'].get('has_table', False))}")
            logger.info(f"  - Chunks with headings: {sum(1 for c in chunks if c['metadata'].get('has_heading', False))}")
        
        return chunks
    
    def _detect_sections(
        self,
        text: str,
        structure: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Detect sections, headings, tables, etc."""
        sections = []
        
        # Split by headings (markdown #)
        heading_pattern = r'^(#{1,6})\s+(.+)$'
        lines = text.split('\n')
        
        current_section = {'type': 'text', 'content': [], 'level': 0, 'heading': ''}
        
        for line in lines:
            heading_match = re.match(heading_pattern, line)
            
            if heading_match:
                # Save previous section
                if current_section['content']:
                    sections.append(current_section)
                
                # Start new section
                level = len(heading_match.group(1))
                current_section = {
                    'type': 'heading',
                    'content': [line],
                    'level': level,
                    'heading': heading_match.group(2)
                }
            else:
                # Check if line is a table
                if self._is_table_line(line):
                    if current_section['type'] != 'table':
                        if current_section['content']:
                            sections.append(current_section)
                        current_section = {'type': 'table', 'content': [], 'level': 0, 'heading': ''}
                    current_section['content'].append(line)
                else:
                    current_section['content'].append(line)
        
        # Add final section
        if current_section['content']:
            sections.append(current_section)
        
        # Convert to text
        for section in sections:
            section['content'] = '\n'.join(section['content'])
        
        return sections
    
    def _is_table_line(self, line: str) -> bool:
        """Detect if line is part of a markdown table."""
        return '|' in line and line.count('|') >= 2
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def _get_overlap(self, chunk: List[Dict]) -> Optional[Dict]:
        """Get overlap text from end of chunk."""
        if not chunk:
            return None
        
        # Get last section
        last_section = chunk[-1]
        last_text = last_section['content']
        
        # Get last N tokens
        tokens = self.tokenizer.encode(last_text)
        if len(tokens) <= self.overlap_tokens:
            return last_section
        
        overlap_tokens = tokens[-self.overlap_tokens:]
        overlap_text = self.tokenizer.decode(overlap_tokens)
        
        return {
            'type': 'text',
            'content': overlap_text,
            'level': 0,
            'heading': ''
        }
    
    def _chunk_to_text(self, chunk: List[Dict]) -> str:
        """Convert chunk list to text."""
        return '\n\n'.join(s['content'] for s in chunk)
    
    def _create_chunk(
        self,
        chunk_sections: List[Dict],
        chunk_index: int,
        structure: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Create final chunk object."""
        content = self._chunk_to_text(chunk_sections)
        
        # Get section heading if available
        section_heading = ''
        for section in chunk_sections:
            if section.get('heading'):
                section_heading = section['heading']
                break
        
        return {
            'content': content,
            'tokens': self._count_tokens(content),
            'chunk_index': chunk_index,
            'section': section_heading,
            'metadata': {
                'sections': len(chunk_sections),
                'has_table': any(s['type'] == 'table' for s in chunk_sections),
                'has_heading': any(s['type'] == 'heading' for s in chunk_sections)
            }
        }
