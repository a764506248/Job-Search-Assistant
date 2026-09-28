from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JSA_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    local_token: str | None = None
    data_dir: Path = Path("data")
    embedding_url: str = "http://127.0.0.1:8766"
    embedding_model: str = "jinaai/jina-embeddings-v2-base-zh"


settings = Settings()
