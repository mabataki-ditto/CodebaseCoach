import pytest

from app.mcp.schemas import McpTool, McpToolCallResult
from app.schemas.agent import ToolCallLog
from app.schemas.repo import RepoParseResponse
from app.services.github_mcp_context_service import build_github_mcp_context
from app.services.mcp_tool_service import McpToolService

pytestmark = pytest.mark.unit


class FakeGithubMcpClient:
    def list_tools(self, server_name: str) -> list[McpTool]:
        return [
            McpTool(name="list_issues", description="List issues"),
            McpTool(name="list_pull_requests", description="List pull requests"),
            McpTool(name="list_commits", description="List commits"),
        ]

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> McpToolCallResult:
        payloads = {
            "list_issues": [
                {"number": 7, "title": "Improve onboarding docs", "state": "open"},
                {"number": 8, "title": "Add migration tests", "state": "open"},
            ],
            "list_pull_requests": [
                {"number": 9, "title": "Refactor workflow", "state": "open"},
            ],
            "list_commits": [
                {"sha": "abc123", "commit": {"message": "Improve docs"}},
            ],
        }
        return McpToolCallResult(content=payloads[tool_name], summary=f"Returned {tool_name}")


class BrokenGithubMcpClient(FakeGithubMcpClient):
    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> McpToolCallResult:
        raise ValueError("broken mcp payload")


def test_builds_markdown_summary_from_github_mcp_tools() -> None:
    tool_logs: list[ToolCallLog] = []
    service = McpToolService(
        client=FakeGithubMcpClient(),
        server_name="github",
        allowed_tools={"list_issues", "list_pull_requests", "list_commits"},
    )

    context = build_github_mcp_context(
        parsed_repo=RepoParseResponse(
            owner="owner",
            repo="repo",
            repo_url="https://github.com/owner/repo",
        ),
        tool_logs=tool_logs,
        service=service,
    )

    assert "## GitHub 协作上下文" in context
    assert "#7 Improve onboarding docs" in context
    assert "#9 Refactor workflow" in context
    assert "Improve docs" in context
    assert len(tool_logs) == 3
    assert all(log.tool_provider == "mcp" for log in tool_logs)


def test_skips_context_when_mcp_client_raises_unexpected_error() -> None:
    tool_logs: list[ToolCallLog] = []
    service = McpToolService(
        client=BrokenGithubMcpClient(),
        server_name="github",
        allowed_tools={"list_issues", "list_pull_requests", "list_commits"},
    )

    context = build_github_mcp_context(
        parsed_repo=RepoParseResponse(
            owner="owner",
            repo="repo",
            repo_url="https://github.com/owner/repo",
        ),
        tool_logs=tool_logs,
        service=service,
    )

    assert context == ""
    assert tool_logs
    assert all(log.status == "failed" for log in tool_logs)
    assert all(log.error_message == "broken mcp payload" for log in tool_logs)


def test_returns_empty_context_when_service_is_missing() -> None:
    context = build_github_mcp_context(
        parsed_repo=RepoParseResponse(
            owner="owner",
            repo="repo",
            repo_url="https://github.com/owner/repo",
        ),
        tool_logs=[],
        service=None,
    )

    assert context == ""