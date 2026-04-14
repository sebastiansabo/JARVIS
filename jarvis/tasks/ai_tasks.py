"""AI-related scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.ai_tasks')


def reindex_rag_documents():
    """Reindex all RAG document sources for the AI agent."""
    try:
        from ai_agent.services.rag_service import RAGService
        svc = RAGService()
        result = svc.index_all_sources()
        total = result.data.get('total', 0) if result.success else 0
        logger.info(f"RAG reindex complete: {total} documents indexed")
    except Exception as e:
        logger.error(f"RAG reindex task failed: {e}")


def extract_ai_knowledge():
    """Extract learned patterns from positively-rated AI responses."""
    try:
        from ai_agent.services.knowledge_service import KnowledgeService
        svc = KnowledgeService()
        result = svc.extract_from_feedback()
        extracted = result.get('extracted', 0)
        merged = result.get('merged', 0)
        if extracted or merged:
            logger.info(f"Knowledge extraction: {extracted} new, {merged} merged")
    except Exception as e:
        logger.error(f"Knowledge extraction task failed: {e}")


def run_daily_digest():
    """Generate and send daily AI-powered digest to admins/managers."""
    try:
        from ai_agent.services.digest_service import generate_and_send
        result = generate_and_send()
        if result.get('skipped'):
            logger.debug(f"Daily digest skipped: {result['skipped']}")
        elif result.get('sent_to'):
            logger.info(f"Daily digest sent to {result['sent_to']} users")
    except Exception as e:
        logger.error(f"Daily digest task failed: {e}")
