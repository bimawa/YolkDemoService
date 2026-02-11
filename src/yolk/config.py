from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="YOLK_")

    app_name: str = "Yolk AI Sales Coach"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://yolk:yolk_dev@localhost:5432/yolk"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"

    rabbitmq_url: str = "amqp://yolk:yolk_dev@localhost:5672/"

    openai_api_key: SecretStr = SecretStr("lm-studio")
    openai_base_url: str = "http://localhost:1234/v1"
    anthropic_api_key: SecretStr = SecretStr("")
    llm_provider: str = "openai"
    llm_model: str = "gemma-2-9b-it-sppo-iter3"

    websocket_heartbeat_interval: int = 30
    websocket_max_message_size: int = 65536

    otlp_endpoint: str = "http://localhost:4317"
    otlp_enabled: bool = False


settings = Settings()
