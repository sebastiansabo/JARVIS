"""
AI Agent Routes

API endpoints and page routes for AI Agent module.
"""

from functools import wraps
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from core.utils.logging_config import get_logger
from . import ai_agent_bp
from .services import AIAgentService
from .models import ConversationStatus

logger = get_logger('jarvis.ai_agent.routes')

# Initialize service (singleton pattern)
_service = None


def get_service() -> AIAgentService:
    """Get or create AI Agent service instance."""
    global _service
    if _service is None:
        _service = AIAgentService()
    return _service


def ai_agent_required(f):
    """Decorator to require AI Agent access permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        # For now, allow all authenticated users
        # Future: add can_access_ai_agent permission
        return f(*args, **kwargs)
    return decorated


# ============== Page Routes ==============

@ai_agent_bp.route('/')
@login_required
@ai_agent_required
def index():
    """AI Agent chat interface page."""
    service = get_service()

    # Get user's recent conversations
    result = service.list_conversations(
        user_id=current_user.id,
        status=ConversationStatus.ACTIVE,
        limit=20,
    )

    conversations = result.data if result.success else []

    # Get available models
    models_result = service.get_available_models()
    models = models_result.data if models_result.success else []

    return render_template(
        'ai_agent/index.html',
        conversations=conversations,
        models=models,
    )


@ai_agent_bp.route('/conversations')
@login_required
@ai_agent_required
def conversations_page():
    """Conversation history page."""
    service = get_service()

    # Get all user conversations (including archived)
    active_result = service.list_conversations(
        user_id=current_user.id,
        status=ConversationStatus.ACTIVE,
        limit=100,
    )

    archived_result = service.list_conversations(
        user_id=current_user.id,
        status=ConversationStatus.ARCHIVED,
        limit=100,
    )

    return render_template(
        'ai_agent/conversations.html',
        active_conversations=active_result.data if active_result.success else [],
        archived_conversations=archived_result.data if archived_result.success else [],
    )


# ============== API Routes ==============

@ai_agent_bp.route('/api/conversations', methods=['GET'])
@login_required
@ai_agent_required
def api_list_conversations():
    """API: List user's conversations."""
    service = get_service()

    status_str = request.args.get('status', 'active')
    try:
        status = ConversationStatus(status_str)
    except ValueError:
        status = ConversationStatus.ACTIVE

    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    result = service.list_conversations(
        user_id=current_user.id,
        status=status,
        limit=min(limit, 100),  # Cap at 100
        offset=offset,
    )

    if not result.success:
        return jsonify({'error': result.error}), 500

    # Convert to serializable format
    conversations = []
    for conv in result.data:
        conversations.append({
            'id': conv.id,
            'title': conv.title,
            'status': conv.status.value,
            'message_count': conv.message_count,
            'total_tokens': conv.total_tokens,
            'total_cost': str(conv.total_cost),
            'created_at': conv.created_at.isoformat() if conv.created_at else None,
            'updated_at': conv.updated_at.isoformat() if conv.updated_at else None,
        })

    return jsonify({'conversations': conversations})


@ai_agent_bp.route('/api/conversations', methods=['POST'])
@login_required
@ai_agent_required
def api_create_conversation():
    """API: Create a new conversation."""
    service = get_service()
    data = request.get_json() or {}

    result = service.create_conversation(
        user_id=current_user.id,
        title=data.get('title'),
        model_config_id=data.get('model_config_id'),
    )

    if not result.success:
        return jsonify({'error': result.error}), 500

    conv = result.data
    return jsonify({
        'id': conv.id,
        'title': conv.title,
        'status': conv.status.value,
        'created_at': conv.created_at.isoformat() if conv.created_at else None,
    }), 201


