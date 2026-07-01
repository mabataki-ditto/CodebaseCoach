import json
from pathlib import Path
from uuid import uuid4

from app.schemas.history import HistoryRecord


def list_history_records(*, history_file: Path) -> list[HistoryRecord]:
    return sorted(_read_history(history_file), key=lambda record: record.created_at, reverse=True)


def add_history_record(
    *,
    history_file: Path,
    repo_url: str,
    owner: str,
    repo: str,
    status: str,
    created_at: str,
    completed_at: str | None,
    docs_dir: str = "",
    core_files_count: int = 0,
    error_message: str | None = None,
    mock_mode: bool = True,
) -> HistoryRecord:
    records = _read_history(history_file)
    record = HistoryRecord(
        id=uuid4().hex,
        repo_url=repo_url,
        owner=owner,
        repo=repo,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        docs_dir=docs_dir,
        core_files_count=core_files_count,
        error_message=error_message,
        mock_mode=mock_mode,
    )
    records.append(record)
    _write_history(history_file, records)
    return record


def delete_history_record(*, history_file: Path, record_id: str) -> bool:
    records = _read_history(history_file)
    remaining = [record for record in records if record.id != record_id]
    if len(remaining) == len(records):
        return False
    _write_history(history_file, remaining)
    return True


def get_history_record(*, history_file: Path, record_id: str) -> HistoryRecord | None:
    for record in _read_history(history_file):
        if record.id == record_id:
            return record
    return None


def _read_history(history_file: Path) -> list[HistoryRecord]:
    if not history_file.exists():
        return []
    try:
        raw_records = json.loads(history_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_records, list):
        return []
    return [HistoryRecord.model_validate(record) for record in raw_records]


def _write_history(history_file: Path, records: list[HistoryRecord]) -> None:
    history_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump() for record in records]
    history_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
