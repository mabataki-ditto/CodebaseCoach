from langgraph.runtime import Runtime

from app.agent_graph.context import AnalysisRuntimeContext, check_cancellation
from app.agent_graph.state import AnalysisState
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.core.config import settings
from app.services.github_service import clone_repository, get_repository_commit_sha


def clone_repo(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntimeContext] | None = None,
) -> AnalysisState:
    """Clone the parsed repository using the existing service."""
    parsed_repo = state["parsed_repo"]
    check_cancellation(runtime)
    adapter = GraphStageAdapter(state)
    local_path = adapter.run(
        key="clone_repository",
        title="Clone repository",
        description="Run workflow stage",
        tool_name="clone_repository",
        input_summary=parsed_repo.repo_url,
        input_payload={"repo_url": parsed_repo.repo_url, "temp_repo_dir": str(settings.temp_repo_path)},
        action=lambda: clone_repository(parsed_repo, settings.temp_repo_path),
        output_summary=lambda result: result.name,
        output_payload=lambda result: {"local_path": str(result), "directory": result.name},
    )
    check_cancellation(runtime)
    return {
        "local_path": str(local_path),
        "repository_commit_sha": get_repository_commit_sha(local_path),
        **adapter.state_update(),
    }
