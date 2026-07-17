from langgraph.runtime import Runtime

from app.agent_graph.context import AnalysisRuntimeContext, check_cancellation
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.agent_graph.state import AnalysisState
from app.services.github_mcp_context_service import build_github_mcp_context


def fetch_github_mcp_context(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntimeContext],
) -> AnalysisState:
    """Fetch optional GitHub context from the process-local MCP service."""
    parsed_repo = state["parsed_repo"]
    input_payload = {"owner": parsed_repo.owner, "repo": parsed_repo.repo}
    adapter = GraphStageAdapter(state)
    service = runtime.context.get("mcp_service") if runtime.context else None

    if service is None:
        adapter.skip(
            key="fetch_github_mcp_context",
            title="Fetch GitHub MCP context",
            description="Fetch read-only GitHub collaboration context through MCP",
            tool_name="fetch_github_mcp_context",
            reason="GitHub MCP server is not configured",
            input_payload=input_payload,
        )
        result: AnalysisState = {
            "github_mcp_context": "",
            "analysis_context": state["analysis_context"],
            **adapter.state_update(),
        }
        check_cancellation(runtime)
        return result

    github_context = adapter.run(
        key="fetch_github_mcp_context",
        title="Fetch GitHub MCP context",
        description="Fetch read-only GitHub collaboration context through MCP",
        tool_name="fetch_github_mcp_context",
        input_summary=f"{parsed_repo.owner}/{parsed_repo.repo}",
        input_payload=input_payload,
        action=lambda: build_github_mcp_context(
            parsed_repo=parsed_repo,
            tool_logs=adapter.tool_logs,
            service=service,
        ),
        output_summary=lambda result: f"GitHub MCP context has {len(result)} characters",
        output_payload=lambda result: {"context_chars": len(result), "enabled": True},
    )
    analysis_context = state["analysis_context"]
    if github_context:
        analysis_context = f"{analysis_context}\n\n{github_context}"
    check_cancellation(runtime)
    return {
        "github_mcp_context": github_context,
        "analysis_context": analysis_context,
        **adapter.state_update(),
    }
