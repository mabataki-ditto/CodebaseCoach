from datetime import UTC, datetime
from pathlib import Path
import re

from app.core.errors import AppError
from app.schemas.agent import GeneratedDocument
from app.schemas.history import HistoryRecord


def save_markdown_documents(
    *,
    owner: str,
    repo: str,
    docs_root: Path,
    documents: list[tuple[str, str, str]],
) -> tuple[list[GeneratedDocument], str]:
    docs_root = docs_root.resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    docs_dir_name = f"{_safe_path_part(owner)}_{_safe_path_part(repo)}_{timestamp}"
    docs_dir = docs_root / docs_dir_name

    try:
        docs_dir.mkdir(parents=True, exist_ok=True)
        saved_documents = [
            _write_document(docs_root=docs_root, docs_dir=docs_dir, title=title, filename=filename, content=content)
            for title, filename, content in documents
        ]
    except OSError as exc:
        raise AppError(
            status_code=500,
            code="DOC_SAVE_FAILED",
            message="Markdown 文档保存失败",
            detail=str(exc),
        ) from exc

    return saved_documents, f"{docs_root.name}/{docs_dir_name}"


def create_markdown_docs_dir(*, owner: str, repo: str, docs_root: Path) -> tuple[Path, str]:
    docs_root = docs_root.resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    docs_dir_name = f"{_safe_path_part(owner)}_{_safe_path_part(repo)}_{timestamp}"
    docs_dir = docs_root / docs_dir_name
    try:
        docs_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppError(
            status_code=500,
            code="DOC_SAVE_FAILED",
            message="Markdown 文档目录创建失败",
            detail=str(exc),
        ) from exc
    return docs_dir, f"{docs_root.name}/{docs_dir_name}"


def save_markdown_document_to_dir(
    *,
    docs_root: Path,
    docs_dir: Path,
    title: str,
    filename: str,
    content: str,
) -> GeneratedDocument:
    docs_root = docs_root.resolve()
    docs_dir = docs_dir.resolve()
    if not _is_relative_to(docs_dir, docs_root):
        raise AppError(
            status_code=500,
            code="DOC_SAVE_FAILED",
            message="Markdown 文档目录无效",
        )
    try:
        return _write_document(docs_root=docs_root, docs_dir=docs_dir, title=title, filename=filename, content=content)
    except OSError as exc:
        raise AppError(
            status_code=500,
            code="DOC_SAVE_FAILED",
            message="Markdown 文档保存失败",
            detail=str(exc),
        ) from exc


def load_markdown_documents_for_history(
    *,
    docs_root: Path,
    history_record: HistoryRecord,
) -> list[GeneratedDocument]:
    docs_root = docs_root.resolve()
    if not history_record.docs_dir.strip():
        raise AppError(
            status_code=404,
            code="DOCS_NOT_FOUND",
            message="历史记录没有可打开的文档目录",
            detail=history_record.id,
        )
    docs_dir = _resolve_docs_dir(docs_root=docs_root, docs_dir=history_record.docs_dir)
    if not docs_dir.exists() or not docs_dir.is_dir():
        raise AppError(
            status_code=404,
            code="DOCS_NOT_FOUND",
            message="历史文档目录不存在",
            detail=history_record.docs_dir,
        )

    documents: list[GeneratedDocument] = []
    for path in sorted(docs_dir.glob("*.md"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        relative_path = path.relative_to(docs_root).as_posix()
        documents.append(
            GeneratedDocument(
                title=path.stem,
                filename=path.name,
                path=f"{docs_root.name}/{relative_path}",
                content=path.read_text(encoding="utf-8"),
            )
        )
    return documents


def _write_document(*, docs_root: Path, docs_dir: Path, title: str, filename: str, content: str) -> GeneratedDocument:
    safe_filename = _safe_filename(filename)
    target_path = (docs_dir / safe_filename).resolve()
    if not _is_relative_to(target_path, docs_root):
        raise AppError(
            status_code=500,
            code="DOC_SAVE_FAILED",
            message="Markdown 文档保存路径无效",
        )

    target_path.write_text(content, encoding="utf-8")
    relative_path = target_path.relative_to(docs_root).as_posix()
    return GeneratedDocument(
        title=title,
        filename=safe_filename,
        path=f"{docs_root.name}/{relative_path}",
        content=content,
    )


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _safe_filename(value: str) -> str:
    filename = re.sub(r"[\\/:*?\"<>|]", "_", value.strip())
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    return filename


def _resolve_docs_dir(*, docs_root: Path, docs_dir: str) -> Path:
    relative = docs_dir.replace("\\", "/")
    prefix = f"{docs_root.name}/"
    if relative.startswith(prefix):
        relative = relative[len(prefix) :]
    target = (docs_root / relative).resolve()
    if not _is_relative_to(target, docs_root):
        raise AppError(
            status_code=400,
            code="INVALID_DOCS_DIR",
            message="历史文档路径无效",
            detail=docs_dir,
        )
    return target


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
