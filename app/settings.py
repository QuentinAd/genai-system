from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    openai_api_key: str | None = None
    rag_index_path: str | None = None
    use_dummy: bool = False

    class Config:
        env_prefix = ""
        env_file = ".env"


settings = Settings()
