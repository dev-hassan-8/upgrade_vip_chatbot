import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_chat_model: str = "gemini-flash-lite-latest"
    gemini_embedding_model: str = "gemini-embedding-001"
    chat_max_retries: int = 2
    chat_retry_delay: float = 1.0

    embedding_batch_size: int = 10
    embedding_batch_delay: float = 1.0
    embedding_max_retries: int = 5

    chroma_persist_directory: str = "./chroma_db"
    chroma_collection_name: str = "upgradevip_gemini"
    vector_store_backend: str = "auto"

    knowledge_base_dir: str = "./knowledge_base"
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 6
    similarity_threshold: float = 0.40

    max_history_messages: int = 12
    log_level: str = "INFO"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def knowledge_base_path(self) -> Path:
        return self.project_root / self.knowledge_base_dir

    @property
    def chroma_path(self) -> Path:
        return self.project_root / self.chroma_persist_directory

    @property
    def use_memory_vector_store(self) -> bool:
        backend = (self.vector_store_backend or "auto").strip().lower()
        if backend == "memory":
            return True
        if backend == "chroma":
            return False
        return bool(os.environ.get("VERCEL"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
