"""
Embedding Service — Multi-provider

Generates vector embeddings for RAG semantic search.
Supports OpenAI and Gemini. Auto-detects the best available provider
by checking environment variables first, then DB model_configs.
"""

import os
import time
import hashlib
from typing import List, Optional, Tuple
from collections import OrderedDict

from core.utils.logging_config import get_logger
from ..config import AIAgentConfig
from ..exceptions import EmbeddingError, ConfigurationError

logger = get_logger('jarvis.ai_agent.services.embedding')

# Module-level query embedding cache (shared across service instances).
_QUERY_CACHE: OrderedDict[str, Tuple[List[float], float]] = OrderedDict()
_QUERY_CACHE_MAX = 256
_QUERY_CACHE_TTL = 600  # 10 minutes

# Provider definitions in priority order (first match wins)
_EMBEDDING_PROVIDERS = [
    {
        'name': 'openai',
        'env_key': 'OPENAI_API_KEY',
        'db_provider': 'openai',
        'model': 'text-embedding-3-small',
        'dimensions': 1536,
    },
    {
        'name': 'gemini',
        'env_key': 'GOOGLE_AI_API_KEY',
        'db_provider': 'gemini',
        'model': 'models/text-embedding-004',
        'dimensions': 768,
    },
]


class EmbeddingService:
    """
    Multi-provider embedding service.

    Auto-detects the best available provider:
      1. OpenAI  (text-embedding-3-small, 1536 dims)
      2. Gemini  (text-embedding-004, 768 dims)

    Keys are resolved from environment variables first, then from
    ai_agent.model_configs in the database.
    """

    def __init__(self, config: Optional[AIAgentConfig] = None):
        self.config = config or AIAgentConfig()
        self._provider_name: Optional[str] = None
        self._api_key: Optional[str] = None
        self._model: Optional[str] = None
        self._dimensions: Optional[int] = None
        self._client = None
        self._detected = False

    # ── Provider detection ──────────────────────────────────────

    def _detect_provider(self) -> None:
        """Auto-detect best available embedding provider (cached)."""
        if self._detected:
            return
        self._detected = True

        for prov in _EMBEDDING_PROVIDERS:
            key = self._find_key(prov['env_key'], prov['db_provider'])
            if key:
                self._provider_name = prov['name']
                self._api_key = key
                self._model = prov['model']
                self._dimensions = prov['dimensions']
                logger.info(
                    f"Embedding provider: {prov['name']} "
                    f"(model={prov['model']}, dims={prov['dimensions']})"
                )
                return

        logger.warning("No embedding provider available — text search fallback only")

    @staticmethod
    def _find_key(env_var: str, db_provider: str) -> Optional[str]:
        """Find API key: env var first, then DB model_configs."""
        # 1. Environment variable
        key = os.environ.get(env_var)
        if key:
            return key

        # 2. Database model_configs (active first, then any)
        try:
            from ..repositories import ModelConfigRepository
            from ..models import LLMProvider
            provider_enum = LLMProvider(db_provider)
            repo = ModelConfigRepository()
            # Check active configs first
            for cfg in repo.get_by_provider(provider_enum):
                if cfg.api_key_encrypted:
                    return cfg.api_key_encrypted
            # Check all configs (key might exist on inactive model)
            for cfg in repo.get_all():
                if cfg.provider == provider_enum and cfg.api_key_encrypted:
                    return cfg.api_key_encrypted
        except Exception as e:
            logger.debug(f"Could not check DB for {db_provider} key: {e}")

        return None

    # ── Public properties ───────────────────────────────────────

    @property
    def provider_name(self) -> Optional[str]:
        """Active embedding provider name ('openai', 'gemini', or None)."""
        self._detect_provider()
        return self._provider_name

    @property
    def dimensions(self) -> Optional[int]:
        """Embedding vector dimensions for the active provider."""
        self._detect_provider()
        return self._dimensions

    def is_available(self) -> bool:
        """Check if any embedding provider is available."""
        self._detect_provider()
        return self._provider_name is not None

    # ── Embedding generation ────────────────────────────────────

    def generate_embedding(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            use_cache: Check/populate query cache (default True).

        Returns:
            Embedding vector (list of floats)

        Raises:
            EmbeddingError: If embedding generation fails
            ConfigurationError: If no provider available
        """
        self._detect_provider()
        if not self._provider_name:
            raise ConfigurationError(
                "No embedding provider available. "
                "Configure an OpenAI or Gemini API key in Settings > AI Agent."
            )

        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")

        # Check cache
        cache_key = None
        if use_cache:
            cache_key = hashlib.md5(text.encode('utf-8')).hexdigest()
            cached = _QUERY_CACHE.get(cache_key)
            if cached:
                embedding, ts = cached
                if (time.time() - ts) < _QUERY_CACHE_TTL:
                    _QUERY_CACHE.move_to_end(cache_key)
                    return embedding
                else:
                    del _QUERY_CACHE[cache_key]

        try:
            if self._provider_name == 'openai':
                embedding = self._embed_openai(text)
            elif self._provider_name == 'gemini':
                embedding = self._embed_gemini(text)
            else:
                raise ConfigurationError(f"Unknown provider: {self._provider_name}")

            logger.debug(f"Generated embedding: {len(embedding)} dims via {self._provider_name}")

            # Cache result
            if use_cache and cache_key:
                _QUERY_CACHE[cache_key] = (embedding, time.time())
                while len(_QUERY_CACHE) > _QUERY_CACHE_MAX:
                    _QUERY_CACHE.popitem(last=False)

            return embedding

        except (EmbeddingError, ConfigurationError):
            raise
        except Exception as e:
            logger.error(f"Embedding failed ({self._provider_name}): {e}")
            raise EmbeddingError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        self._detect_provider()
        if not self._provider_name:
            raise ConfigurationError("No embedding provider available")

        try:
            if self._provider_name == 'openai':
                return self._batch_openai(texts, batch_size)
            elif self._provider_name == 'gemini':
                return self._batch_gemini(texts, batch_size)
            else:
                raise ConfigurationError(f"Unknown provider: {self._provider_name}")
        except (EmbeddingError, ConfigurationError):
            raise
        except Exception as e:
            logger.error(f"Batch embedding failed ({self._provider_name}): {e}")
            raise EmbeddingError(f"Batch embedding failed: {e}")

    def compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content for change detection."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    # ── OpenAI backend ──────────────────────────────────────────

    def _get_openai_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def _embed_openai(self, text: str) -> List[float]:
        """Generate single embedding via OpenAI."""
        import openai as openai_mod
        try:
            client = self._get_openai_client()
            response = client.embeddings.create(model=self._model, input=text)
            return response.data[0].embedding
        except openai_mod.RateLimitError as e:
            raise EmbeddingError(f"OpenAI rate limit: {e}")
        except openai_mod.AuthenticationError as e:
            raise ConfigurationError(f"Invalid OpenAI API key: {e}")

    def _batch_openai(self, texts: List[str], batch_size: int) -> List[List[float]]:
        """Batch embed via OpenAI (native batching)."""
        client = self._get_openai_client()
        embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = [t for t in texts[i:i + batch_size] if t and t.strip()]
            if not batch:
                continue
            response = client.embeddings.create(model=self._model, input=batch)
            embeddings.extend([item.embedding for item in response.data])
            logger.debug(f"OpenAI batch: {len(batch)} texts embedded")
        return embeddings

    # ── Gemini backend ──────────────────────────────────────────

    def _embed_gemini(self, text: str) -> List[float]:
        """Generate single embedding via Google Gemini."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ConfigurationError("google-generativeai not installed")

        genai.configure(api_key=self._api_key)
        result = genai.embed_content(
            model=self._model,
            content=text,
            task_type='retrieval_document',
        )
        return result['embedding']

    def _batch_gemini(self, texts: List[str], batch_size: int) -> List[List[float]]:
        """Batch embed via Gemini (sequential — no native batch API)."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ConfigurationError("google-generativeai not installed")

        genai.configure(api_key=self._api_key)
        embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = [t for t in texts[i:i + batch_size] if t and t.strip()]
            for txt in batch:
                result = genai.embed_content(
                    model=self._model,
                    content=txt,
                    task_type='retrieval_document',
                )
                embeddings.append(result['embedding'])
            logger.debug(f"Gemini batch: {len(batch)} texts embedded")
        return embeddings
