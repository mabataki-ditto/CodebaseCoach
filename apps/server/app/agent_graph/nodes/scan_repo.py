from pathlib import Path

from langgraph.runtime import Runtime

from app.agent_graph.context import AnalysisRuntimeContext, check_cancellation
from app.agent_graph.state import AnalysisState
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.core.config import settings
from app.services.file_tree_service import build_file_tree, read_basic_files, scan_repo_metrics


def scan_repo(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntimeContext] | None = None,
) -> AnalysisState:
    """Build the file tree and basic-file summaries with existing services."""
    local_path = Path(state["local_path"])
    check_cancellation(runtime)
    adapter = GraphStageAdapter(state)
    repo_scan_metrics = scan_repo_metrics(local_path)
    file_tree = adapter.run(
        key="build_file_tree",
        title="Build file tree",
        description="Run workflow stage",
        tool_name="build_file_tree",
        input_summary=str(local_path),
        input_payload={
            "local_path": str(local_path),
            "max_depth": settings.max_file_tree_depth,
            "max_entries": settings.max_file_tree_entries,
        },
        action=lambda: build_file_tree(
            local_path,
            max_depth=settings.max_file_tree_depth,
            max_entries=settings.max_file_tree_entries,
        ),
        output_summary=lambda result: f"Returned {len(result)} top-level nodes",
        output_payload=lambda result: {"top_level_nodes": len(result)},
    )
    basic_files = adapter.run(
        key="read_basic_files",
        title="Read basic files",
        description="Run workflow stage",
        tool_name="read_basic_files",
        input_summary=f"max_bytes={settings.max_basic_file_bytes}",
        input_payload={"max_bytes": settings.max_basic_file_bytes},
        action=lambda: read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes),
        output_summary=lambda result: f"Read {len(result)} basic files",
        output_payload=lambda result: {"read_files": [file.path for file in result]},
        related_files=lambda result: [file.path for file in result],
    )
    check_cancellation(runtime)
    return {
        "file_tree": file_tree,
        "basic_files": basic_files,
        "repo_scan_metrics": repo_scan_metrics,
        **adapter.state_update(),
    }
