"""Knowledge Service — extracts and manages learned patterns from user feedback.

Processes positively-rated AI responses to extract reusable patterns.
Supports both LLM-based extraction and heuristic fallback.
"""

import json
from typing import Optional, List, Dict

from core.utils.logging_config import get_logger
from ..config import AIAgentConfig
from ..repositories.feedback_repository import FeedbackRepository
from ..repositories.knowledge_repository import KnowledgeRepository
from .embedding_service import EmbeddingService

logger = get_logger('jarvis.ai_agent.services.knowledge')

# Extraction prompt for the LLM
EXTRACTION_PROMPT = """You are analyzing successful AI assistant interactions to extract reusable patterns.

Below are pairs of user queries and AI responses that received positive feedback (thumbs up).
Extract general, reusable patterns that would help the AI handle similar queries better in the future.

Rules:
- Extract 1-3 patterns per interaction (only if genuinely useful)
- Patterns must be GENERIC — never include user names, specific IDs, or private data
- Focus on: which tools work for which query types, Romanian language mappings, domain-specific knowledge
- Categories: tool_usage, query_pattern, domain_fact, response_style

Return a JSON array of objects: [{"pattern": "...", "category": "..."}]
If no useful patterns can be extracted, return an empty array: []

Interactions:
"""


class KnowledgeService:
    """Service for extracting and managing learned knowledge patterns."""

    def __init__(self, config: Optional[AIAgentConfig] = None):
        self.config = config or AIAgentConfig()
        self.feedback_repo = FeedbackRepository()
        self.knowledge_repo = KnowledgeRepository()
        self.embedding_service = EmbeddingService(self.config)

    def extract_from_feedback(self) -> Dict:
        """Extract knowledge patterns from positively-rated messages.

        Returns dict with extraction results.
        """
        # Get the last processed feedback ID
        last_id = self._get_last_processed_id()

        # Get unprocessed positive feedback
        feedbacks = self.feedback_repo.get_unprocessed_positive(last_id, limit=50)
        if not feedbacks:
            return {'extracted': 0, 'merged': 0, 'message': 'No new positive feedback to process'}

        extracted = 0
        merged = 0

        # Process in batches of 10
        for i in range(0, len(feedbacks), 10):
            batch = feedbacks[i:i + 10]

            # Try heuristic extraction first (no LLM needed)
            for fb in batch:
                heuristic_patterns = self._extract_heuristic(fb)
                for pattern, category in heuristic_patterns:
                    result = self._store_pattern(pattern, category)
                    if result == 'new':
                        extracted += 1
                    elif result == 'merged':
                        merged += 1

            # Try LLM-based extraction for richer patterns
            llm_patterns = self._extract_with_llm(batch)
            for pattern, category in llm_patterns:
                result = self._store_pattern(pattern, category)
                if result == 'new':
                    extracted += 1
                elif result == 'merged':
                    merged += 1

        # Update the watermark
        if feedbacks:
            max_id = max(fb['feedback_id'] for fb in feedbacks)
            self._set_last_processed_id(max_id)

        logger.info(f"Knowledge extraction: {extracted} new, {merged} merged from {len(feedbacks)} feedbacks")
        return {'extracted': extracted, 'merged': merged, 'processed': len(feedbacks)}

    def get_relevant_patterns(self, query_text: str, limit: int = 5) -> List[str]:
        """Get learned patterns relevant to a query.

        Returns list of pattern strings for injection into system prompt.
        """
        if not self.embedding_service.is_available():
            # Fallback: return top patterns by confidence
            patterns = self.knowledge_repo.get_all_active(limit=limit)
            return [p['pattern'] for p in patterns]

        try:
            embedding = self.embedding_service.generate_embedding(query_text)
            if not embedding:
                return []
            results = self.knowledge_repo.search_by_vector(embedding, limit=limit, min_score=0.3)
            return [r['pattern'] for r in results]
        except Exception as e:
            logger.warning(f"Knowledge vector search failed: {e}")
            # Fallback to top patterns
            patterns = self.knowledge_repo.get_all_active(limit=limit)
            return [p['pattern'] for p in patterns]

    def _extract_heuristic(self, feedback: dict) -> List[tuple]:
        """Extract patterns from feedback without LLM (fast, cheap).

        Looks for tool usage in rag_sources metadata.
        """
        patterns = []
        user_query = feedback.get('user_query', '')
        rag_sources = feedback.get('rag_sources')

        if not user_query:
            return patterns

        # If the response used RAG sources, note what source types were useful
        if rag_sources and isinstance(rag_sources, list):
            source_types = set()
            for src in rag_sources:
                if isinstance(src, dict) and src.get('source_type'):
                    source_types.add(src['source_type'])
            if source_types:
                query_preview = user_query[:80].replace('"', "'")
                patterns.append((
                    f"Queries like \"{query_preview}\" benefit from {', '.join(sorted(source_types))} RAG sources",
                    'query_pattern'
                ))

        return patterns

    def _extract_with_llm(self, batch: List[dict]) -> List[tuple]:
        """Extract patterns using LLM (richer, more expensive)."""
        # Build the prompt with anonymized interactions
        interactions = []
        for fb in batch:
            user_q = fb.get('user_query', '').strip()
            assistant_a = fb.get('assistant_content', '').strip()
            if user_q and assistant_a:
                # Truncate long responses
                if len(assistant_a) > 500:
                    assistant_a = assistant_a[:500] + '...'
                interactions.append(f"User: {user_q}\nAssistant: {assistant_a}")

        if not interactions:
            return []

        prompt = EXTRACTION_PROMPT + '\n\n---\n'.join(interactions)

        # Use the cheapest available provider
        provider, model_name, api_key = self._get_cheapest_provider()
        if not provider:
            logger.warning("No LLM provider available for knowledge extraction")
            return []

        try:
            response = provider.generate(
                model_name=model_name,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=1024,
                temperature=0.3,
                api_key=api_key,
            )

            # Parse JSON from response
            content = response.content.strip()
            # Handle markdown code blocks
            if content.startswith('```'):
                content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()

            patterns = json.loads(content)
            if not isinstance(patterns, list):
                return []

            result = []
            for p in patterns:
                if isinstance(p, dict) and p.get('pattern') and p.get('category'):
                    category = p['category']
                    if category not in ('tool_usage', 'query_pattern', 'domain_fact', 'response_style'):
                        category = 'query_pattern'
                    result.append((p['pattern'], category))

            return result

        except Exception as e:
            logger.warning(f"LLM knowledge extraction failed: {e}")
            return []

    def _store_pattern(self, pattern: str, category: str) -> str:
        """Store a pattern, deduplicating via vector similarity.

        Returns 'new', 'merged', or 'skipped'.
        """
        if not pattern or len(pattern) < 10:
            return 'skipped'

        # Try to embed for dedup
        embedding = None
        if self.embedding_service.is_available():
            try:
                embedding = self.embedding_service.generate_embedding(pattern)
            except Exception:
                pass

        # Check for similar existing pattern
        if embedding:
            similar = self.knowledge_repo.find_similar(embedding, threshold=0.92)
            if similar:
                self.knowledge_repo.increment_source_count(similar['id'])
                return 'merged'

        # Insert new pattern
        self.knowledge_repo.create(pattern, category, embedding)
        return 'new'

    def _get_cheapest_provider(self):
        """Get the cheapest available LLM provider for extraction.

        Prefers: groq > grok > openai > gemini > claude (by cost).
        """
        from ..repositories import ModelConfigRepository
        repo = ModelConfigRepository()

        preferred_order = ['groq', 'grok', 'openai', 'gemini', 'claude']
        all_models = repo.get_all_active()

        for provider_name in preferred_order:
            for model in all_models:
                if model.provider.value == provider_name:
                    from ..providers import (
                        GroqProvider, GrokProvider, OpenAIProvider,
                        GeminiProvider, ClaudeProvider
                    )
                    provider_map = {
                        'groq': GroqProvider,
                        'grok': GrokProvider,
                        'openai': OpenAIProvider,
                        'gemini': GeminiProvider,
                        'claude': ClaudeProvider,
                    }
                    provider_cls = provider_map.get(provider_name)
                    if provider_cls:
                        return provider_cls(), model.model_name, model.api_key_encrypted

        return None, None, None

    def _get_last_processed_id(self) -> int:
        """Get the last processed feedback ID from settings."""
        try:
            from core.notifications.repositories.notification_repository import NotificationRepository
            repo = NotificationRepository()
            settings = repo.get_settings()
            return int(settings.get('knowledge_last_feedback_id', '0'))
        except Exception:
            return 0

    def _set_last_processed_id(self, feedback_id: int) -> None:
        """Update the last processed feedback ID."""
        try:
            from core.notifications.repositories.notification_repository import NotificationRepository
            repo = NotificationRepository()
            repo.save_settings_bulk({'knowledge_last_feedback_id': str(feedback_id)})
        except Exception as e:
            logger.error(f"Failed to update knowledge watermark: {e}")
