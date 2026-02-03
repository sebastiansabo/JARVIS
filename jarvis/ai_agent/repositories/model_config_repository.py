"""
Model Config Repository

Database operations for AI Agent model configurations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from ..models import ModelConfig, LLMProvider

logger = get_logger('jarvis.ai_agent.repo.model_config')


class ModelConfigRepository:
    """Repository for ModelConfig entities."""

    def get_by_id(self, config_id: int) -> Optional[ModelConfig]:
        """
        Get a model configuration by ID.

        Args:
            config_id: ID of the configuration

        Returns:
            ModelConfig or None if not found
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                SELECT id, provider, model_name, display_name,
                       api_key_encrypted, base_url,
                       cost_per_1k_input, cost_per_1k_output,
                       max_tokens, rate_limit_rpm, rate_limit_tpm,
                       default_temperature, is_active, is_default,
                       created_at, updated_at
                FROM ai_agent.model_configs
                WHERE id = %s
            """, (config_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_model_config(row)

        finally:
            release_db(conn)

    def get_default(self, provider: Optional[LLMProvider] = None) -> Optional[ModelConfig]:
        """
        Get the default model configuration.

        Args:
            provider: Optional provider to filter by

        Returns:
            Default ModelConfig or None
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            if provider:
                cursor.execute("""
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
                cursor.execute("""
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

            row = cursor.fetchone()
            if not row:
                # Fallback to any active model
                cursor.execute("""
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
                row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_model_config(row)

        finally:
            release_db(conn)

    def get_all_active(self) -> List[ModelConfig]:
        """
        Get all active model configurations.

        Returns:
            List of active ModelConfigs
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
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

            return [self._row_to_model_config(row) for row in cursor.fetchall()]

        finally:
            release_db(conn)

    def get_by_provider(self, provider: LLMProvider) -> List[ModelConfig]:
        """
        Get all active configurations for a provider.

        Args:
            provider: LLM provider

        Returns:
            List of ModelConfigs for the provider
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
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

            return [self._row_to_model_config(row) for row in cursor.fetchall()]

        finally:
            release_db(conn)

    def update_api_key(self, config_id: int, api_key_encrypted: str) -> bool:
        """
        Update the API key for a configuration.

        Args:
            config_id: ID of the configuration
            api_key_encrypted: Encrypted API key

        Returns:
            True if updated
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                UPDATE ai_agent.model_configs
                SET api_key_encrypted = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (api_key_encrypted, config_id))

            row = cursor.fetchone()
            conn.commit()
            return row is not None

        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating API key: {e}")
            raise

        finally:
            release_db(conn)

    def set_default(self, config_id: int) -> bool:
        """
        Set a configuration as the default for its provider.

        Args:
            config_id: ID of the configuration

        Returns:
            True if updated
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Get the provider
            cursor.execute("""
                SELECT provider FROM ai_agent.model_configs WHERE id = %s
            """, (config_id,))
            row = cursor.fetchone()
            if not row:
                return False

            provider = row['provider']

            # Clear existing default for this provider
            cursor.execute("""
                UPDATE ai_agent.model_configs
                SET is_default = FALSE, updated_at = NOW()
                WHERE provider = %s AND is_default = TRUE
            """, (provider,))

            # Set new default
            cursor.execute("""
                UPDATE ai_agent.model_configs
                SET is_default = TRUE, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (config_id,))

            row = cursor.fetchone()
            conn.commit()
            return row is not None

        except Exception as e:
            conn.rollback()
            logger.error(f"Error setting default model: {e}")
            raise

        finally:
            release_db(conn)

    def toggle_active(self, config_id: int, is_active: bool) -> bool:
        """
        Enable or disable a configuration.

        Args:
            config_id: ID of the configuration
            is_active: New active status

        Returns:
            True if updated
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                UPDATE ai_agent.model_configs
                SET is_active = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (is_active, config_id))

            row = cursor.fetchone()
            conn.commit()
            return row is not None

        except Exception as e:
            conn.rollback()
            logger.error(f"Error toggling model active status: {e}")
            raise

        finally:
            release_db(conn)

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
