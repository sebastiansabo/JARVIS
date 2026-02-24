"""
AI Agent Routes

API endpoints and page routes for AI Agent module.
"""

from functools import wraps
from flask import request, jsonify, redirect, url_for, Response, stream_with_context
from flask_login import login_required, current_user

from core.utils.logging_config import get_logger
from core.utils.api_helpers import error_response
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
            return redirect(url_for('auth.login'))
        # For now, allow all authenticated users
        # Future: add can_access_ai_agent permission
        return f(*args, **kwargs)
    return decorated


# ============== Page Routes ==============

@ai_agent_bp.route('/')
@login_required
def index():
    """Redirect to React AI Agent page."""
    return redirect('/app/ai-agent')


@ai_agent_bp.route('/conversations')
@login_required
def conversations_page():
    """Redirect to React AI Agent page."""
    return redirect('/app/ai-agent')


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
        return error_response(result.error, 500)

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
        return error_response(result.error, 500)

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
        return error_response(result.error, 404)

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
        return error_response(result.error, 404)

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
        return error_response(result.error, 404)

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
        return error_response('Request body required')

    conversation_id = data.get('conversation_id')
    message = data.get('message', '').strip()
    model_config_id = data.get('model_config_id')

    if not conversation_id:
        return error_response('conversation_id required')

    if not message:
        return error_response('message required')

    result = service.chat(
        conversation_id=conversation_id,
        user_id=current_user.id,
        user_message=message,
        model_config_id=model_config_id,
    )

    if not result.success:
        logger.error(f"Chat failed: {result.error}")
        return error_response(result.error, 500)

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
        return error_response(result.error, 500)

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


