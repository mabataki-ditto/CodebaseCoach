from app.agent.prompts import build_analysis_context as create_analysis_context
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.agent_graph.state import AnalysisState


def build_analysis_context(state: AnalysisState) -> AnalysisState:
    """Assemble the LLM input context through the existing prompt service."""
    basic_files = state["basic_files"]
    core_files = state["core_files"]
    adapter = GraphStageAdapter(state)
    analysis_context = adapter.run(
        key="build_analysis_context",
        title="Build analysis context",
        description="Run workflow stage",
        tool_name="build_analysis_context",
        input_summary=f"basic_files={len(basic_files)}, core_files={len(core_files)}",
        input_payload={
            "basic_files": [file.path for file in basic_files],
            "core_files": [file.path for file in core_files],
        },
        action=lambda: create_analysis_context(
            parsed_repo=state["parsed_repo"],
            basic_files=basic_files,
            core_files=core_files,
        ),
        output_summary=lambda result: f"Context has {len(result)} characters",
        output_payload=lambda result: {
            "context_chars": len(result),
            "used_for_context": [file.path for file in core_files if file.used_for_context],
        },
        related_files=lambda _: [file.path for file in core_files if file.used_for_context],
    )
    return {"analysis_context": analysis_context, **adapter.state_update()}
