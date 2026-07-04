import json
import os
from pathlib import Path

from app.core.config import SERVER_DIR
from app.mcp.schemas import McpConfig, McpServerConfig


def load_mcp_config(config_file: str | None, *, env_values: dict[str, str | None] | None = None) -> McpConfig:
    if not config_file:
        return McpConfig()

    path = _resolve_config_path(config_file)
    if not path.exists():
        return McpConfig()

    payload = json.loads(path.read_text(encoding="utf-8"))
    config = McpConfig.model_validate(payload)
    return McpConfig(servers=[_expand_server_env(server, env_values=env_values or {}) for server in config.servers])


def get_enabled_server(config: McpConfig, server_name: str) -> McpServerConfig | None:
    for server in config.servers:
        if server.name == server_name and server.enabled:
            return server
    return None


def _resolve_config_path(config_file: str) -> Path:
    path = Path(config_file)
    if path.is_absolute():
        return path
    return (SERVER_DIR / path).resolve()


def _expand_server_env(server: McpServerConfig, *, env_values: dict[str, str | None]) -> McpServerConfig:
    env = {}
    for key, value in server.env.items():
        env[key] = _expand_env_value(value, env_values=env_values)
    return server.model_copy(update={"env": env})


def _expand_env_value(value: str, *, env_values: dict[str, str | None]) -> str:
    if value.startswith("${") and value.endswith("}"):
        name = value[2:-1]
        return env_values.get(name) or os.getenv(name, "")
    return value
