"""Model Config Repository — AI Agent model configurations."""
from decimal import Decimal
from typing import Optional, List

from core.base_repository import BaseRepository
from core.utils.logging_config import get_logger
from ..models import ModelConfig, LLMProvider

logger = get_logger('jarvis.ai_agent.repo.model_config')


class ModelConfigRepository(BaseRepository):
    """Repository for ModelConfig entities."""

    def get_by_id(self, config_id: int) -> Optional[ModelConfig]:
        """Get a model configuration by ID."""
        row = self.query_one("""
            SELECT id, provider, model_name, display_name,
                   api_key_encrypted, base_url,
                   cost_per_1k_input, cost_per_1k_output,
                   max_tokens, rate_limit_rpm, rate_limit_tpm,
                   default_temperature, is_active, is_default,
                   created_at, updated_at
            FROM ai_agent.model_configs
            WHERE id = %s
        """, (config_id,))
        return self._row_to_model_config(row) if row else None

    def get_default(self, provider: Optional[LLMProvider] = None) -> Optional[ModelConfig]:
        """Get the default model configuration (with fallback to any active)."""
        if provider:
            row = self.query_one("""
                SELECT id, provider, model_name, display_name,
                       api_key_encrypted, base_url,
                       cost_per_1k_input, cost_per_1k_output,
                       max_tokens, rate_limit_rpm, rate_limit_tpm,
                       default_temperature, is_active, is_default,
                       created_at, updated_at
                FROM ai_agent.model_configs
                WHERE provider = %s AND is_default = TRUE AND is_active = TRUE
                LIMIT 1
            """, (provider.value,))
        else:
            row = self.query_one("""
                SELECT id, provider, model_name, display_name,
                       api_key_encrypted, base_url,
                       cost_per_1k_input, cost_per_1k_output,
                       max_tokens, rate_limit_rpm, rate_limit_tpm,
                       default_temperature, is_active, is_default,
                       created_at, updated_at
                FROM ai_agent.model_configs
                WHERE is_default = TRUE AND is_active = TRUE
                ORDER BY
                    CASE provider
                        WHEN 'claude' THEN 1
                        WHEN 'openai' THEN 2
                        ELSE 3
                    END
                LIMIT 1
            """)

        if not row:
            # Fallback to any active model
            row = self.query_one("""
                SELECT id, provider, model_name, display_name,
                       api_key_encrypted, base_url,
                       cost_per_1k_input, cost_per_1k_output,
                       max_tokens, rate_limit_rpm, rate_limit_tpm,
                       default_temperature, is_active, is_default,
                       created_at, updated_at
                FROM ai_agent.model_configs
                WHERE is_active = TRUE
                ORDER BY
                    CASE provider
                        WHEN 'claude' THEN 1
                        WHEN 'openai' THEN 2
                        ELSE 3
                    END
                LIMIT 1
            """)

        return self._row_to_model_config(row) if row else None

    def get_all(self) -> List[ModelConfig]:
        """Get all model configurations (including inactive)."""
        rows = self.query_all("""
            SELECT id, provider, model_name, display_name,
                   api_key_encrypted, base_url,
                   cost_per_1k_input, cost_per_1k_output,
                   max_tokens, rate_limit_rpm, rate_limit_tpm,
                   default_temperature, is_active, is_default,
                   created_at, updated_at
            FROM ai_agent.model_configs
            ORDER BY
                CASE provider
                    WHEN 'claude' THEN 1
                    WHEN 'openai' THEN 2
                    WHEN 'groq' THEN 3
                    ELSE 4
                END,
                is_default DESC, model_name
        """)
        return [self._row_to_model_config(row) for row in rows]

    def get_all_active(self) -> List[ModelConfig]:
        """Get all active model configurations."""
        rows = self.query_all("""
            SELECT id, provider, model_name, display_name,
                   api_key_encrypted, base_url,
                   cost_per_1k_input, cost_per_1k_output,
                   max_tokens, rate_limit_rpm, rate_limit_tpm,
                   default_temperature, is_active, is_default,
                   created_at, updated_at
            FROM ai_agent.model_configs
            WHERE is_active = TRUE
            ORDER BY
                CASE provider
                    WHEN 'claude' THEN 1
                    WHEN 'openai' THEN 2
                    WHEN 'groq' THEN 3
                    ELSE 4
                END,
                is_default DESC,
                model_name
        """)
        return [self._row_to_model_config(row) for row in rows]

    def get_by_provider(self, provider: LLMProvider) -> List[ModelConfig]:
        """Get all active configurations for a provider."""
        rows = self.query_all("""
            SELECT id, provider, model_name, display_name,
                   api_key_encrypted, base_url,
                   cost_per_1k_input, cost_per_1k_output,
                   max_tokens, rate_limit_rpm, rate_limit_tpm,
                   default_temperature, is_active, is_default,
                   created_at, updated_at
            FROM ai_agent.model_configs
            WHERE provider = %s AND is_active = TRUE
            ORDER BY is_default DESC, model_name
        """, (provider.value,))
        return [self._row_to_model_config(row) for row in rows]

    def update_api_key(self, config_id: int, api_key_encrypted: str) -> bool:
        """Update the API key for a configuration."""
        return self.execute("""
            UPDATE ai_agent.model_configs
            SET api_key_encrypted = %s, updated_at = NOW()
            WHERE id = %s
        """, (api_key_encrypted, config_id)) > 0

    def set_default(self, config_id: int) -> bool:
        """Set a configuration as the default (clears all other defaults)."""
        def _work(cursor):
            cursor.execute("""
                UPDATE ai_agent.model_configs
                SET is_default = FALSE, updated_at = NOW()
                WHERE is_default = TRUE
            """)
            cursor.execute("""
                UPDATE ai_agent.model_configs
                SET is_default = TRUE, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (config_id,))
            return cursor.fetchone() is not None
        return self.execute_many(_work)

    def toggle_active(self, config_id: int, is_active: bool) -> bool:
        """Enable or disable a configuration."""
        return self.execute("""
            UPDATE ai_agent.model_configs
            SET is_active = %s, updated_at = NOW()
            WHERE id = %s
        """, (is_active, config_id)) > 0

    def _row_to_model_config(self, row: dict) -> ModelConfig:
        """Convert database row to ModelConfig model."""
        return ModelConfig(
            id=row['id'],
            provider=LLMProvider(row['provider']),
            model_name=row['model_name'],
            display_name=row['display_name'],
            api_key_encrypted=row['api_key_encrypted'],
            base_url=row['base_url'],
            cost_per_1k_input=Decimal(str(row['cost_per_1k_input'])) if row['cost_per_1k_input'] else Decimal("0"),
            cost_per_1k_output=Decimal(str(row['cost_per_1k_output'])) if row['cost_per_1k_output'] else Decimal("0"),
            max_tokens=row['max_tokens'] or 4096,
            rate_limit_rpm=row['rate_limit_rpm'] or 60,
            rate_limit_tpm=row['rate_limit_tpm'] or 100000,
            default_temperature=Decimal(str(row['default_temperature'])) if row['default_temperature'] else Decimal("0.7"),
            is_active=row['is_active'],
            is_default=row['is_default'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
