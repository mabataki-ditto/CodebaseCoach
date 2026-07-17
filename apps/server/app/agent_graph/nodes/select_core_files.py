from pathlib import Path

from app.agent_graph.stage_adapter import GraphStageAdapter
from app.agent_graph.state import AnalysisState
from app.core.config import settings
from app.services.file_selector_service import select_core_files_with_metrics


def select_core_files(state: AnalysisState) -> AnalysisState:
    """Select core files through the existing deterministic service."""
    local_path = Path(state["local_path"])
    adapter = GraphStageAdapter(state)
    core_files, selection_metrics = adapter.run(
        key="select_core_files",
        title="Select core files",
        description="Run workflow stage",
        tool_name="select_core_files",
        input_summary=f"max_files={settings.max_core_files}, max_bytes={settings.max_core_file_bytes}",
        input_payload={"max_files": settings.max_core_files, "max_bytes": settings.max_core_file_bytes},
        action=lambda: select_core_files_with_metrics(
            local_path,
            max_files=settings.max_core_files,
            max_bytes=settings.max_core_file_bytes,
        ),
        output_summary=lambda result: f"Selected {len(result[0])} core files",
        output_payload=lambda result: {
            "candidate_core_files": result[1].candidate_core_files,
            "selected_files": [file.path for file in result[0]],
            "used_for_context": [file.path for file in result[0] if file.used_for_context],
        },
        related_files=lambda result: [file.path for file in result[0]],
    )
    return {
        "core_files": core_files,
        "selection_metrics": selection_metrics,
        **adapter.state_update(),
    }
