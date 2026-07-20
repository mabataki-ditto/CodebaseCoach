from langgraph.types import Overwrite

from app.agent_graph.document_state import DocumentSubgraphState


def prepare_repository_recovery(state: DocumentSubgraphState) -> DocumentSubgraphState:
    """Keep recovered documents only when the rebuilt repository is identical."""
    source_sha = state.get("recovery_source_commit_sha")
    if not source_sha:
        return {}
    if source_sha == state.get("repository_commit_sha"):
        return {"recovery_mode": "rebuild_repository"}
    return {
        "recovery_mode": "full_restart",
        "document_results": Overwrite([]),
    }
