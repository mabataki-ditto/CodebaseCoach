import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.errors import AppError


_CHECKPOINT_TYPES = [
    ("app.agent_graph.document_result", "DocumentGenerationResult"),
    ("app.core.errors", "ErrorDetail"),
    ("app.schemas.agent", "AgentStep"),
    ("app.schemas.agent", "ContextDirectoryCoverage"),
    ("app.schemas.agent", "ContextQualityReport"),
    ("app.schemas.agent", "ContextSelectionReasonCount"),
    ("app.schemas.agent", "CoreFileSummary"),
    ("app.schemas.agent", "GeneratedDocumentEvaluation"),
    ("app.schemas.agent", "GeneratedResultEvaluation"),
    ("app.schemas.agent", "ToolCallLog"),
    ("app.schemas.metrics", "CoreFileCandidateMetric"),
    ("app.schemas.metrics", "CoreFileSelectionMetrics"),
    ("app.schemas.metrics", "RepoScanMetrics"),
    ("app.schemas.repo", "BasicFileSummary"),
    ("app.schemas.repo", "FileTreeNode"),
    ("app.schemas.repo", "RepoParseResponse"),
    ("app.services.llm_call_service", "LLMCallRecord"),
]


class GraphRunService:
    """Own the separate SQLite store used only for LangGraph runtime state."""

    def __init__(self, checkpoint_path: Path) -> None:
        self.checkpoint_path = checkpoint_path.resolve()
        try:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                self.checkpoint_path,
                check_same_thread=False,
            )
        except (OSError, sqlite3.Error) as error:
            raise AppError(
                status_code=500,
                code="GRAPH_CHECKPOINT_OPEN_FAILED",
                message="Unable to open the LangGraph checkpoint store",
                detail=str(error),
            ) from error
        serializer = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)
        self._checkpointer = SqliteSaver(self._connection, serde=serializer)
        self._closed = False

    @property
    def checkpointer(self) -> SqliteSaver:
        return self._checkpointer

    def thread_config(self, thread_id: str, *, max_concurrency: int | None = None) -> dict[str, Any]:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        if max_concurrency is not None:
            config["max_concurrency"] = max_concurrency
        return config

    def has_checkpoint(self, thread_id: str) -> bool:
        return self._checkpointer.get_tuple(self.thread_config(thread_id)) is not None

    def delete_thread(self, thread_id: str) -> None:
        self._checkpointer.delete_thread(thread_id)

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "GraphRunService":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
