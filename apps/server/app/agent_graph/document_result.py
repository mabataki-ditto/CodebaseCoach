from dataclasses import dataclass

from app.schemas.agent import AgentStep, ToolCallLog
from app.services.llm_call_service import LLMCallRecord


@dataclass(frozen=True)
class DocumentGenerationResult:
    index: int
    title: str
    filename: str
    content: str
    llm_call_record: LLMCallRecord
    agent_step: AgentStep
    tool_log: ToolCallLog


def merge_document_results(
    left: list[DocumentGenerationResult],
    right: list[DocumentGenerationResult],
) -> list[DocumentGenerationResult]:
    """Merge parallel branch results by their fixed prompt index."""
    by_index = {result.index: result for result in left}
    by_index.update({result.index: result for result in right})
    return [by_index[index] for index in sorted(by_index)]