@ai_agent_bp.route('/api/chat/stream', methods=['POST'])
@login_required
@ai_agent_required
def api_chat_stream():
    """
    API: Send a message and stream the AI response via SSE.

    Same request body as /api/chat. Returns text/event-stream with:
    - event: token  — incremental text chunks
    - event: done   — final metadata (message_id, tokens, cost, rag_sources)
    - event: error  — error message
    """
    service = get_service()
    data = request.get_json()

    if not data:
        return error_response('Request body required')

    conversation_id = data.get('conversation_id')
    message = data.get('message', '').strip()
    model_config_id = data.get('model_config_id')

    if not conversation_id:
        return error_response('conversation_id required')
    if not message:
        return error_response('message required')

    return Response(
        stream_with_context(service.chat_stream(
            conversation_id=conversation_id,
            user_id=current_user.id,
            user_message=message,
            model_config_id=model_config_id,
        )),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


# ============== Admin Routes ==============

@ai_agent_bp.route('/api/rag/reindex', methods=['POST'])
@login_required
@ai_agent_required
def api_rag_reindex():
    """
    API: Trigger RAG document reindexing.

    Admin-only endpoint for reindexing data sources.
    Supports optional source_type param to reindex a specific type,
    otherwise reindexes all sources.
    """
    # Check admin permission
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    from .services import RAGService
    from .models import RAGSourceType
    rag_service = RAGService()

    data = request.get_json() or {}
    limit = data.get('limit', 500)
    source_type = data.get('source_type')

    # Map source_type string to specific batch method
    BATCH_METHODS = {
        'invoice': rag_service.index_invoices_batch,
        'company': rag_service.index_companies_batch,
        'department': rag_service.index_departments_batch,
        'employee': rag_service.index_employees_batch,
        'transaction': rag_service.index_transactions_batch,
        'efactura': rag_service.index_efactura_batch,
        'event': rag_service.index_events_batch,
        'marketing': rag_service.index_marketing_batch,
        'approval': rag_service.index_approvals_batch,
        'tag': rag_service.index_tags_batch,
    }

    if source_type:
        # Validate source_type
        if source_type not in BATCH_METHODS:
            valid = ', '.join(BATCH_METHODS.keys())
            return error_response(f'Invalid source_type. Valid: {valid}')

        result = BATCH_METHODS[source_type](limit=limit)
        if not result.success:
            return error_response(result.error, 500)

        return jsonify({
            'success': True,
            'source_type': source_type,
            'indexed': result.data.get('indexed', 0),
        })
    else:
        # Reindex all sources
        result = rag_service.index_all_sources(limit=limit)
        if not result.success:
            return error_response(result.error, 500)

        return jsonify({
            'success': True,
            'by_source': result.data.get('by_source', {}),
            'total': result.data.get('total', 0),
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


# ============== Model Management Routes ==============

@ai_agent_bp.route('/api/models/all', methods=['GET'])
@login_required
@ai_agent_required
def api_list_all_models():
    """API: List all models including inactive (admin)."""
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    from .repositories import ModelConfigRepository
    repo = ModelConfigRepository()

    models = []
    for model in repo.get_all():
        models.append({
            'id': model.id,
            'provider': model.provider.value,
            'model_name': model.model_name,
            'display_name': model.display_name,
            'cost_per_1k_input': str(model.cost_per_1k_input),
            'cost_per_1k_output': str(model.cost_per_1k_output),
            'max_tokens': model.max_tokens,
            'default_temperature': str(model.default_temperature),
            'is_active': model.is_active,
            'is_default': model.is_default,
            'has_api_key': bool(model.api_key_encrypted),
        })

    return jsonify({'models': models})


@ai_agent_bp.route('/api/models/<int:model_id>/default', methods=['PUT'])
@login_required
@ai_agent_required
def api_set_default_model(model_id: int):
    """API: Set a model as default for its provider."""
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    from .repositories import ModelConfigRepository
    repo = ModelConfigRepository()

    success = repo.set_default(model_id)
    if not success:
        return error_response('Model not found', 404)

    return jsonify({'success': True})


@ai_agent_bp.route('/api/models/<int:model_id>/toggle', methods=['PUT'])
@login_required
@ai_agent_required
def api_toggle_model(model_id: int):
    """API: Enable or disable a model."""
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    data = request.get_json() or {}
    is_active = data.get('is_active', True)

    from .repositories import ModelConfigRepository
    repo = ModelConfigRepository()

    success = repo.toggle_active(model_id, is_active)
    if not success:
        return error_response('Model not found', 404)

    return jsonify({'success': True})


@ai_agent_bp.route('/api/models/<int:model_id>/api-key', methods=['PUT'])
@login_required
@ai_agent_required
def api_update_model_key(model_id: int):
    """API: Update a model's API key."""
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    data = request.get_json() or {}
    api_key = data.get('api_key', '').strip()
    if not api_key:
        return error_response('api_key required')

    from .repositories import ModelConfigRepository
    repo = ModelConfigRepository()

    success = repo.update_api_key(model_id, api_key)
    if not success:
        return error_response('Model not found', 404)

    return jsonify({'success': True})


# ============== AI Settings Routes ==============

AI_SETTINGS_KEYS = [
    'ai_rag_enabled', 'ai_analytics_enabled', 'ai_rag_top_k',
    'ai_temperature', 'ai_max_tokens',
]


@ai_agent_bp.route('/api/settings', methods=['GET'])
@login_required
@ai_agent_required
def api_get_ai_settings():
    """API: Get AI configuration settings."""
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    from core.notifications.repositories.notification_repository import NotificationRepository
    repo = NotificationRepository()

    all_settings = repo.get_settings()

    # Extract only AI-related settings with defaults
    settings = {
        'ai_rag_enabled': all_settings.get('ai_rag_enabled', 'true'),
        'ai_analytics_enabled': all_settings.get('ai_analytics_enabled', 'true'),
        'ai_rag_top_k': all_settings.get('ai_rag_top_k', '5'),
        'ai_temperature': all_settings.get('ai_temperature', '0.7'),
        'ai_max_tokens': all_settings.get('ai_max_tokens', '2048'),
    }

    return jsonify({'settings': settings})


@ai_agent_bp.route('/api/settings', methods=['POST'])
@login_required
@ai_agent_required
def api_save_ai_settings():
    """API: Save AI configuration settings."""
    if not getattr(current_user, 'can_access_settings', False):
        return error_response('Admin access required', 403)

    data = request.get_json() or {}

    from core.notifications.repositories.notification_repository import NotificationRepository
    repo = NotificationRepository()

    # Only save recognized AI settings
    to_save = {k: str(v) for k, v in data.items() if k in AI_SETTINGS_KEYS}

    if to_save:
        repo.save_settings_bulk(to_save)

    return jsonify({'success': True})


@ai_agent_bp.route('/api/rag-source-permissions', methods=['GET'])
@login_required
@ai_agent_required
def api_rag_source_permissions():
    """API: Get which RAG sources the current user can access."""
    service = get_service()
    allowed = service.get_allowed_rag_sources(current_user.id)
    if allowed is None:
        # None means all sources allowed
        from .models import RAGSourceType
        all_sources = [s.value for s in RAGSourceType]
    else:
        all_sources = [s.value for s in allowed]
    return jsonify({'allowed_sources': all_sources})
