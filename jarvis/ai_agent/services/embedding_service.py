"""
Embedding Service

Generates vector embeddings using OpenAI's text-embedding-3-small model.
These embeddings are used for semantic search in RAG.
"""

import os
from typing import List, Optional
import hashlib

import openai

from core.utils.logging_config import get_logger
from ..config import AIAgentConfig
from ..exceptions import EmbeddingError, ConfigurationError

logger = get_logger('jarvis.ai_agent.services.embedding')


class EmbeddingService:
    """
    Service for generating text embeddings.

    Uses OpenAI's text-embedding-3-small model (1536 dimensions).
    """

    def __init__(self, config: Optional[AIAgentConfig] = None):
        """
        Initialize embedding service.

        Args:
            config: Optional AIAgentConfig, uses defaults if not provided
        """
        self.config = config or AIAgentConfig()
        self._client = None

    def _get_client(self) -> openai.OpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ConfigurationError("OPENAI_API_KEY not found in environment")
            self._client = openai.OpenAI(api_key=api_key)
        return self._client

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of 1536 floats (embedding vector)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")

        try:
            client = self._get_client()

            response = client.embeddings.create(
                model=self.config.embedding_model,
                input=text,
            )

            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding: {len(embedding)} dimensions")

            return embedding

        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit: {e}")
            raise EmbeddingError(f"Rate limit exceeded: {e}")

        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication failed: {e}")
            raise ConfigurationError(f"Invalid OpenAI API key: {e}")

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise EmbeddingError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        OpenAI supports batching up to 2048 texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not texts:
            return []

        embeddings = []

        try:
            client = self._get_client()

            # Process in batches
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]

                # Filter empty texts
                valid_texts = [t for t in batch if t and t.strip()]
                if not valid_texts:
                    continue

                response = client.embeddings.create(
                    model=self.config.embedding_model,
                    input=valid_texts,
                )

                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)

                logger.debug(f"Generated batch of {len(batch_embeddings)} embeddings")

            return embeddings

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise EmbeddingError(f"Batch embedding failed: {e}")

    def compute_content_hash(self, content: str) -> str:
        """
        Compute SHA256 hash of content.

        Used to detect content changes and avoid recomputing embeddings.

        Args:
            content: Text content

        Returns:
            SHA256 hex digest
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def is_available(self) -> bool:
        """
        Check if embedding service is available.

        Returns:
            True if OPENAI_API_KEY is configured
        """
        return bool(os.environ.get('OPENAI_API_KEY'))
