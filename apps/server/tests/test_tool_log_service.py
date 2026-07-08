import pytest

from app.core.errors import AppError
from app.services.tool_log_service import record_tool_call

pytestmark = pytest.mark.unit


def test_record_tool_call_adds_registry_audit_metadata() -> None:
    logs = []

    log = record_tool_call(
        logs,
        tool_name="clone_repository",
        status="success",
        input_summary="https://github.com/owner/repo",
        output_summary="repo",
        input_payload={"repo_url": "https://github.com/owner/repo"},
        output_payload={"local_path": "temp_repos/repo"},
        duration_ms=12,
    )

    assert log.tool_provider == "builtin"
    assert log.permission == "network"
    assert not log.requires_confirmation
    assert "repo_url" in log.input_schema["properties"]
    assert log.input["repo_url"] == "https://github.com/owner/repo"
    assert logs[0] == log


def test_record_tool_call_redacts_sensitive_input_fields() -> None:
    logs = []

    log = record_tool_call(
        logs,
        tool_name="llm_service.generate_markdown_documents",
        status="success",
        input_summary="provider=openai",
        output_summary="Generated 1 document",
        input_payload={"provider": "openai", "api_key": "sk-secret", "token": "secret-token"},
        output_payload={"documents": ["01.md"]},
        duration_ms=20,
    )

    assert log.permission == "llm"
    assert log.input["api_key"] == "[redacted]"
    assert log.input["token"] == "[redacted]"
    assert log.input["provider"] == "openai"


def test_record_tool_call_rejects_unregistered_tools() -> None:
    with pytest.raises(AppError) as raised:
        record_tool_call(
            [],
            tool_name="unknown_tool",
            status="success",
            input_summary="",
            output_summary="",
            duration_ms=0,
        )

    assert raised.value.code == "TOOL_NOT_REGISTERED"