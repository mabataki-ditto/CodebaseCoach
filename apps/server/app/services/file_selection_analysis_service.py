import ast
import json
import os
import re
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CODE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".mjs", ".cjs")
PRIMARY_ENTRY_STEMS = {"index", "main", "module"}
WALK_IGNORED_DIRS = {
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
}


@dataclass
class RepositorySelectionLayout:
    entry_paths: set[str] = field(default_factory=set)
    primary_entry_paths: set[str] = field(default_factory=set)
    dependency_entry_paths: set[str] = field(default_factory=set)
    package_weights: dict[str, int] = field(default_factory=dict)
    excluded_roots: set[str] = field(default_factory=set)

    def package_weight(self, relative_path: str) -> int:
        return max(
            (weight for package_root, weight in self.package_weights.items() if _is_under(relative_path, package_root)),
            default=0,
        )

    def is_excluded(self, relative_path: str) -> bool:
        return any(_is_under(relative_path, excluded_root) for excluded_root in self.excluded_roots)


@dataclass(frozen=True)
class FileDependencySignal:
    distance_from_entry: int | None = None
    inbound_count: int = 0
    outbound_count: int = 0
    structural_definition_count: int = 0
    registration_depth: int | None = None
    type_only: bool = False


def discover_repository_layout(root: Path) -> RepositorySelectionLayout:
    root = root.resolve()
    layout = RepositorySelectionLayout()
    _discover_python_layout(root, layout)
    _discover_javascript_layout(root, layout)
    return layout


def build_dependency_signals(
    root: Path,
    candidate_paths: list[Path],
    entry_paths: set[str],
) -> dict[str, FileDependencySignal]:
    root = root.resolve()
    known_paths = {path.relative_to(root).as_posix() for path in candidate_paths}
    graph: dict[str, set[str]] = {}
    contents: dict[str, str] = {}
    structural_definitions: dict[str, int] = {}
    directly_registered_paths: set[str] = set()
    type_only_paths: set[str] = set()

    for path in candidate_paths:
        relative_path = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        contents[relative_path] = content
        if path.suffix.lower() == ".py":
            dependencies, registered_dependencies = _python_dependencies(relative_path, content, known_paths)
            graph[relative_path] = dependencies
            directly_registered_paths.update(registered_dependencies)
            structural_definitions[relative_path] = _python_definition_count(content)
        elif path.suffix.lower() in CODE_EXTENSIONS[1:]:
            graph[relative_path] = _javascript_dependencies(relative_path, content, known_paths)
            if path.suffix.lower() in {".ts", ".tsx"} and _is_typescript_type_only(content):
                type_only_paths.add(relative_path)
        else:
            graph[relative_path] = set()

    behavior_paths = {path for path in known_paths if Path(path).suffix.lower() in {".yaml", ".yml"}}
    for source_path, content in contents.items():
        if Path(source_path).suffix.lower() not in CODE_EXTENSIONS:
            continue
        graph[source_path].update(path for path in behavior_paths if Path(path).name in content)

    registered_implementation_paths: set[str] = set()
    for registered_path in directly_registered_paths:
        registered_implementation_paths.update(graph.get(registered_path, set()))
    registered_implementation_paths.difference_update(directly_registered_paths)

    inbound: dict[str, int] = {path: 0 for path in known_paths}
    for dependencies in graph.values():
        for dependency in dependencies:
            inbound[dependency] += 1

    distances: dict[str, int] = {}
    queue = deque(path for path in entry_paths if path in known_paths)
    for path in queue:
        distances[path] = 0
    while queue:
        current = queue.popleft()
        for dependency in graph.get(current, set()):
            if dependency in distances:
                continue
            distances[dependency] = distances[current] + 1
            queue.append(dependency)

    return {
        path: FileDependencySignal(
            distance_from_entry=distances.get(path),
            inbound_count=inbound[path],
            outbound_count=len(graph[path]),
            structural_definition_count=structural_definitions.get(path, 0),
            registration_depth=(
                1
                if path in directly_registered_paths
                else 2 if path in registered_implementation_paths else None
            ),
            type_only=path in type_only_paths,
        )
        for path in known_paths
    }


