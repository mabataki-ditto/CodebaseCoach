from datetime import UTC, datetime
from pathlib import Path
import re

from app.core.errors import AppError
from app.schemas.agent import GeneratedDocument


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