@ai_agent_bp.route('/api/conversations/<int:conversation_id>', methods=['GET'])
@login_required
@ai_agent_required
def api_get_conversation(conversation_id: int):
    """API: Get conversation with messages."""
    service = get_service()

    result = service.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    if not result.success:
        return jsonify({'error': result.error}), 404

    data = result.data
    conv = data['conversation']
    messages = data['messages']

    return jsonify({
        'conversation': {
            'id': conv.id,
            'title': conv.title,
            'status': conv.status.value,
            'message_count': conv.message_count,
            'total_tokens': conv.total_tokens,
            'total_cost': str(conv.total_cost),
            'model_config_id': conv.model_config_id,
            'created_at': conv.created_at.isoformat() if conv.created_at else None,
            'updated_at': conv.updated_at.isoformat() if conv.updated_at else None,
        },
        'messages': [
            {
                'id': msg.id,
                'role': msg.role.value,
                'content': msg.content,
                'input_tokens': msg.input_tokens,
                'output_tokens': msg.output_tokens,
                'cost': str(msg.cost),
                'response_time_ms': msg.response_time_ms,
                'created_at': msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ],
    })


@ai_agent_bp.route('/api/conversations/<int:conversation_id>/archive', methods=['POST'])
@login_required
@ai_agent_required
def api_archive_conversation(conversation_id: int):
    """API: Archive a conversation."""
    service = get_service()

    result = service.archive_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    if not result.success:
        return jsonify({'error': result.error}), 404

    return jsonify({'success': True})


@ai_agent_bp.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
@login_required
@ai_agent_required
def api_delete_conversation(conversation_id: int):
    """API: Delete a conversation."""
    service = get_service()

    result = service.delete_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    if not result.success:
        return jsonify({'error': result.error}), 404

    return jsonify({'success': True})


@ai_agent_bp.route('/api/chat', methods=['POST'])
@login_required
@ai_agent_required
def api_chat():
    """
    API: Send a message and get AI response.

    Request body:
        {
            "conversation_id": int,
            "message": str,
            "model_config_id": int (optional)
        }

    Response:
        {
            "message": {
                "id": int,
                "role": "assistant",
                "content": str,
                ...
            },
            "tokens_used": int,
            "cost": str,
            "response_time_ms": int
        }
    """
    service = get_service()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body required'}), 400

    conversation_id = data.get('conversation_id')
    message = data.get('message', '').strip()
    model_config_id = data.get('model_config_id')

    if not conversation_id:
        return jsonify({'error': 'conversation_id required'}), 400

    if not message:
        return jsonify({'error': 'message required'}), 400

    result = service.chat(
        conversation_id=conversation_id,
        user_id=current_user.id,
        user_message=message,
        model_config_id=model_config_id,
    )

    if not result.success:
        logger.error(f"Chat failed: {result.error}")
        return jsonify({'error': result.error}), 500

    response = result.data
    msg = response.message

    return jsonify({
        'message': {
            'id': msg.id,
            'role': msg.role.value,
            'content': msg.content,
            'input_tokens': msg.input_tokens,
            'output_tokens': msg.output_tokens,
            'cost': str(msg.cost),
            'response_time_ms': msg.response_time_ms,
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
        },
        'rag_sources': [
            {
                'doc_id': src.doc_id,
                'score': src.score,
                'snippet': src.snippet,
                'source_type': src.source_type,
            }
            for src in response.rag_sources
        ],
        'tokens_used': response.tokens_used,
        'cost': str(response.cost),
        'response_time_ms': response.response_time_ms,
    })


@ai_agent_bp.route('/api/models', methods=['GET'])
@login_required
@ai_agent_required
def api_list_models():
    """API: List available LLM models."""
    service = get_service()

    result = service.get_available_models()

    if not result.success:
        return jsonify({'error': result.error}), 500

    models = []
    for model in result.data:
        models.append({
            'id': model.id,
            'provider': model.provider.value,
            'model_name': model.model_name,
            'display_name': model.display_name,
            'cost_per_1k_input': str(model.cost_per_1k_input),
            'cost_per_1k_output': str(model.cost_per_1k_output),
            'max_tokens': model.max_tokens,
            'is_default': model.is_default,
        })

    return jsonify({'models': models})


# ============== Admin Routes ==============

@ai_agent_bp.route('/api/rag/reindex', methods=['POST'])
@login_required
@ai_agent_required
def api_rag_reindex():
    """
    API: Trigger RAG document reindexing.

    Admin-only endpoint for reindexing invoice data.
    Requires settings access permission.
    """
    # Check admin permission
    if not getattr(current_user, 'can_access_settings', False):
        return jsonify({'error': 'Admin access required'}), 403

    from .services import RAGService
    rag_service = RAGService()

    data = request.get_json() or {}
    limit = data.get('limit', 100)

    result = rag_service.index_invoices_batch(limit=limit)

    if not result.success:
        return jsonify({'error': result.error}), 500

    return jsonify({
        'success': True,
        'indexed': result.data.get('indexed', 0),
    })


@ai_agent_bp.route('/api/rag/stats', methods=['GET'])
@login_required
@ai_agent_required
def api_rag_stats():
    """
    API: Get RAG statistics.

    Returns document counts and capability status.
    """
    from .services import RAGService
    rag_service = RAGService()

    stats = rag_service.get_stats()

    return jsonify({
        'total_documents': stats.get('total_documents', 0),
        'by_source_type': stats.get('by_source_type', {}),
        'has_pgvector': stats.get('has_pgvector', False),
        'has_embeddings': stats.get('has_embeddings', False),
    })
