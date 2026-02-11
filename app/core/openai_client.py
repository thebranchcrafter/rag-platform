from openai import AsyncOpenAI
from app.core.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Validate API key is set
if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.strip() == "":
    logger.warning("OPENAI_API_KEY is not set. OpenAI features will not work.")

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

async def get_embedding(text: str) -> list[float]:
    """
    Generate embedding for text using OpenAI.
    
    Args:
        text: Input text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    if not client:
        raise ValueError(
            "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable. "
            "You can obtain an API key from https://platform.openai.com/account/api-keys"
        )
    try:
        response = await client.embeddings.create(
            model=settings.OPENAI_MODEL_EMBEDDING,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        raise


async def get_chat_completion(messages: list[dict], max_tokens: Optional[int] = None) -> str:
    """
    Get chat completion from OpenAI.
    Optimized with configurable max_tokens for faster responses.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        max_tokens: Optional maximum tokens in response (default: None, uses model default)
        
    Returns:
        Generated response text
    """
    if not client:
        raise ValueError(
            "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable. "
            "You can obtain an API key from https://platform.openai.com/account/api-keys"
        )
    try:
        # Optimize: lower temperature for faster, more deterministic responses
        # Add max_tokens to limit response length and speed up generation
        params = {
            "model": settings.OPENAI_MODEL_CHAT,
            "messages": messages,
            "temperature": 0.3  # Lower temperature = faster, more focused responses
        }
        if max_tokens:
            params["max_tokens"] = max_tokens
        
        response = await client.chat.completions.create(**params)
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error getting chat completion: {str(e)}")
        raise
