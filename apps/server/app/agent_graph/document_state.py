from typing import Annotated, TypedDict

from app.agent_graph.document_result import DocumentGenerationResult, merge_document_results
from app.agent_graph.state import AnalysisState
from app.schemas.agent import AgentStep, ToolCallLog
from app.services.llm_call_service import LLMCallRecord


class DocumentSubgraphState(AnalysisState, total=False):
    document_results: Annotated[list[DocumentGenerationResult], merge_document_results]


class DocumentSubgraphOutput(TypedDict, total=False):
    documents: list[tuple[str, str, str]]
    llm_call_records: list[LLMCallRecord]
    agent_steps: list[AgentStep]
    tool_logs: list[ToolCallLog]
