from pathlib import Path

from app.schemas.agent import CoreFileSummary
from app.schemas.metrics import CoreFileCandidateMetric, CoreFileSelectionMetrics

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
    "test",
    "tests",
    "__tests__",
}

PRIORITY_FILE_NAMES = {
    "readme.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
    "vite.config.ts",
}

PRIORITY_FILE_ORDER = {
    "readme.md": 0,
    "package.json": 1,
    "pyproject.toml": 2,
    "requirements.txt": 3,
    "tsconfig.json": 4,
    "vite.config.ts": 5,
}

PRIORITY_PATHS = {
    "src/main.ts",
    "src/index.ts",
    "src/app.vue",
    "app/main.py",
    "main.py",
    "app.py",
    "server.py",
    "index.ts",
    "index.js",
}

ENTRY_STEMS = {"main", "index", "app", "server"}
PRIORITY_DIRS = {"src", "app", "core", "agent", "agents", "tools", "services", "api", "routes", "components"}

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".css",
    ".scss",
    ".html",
    ".mjs",
    ".cjs",
}

FILE_TYPES = {
    ".md": "Markdown",
    ".txt": "Text",
    ".json": "JSON",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TSX",
    ".js": "JavaScript",
    ".jsx": "JSX",
    ".vue": "Vue",
    ".css": "CSS",
    ".scss": "SCSS",
    ".html": "HTML",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
}


def select_core_files(root: Path, *, max_files: int = 12, max_bytes: int = 12_000) -> list[CoreFileSummary]:
    core_files, _ = select_core_files_with_metrics(root, max_files=max_files, max_bytes=max_bytes)
    return core_files


def select_core_files_with_metrics(
    root: Path,
    *,
    max_files: int = 12,
    max_bytes: int = 12_000,
) -> tuple[list[CoreFileSummary], CoreFileSelectionMetrics]:
    root = root.resolve()
    candidates = [_build_candidate(path, root) for path in root.rglob("*") if _is_candidate_file(path, root)]
    ranked = sorted(
        [candidate for candidate in candidates if candidate[0] > 0],
        key=lambda item: (-item[0], item[1], item[2].count("/"), item[2].lower()),
    )

    selected: list[CoreFileSummary] = []
    candidate_summaries: list[CoreFileCandidateMetric] = []
    candidate_core_files = 0
    raw_candidate_chars = 0

    for score, _, _, reason, path in ranked:
        candidate = _read_core_file_candidate(path, root=root, reason=reason, max_bytes=max_bytes)
        if candidate is None:
            continue

        summary, full_content_chars = candidate
        candidate_core_files += 1
        raw_candidate_chars += full_content_chars
        candidate_summaries.append(
            CoreFileCandidateMetric(
                path=summary.path,
                file_type=summary.file_type,
                size=summary.size,
                reason=summary.reason,
                score=score,
                truncated=summary.truncated,
            )
        )

        if len(selected) >= max_files:
            continue

        selected.append(summary)

    return selected, CoreFileSelectionMetrics(
        candidate_core_files=candidate_core_files,
        raw_candidate_chars=raw_candidate_chars,
        candidates=candidate_summaries,
    )


def _read_core_file_candidate(
    path: Path,
    *,
    root: Path,
    reason: str,
    max_bytes: int,
) -> tuple[CoreFileSummary, int] | None:
    size = path.stat().st_size
    content_bytes = path.read_bytes()

    if b"\0" in content_bytes:
        return None

    content_preview = content_bytes[:max_bytes].decode("utf-8", errors="replace")
    full_content_chars = len(content_bytes.decode("utf-8", errors="replace"))
    summary = CoreFileSummary(
        path=path.relative_to(root).as_posix(),
        file_type=_file_type(path),
        size=size,
        content_preview=content_preview,
        truncated=size > max_bytes,
        reason=reason,
    )
    return summary, full_content_chars


def _is_candidate_file(path: Path, root: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False
    if any(part.lower() in IGNORED_NAMES for part in relative.parts):
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in PRIORITY_FILE_NAMES


def _build_candidate(path: Path, root: Path) -> tuple[int, int, str, str, Path]:
    relative_path = path.relative_to(root).as_posix()
    lower_path = relative_path.lower()
    lower_name = path.name.lower()
    path_parts = {part.lower() for part in Path(lower_path).parts[:-1]}

    score = 0
    reasons: list[str] = []

    if lower_name in PRIORITY_FILE_NAMES:
        score += 3_000 if "/" not in lower_path else 2_000
        reasons.append("基础项目文件")
    if lower_path in PRIORITY_PATHS:
        score += 900
        reasons.append("入口文件")
    if path.stem.lower() in ENTRY_STEMS:
        score += 320
        reasons.append("入口命名")
    matched_dirs = sorted(path_parts & PRIORITY_DIRS)
    if matched_dirs:
        score += 220 + len(matched_dirs) * 20
        reasons.append(f"位于核心目录 {', '.join(matched_dirs)}")
    if path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".vue"}:
        score += 40
        reasons.append("源码文件")

    reason = "；".join(reasons) if reasons else "可读项目文件"
    priority_order = PRIORITY_FILE_ORDER.get(lower_name, 100)
    return score, priority_order, relative_path, reason, path


def _file_type(path: Path) -> str:
    if path.name.lower() == "requirements.txt":
        return "Python Requirements"
    if path.name.lower() == "package.json":
        return "Package Manifest"
    return FILE_TYPES.get(path.suffix.lower(), "Text")
