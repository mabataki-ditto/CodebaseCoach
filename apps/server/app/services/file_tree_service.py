import os
from pathlib import Path

from app.schemas.metrics import RepoScanMetrics
from app.schemas.repo import BasicFileSummary, FileTreeNode

IGNORED_NAMES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".nuxt",
    ".cache",
    ".idea",
    ".vscode",
}

BASIC_FILE_NAMES = {
    "readme.md": "markdown",
    "package.json": "json",
    "requirements.txt": "python-requirements",
    "pyproject.toml": "python-project",
}


def build_file_tree(root: Path, *, max_depth: int = 4, max_entries: int = 1_000) -> list[FileTreeNode]:
    counter = _EntryCounter(max_entries=max_entries)
    return _build_children(root.resolve(), root.resolve(), depth=0, max_depth=max_depth, counter=counter)


def scan_repo_metrics(root: Path) -> RepoScanMetrics:
    root = root.resolve()
    metrics = RepoScanMetrics()

    for _, dirnames, filenames in os.walk(root):
        ignored = [name for name in dirnames if name.lower() in IGNORED_NAMES]
        metrics.ignored_dirs += len(ignored)
        dirnames[:] = [name for name in dirnames if name.lower() not in IGNORED_NAMES]
        metrics.total_files += len(filenames)

    return metrics


def read_basic_files(root: Path, *, max_bytes: int = 20_000) -> list[BasicFileSummary]:
    summaries: list[BasicFileSummary] = []
    root = root.resolve()

    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.is_symlink():
            continue

        file_type = BASIC_FILE_NAMES.get(path.name.lower())
        if file_type is None:
            continue

        summary = _read_text_file_summary(path, root=root, file_type=file_type, max_bytes=max_bytes)
        if summary is not None:
            summaries.append(summary)

    return summaries


def _build_children(
    current: Path,
    root: Path,
    *,
    depth: int,
    max_depth: int,
    counter: "_EntryCounter",
) -> list[FileTreeNode]:
    if depth >= max_depth or counter.is_full:
        return []

    nodes: list[FileTreeNode] = []
    children = sorted(
        [item for item in current.iterdir() if _should_include(item)],
        key=lambda item: (item.is_file(), item.name.lower()),
    )

    for item in children:
        if counter.is_full:
            break
        counter.increment()
        relative_path = item.relative_to(root).as_posix()
        node_type = "directory" if item.is_dir() else "file"
        child_nodes: list[FileTreeNode] = []

        if item.is_dir():
            child_nodes = _build_children(
                item,
                root,
                depth=depth + 1,
                max_depth=max_depth,
                counter=counter,
            )

        nodes.append(
            FileTreeNode(
                name=item.name,
                path=relative_path,
                type=node_type,
                children=child_nodes,
            )
        )

    return nodes


def _should_include(path: Path) -> bool:
    if path.name.lower() in IGNORED_NAMES or path.is_symlink():
        return False
    return path.is_dir() or path.is_file()


def _read_text_file_summary(
    path: Path,
    *,
    root: Path,
    file_type: str,
    max_bytes: int,
) -> BasicFileSummary | None:
    size = path.stat().st_size
    with path.open("rb") as file:
        content_bytes = file.read(max_bytes)

    if b"\0" in content_bytes:
        return None

    content_preview = content_bytes.decode("utf-8", errors="replace")
    return BasicFileSummary(
        path=path.relative_to(root).as_posix(),
        file_type=file_type,
        size=size,
        content_preview=content_preview,
        truncated=size > max_bytes,
    )


class _EntryCounter:
    def __init__(self, *, max_entries: int) -> None:
        self.max_entries = max_entries
        self.value = 0

    @property
    def is_full(self) -> bool:
        return self.value >= self.max_entries

    def increment(self) -> None:
        self.value += 1