def _discover_python_layout(root: Path, layout: RepositorySelectionLayout) -> None:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return

    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return

    project = pyproject.get("project")
    if not isinstance(project, dict):
        return

    package_root = _python_package_root(root, project.get("name"))
    if package_root is not None:
        relative_root = package_root.relative_to(root).as_posix()
        layout.package_weights[relative_root] = 500
        for filename in ("__init__.py", "__main__.py"):
            path = package_root / filename
            if path.is_file():
                relative_path = path.relative_to(root).as_posix()
                layout.entry_paths.add(relative_path)
                layout.primary_entry_paths.add(relative_path)
                layout.dependency_entry_paths.add(relative_path)

    scripts = project.get("scripts")
    if isinstance(scripts, dict):
        for target in scripts.values():
            if not isinstance(target, str):
                continue
            module_path = _resolve_python_module(root, target.split(":", 1)[0])
            if module_path is not None:
                relative_path = module_path.relative_to(root).as_posix()
                layout.entry_paths.add(relative_path)
                layout.primary_entry_paths.add(relative_path)
                layout.dependency_entry_paths.add(relative_path)


def _discover_javascript_layout(root: Path, layout: RepositorySelectionLayout) -> None:
    manifests = list(_find_files(root, "package.json"))
    root_manifest = _read_json(root / "package.json")
    has_workspaces = isinstance(root_manifest, dict) and bool(root_manifest.get("workspaces"))

    for manifest_path in manifests:
        package_root = manifest_path.parent
        manifest = _read_json(manifest_path)
        if manifest is None:
            continue

        relative_root = "" if package_root == root else package_root.relative_to(root).as_posix()
        is_root = package_root == root
        if not is_root and manifest.get("private") is True:
            layout.excluded_roots.add(relative_root)
            continue
        if is_root and has_workspaces and not (package_root / "src").is_dir():
            continue

        package_name = manifest.get("name") if isinstance(manifest.get("name"), str) else package_root.name
        is_primary = _normalize_name(package_name.split("/")[-1]) == _normalize_name(root.name)
        layout.package_weights[relative_root] = 500 if is_primary or (is_root and not has_workspaces) else 250
        entry_paths, primary_entry_paths = _javascript_entry_paths(root, package_root, manifest)
        layout.entry_paths.update(entry_paths)
        layout.primary_entry_paths.update(primary_entry_paths)
        if primary_entry_paths:
            layout.dependency_entry_paths.add(
                min(primary_entry_paths, key=lambda path: (path.count("/"), path.lower()))
            )


def _javascript_entry_paths(
    root: Path,
    package_root: Path,
    manifest: dict[str, Any],
) -> tuple[set[str], set[str]]:
    entries: set[Path] = set()
    primary_entries: set[Path] = set()

    def add_entry(candidate: Path) -> None:
        entries.add(candidate)
        relative_to_package = candidate.relative_to(package_root)
        if (
            relative_to_package.parts
            and relative_to_package.parts[0] == "src"
            and (len(relative_to_package.parts) == 2 or candidate.stem.lower() in PRIMARY_ENTRY_STEMS)
        ):
            primary_entries.add(candidate)

    for value in _manifest_strings(manifest):
        candidate = package_root / value.removeprefix("./")
        if candidate.is_file() and candidate.suffix.lower() in CODE_EXTENSIONS:
            add_entry(candidate)

    for config_path in package_root.glob("tsdown.config.*"):
        try:
            content = config_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.findall(r"[\"'](\.?/?src/[^\"']+\.(?:ts|tsx|js|jsx|vue|mjs|cjs))[\"']", content):
            candidate = package_root / match.removeprefix("./")
            if candidate.is_file():
                add_entry(candidate)

    for stem in ("index", "module", "main"):
        for extension in CODE_EXTENSIONS[1:]:
            candidate = package_root / "src" / f"{stem}{extension}"
            if candidate.is_file():
                add_entry(candidate)
                break

    return (
        {path.relative_to(root).as_posix() for path in entries},
        {path.relative_to(root).as_posix() for path in primary_entries},
    )


def _python_package_root(root: Path, project_name: object) -> Path | None:
    if not isinstance(project_name, str):
        return None
    normalized_name = _normalize_name(project_name)
    for source_root in (root / "src", root):
        if not source_root.is_dir():
            continue
        for candidate in source_root.iterdir():
            if candidate.is_dir() and _normalize_name(candidate.name) == normalized_name:
                return candidate
    return None


def _resolve_python_module(root: Path, module: str) -> Path | None:
    module_path = Path(*module.split("."))
    for source_root in (root / "src", root):
        for candidate in (source_root / module_path.with_suffix(".py"), source_root / module_path / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def _find_files(root: Path, filename: str):
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name.lower() not in WALK_IGNORED_DIRS]
        if filename in filenames:
            yield Path(current) / filename


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _manifest_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _manifest_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _manifest_strings(item)


