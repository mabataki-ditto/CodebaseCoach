import json
import os
import queue
import subprocess
import threading
import time
from itertools import count
from typing import Any

from app.core.errors import AppError
from app.mcp.schemas import McpServerConfig, McpTool, McpToolCallResult


class StdioMcpClient:
    def __init__(self, servers: list[McpServerConfig]) -> None:
        self._servers = {server.name: server for server in servers}
        self._request_ids = count(1)

    def list_tools(self, server_name: str) -> list[McpTool]:
        result = self._request(server_name, "tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [
            McpTool(
                name=str(tool.get("name", "")),
                description=str(tool.get("description", "")),
                input_schema=tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {},
                output_schema=tool.get("outputSchema") if isinstance(tool.get("outputSchema"), dict) else {},
            )
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        ]

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        result = self._request(
            server_name,
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        return McpToolCallResult(content=result, summary=_summarize_result(result))

    def _request(self, server_name: str, method: str, params: dict[str, Any]) -> Any:
        server = self._servers.get(server_name)
        if server is None or not server.enabled:
            raise AppError(
                status_code=400,
                code="MCP_SERVER_NOT_CONFIGURED",
                message="MCP server is not configured",
                detail=server_name,
            )
        if server.transport != "stdio":
            raise AppError(
                status_code=400,
                code="MCP_TRANSPORT_UNSUPPORTED",
                message="Only stdio MCP transport is supported in this version",
                detail=server.transport,
            )

        env = os.environ.copy()
        env.update(server.env)
        try:
            process = subprocess.Popen(
                [server.command, *server.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
            )
        except OSError as exc:
            raise AppError(
                status_code=502,
                code="MCP_SERVER_START_FAILED",
                message="MCP server failed to start",
                detail=f"{server.name}: {exc}",
            ) from exc
        request_id = next(self._request_ids)
        initialize_id = next(self._request_ids)
        lines = _write_requests_and_read_response_lines(
            process,
            timeout_seconds=server.timeout_ms / 1000,
            requests=[
                {
                    "jsonrpc": "2.0",
                    "id": initialize_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "CodebaseCoach", "version": "0.1.0"},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
            ],
            request_id=request_id,
            server_name=server_name,
        )
        return _parse_json_rpc_response(lines, server_name=server_name, request_id=request_id)


def _write_requests_and_read_response_lines(
    process: subprocess.Popen,
    *,
    timeout_seconds: float,
    requests: list[dict[str, Any]],
    request_id: int,
    server_name: str,
) -> list[str]:
    line_queue: queue.Queue[str] = queue.Queue()

    def read_stdout() -> None:
        if process.stdout is None:
            return
        for stdout_line in process.stdout:
            line_queue.put(stdout_line)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()

    if process.stdin is None:
        raise AppError(
            status_code=502,
            code="MCP_SERVER_FAILED",
            message="MCP server stdin is unavailable",
            detail=server_name,
        )
    for request in requests:
        process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
    process.stdin.flush()

    lines: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            line = line_queue.get(timeout=0.1)
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        lines.append(line)
        if _line_has_response_id(line, request_id):
            _stop_process(process)
            return lines

    _stop_process(process)
    stderr = ""
    if process.stderr is not None:
        try:
            stderr = process.stderr.read()
        except Exception:
            stderr = ""
    if stderr:
        raise AppError(
            status_code=502,
            code="MCP_SERVER_FAILED",
            message="MCP server failed",
            detail=stderr.strip() or server_name,
        )
    raise AppError(
        status_code=504,
        code="MCP_SERVER_TIMEOUT",
        message="MCP server timed out",
        detail=server_name,
    )


def _line_has_response_id(line: str, request_id: int) -> bool:
    try:
        payload = json.loads(line.strip())
    except json.JSONDecodeError:
        return False
    return payload.get("id") == request_id


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()


def _parse_json_rpc_response(lines: list[str], *, server_name: str, request_id: int) -> Any:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in payload:
            raise AppError(
                status_code=502,
                code="MCP_TOOL_CALL_FAILED",
                message="MCP tool call failed",
                detail=json.dumps(payload["error"], ensure_ascii=False),
            )
        if payload.get("id") == request_id and "result" in payload:
            return payload["result"]
    raise AppError(
        status_code=502,
        code="MCP_INVALID_RESPONSE",
        message="MCP server returned no JSON-RPC result",
        detail=server_name,
    )


def _summarize_result(result: Any) -> str:
    if isinstance(result, dict):
        if isinstance(result.get("content"), list):
            return f"Returned {len(result['content'])} content items"
        return f"Returned {len(result)} fields"
    if isinstance(result, list):
        return f"Returned {len(result)} items"
    return "Returned MCP result"
