from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    logging_level: str | None = None
    openai_api_key: str | None = None
    openai_api_base: str | None = None
    rag_index_path: str | None = None
    use_dummy: bool = False
    timeout_seconds: float = 30.0
    chat_max_concurrency: int = 4


settings = Settings()
