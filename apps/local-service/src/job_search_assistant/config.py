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
    # 关闭后不再调用 embedding 服务，RAG 降级为纯 FTS5/BM25 关键词检索。
    # 低配部署（如 2核2G）建议置为 false，可省掉常驻 0.6~1.2GB 的推理容器。
    embedding_enabled: bool = True


settings = Settings()
