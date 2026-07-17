from collections.abc import Callable
from typing import TypedDict

from langgraph.runtime import Runtime

from app.services.mcp_tool_service import McpToolService


class AnalysisRuntimeContext(TypedDict, total=False):
    """Process-local dependencies that must not be stored in AnalysisState."""

    mcp_service: McpToolService | None
    llm_api_key: str | None
    llm_model: str
    llm_base_url: str | None
    llm_provider: str
    cancel_check: Callable[[], None] | None


def check_cancellation(runtime: Runtime[AnalysisRuntimeContext] | None) -> None:
    callback = runtime.context.get("cancel_check") if runtime and runtime.context else None
    if callback is not None:
        callback()
