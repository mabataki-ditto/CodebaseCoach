from collections.abc import Callable

from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from app.agent.prompts import DocumentPrompt
from app.agent_graph.context import AnalysisRuntimeContext, check_cancellation
from app.agent_graph.document_result import DocumentGenerationResult
from app.agent_graph.document_state import DocumentSubgraphState
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.services.llm_call_service import LLMCallService
from app.services.llm_service import DEFAULT_PROVIDER, generate_markdown_document


def make_generate_document_node(
    document_index: int,
    prompt: DocumentPrompt,
) -> Callable[[DocumentSubgraphState, Runtime[AnalysisRuntimeContext]], DocumentSubgraphState]:
    """Build one fixed document node for the internal parallel fan-out."""

    def generate_document(
        state: DocumentSubgraphState,
        runtime: Runtime[AnalysisRuntimeContext],
    ) -> DocumentSubgraphState:
        runtime_context = runtime.context or {}
        check_cancellation(runtime)
        provider = runtime_context.get("llm_provider") or DEFAULT_PROVIDER
        model = runtime_context.get("llm_model") or ""
        retry_count = state.get("quality_retry_count", 0)
        retry_indices = state.get("quality_retry_indices", [])
        existing_result = next(
            (
                result
                for result in state.get("document_results", [])
                if result.index == document_index
            ),
            None,
        )
        if existing_result is not None and not (
            retry_count and document_index in retry_indices
        ):
            _emit_document_ready(result=existing_result, document_index=document_index)
            return {}
        if retry_count and retry_indices and document_index not in retry_indices:
            return {}
        generation_context = state["analysis_context"]
        quality_feedback = state.get("quality_feedback", "").strip()
        if retry_count and quality_feedback:
            generation_context = f"{generation_context}\n\n## Quality evaluation feedback\n\n{quality_feedback}"
        recorder = LLMCallService(provider=provider, model=model)
        adapter = GraphStageAdapter(state)
        input_payload = {
            "provider": provider,
            "model": model,
            "base_url": runtime_context.get("llm_base_url"),
            "document_count": 1,
            "document_index": document_index + 1,
            "filename": prompt.filename,
        }
        if retry_count:
            input_payload["quality_retry_count"] = retry_count
        step_key = f"generate_document_{document_index + 1:02d}"
        if retry_count:
            step_key = f"{step_key}_retry_{retry_count}"
        document = adapter.run(
            key=step_key,
            title=f"Generate Markdown with LLM: {prompt.title}",
            description="Generate one fixed Markdown document in the internal parallel subgraph",
            tool_name="llm_service.generate_markdown_documents",
            input_summary=f"provider={provider}, model={model}, document={prompt.filename}",
            input_payload=input_payload,
            action=lambda: generate_markdown_document(
                document_prompt=prompt,
                context=generation_context,
                api_key=runtime_context.get("llm_api_key"),
                model=model,
                base_url=runtime_context.get("llm_base_url"),
                recorder=recorder,
            ),
            output_summary=lambda result: f"Generated {result[1]}",
            output_payload=lambda result: {"documents": [result[1]]},
            related_files=lambda _: [file.path for file in state.get("core_files", []) if file.used_for_context],
        )
        audit_update = adapter.state_update()
        result = DocumentGenerationResult(
            index=document_index,
            title=document[0],
            filename=document[1],
            content=document[2],
            llm_call_record=recorder.records[-1],
            agent_step=audit_update["agent_steps"][-1],
            tool_log=audit_update["tool_logs"][-1],
        )
        _emit_document_ready(
            result=result,
            document_index=document_index,
        )
        check_cancellation(runtime)
        return {"document_results": [result]}

    return generate_document


def _emit_document_ready(*, result: DocumentGenerationResult, document_index: int) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(
        {
            "event_id": f"{result.agent_step.id}:document-ready",
            "type": "document_ready",
            "payload": {
                "index": document_index,
                "title": result.title,
                "filename": result.filename,
                "content": result.content,
            },
        }
    )
