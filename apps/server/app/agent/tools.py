from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AppError


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    provider: str
    permission: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    redact_fields: tuple[str, ...] = ()
    requires_confirmation: bool = False


_STRING_SCHEMA = {"type": "string"}
_INTEGER_SCHEMA = {"type": "integer"}
_BOOLEAN_SCHEMA = {"type": "boolean"}


BUILTIN_TOOLS: dict[str, ToolDefinition] = {
    "parse_github_repo_url": ToolDefinition(
        name="parse_github_repo_url",
        provider="builtin",
        permission="read",
        description="Parse and normalize a GitHub repository URL.",
        input_schema={"type": "object", "properties": {"repo_url": _STRING_SCHEMA}, "required": ["repo_url"]},
        output_schema={"type": "object", "properties": {"owner": _STRING_SCHEMA, "repo": _STRING_SCHEMA, "repo_url": _STRING_SCHEMA}},
    ),
    "clone_repository": ToolDefinition(
        name="clone_repository",
        provider="builtin",
        permission="network",
        description="Clone a public GitHub repository into the configured temporary directory.",
        input_schema={
            "type": "object",
            "properties": {"repo_url": _STRING_SCHEMA, "temp_repo_dir": _STRING_SCHEMA},
            "required": ["repo_url", "temp_repo_dir"],
        },
        output_schema={"type": "object", "properties": {"local_path": _STRING_SCHEMA, "directory": _STRING_SCHEMA}},
    ),
    "build_file_tree": ToolDefinition(
        name="build_file_tree",
        provider="builtin",
        permission="read",
        description="Build a filtered repository file tree.",
        input_schema={
            "type": "object",
            "properties": {"local_path": _STRING_SCHEMA, "max_depth": _INTEGER_SCHEMA, "max_entries": _INTEGER_SCHEMA},
        },
        output_schema={"type": "object", "properties": {"top_level_nodes": _INTEGER_SCHEMA}},
    ),
    "read_basic_files": ToolDefinition(
        name="read_basic_files",
        provider="builtin",
        permission="read",
        description="Read basic project files such as README and package manifests.",
        input_schema={"type": "object", "properties": {"max_bytes": _INTEGER_SCHEMA}},
        output_schema={"type": "object", "properties": {"read_files": {"type": "array", "items": _STRING_SCHEMA}}},
    ),
    "select_core_files": ToolDefinition(
        name="select_core_files",
        provider="builtin",
        permission="read",
        description="Select and read candidate core files for the LLM context.",
        input_schema={"type": "object", "properties": {"max_files": _INTEGER_SCHEMA, "max_bytes": _INTEGER_SCHEMA}},
        output_schema={
            "type": "object",
            "properties": {
                "candidate_core_files": _INTEGER_SCHEMA,
                "selected_files": {"type": "array", "items": _STRING_SCHEMA},
                "used_for_context": {"type": "array", "items": _STRING_SCHEMA},
            },
        },
    ),
    "build_analysis_context": ToolDefinition(
        name="build_analysis_context",
        provider="builtin",
        permission="read",
        description="Assemble repository metadata and selected files into LLM context.",
        input_schema={
            "type": "object",
            "properties": {
                "basic_files": {"type": "array", "items": _STRING_SCHEMA},
                "core_files": {"type": "array", "items": _STRING_SCHEMA},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "context_chars": _INTEGER_SCHEMA,
                "used_for_context": {"type": "array", "items": _STRING_SCHEMA},
            },
        },
    ),
    "llm_service.generate_markdown_documents": ToolDefinition(
        name="llm_service.generate_markdown_documents",
        provider="builtin",
        permission="llm",
        description="Generate Markdown documents through the configured OpenAI-compatible LLM service.",
        input_schema={
            "type": "object",
            "properties": {
                "provider": _STRING_SCHEMA,
                "model": _STRING_SCHEMA,
                "base_url": _STRING_SCHEMA,
                "document_count": _INTEGER_SCHEMA,
            },
        },
        output_schema={"type": "object", "properties": {"documents": {"type": "array", "items": _STRING_SCHEMA}}},
        redact_fields=("api_key", "token", "authorization"),
    ),
    "save_markdown_documents": ToolDefinition(
        name="save_markdown_documents",
        provider="builtin",
        permission="write",
        description="Save generated Markdown documents under the configured generated_docs directory.",
        input_schema={
            "type": "object",
            "properties": {"docs_root": _STRING_SCHEMA, "document_count": _INTEGER_SCHEMA},
        },
        output_schema={
            "type": "object",
            "properties": {"docs_dir": _STRING_SCHEMA, "documents": {"type": "array", "items": _STRING_SCHEMA}},
        },
    ),
    "evaluate_generated_documents": ToolDefinition(
        name="evaluate_generated_documents",
        provider="builtin",
        permission="read",
        description="Run deterministic quality checks against generated Markdown documents.",
        input_schema={
            "type": "object",
            "properties": {
                "document_count": _INTEGER_SCHEMA,
                "context_file_count": _INTEGER_SCHEMA,
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "textcitation_score": {"type": "number"},
                "coverage_score": {"type": "number"},
                "hallucination_risk": {"type": "number"},
                "usefulness_score": {"type": "number"},
                "issue_count": _INTEGER_SCHEMA,
            },
        },
    ),
    "fetch_github_mcp_context": ToolDefinition(
        name="fetch_github_mcp_context",
        provider="builtin",
        permission="read",
        description="Fetch read-only GitHub collaboration context through MCP.",
        input_schema={
            "type": "object",
            "properties": {
                "owner": _STRING_SCHEMA,
                "repo": _STRING_SCHEMA,
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "context_chars": _INTEGER_SCHEMA,
                "enabled": _BOOLEAN_SCHEMA,
            },
        },
    ),
}


ALLOWED_TOOL_PERMISSIONS = {"read", "network", "llm", "write"}
SENSITIVE_FIELD_NAMES = {"api_key", "apikey", "token", "authorization", "password", "secret"}


def get_tool_definition(tool_name: str) -> ToolDefinition:
    definition = BUILTIN_TOOLS.get(tool_name)
    if definition is None:
        raise AppError(
            status_code=500,
            code="TOOL_NOT_REGISTERED",
            message="工具未注册，拒绝执行",
            detail=tool_name,
        )
    return definition


def assert_tool_allowed(tool_name: str) -> ToolDefinition:
    definition = get_tool_definition(tool_name)
    if definition.permission not in ALLOWED_TOOL_PERMISSIONS or definition.requires_confirmation:
        raise AppError(
            status_code=403,
            code="TOOL_PERMISSION_DENIED",
            message="工具权限需要人工确认，已拒绝自动执行",
            detail=tool_name,
        )
    return definition


def redact_tool_payload(value: Any, *, definition: ToolDefinition) -> Any:
    redact_fields = {field.lower() for field in definition.redact_fields} | SENSITIVE_FIELD_NAMES
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in redact_fields else redact_tool_payload(item, definition=definition)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_tool_payload(item, definition=definition) for item in value]
    return value
