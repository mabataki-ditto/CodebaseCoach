from typing import Any

from app.core.errors import AppError
from app.schemas.agent import ToolCallLog
from app.schemas.repo import RepoParseResponse
from app.services.mcp_tool_service import McpToolService


GITHUB_MCP_ALLOWED_TOOLS = {
    "list_issues",
    "list_pull_requests",
    "list_commits",
}


def build_github_mcp_context(
    *,
    parsed_repo: RepoParseResponse,
    tool_logs: list[ToolCallLog],
    service: McpToolService | None,
    max_items: int = 5,
) -> str:
    if service is None:
        return ""

    sections: list[str] = ["## GitHub 协作上下文"]
    issues = _safe_call(
        service,
        tool_logs=tool_logs,
        tool_name="list_issues",
        arguments={"owner": parsed_repo.owner, "repo": parsed_repo.repo, "state": "open", "per_page": max_items},
    )
    if issues is not None:
        sections.append(_items_section("Recent open issues", _as_items(issues), max_items=max_items))

    pull_requests = _safe_call(
        service,
        tool_logs=tool_logs,
        tool_name="list_pull_requests",
        arguments={"owner": parsed_repo.owner, "repo": parsed_repo.repo, "state": "open", "per_page": max_items},
    )
    if pull_requests is not None:
        sections.append(_items_section("Recent pull requests", _as_items(pull_requests), max_items=max_items))

    commits = _safe_call(
        service,
        tool_logs=tool_logs,
        tool_name="list_commits",
        arguments={"owner": parsed_repo.owner, "repo": parsed_repo.repo, "perPage": max_items},
    )
    if commits is not None:
        sections.append(_items_section("Recent commits", _as_items(commits), max_items=max_items))

    return "\n\n".join(section for section in sections if section.strip()) if len(sections) > 1 else ""


def _safe_call(
    service: McpToolService,
    *,
    tool_logs: list[ToolCallLog],
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    try:
        return service.call_tool(tool_logs=tool_logs, tool_name=tool_name, arguments=arguments).content
    except AppError:
        return None


def _items_section(title: str, items: list[dict[str, Any]], *, max_items: int) -> str:
    lines = [f"### {title}"]
    if not items:
        lines.append("- None returned")
        return "\n".join(lines)
    for item in items[:max_items]:
        number = item.get("number")
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        title_value = (
            item.get("title")
            or item.get("name")
            or item.get("tag_name")
            or commit.get("message")
            or item.get("sha")
            or "Untitled"
        )
        state = item.get("state")
        prefix = f"#{number} " if number is not None else ""
        suffix = f" ({state})" if state else ""
        lines.append(f"- {prefix}{title_value}{suffix}")
    return "\n".join(lines)


def _as_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            return [item for item in nodes if isinstance(item, dict)]
    return []
