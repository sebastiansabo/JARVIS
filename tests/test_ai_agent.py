"""Unit tests for the AI Agent module.

Tests:
- ToolRegistry: registration, schemas, execution, permissions
- Tool permission filtering
- Tool execution error handling
"""

import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


# ═══════════════════════════════════════════════
# ToolRegistry Tests
# ═══════════════════════════════════════════════

class TestToolRegistry:

    def _make_registry(self):
        from ai_agent.tools.registry import ToolRegistry
        return ToolRegistry()

    def test_register_and_count(self):
        registry = self._make_registry()
        registry.register(
            name='test_tool',
            description='A test tool',
            input_schema={'type': 'object', 'properties': {'q': {'type': 'string'}}},
            handler=lambda params, uid: {'result': 'ok'},
        )
        assert registry.tool_count == 1

    def test_register_multiple(self):
        registry = self._make_registry()
        for i in range(5):
            registry.register(
                name=f'tool_{i}',
                description=f'Tool {i}',
                input_schema={'type': 'object'},
                handler=lambda p, u: {},
            )
        assert registry.tool_count == 5

    def test_has_tool(self):
        registry = self._make_registry()
        registry.register('my_tool', 'desc', {}, lambda p, u: {})
        assert registry.has_tool('my_tool') is True
        assert registry.has_tool('nope') is False

    def test_get_schemas_all(self):
        registry = self._make_registry()
        registry.register('tool_a', 'desc a', {'type': 'object'}, lambda p, u: {})
        registry.register('tool_b', 'desc b', {'type': 'object'}, lambda p, u: {})

        schemas = registry.get_schemas()
        assert len(schemas) == 2
        names = {s['name'] for s in schemas}
        assert names == {'tool_a', 'tool_b'}

    def test_get_schemas_format(self):
        registry = self._make_registry()
        registry.register(
            'invoice_list', 'List invoices',
            {'type': 'object', 'properties': {'limit': {'type': 'integer'}}},
            lambda p, u: {}
        )
        schemas = registry.get_schemas()
        assert schemas[0]['name'] == 'invoice_list'
        assert schemas[0]['description'] == 'List invoices'
        assert 'input_schema' in schemas[0]

    def test_execute_success(self):
        registry = self._make_registry()
        registry.register(
            'echo', 'Echo params', {},
            handler=lambda params, uid: {'echo': params.get('msg', ''), 'user': uid}
        )
        result = registry.execute('echo', {'msg': 'hello'}, user_id=42)
        assert result == {'echo': 'hello', 'user': 42}

    def test_execute_unknown_tool(self):
        registry = self._make_registry()
        result = registry.execute('nonexistent', {}, user_id=1)
        assert 'error' in result
        assert 'Unknown tool' in result['error']

    def test_execute_handler_exception(self):
        def failing_handler(params, uid):
            raise RuntimeError('boom')

        registry = self._make_registry()
        registry.register('fail', 'Fails', {}, failing_handler)
        result = registry.execute('fail', {}, user_id=1)
        assert 'error' in result
        assert 'boom' in result['error']

    # ---- Permission filtering ----

    def test_schemas_no_permission_filter(self):
        """When user_permissions is None, all tools are returned."""
        registry = self._make_registry()
        registry.register('public', 'Public', {}, lambda p, u: {}, permission=None)
        registry.register('private', 'Private', {}, lambda p, u: {}, permission='ai_agent.access')

        schemas = registry.get_schemas(user_permissions=None)
        assert len(schemas) == 2

    def test_schemas_with_permission(self):
        registry = self._make_registry()
        registry.register('public', 'Public', {}, lambda p, u: {}, permission=None)
        registry.register('admin_only', 'Admin', {}, lambda p, u: {}, permission='admin')

        # User with admin permission
        schemas = registry.get_schemas(user_permissions={'admin', 'user'})
        assert len(schemas) == 2

        # User without admin permission
        schemas = registry.get_schemas(user_permissions={'user'})
        assert len(schemas) == 1
        assert schemas[0]['name'] == 'public'

    def test_schemas_empty_permissions(self):
        registry = self._make_registry()
        registry.register('t1', 'T1', {}, lambda p, u: {}, permission='a')
        registry.register('t2', 'T2', {}, lambda p, u: {}, permission=None)

        schemas = registry.get_schemas(user_permissions=set())
        assert len(schemas) == 1
        assert schemas[0]['name'] == 't2'

    def test_execute_permission_denied(self):
        registry = self._make_registry()
        registry.register('secret', 'Secret', {}, lambda p, u: {'data': 'ok'}, permission='admin')

        result = registry.execute('secret', {}, user_id=1, user_permissions={'user'})
        assert 'error' in result
        assert 'Permission denied' in result['error']

    def test_execute_permission_granted(self):
        registry = self._make_registry()
        registry.register('secret', 'Secret', {}, lambda p, u: {'data': 'ok'}, permission='admin')

        result = registry.execute('secret', {}, user_id=1, user_permissions={'admin'})
        assert result == {'data': 'ok'}

    def test_execute_no_permission_check(self):
        """When user_permissions is None, permission check is skipped."""
        registry = self._make_registry()
        registry.register('secret', 'Secret', {}, lambda p, u: {'data': 'ok'}, permission='admin')

        result = registry.execute('secret', {}, user_id=1, user_permissions=None)
        assert result == {'data': 'ok'}

    # ---- Overwrite behavior ----

    def test_register_overwrites(self):
        registry = self._make_registry()
        registry.register('tool', 'V1', {}, lambda p, u: {'v': 1})
        registry.register('tool', 'V2', {}, lambda p, u: {'v': 2})

        assert registry.tool_count == 1
        result = registry.execute('tool', {}, user_id=1)
        assert result == {'v': 2}


# ═══════════════════════════════════════════════
# Global Registry Tests (integration — tests the actual tool definitions)
# ═══════════════════════════════════════════════

class TestGlobalToolRegistry:

    def test_global_registry_loads(self):
        """The global registry should auto-load all tool definitions."""
        from ai_agent.tools.registry import tool_registry
        assert tool_registry.tool_count >= 10  # We registered 10 tools

    def test_global_registry_has_known_tools(self):
        from ai_agent.tools.registry import tool_registry
        known_tools = [
            'search_invoices', 'get_invoice_details',
            'get_invoice_summary', 'get_pending_approvals',
        ]
        for name in known_tools:
            assert tool_registry.has_tool(name), f'Missing tool: {name}'

    def test_global_schemas_format(self):
        from ai_agent.tools.registry import tool_registry
        schemas = tool_registry.get_schemas()
        for schema in schemas:
            assert 'name' in schema
            assert 'description' in schema
            assert 'input_schema' in schema
            assert isinstance(schema['input_schema'], dict)
