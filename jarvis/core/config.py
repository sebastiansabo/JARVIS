import os
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVOICES_DIR = os.path.join(BASE_DIR, 'Invoices')


@dataclass
class AppConfig:
    secret_key: str
    database_url: str
    flask_env: str = 'development'
    log_level: str = 'INFO'
    anthropic_api_key: str = ''
    slow_query_threshold_ms: int = 200

    @classmethod
    def from_env(cls) -> 'AppConfig':
        return cls(
            secret_key=os.environ.get('FLASK_SECRET_KEY', os.environ.get('SECRET_KEY', '')),
            database_url=os.environ.get('DATABASE_URL', ''),
            flask_env=os.environ.get('FLASK_ENV', 'development'),
            log_level=os.environ.get('LOG_LEVEL', 'INFO'),
            anthropic_api_key=os.environ.get('ANTHROPIC_API_KEY', ''),
            slow_query_threshold_ms=int(os.environ.get('SLOW_QUERY_MS', '200')),
        )

    def validate(self):
        if not self.secret_key:
            raise ValueError('FLASK_SECRET_KEY must be set in production')
