from app.agent_graph.state import AnalysisState
from app.services.metrics_service import build_context_quality_report as create_context_quality_report


def build_context_quality_report(state: AnalysisState) -> AnalysisState:
    """Build the existing deterministic context quality report."""
    report = create_context_quality_report(
        selection_metrics=state["selection_metrics"],
        core_files=state["core_files"],
    )
    return {"context_quality_report": report}
