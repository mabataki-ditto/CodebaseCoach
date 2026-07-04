from typing import Any, Protocol

from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    name: str
    enabled: bool = True
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    readonly: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(default=8000, ge=1)


class McpConfig(BaseModel):
    servers: list[McpServerConfig] = Field(default_factory=list)


class McpTool(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class McpToolCallResult(BaseModel):
    content: Any = None
    summary: str = ""


class McpClient(Protocol):
    def list_tools(self, server_name: str) -> list[McpTool]:
        ...

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        ...

