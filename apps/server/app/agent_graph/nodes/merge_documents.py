from app.agent_graph.document_state import DocumentSubgraphState


def merge_documents(state: DocumentSubgraphState) -> DocumentSubgraphState:
    """Publish parallel document results using the fixed prompt order."""
    results = sorted(state.get("document_results", []), key=lambda result: result.index)
    retry_count = state.get("quality_retry_count", 0)
    retry_indices = set(state.get("quality_retry_indices", []))
    audit_results = (
        [result for result in results if result.index in retry_indices]
        if retry_count and retry_indices
        else results
    )
    return {
        "documents": [(result.title, result.filename, result.content) for result in results],
        "llm_call_records": [
            *state.get("llm_call_records", []),
            *(result.llm_call_record for result in audit_results),
        ],
        "agent_steps": [*state.get("agent_steps", []), *(result.agent_step for result in audit_results)],
        "tool_logs": [*state.get("tool_logs", []), *(result.tool_log for result in audit_results)],
    }
