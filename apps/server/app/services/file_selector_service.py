import os
from pathlib import Path

from app.schemas.agent import CoreFileSummary
from app.schemas.metrics import CoreFileCandidateMetric, CoreFileSelectionMetrics
from app.services.file_selection_analysis_service import (
    FileDependencySignal,
    RepositorySelectionLayout,
    build_dependency_signals,
    discover_repository_layout,
)

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
    "test-dts",
}

METADATA_FILE_NAMES = {
    "readme.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}

ENTRY_STEMS = {"main", "index", "app", "server"}
AUXILIARY_STEMS = {
    "config",
    "constants",
    "diagnostics",
    "env",
    "helpers",
    "logging",
    "signals",
    "symbols",
    "types",
    "typing",
    "utils",
}
PRIORITY_DIRS = {"src", "app", "core", "agent", "agents", "tools", "services", "api", "routes", "components"}
NOISE_DIRS = {"docs", "doc", "examples", "example", "playground", "samples", "sample", "benchmarks", "fixtures"}

SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".mjs", ".cjs"}
BEHAVIOR_EXTENSIONS = {".yaml", ".yml"}

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
    layout = discover_repository_layout(root)
    eligible_paths = [
        path for path in _iter_repository_files(root) if _is_candidate_file(path, root, layout)
    ]
    primary_paths = [path for path in eligible_paths if not _is_noise_path(path, root)]
    fallback_paths = [path for path in eligible_paths if _is_noise_path(path, root)]
    candidate_paths = primary_paths if len(primary_paths) >= max_files else primary_paths + fallback_paths
    primary_entry_paths = _select_primary_entry_paths(layout, max_files)
    secondary_entry_paths = layout.entry_paths - primary_entry_paths
    dependency_entry_paths = primary_entry_paths & layout.dependency_entry_paths
    dependency_signals = build_dependency_signals(
        root,
        candidate_paths,
        dependency_entry_paths or primary_entry_paths,
    )
    candidates = [
        _build_candidate(
            path,
            root,
            layout,
            dependency_signals[path.relative_to(root).as_posix()],
            primary_entry_paths,
            secondary_entry_paths,
        )
        for path in candidate_paths
    ]
    ranked = sorted(
        [candidate for candidate in candidates if candidate[0] > 0],
        key=lambda item: (-item[0], item[1].count("/"), item[1].lower()),
    )

    selected: list[CoreFileSummary] = []
    candidate_summaries: list[CoreFileCandidateMetric] = []
    candidate_core_files = 0
    raw_candidate_chars = 0

    for score, _, reason, path in ranked:
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


def _iter_repository_files(root: Path):
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name.lower() not in IGNORED_NAMES]
        for filename in filenames:
            yield Path(current) / filename


def _is_candidate_file(path: Path, root: Path, layout: RepositorySelectionLayout) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False
    relative_path = relative.as_posix()
    if any(part.lower() in IGNORED_NAMES for part in relative.parts) or layout.is_excluded(relative_path):
        return False
    if _is_metadata_file(path) or _is_test_file(path):
        return False
    if path.suffix.lower() in SOURCE_EXTENSIONS:
        return not path.name.lower().endswith((".d.ts", ".min.js"))
    return path.suffix.lower() in BEHAVIOR_EXTENSIONS and bool({"prompts", "templates"} & {part.lower() for part in relative.parts})


