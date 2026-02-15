"""Cloud OCR using AWS Textract or Azure Document Intelligence."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# Optional cloud OCR imports
try:
    import boto3
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    logger.warning("boto3 not available. AWS Textract will not work.")

try:
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    logger.warning("Azure Document Intelligence SDK not available.")


@dataclass
class ExtractedContent:
    """Extracted content from cloud OCR."""
    text: str
    tables: List[List[List[str]]]
    metadata: Dict[str, Any]
    confidence: float = 0.95  # Cloud OCR typically very confident
    pages_processed: int = 0


class CloudOCRService:
    """Extract text using cloud OCR (AWS Textract or Azure Document Intelligence)."""
    
    def __init__(self):
        self.provider = settings.CLOUD_OCR_PROVIDER.lower()
        
        logger.info(f"[Cloud OCR] Initializing cloud OCR service")
        logger.debug(f"[Cloud OCR] Provider: {self.provider}")
        logger.debug(f"[Cloud OCR] Cloud OCR enabled: {settings.ENABLE_CLOUD_OCR}")
        logger.debug(f"[Cloud OCR] AWS available: {AWS_AVAILABLE}")
        logger.debug(f"[Cloud OCR] Azure available: {AZURE_AVAILABLE}")
        
        # Debug: Log credential status (without exposing secrets)
        if self.provider == "aws":
            has_access_key = bool(settings.AWS_ACCESS_KEY_ID)
            has_secret_key = bool(settings.AWS_SECRET_ACCESS_KEY)
            logger.debug(f"[Cloud OCR] AWS credentials status:")
            logger.debug(f"  - AWS_ACCESS_KEY_ID present: {has_access_key} ({'configured' if has_access_key else 'NOT configured'})")
            logger.debug(f"  - AWS_SECRET_ACCESS_KEY present: {has_secret_key} ({'configured' if has_secret_key else 'NOT configured'})")
            logger.debug(f"  - AWS_REGION: {settings.AWS_REGION}")
        
        # Initialize AWS Textract if available
        if self.provider == "aws" and AWS_AVAILABLE:
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                logger.info("[Cloud OCR] Initializing AWS Textract client")
                logger.debug(f"[Cloud OCR] AWS Region: {settings.AWS_REGION}")
                self.textract_client = boto3.client(
                    'textract',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION
                )
                logger.info("[Cloud OCR] AWS Textract client initialized successfully")
            else:
                logger.warning("[Cloud OCR] AWS credentials not configured")
                self.textract_client = None
        else:
            self.textract_client = None
            if self.provider == "aws":
                logger.warning(f"[Cloud OCR] AWS selected but not available (boto3 installed: {AWS_AVAILABLE})")
        
        # Initialize Azure Document Intelligence if available
        if self.provider == "azure" and AZURE_AVAILABLE:
            if settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and settings.AZURE_DOCUMENT_INTELLIGENCE_KEY:
                logger.info("[Cloud OCR] Initializing Azure Document Intelligence client")
                logger.debug(f"[Cloud OCR] Azure Endpoint: {settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT}")
                self.azure_client = DocumentIntelligenceClient(
                    endpoint=settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT,
                    credential=AzureKeyCredential(settings.AZURE_DOCUMENT_INTELLIGENCE_KEY)
                )
                logger.info("[Cloud OCR] Azure Document Intelligence client initialized successfully")
            else:
                logger.warning("[Cloud OCR] Azure credentials not configured")
                self.azure_client = None
        else:
            self.azure_client = None
            if self.provider == "azure":
                logger.warning(f"[Cloud OCR] Azure selected but not available (SDK installed: {AZURE_AVAILABLE})")
        
        # Log final status
        logger.info(f"[Cloud OCR] Service status:")
        logger.info(f"  - Provider: {self.provider}")
        logger.info(f"  - AWS Textract: {'✓' if self.textract_client else '✗'}")
        logger.info(f"  - Azure DI: {'✓' if self.azure_client else '✗'}")
    
    async def extract(
        self,
        file_path: str,
        file_type: str,
        pages: Optional[List[int]] = None
    ) -> ExtractedContent:
        """Extract text using cloud OCR."""
        logger.info(f"[Cloud OCR] Starting extraction for {file_type} file: {file_path}")
        logger.debug(f"[Cloud OCR] Pages to process: {pages if pages else 'all'}")
        logger.debug(f"[Cloud OCR] Max pages limit: {settings.MAX_CLOUD_OCR_PAGES}")
        
        if self.provider == "aws" and self.textract_client:
            logger.info("[Cloud OCR] Using AWS Textract")
            return await self._extract_with_textract(file_path, pages)
        elif self.provider == "azure" and self.azure_client:
            logger.info("[Cloud OCR] Using Azure Document Intelligence")
            return await self._extract_with_azure(file_path, pages)
        else:
            error_msg = (
                f"Cloud OCR not available. Provider: {self.provider}, "
                f"AWS configured: {self.textract_client is not None}, "
                f"Azure configured: {self.azure_client is not None}"
            )
            logger.error(f"[Cloud OCR] {error_msg}")
            raise ValueError(error_msg)
    
    async def _extract_with_textract(
        self,
        file_path: str,
        pages: Optional[List[int]] = None
    ) -> ExtractedContent:
        """Extract text using AWS Textract."""
        try:
            import asyncio
            from botocore.exceptions import ClientError
            import time
            
            with open(file_path, 'rb') as f:
                document_bytes = f.read()
            
            file_size_mb = len(document_bytes) / (1024 * 1024)
            file_size_kb = len(document_bytes) / 1024
            logger.info(f"[Cloud OCR/Textract] Processing document ({file_size_mb:.2f} MB, {file_size_kb:.2f} KB)")
            
            # AWS Textract limits:
            # - Synchronous APIs (detect_document_text, analyze_document): Max 5MB, single page
            # - Asynchronous APIs (start_document_text_detection, start_document_analysis): Up to 500MB, multi-page
            
            # AWS Textract sync APIs only support single-page documents
            # For multi-page PDFs, we need async API (requires S3)
            # Try detect_document_text first (most compatible, single page only)
            # Then try analyze_document if detect_document_text works
            
            response = None
            last_error = None
            
            # Strategy 1: Try detect_document_text (most compatible, but no tables)
            if file_size_kb <= 5000:  # 5MB limit for sync API
                try:
                    logger.info("[Cloud OCR/Textract] Attempting detect_document_text (most compatible)")
                    response = self.textract_client.detect_document_text(
                        Document={'Bytes': document_bytes}
                    )
                    logger.info("[Cloud OCR/Textract] detect_document_text succeeded")
                except ClientError as e1:
                    error_code1 = e1.response.get('Error', {}).get('Code', 'Unknown')
                    last_error = e1
                    logger.warning(f"[Cloud OCR/Textract] detect_document_text failed ({error_code1}): {str(e1)}")
                    
                    # Strategy 2: Try analyze_document (supports tables, but more strict)
                    if error_code1 in ['UnsupportedDocumentException', 'InvalidParameterException']:
                        try:
                            logger.info("[Cloud OCR/Textract] Trying analyze_document (supports tables)")
                            response = self.textract_client.analyze_document(
                                Document={'Bytes': document_bytes},
                                FeatureTypes=['TABLES', 'FORMS']
                            )
                            logger.info("[Cloud OCR/Textract] analyze_document succeeded")
                        except ClientError as e2:
                            error_code2 = e2.response.get('Error', {}).get('Code', 'Unknown')
                            last_error = e2
                            logger.error(f"[Cloud OCR/Textract] analyze_document also failed ({error_code2}): {str(e2)}")
            
            # If both sync APIs failed, the document might be:
            # 1. Multi-page (sync APIs only support single page)
            # 2. Too large (>5MB)
            # 3. Corrupted or unsupported format
            if response is None:
                error_code = last_error.response.get('Error', {}).get('Code', 'Unknown') if last_error else 'Unknown'
                error_msg = str(last_error) if last_error else 'Unknown error'
                
                # Log the reason for fallback (for debugging)
                if 'UnsupportedDocumentException' in error_code or 'UnsupportedDocumentException' in error_msg:
                    logger.warning(
                        f"[Cloud OCR/Textract] Document appears to be multi-page or unsupported format. "
                        f"Textract sync APIs only support single-page documents. "
                        f"Size: {file_size_mb:.2f} MB. "
                        f"Falling back to local OCR automatically."
                    )
                else:
                    logger.warning(
                        f"[Cloud OCR/Textract] Cannot process document ({error_code}): {error_msg}. "
                        f"Size: {file_size_mb:.2f} MB. "
                        f"Falling back to local OCR automatically."
                    )
                
                # Raise a simple exception that will trigger automatic fallback
                raise ValueError("Cloud OCR cannot process this document, falling back to local OCR")
            
            # Parse response
            extracted = self._parse_textract_response(response)
            
            logger.info(f"[Cloud OCR/Textract] Extraction complete: {len(extracted['text'])} chars, {len(extracted.get('tables', []))} tables")
            
            return ExtractedContent(
                text=extracted['text'],
                tables=extracted.get('tables', []),
                metadata={
                    "extraction_method": "aws_textract",
                    "provider": "aws",
                    "blocks_count": len(response.get('Blocks', [])),
                    "file_size_mb": file_size_mb
                },
                confidence=extracted.get('confidence', 0.95),
                pages_processed=extracted.get('pages', 1)
            )
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = str(e)
            logger.error(f"[Cloud OCR/Textract] AWS error ({error_code}): {error_msg}")
            
            # Provide helpful error messages
            if error_code == 'UnsupportedDocumentException':
                raise ValueError(f"AWS Textract: Document format not supported. "
                               f"Textract supports PDF, PNG, JPEG, TIFF. "
                               f"Document size: {file_size_mb:.2f} MB. "
                               f"Try using local OCR instead.")
            elif error_code == 'InvalidParameterException':
                raise ValueError(f"AWS Textract: Invalid document parameters. "
                               f"Document may be corrupted or too large for sync API. "
                               f"Size: {file_size_mb:.2f} MB")
            else:
                raise ValueError(f"AWS Textract error ({error_code}): {error_msg}")
        except Exception as e:
            logger.error(f"[Cloud OCR/Textract] Extraction failed: {str(e)}", exc_info=True)
            raise
    
    async def _extract_with_azure(
        self,
        file_path: str,
        pages: Optional[List[int]] = None
    ) -> ExtractedContent:
        """Extract text using Azure Document Intelligence."""
        try:
            with open(file_path, 'rb') as f:
                document_bytes = f.read()
            
            # Call Azure Document Intelligence
            poller = self.azure_client.begin_analyze_document(
                model_id="prebuilt-layout",
                analyze_request=document_bytes,
                content_type="application/pdf"
            )
            result = poller.result()
            
            # Parse response
            extracted = self._parse_azure_response(result)
            
            return ExtractedContent(
                text=extracted['text'],
                tables=extracted.get('tables', []),
                metadata={
                    "extraction_method": "azure_document_intelligence",
                    "provider": "azure"
                },
                confidence=0.95,
                pages_processed=len(result.pages) if result.pages else 1
            )
        
        except Exception as e:
            logger.error(f"Azure extraction failed: {str(e)}")
            raise
    
    def _parse_textract_response(self, response: Dict) -> Dict[str, Any]:
        """Parse AWS Textract response, including tables."""
        blocks = response.get('Blocks', [])
        
        # Build block map for relationships
        block_map = {b['Id']: b for b in blocks}
        
        # Extract text from LINE blocks
        text_blocks = [b for b in blocks if b['BlockType'] == 'LINE']
        text_lines = []
        current_page = 1
        
        for block in text_blocks:
            page = block.get('Page', current_page)
            if page != current_page:
                text_lines.append(f"\n[Página {page}]\n")
                current_page = page
            text_lines.append(block['Text'])
        
        text = '\n'.join(text_lines)
        
        # Extract tables (Textract provides table structure)
        tables = []
        table_blocks = [b for b in blocks if b['BlockType'] == 'TABLE']
        
        for table_block in table_blocks:
            table_data = []
            relationships = table_block.get('Relationships', [])
            
            # Get all cells in this table
            cell_ids = []
            for rel in relationships:
                if rel['Type'] == 'CHILD':
                    cell_ids.extend(rel.get('Ids', []))
            
            # Extract cell data
            cells = {}
            for cell_id in cell_ids:
                cell = block_map.get(cell_id)
                if cell and cell['BlockType'] == 'CELL':
                    row_index = cell.get('RowIndex', 0)
                    col_index = cell.get('ColumnIndex', 0)
                    cell_text = ""
                    
                    # Get text from cell's children
                    cell_rels = cell.get('Relationships', [])
                    for rel in cell_rels:
                        if rel['Type'] == 'CHILD':
                            for child_id in rel.get('Ids', []):
                                child = block_map.get(child_id)
                                if child and child['BlockType'] == 'WORD':
                                    cell_text += child.get('Text', '') + ' '
                    
                    if (row_index, col_index) not in cells:
                        cells[(row_index, col_index)] = cell_text.strip()
            
            # Convert to table structure (list of rows)
            if cells:
                max_row = max(r for r, c in cells.keys())
                max_col = max(c for r, c in cells.keys())
                
                table_rows = []
                for row in range(1, max_row + 1):
                    table_row = []
                    for col in range(1, max_col + 1):
                        table_row.append(cells.get((row, col), ''))
                    table_rows.append(table_row)
                
                if table_rows:
                    tables.append(table_rows)
                    logger.debug(f"[Cloud OCR/Textract] Extracted table with {len(table_rows)} rows, {len(table_rows[0]) if table_rows else 0} columns")
        
        pages = len(set(b.get('Page', 1) for b in blocks))
        
        return {
            'text': text,
            'tables': tables,
            'confidence': 0.95,
            'pages': pages
        }
    
    def _parse_azure_response(self, result) -> Dict[str, Any]:
        """Parse Azure Document Intelligence response."""
        # Extract text from paragraphs
        text_parts = []
        if hasattr(result, 'paragraphs') and result.paragraphs:
            for para in result.paragraphs:
                if hasattr(para, 'content'):
                    text_parts.append(para.content)
        
        text = '\n'.join(text_parts)
        
        # Extract tables
        tables = []
        if hasattr(result, 'tables') and result.tables:
            for table in result.tables:
                table_data = []
                # Azure tables have cells with row/column indices
                # Would need more complex parsing
                tables.append(table_data)
        
        return {
            'text': text,
            'tables': tables
        }
