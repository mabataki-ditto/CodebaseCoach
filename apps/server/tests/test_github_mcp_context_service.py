import unittest

from app.mcp.schemas import McpTool, McpToolCallResult
from app.schemas.agent import ToolCallLog
from app.schemas.repo import RepoParseResponse
from app.services.github_mcp_context_service import build_github_mcp_context
from app.services.mcp_tool_service import McpToolService


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


class GithubMcpContextServiceTests(unittest.TestCase):
    def test_builds_markdown_summary_from_github_mcp_tools(self) -> None:
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

        self.assertIn("## GitHub 协作上下文", context)
        self.assertIn("#7 Improve onboarding docs", context)
        self.assertIn("#9 Refactor workflow", context)
        self.assertIn("Improve docs", context)
        self.assertEqual(len(tool_logs), 3)
        self.assertTrue(all(log.tool_provider == "mcp" for log in tool_logs))

    def test_skips_context_when_mcp_client_raises_unexpected_error(self) -> None:
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

        self.assertEqual(context, "")
        self.assertTrue(tool_logs)
        self.assertTrue(all(log.status == "failed" for log in tool_logs))
        self.assertTrue(all(log.error_message == "broken mcp payload" for log in tool_logs))

    def test_returns_empty_context_when_service_is_missing(self) -> None:
        context = build_github_mcp_context(
            parsed_repo=RepoParseResponse(
                owner="owner",
                repo="repo",
                repo_url="https://github.com/owner/repo",
            ),
            tool_logs=[],
            service=None,
        )

        self.assertEqual(context, "")


if __name__ == "__main__":
    unittest.main()