def _is_under(path: str, root: str) -> bool:
    return not root or path == root or path.startswith(f"{root}/")


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]", "", value.lower())


def _python_dependencies(
    relative_path: str,
    content: str,
    known_paths: set[str],
) -> tuple[set[str], set[str]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set(), set()

    dependencies: set[str] = set()
    current_parent = Path(relative_path).parent
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = current_parent
                for _ in range(node.level - 1):
                    base = base.parent
                modules = [node.module] if node.module else [alias.name for alias in node.names]
                for module in modules:
                    if module:
                        dependency = _resolve_known_module(base / Path(*module.split(".")), known_paths)
                        if dependency:
                            dependencies.add(dependency)
            elif node.module:
                dependency = _resolve_absolute_module(node.module, known_paths)
                if dependency:
                    dependencies.add(dependency)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                dependency = _resolve_absolute_module(alias.name, known_paths)
                if dependency:
                    dependencies.add(dependency)
    registered_dependencies = _python_registered_module_dependencies(relative_path, tree, known_paths)
    dependencies.update(registered_dependencies)
    return dependencies, registered_dependencies


def _python_registered_module_dependencies(
    relative_path: str,
    tree: ast.Module,
    known_paths: set[str],
) -> set[str]:
    parts = Path(relative_path).parts
    package_index = 1 if parts and parts[0] == "src" else 0
    if len(parts) <= package_index:
        return set()
    package_root = Path(*parts[: package_index + 1])
    dependencies: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        target_names = [target.id.lower() for target in targets if isinstance(target, ast.Name)]
        if value is None or not any("plugin" in name or "module" in name for name in target_names):
            continue
        for item in ast.walk(value):
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                continue
            module = item.value
            if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module):
                continue
            dependency = _resolve_absolute_module(module, known_paths)
            if dependency is None:
                dependency = _resolve_known_module(package_root / Path(*module.split(".")), known_paths)
            if dependency:
                dependencies.add(dependency)
    return dependencies


def _python_definition_count(content: str) -> int:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return 0
    return sum(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in tree.body
    )


def _javascript_dependencies(relative_path: str, content: str, known_paths: set[str]) -> set[str]:
    dependencies: set[str] = set()
    patterns = (
        r"(?ms)^\s*(?!import\s+type\b|export\s+type\b)(?:import|export)\b.*?\bfrom\s*[\"'](\.[^\"']+)[\"']",
        r"(?m)^\s*import\s*[\"'](\.[^\"']+)[\"']",
    )
    for pattern in patterns:
        for specifier in re.findall(pattern, content):
            dependency = _resolve_javascript_path(Path(relative_path).parent, specifier, known_paths)
            if dependency:
                dependencies.add(dependency)
    return dependencies


def _is_typescript_type_only(content: str) -> bool:
    has_type_declaration = bool(re.search(r"\b(?:interface|type|declare)\b", content))
    has_runtime_declaration = bool(re.search(r"\b(?:const|let|var|function|class|enum)\b", content))
    has_runtime_reexport = bool(
        re.search(r"(?m)^\s*export\s+(?!type\b)(?:\*\s+from|\{[^}]+\}\s+from)", content)
    )
    return has_type_declaration and not has_runtime_declaration and not has_runtime_reexport


def _resolve_absolute_module(module: str, known_paths: set[str]) -> str | None:
    module_path = Path(*module.split("."))
    for base in (Path("src"), Path()):
        dependency = _resolve_known_module(base / module_path, known_paths)
        if dependency:
            return dependency
    return None


def _resolve_known_module(module_path: Path, known_paths: set[str]) -> str | None:
    for candidate in (module_path.with_suffix(".py"), module_path / "__init__.py"):
        path = candidate.as_posix()
        if path in known_paths:
            return path
    return None


def _resolve_javascript_path(parent: Path, specifier: str, known_paths: set[str]) -> str | None:
    target = parent / specifier.split("?", 1)[0]
    candidates = [target]
    if target.suffix.lower() in {".js", ".mjs", ".cjs"}:
        candidates.append(target.with_suffix(""))
    for candidate in candidates:
        path = candidate.as_posix()
        if path in known_paths:
            return path
        for extension in CODE_EXTENSIONS[1:]:
            file_path = f"{path}{extension}"
            if file_path in known_paths:
                return file_path
            index_path = f"{path}/index{extension}"
            if index_path in known_paths:
                return index_path
    return None
