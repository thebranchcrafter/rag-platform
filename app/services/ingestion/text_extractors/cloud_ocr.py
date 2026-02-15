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
            with open(file_path, 'rb') as f:
                document_bytes = f.read()
            
            # Call Textract
            # Note: Textract doesn't support page selection in basic API
            # For page selection, would need to use async API
            response = self.textract_client.detect_document_text(
                Document={'Bytes': document_bytes}
            )
            
            # Parse response
            extracted = self._parse_textract_response(response)
            
            return ExtractedContent(
                text=extracted['text'],
                tables=extracted.get('tables', []),
                metadata={
                    "extraction_method": "aws_textract",
                    "provider": "aws",
                    "blocks_count": len(response.get('Blocks', []))
                },
                confidence=extracted.get('confidence', 0.95),
                pages_processed=extracted.get('pages', 1)
            )
        
        except Exception as e:
            logger.error(f"Textract extraction failed: {str(e)}")
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
        """Parse AWS Textract response."""
        blocks = response.get('Blocks', [])
        
        # Extract text blocks
        text_blocks = [b for b in blocks if b['BlockType'] == 'LINE']
        text = '\n'.join(b['Text'] for b in text_blocks)
        
        # Extract tables (simplified)
        tables = []
        # Textract tables are complex, would need more parsing
        
        return {
            'text': text,
            'tables': tables,
            'confidence': 0.95,
            'pages': len(set(b.get('Page', 1) for b in blocks))
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
