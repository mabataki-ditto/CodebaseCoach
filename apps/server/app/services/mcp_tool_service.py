from time import perf_counter
from typing import Any

from app.agent.tools import ToolDefinition
from app.core.errors import AppError
from app.mcp.schemas import McpClient, McpTool, McpToolCallResult
from app.schemas.agent import ToolCallLog
from app.services.tool_log_service import record_tool_call


class McpToolService:
    def __init__(
        self,
        *,
        client: McpClient,
        server_name: str,
        allowed_tools: set[str],
    ) -> None:
        self._client = client
        self._server_name = server_name
        self._allowed_tools = allowed_tools

    @property
    def server_name(self) -> str:
        return self._server_name

    def discover_tools(self) -> list[ToolDefinition]:
        return [
            self._definition_for_tool(tool)
            for tool in self._client.list_tools(self._server_name)
            if self._is_allowed_tool(tool.name)
        ]

    def call_tool(
        self,
        *,
        tool_logs: list[ToolCallLog],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpToolCallResult:
        if not self._is_allowed_tool(tool_name):
            raise AppError(
                status_code=403,
                code="MCP_TOOL_NOT_ALLOWED",
                message="MCP tool is not allowed",
                detail=f"{self._server_name}.{tool_name}",
            )

        definition = self._definition_for_tool(McpTool(name=tool_name))
        started = perf_counter()
        try:
            result = self._client.call_tool(self._server_name, tool_name, arguments)
        except AppError as exc:
            record_tool_call(
                tool_logs,
                tool_name=definition.name,
                status="failed",
                input_summary=_summarize_arguments(arguments),
                output_summary="Failed",
                input_payload=arguments,
                output_payload={"error_code": exc.code},
                duration_ms=int((perf_counter() - started) * 1000),
                error_message=exc.detail or exc.message,
                definition=definition,
            )
            raise
        except Exception as exc:
            record_tool_call(
                tool_logs,
                tool_name=definition.name,
                status="failed",
                input_summary=_summarize_arguments(arguments),
                output_summary="Failed",
                input_payload=arguments,
                output_payload={"error_code": "MCP_TOOL_CALL_UNEXPECTED"},
                duration_ms=int((perf_counter() - started) * 1000),
                error_message=str(exc),
                definition=definition,
            )
            raise AppError(
                status_code=502,
                code="MCP_TOOL_CALL_UNEXPECTED",
                message="MCP tool call failed unexpectedly",
                detail=str(exc),
            ) from exc

        output_payload = result.content if isinstance(result.content, dict) else {"content": result.content}
        record_tool_call(
            tool_logs,
            tool_name=definition.name,
            status="success",
            input_summary=_summarize_arguments(arguments),
            output_summary=result.summary or _summarize_result(result.content),
            input_payload=arguments,
            output_payload=output_payload,
            duration_ms=int((perf_counter() - started) * 1000),
            definition=definition,
        )
        return result

    def _is_allowed_tool(self, tool_name: str) -> bool:
        return tool_name in self._allowed_tools

    def _definition_for_tool(self, tool: McpTool) -> ToolDefinition:
        return ToolDefinition(
            name=f"mcp.{self._server_name}.{tool.name}",
            provider="mcp",
            permission="read",
            description=tool.description or f"Read-only MCP tool {self._server_name}.{tool.name}",
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            redact_fields=("GITHUB_PERSONAL_ACCESS_TOKEN",),
            requires_confirmation=False,
        )


def _summarize_arguments(arguments: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in arguments.items() if key.lower() not in {"token", "authorization"}]
    return ", ".join(parts) if parts else "MCP tool call"


def _summarize_result(result: Any) -> str:
    if isinstance(result, list):
        return f"Returned {len(result)} items"
    if isinstance(result, dict):
        if isinstance(result.get("items"), list):
            return f"Returned {len(result['items'])} items"
        return f"Returned {len(result)} fields"
    return "Returned MCP result"
