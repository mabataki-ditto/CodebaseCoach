from pathlib import Path
import threading
import time

import pytest
from langgraph.runtime import Runtime

import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.generate_document as generate_document_module
import app.agent_graph.runner as runner_module
from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.context import AnalysisRuntimeContext
from app.agent_graph.document_subgraph import build_document_generation_subgraph
from app.agent_graph.graph_builder import build_analysis_graph
from app.agent_graph.nodes.generate_document import make_generate_document_node
from app.agent_graph.runner import run_analysis_graph
from app.core.config import get_settings
from app.core.errors import AppError

pytestmark = pytest.mark.unit


def _create_sample_repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "README.md").write_text("# Sample\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")


def test_phase3_document_subgraph_is_opt_in() -> None:
    default_graph = build_analysis_graph()
    document_graph = build_analysis_graph(include_document_generation=True)
    internal_graph = build_document_generation_subgraph()

    assert "generate_documents" not in default_graph.get_graph().nodes
    assert "generate_documents" in document_graph.get_graph().nodes
    assert [
        f"generate_document_{index:02d}" for index in range(1, len(REAL_DOCUMENT_PROMPTS) + 1)
    ] == [
        name for name in internal_graph.get_graph().nodes if name.startswith("generate_document_")
    ]
    assert "merge_documents" in internal_graph.get_graph().nodes
    assert document_graph.checkpointer is None
    assert internal_graph.checkpointer is None


def test_phase3_parallel_documents_are_merged_in_prompt_order(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)
    phase3_settings = get_settings().model_copy(update={"llm_max_workers": 4})
    monkeypatch.setattr(runner_module, "get_settings", lambda: phase3_settings)

    concurrent_started = threading.Event()
    active_lock = threading.Lock()
    thread_ids: set[int] = set()
    expected_concurrency = min(phase3_settings.llm_max_workers, len(REAL_DOCUMENT_PROMPTS))

    def fake_generate_document(*, document_prompt, context, api_key, model, base_url, recorder):
        assert context
        assert api_key == "phase-3-secret"
        with active_lock:
            thread_ids.add(threading.get_ident())
            if len(thread_ids) >= expected_concurrency:
                concurrent_started.set()
        assert concurrent_started.wait(timeout=5)
        document_index = int(document_prompt.filename[:2])
        time.sleep((len(REAL_DOCUMENT_PROMPTS) - document_index) * 0.002)
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=document_index,
            status="success",
            total_tokens=document_index,
        )
        return document_prompt.title, document_prompt.filename, f"# {document_prompt.title}"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fake_generate_document)

    result = run_analysis_graph(
        "owner/repo",
        include_document_generation=True,
        llm_api_key="phase-3-secret",
        llm_model="phase-3-model",
        llm_base_url="https://example.test/v1",
    )

    assert len(thread_ids) > 1
    assert [filename for _, filename, _ in result["documents"]] == [
        prompt.filename for prompt in REAL_DOCUMENT_PROMPTS
    ]
    assert [record.prompt_type for record in result["llm_call_records"]] == [
        prompt.title for prompt in REAL_DOCUMENT_PROMPTS
    ]
    assert [step.key for step in result["agent_steps"][-7:]] == [
        f"generate_document_{index:02d}" for index in range(1, 8)
    ]
    assert [log.tool_name for log in result["tool_logs"][-7:]] == [
        "llm_service.generate_markdown_documents"
    ] * 7
    assert all("quality_retry_count" not in log.input for log in result["tool_logs"][-7:])
    assert "llm_api_key" not in result
    assert "document_results" not in result
    assert "phase-3-secret" not in repr(result["agent_steps"])
    assert "phase-3-secret" not in repr(result["tool_logs"])


def test_phase3_document_node_delegates_to_existing_llm_service(monkeypatch) -> None:
    prompt = REAL_DOCUMENT_PROMPTS[0]
    captured: dict[str, object] = {}

    def fake_generate_document(**kwargs):
        captured.update(kwargs)
        kwargs["recorder"].record(
            prompt_type=prompt.title,
            duration_ms=3,
            status="success",
            total_tokens=9,
        )
        return prompt.title, prompt.filename, "# body"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fake_generate_document)
    node = make_generate_document_node(0, prompt)
    runtime = Runtime[AnalysisRuntimeContext](
        context={
            "llm_api_key": "secret",
            "llm_model": "model",
            "llm_base_url": "https://example.test/v1",
            "llm_provider": "deepseek",
        }
    )

    update = node(
        {"analysis_context": "context", "core_files": [], "agent_steps": [], "tool_logs": []},
        runtime,
    )

    assert captured["document_prompt"] is prompt
    assert captured["context"] == "context"
    assert len(update["document_results"]) == 1
    assert "agent_steps" not in update
    assert "tool_logs" not in update


def test_phase3_document_node_preserves_app_error_and_audit(monkeypatch) -> None:
    original_error = AppError(
        status_code=502,
        code="LLM_CALL_FAILED",
        message="generation failed",
        detail="upstream failed",
    )
    calls = 0

    def fail_generation(**kwargs):
        nonlocal calls
        calls += 1
        kwargs["recorder"].record(
            prompt_type=REAL_DOCUMENT_PROMPTS[0].title,
            duration_ms=0,
            status="failed",
            error_message=original_error.message,
        )
        raise original_error

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fail_generation)
    node = make_generate_document_node(0, REAL_DOCUMENT_PROMPTS[0])
    runtime = Runtime[AnalysisRuntimeContext](
        context={"llm_api_key": "secret", "llm_model": "model", "llm_provider": "deepseek"}
    )

    with pytest.raises(AppError) as raised:
        node({"analysis_context": "context", "core_files": []}, runtime)

    assert calls == 1
    assert raised.value is original_error
    assert raised.value.agent_steps[-1].key == "generate_document_01"
    assert raised.value.agent_steps[-1].status == "failed"
    assert raised.value.tool_logs[-1].status == "failed"
    assert "secret" not in repr(raised.value.agent_steps)
    assert "secret" not in repr(raised.value.tool_logs)


def test_phase3_missing_api_key_keeps_existing_error_code(monkeypatch) -> None:
    node = make_generate_document_node(0, REAL_DOCUMENT_PROMPTS[0])
    runtime = Runtime[AnalysisRuntimeContext](
        context={"llm_api_key": None, "llm_model": "model", "llm_provider": "deepseek"}
    )

    with pytest.raises(AppError) as raised:
        node({"analysis_context": "context", "core_files": []}, runtime)

    assert raised.value.code == "LLM_API_KEY_MISSING"
    assert raised.value.agent_steps[-1].status == "failed"
