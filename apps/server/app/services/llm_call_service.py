from dataclasses import dataclass


@dataclass(frozen=True)
class LLMCallRecord:
    provider: str
    model: str
    prompt_type: str
    duration_ms: int
    status: str
    error_message: str | None = None


class LLMCallService:
    def __init__(self, *, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._records: list[LLMCallRecord] = []

    def record(
        self,
        *,
        prompt_type: str,
        duration_ms: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        self._records.append(
            LLMCallRecord(
                provider=self._provider,
                model=self._model,
                prompt_type=prompt_type,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message,
            )
        )

    @property
    def records(self) -> list[LLMCallRecord]:
        return list(self._records)