def _build_candidate(
    path: Path,
    root: Path,
    layout: RepositorySelectionLayout,
    dependency_signal: FileDependencySignal,
    primary_entry_paths: set[str],
    secondary_entry_paths: set[str],
) -> tuple[int, str, str, Path]:
    relative_path = path.relative_to(root).as_posix()
    path_parts = {part.lower() for part in Path(relative_path).parts[:-1]}

    score = 100 + layout.package_weight(relative_path)
    reasons: list[str] = []

    if relative_path in primary_entry_paths:
        score += 10_000
        reasons.append("由项目声明或包结构识别为入口")
    elif relative_path in secondary_entry_paths:
        score += 800
        reasons.append("由构建配置识别为辅助发布入口")
    elif dependency_signal.distance_from_entry is not None:
        distance_bonus = max(600, 3_000 - (dependency_signal.distance_from_entry - 1) * 400)
        score += distance_bonus
        reasons.append(f"距入口依赖链 {dependency_signal.distance_from_entry} 层")
    if dependency_signal.inbound_count:
        score += min(dependency_signal.inbound_count, 20) * 120
        reasons.append(f"被 {dependency_signal.inbound_count} 个内部文件引用")
    if dependency_signal.outbound_count:
        score += min(dependency_signal.outbound_count, 20) * 40
        reasons.append(f"编排 {dependency_signal.outbound_count} 个内部依赖")
    if dependency_signal.registration_depth == 1:
        score += 2_600
        reasons.append("由运行时注册表加载")
    elif dependency_signal.registration_depth == 2:
        score += 1_000
        reasons.append("属于运行时注册模块的直接实现")
    if dependency_signal.structural_definition_count:
        score += min(dependency_signal.structural_definition_count, 2) * 350
        reasons.append("包含核心类型定义")
    if dependency_signal.type_only:
        score = max(1, score - 2_500)
        reasons.append("仅包含类型声明")
    if path.stem.lower() in ENTRY_STEMS:
        score += 120
        reasons.append("入口命名")
    matched_dirs = sorted(path_parts & PRIORITY_DIRS)
    if matched_dirs:
        score += 100 + len(matched_dirs) * 20
        reasons.append(f"位于核心目录 {', '.join(matched_dirs)}")
    if path.suffix.lower() in SOURCE_EXTENSIONS:
        implementation_size = min(path.stat().st_size // 1_000, 10)
        score += implementation_size * 100
        if implementation_size:
            reasons.append("包含较完整的源码实现")
        reasons.append("源码文件")
    else:
        score += 40
        reasons.append("行为定义文件")

    if relative_path not in layout.entry_paths and _is_auxiliary_module(path):
        score = max(1, score - 1_000)
        reasons.append("辅助模块降权")
    if relative_path not in layout.entry_paths and path.stem.lower() == "index":
        score = max(1, score - 300)
        reasons.append("非包入口聚合文件降权")

    if _is_noise_path(path, root):
        score = 1
        reasons.append("仅在核心源码不足时补位")

    reason = "；".join(reasons) if reasons else "可读项目文件"
    return score, relative_path, reason, path


def _select_primary_entry_paths(layout: RepositorySelectionLayout, max_files: int) -> set[str]:
    if max_files <= 0:
        return set()
    entry_budget = min(len(layout.primary_entry_paths), max(1, max_files // 4))
    ranked = sorted(
        layout.primary_entry_paths,
        key=lambda path: (-layout.package_weight(path), path.count("/"), path.lower()),
    )
    return set(ranked[:entry_budget])


def _is_metadata_file(path: Path) -> bool:
    name = path.name.lower()
    if name in METADATA_FILE_NAMES or name.startswith("readme."):
        return True
    return name.startswith(("tsconfig.", "vite.config.", "tsdown.config.", "nuxt.config.", "webpack.config.", "rollup.config."))


def _is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("test_") or any(marker in name for marker in (".test.", ".spec."))


def _is_auxiliary_module(path: Path) -> bool:
    stem = path.stem.lower()
    return stem in AUXILIARY_STEMS or stem.endswith(("constants", "helpers", "symbols", "types", "utils"))


def _is_noise_path(path: Path, root: Path) -> bool:
    relative_parts = {part.lower() for part in path.relative_to(root).parts[:-1]}
    return bool(relative_parts & NOISE_DIRS)


def _file_type(path: Path) -> str:
    if path.name.lower() == "requirements.txt":
        return "Python Requirements"
    if path.name.lower() == "package.json":
        return "Package Manifest"
    return FILE_TYPES.get(path.suffix.lower(), "Text")
