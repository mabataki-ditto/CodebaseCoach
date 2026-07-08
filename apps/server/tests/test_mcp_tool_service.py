import json
import os
import tempfile
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.mcp.client import StdioMcpClient
from app.mcp.config import load_mcp_config
from app.mcp.schemas import McpServerConfig, McpTool, McpToolCallResult
from app.services.mcp_tool_service import McpToolService

pytestmark = pytest.mark.unit


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self, server_name: str) -> list[McpTool]:
        return [
            McpTool(
                name="list_pull_requests",
                description="List pull requests",
                input_schema={"type": "object"},
            ),
            McpTool(
                name="create_issue",
                description="Create an issue",
                input_schema={"type": "object"},
            ),
        ]

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> McpToolCallResult:
        self.calls.append((tool_name, arguments))
        return McpToolCallResult(
            content={"items": [{"number": 1, "title": "Fix docs"}]},
            summary="Returned 1 item",
        )


def test_load_mcp_config_expands_environment_values() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "mcp.servers.json"
        config_path.write_text(
            json.dumps(
                {
                    "servers": [
                        {
                            "name": "github",
                            "enabled": True,
                            "command": "npx",
                            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},
                            "allowed_tools": ["list_issues"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        original_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = "test-token"
        try:
            config = load_mcp_config(str(config_path))
        finally:
            if original_token is None:
                os.environ.pop("GITHUB_PERSONAL_ACCESS_TOKEN", None)
            else:
                os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = original_token

    assert config.servers[0].env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "test-token"
    assert config.servers[0].allowed_tools == ["list_issues"]


def test_load_mcp_config_prefers_explicit_env_values() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "mcp.servers.json"
        config_path.write_text(
            json.dumps(
                {
                    "servers": [
                        {
                            "name": "github",
                            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        config = load_mcp_config(
            str(config_path),
            env_values={"GITHUB_PERSONAL_ACCESS_TOKEN": "settings-token"},
        )

    assert config.servers[0].env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "settings-token"


def test_discovers_readonly_github_tools() -> None:
    service = McpToolService(
        client=FakeMcpClient(),
        server_name="github",
        allowed_tools={"list_pull_requests"},
    )

    tools = service.discover_tools()

    assert len(tools) == 1
    assert tools[0].name == "mcp.github.list_pull_requests"
    assert tools[0].provider == "mcp"
    assert tools[0].permission == "read"
    assert not tools[0].requires_confirmation


def test_rejects_tools_outside_allowlist() -> None:
    service = McpToolService(
        client=FakeMcpClient(),
        server_name="github",
        allowed_tools={"list_pull_requests"},
    )

    with pytest.raises(AppError) as raised:
        service.call_tool(
            tool_logs=[],
            tool_name="create_issue",
            arguments={"title": "unsafe"},
        )

    assert raised.value.code == "MCP_TOOL_NOT_ALLOWED"


def test_call_tool_records_mcp_audit_log_and_redacts_sensitive_fields() -> None:
    tool_logs = []
    service = McpToolService(
        client=FakeMcpClient(),
        server_name="github",
        allowed_tools={"list_pull_requests"},
    )

    result = service.call_tool(
        tool_logs=tool_logs,
        tool_name="list_pull_requests",
        arguments={
            "owner": "owner",
            "repo": "repo",
            "token": "secret-token",
        },
    )

    assert result.summary == "Returned 1 item"
    assert len(tool_logs) == 1
    assert tool_logs[0].tool_provider == "mcp"
    assert tool_logs[0].tool_name == "mcp.github.list_pull_requests"
    assert tool_logs[0].permission == "read"
    assert tool_logs[0].status == "success"
    assert tool_logs[0].input["token"] == "[redacted]"
    assert tool_logs[0].output["items"][0]["title"] == "Fix docs"


def test_stdio_client_wraps_missing_command_as_app_error() -> None:
    client = StdioMcpClient(
        [
            McpServerConfig(
                name="github",
                command="definitely-missing-mcp-command",
                allowed_tools=["list_issues"],
            )
        ]
    )

    with pytest.raises(AppError) as raised:
        client.list_tools("github")

    assert raised.value.code == "MCP_SERVER_START_FAILED"