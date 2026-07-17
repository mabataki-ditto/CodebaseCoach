from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


SERVER_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    analysis_engine: Literal["legacy", "langgraph"] = "legacy"
    llm_provider: str = "deepseek"
    llm_api_key: str | None = None
    llm_model: str = "deepseek-v4-flash"
    llm_base_url: str | None = "https://api.deepseek.com"
    openai_api_key: str | None = None
    openai_model: str = "deepseek-v4-flash"
    temp_repo_dir: str = "../../temp_repos"
    generated_docs_dir: str = "../../generated_docs"
    history_file: str = "../../data/history.json"
    database_url: str = "sqlite:///../../data/codebasecoach.db"
    graph_checkpoint_file: str = "../../data/langgraph_checkpoints.sqlite3"
    backend_cors_origins: str = "http://localhost:5173"
    max_basic_file_bytes: int = 20_000
    max_core_files: int = 12
    max_core_file_bytes: int = 12_000
    max_file_tree_depth: int = 4
    max_file_tree_entries: int = 1_000
    llm_max_workers: int = 4
    mcp_config_file: str | None = None
    mcp_readonly: bool = True
    github_personal_access_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def temp_repo_path(self) -> Path:
        return self._resolve_from_server_dir(self.temp_repo_dir)

    @property
    def generated_docs_path(self) -> Path:
        return self._resolve_from_server_dir(self.generated_docs_dir)

    @property
    def history_path(self) -> Path:
        return self._resolve_from_server_dir(self.history_file)

    @property
    def graph_checkpoint_path(self) -> Path:
        return self._resolve_from_server_dir(self.graph_checkpoint_file)

    @property
    def resolved_database_url(self) -> str:
        if not self.database_url.startswith("sqlite:///"):
            return self.database_url
        raw_path = self.database_url.removeprefix("sqlite:///")
        if raw_path in {":memory:", ""}:
            return self.database_url
        path = self._resolve_from_server_dir(raw_path)
        return f"sqlite:///{path.as_posix()}"

    @property
    def mcp_config_path(self) -> Path | None:
        if not self.mcp_config_file:
            return None
        return self._resolve_from_server_dir(self.mcp_config_file)

    def _resolve_from_server_dir(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path.resolve()
        return (SERVER_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
