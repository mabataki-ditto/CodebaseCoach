import json
from pathlib import Path

import pytest

from app.services.file_selector_service import select_core_files, select_core_files_with_metrics

pytestmark = pytest.mark.unit


def test_python_manifest_entries_are_selected_without_metadata_or_examples(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        """
[project]
name = "Demo"

[project.scripts]
demo = "demo.cli:main"
""".strip(),
    )
    _write(tmp_path / "README.md", "demo")
    _write(tmp_path / "src/demo/__init__.py", "from .app import DemoApp")
    _write(tmp_path / "src/demo/__main__.py", "from .cli import main\nmain()")
    _write(tmp_path / "src/demo/cli.py", "from .app import DemoApp\ndef main(): return DemoApp()")
    _write(tmp_path / "src/demo/app.py", "from .service import Service\nclass DemoApp: pass")
    _write(tmp_path / "src/demo/service.py", "class Service: pass")
    _write(tmp_path / "examples/main.py", "print('example')")
    for index in range(15):
        _write(tmp_path / f"src/demo/a{index:02d}.py", f"VALUE = {index}")

    selected, metrics = select_core_files_with_metrics(tmp_path)
    paths = [file.path for file in selected]
    by_path = {file.path: file for file in selected}

    assert {"src/demo/__init__.py", "src/demo/__main__.py", "src/demo/cli.py"} <= set(paths)
    assert "项目声明" in by_path["src/demo/__init__.py"].reason
    assert "项目声明" in by_path["src/demo/__main__.py"].reason
    assert "src/demo/app.py" in paths
    assert "README.md" not in paths
    assert "pyproject.toml" not in paths
    assert "examples/main.py" not in paths
    assert "examples/main.py" not in {item.path for item in metrics.candidates}


def test_python_entry_dependency_chain_outranks_unreferenced_source(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"')
    _write(tmp_path / "src/demo/__init__.py", "from .api import create_app")
    _write(tmp_path / "src/demo/api.py", "from .engine import Engine\ndef create_app(): return Engine()")
    _write(tmp_path / "src/demo/engine.py", "from .state import State\nclass Engine: pass")
    _write(tmp_path / "src/demo/state.py", "class State: pass")
    for index in range(15):
        _write(tmp_path / f"src/demo/a{index:02d}.py", f"VALUE = {index}")

    paths = [file.path for file in select_core_files(tmp_path)]

    assert {"src/demo/api.py", "src/demo/engine.py", "src/demo/state.py"} <= set(paths)


def test_python_structural_module_outranks_shallow_signal_module(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"')
    _write(tmp_path / "src/demo/__init__.py", "from .app import App\nfrom .helpers import helper\nfrom .signals import signal")
    _write(tmp_path / "src/demo/app.py", "from .sessions import Session\nclass App: pass")
    _write(tmp_path / "src/demo/helpers.py", "def helper(): return True")
    _write(tmp_path / "src/demo/signals.py", "signal = object()")
    _write(tmp_path / "src/demo/sessions.py", "class Session: pass\nclass SessionStore: pass")

    paths = [file.path for file in select_core_files(tmp_path, max_files=4)]

    assert "src/demo/sessions.py" in paths
    assert "src/demo/signals.py" not in paths


def test_python_top_level_functions_count_as_structural_definitions(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"')
    _write(tmp_path / "src/demo/__init__.py", "from .api import get, post\nfrom .noise import Noise")
    _write(tmp_path / "src/demo/api.py", "def get(): return True\ndef post(): return True")
    _write(tmp_path / "src/demo/noise.py", "class Noise: pass")

    paths = [file.path for file in select_core_files(tmp_path, max_files=2)]

    assert "src/demo/api.py" in paths
    assert "src/demo/noise.py" not in paths


def test_python_plugin_registry_connects_dynamically_loaded_core_modules(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "demo"\n\n[project.scripts]\ndemo = "demo.config:main"',
    )
    _write(tmp_path / "src/demo/__init__.py", "from .config import main")
    _write(tmp_path / "src/demo/__main__.py", "from .config import main\nmain()")
    _write(
        tmp_path / "src/demo/config.py",
        """
from .noise00 import Noise0
from .noise01 import Noise1
from .noise02 import Noise2
from .noise03 import Noise3
from .noise04 import Noise4

default_plugins = ("runner", "python", "terminal", "assertion")

def main(): return 0
""".strip(),
    )
    _write(tmp_path / "src/demo/runner.py", "class Runner: pass")
    _write(tmp_path / "src/demo/python.py", "class PythonCollector: pass")
    _write(tmp_path / "src/demo/terminal.py", "class TerminalReporter: pass")
    _write(tmp_path / "src/demo/assertion/__init__.py", "from .rewrite import AssertionRewriter")
    _write(tmp_path / "src/demo/assertion/rewrite.py", "class AssertionRewriter: pass")
    for index in range(12):
        _write(tmp_path / f"src/demo/noise{index:02d}.py", f"class Noise{index}: pass")

    paths = [file.path for file in select_core_files(tmp_path, max_files=9)]

    assert {
        "src/demo/runner.py",
        "src/demo/python.py",
        "src/demo/terminal.py",
        "src/demo/assertion/__init__.py",
        "src/demo/assertion/rewrite.py",
    } <= set(paths)


def test_typescript_workspaces_select_publishable_package_entries(tmp_path: Path) -> None:
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "workspace", "private": True, "workspaces": ["packages/*"]}),
    )
    _write(tmp_path / "README.md", "workspace")
    _write(tmp_path / "packages/main/package.json", json.dumps({"name": "main", "exports": {".": "./dist/main.mjs"}}))
    _write(tmp_path / "packages/main/tsdown.config.ts", "export default { entry: ['./src/index.ts'] }")
    _write(tmp_path / "packages/main/src/main.ts", "import { helper } from './helper'\nexport const createMain = helper")
    _write(tmp_path / "packages/main/src/helper.ts", "export const helper = () => true")
    _write(tmp_path / "packages/main/src/zengine.ts", "import { state } from './zstate'\nexport const engine = state")
    _write(tmp_path / "packages/main/src/zstate.ts", "export const state = true")
    _write(tmp_path / "packages/main/src/index.ts", "export { createMain } from './main'\nexport { engine } from './zengine'")
    _write(tmp_path / "packages/testing/package.json", json.dumps({"name": "@demo/testing", "exports": {".": "./dist/index.mjs"}}))
    _write(tmp_path / "packages/testing/src/index.ts", "export { createTesting } from './testing'")
    _write(tmp_path / "packages/testing/src/testing.ts", "export const createTesting = () => true")
    _write(tmp_path / "packages/docs/package.json", json.dumps({"name": "@demo/docs", "private": True}))
    _write(tmp_path / "packages/docs/src/index.ts", "export const docs = true")
    for index in range(15):
        _write(tmp_path / f"packages/main/src/noise{index:02d}.ts", f"export const value{index} = {index}")

    paths = [file.path for file in select_core_files(tmp_path)]

    assert "packages/main/src/index.ts" in paths
    assert "packages/testing/src/index.ts" in paths
    assert "packages/main/src/main.ts" in paths
    assert "packages/main/src/zengine.ts" in paths
    assert "packages/main/src/zstate.ts" in paths
    assert not any(path.endswith("package.json") for path in paths)
    assert not any(path.startswith("packages/docs/") for path in paths)


def test_typescript_auxiliary_build_entries_do_not_exhaust_core_budget(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", json.dumps({"name": "demo"}))
    _write(
        tmp_path / "tsdown.config.ts",
        """
export default {
  entry: {
    demo: './src/index.ts',
    experimental: './src/experimental/index.ts',
    unplugin: './src/unplugin/index.ts',
    vite: './src/unplugin/vite.ts',
    webpack: './src/unplugin/webpack.ts',
    rollup: './src/unplugin/rollup.ts',
    rolldown: './src/unplugin/rolldown.ts',
    esbuild: './src/unplugin/esbuild.ts',
    rspack: './src/unplugin/rspack.ts',
    farm: './src/unplugin/farm.ts',
    parcel: './src/unplugin/parcel.ts',
    metro: './src/unplugin/metro.ts',
    volar: './src/volar/sfc-route-blocks.ts',
  },
}
""".strip(),
    )
    _write(
        tmp_path / "src/index.ts",
        "\n".join(
            [
                "export { router } from './router'",
                "export { matcher } from './matcher'",
                "export { history } from './history'",
                *(f"export {{ core{index} }} from './runtime/core{index}'" for index in range(5)),
            ]
        ),
    )
    _write(tmp_path / "src/router.ts", "import { matcher } from './matcher'\nexport const router = matcher")
    _write(tmp_path / "src/matcher.ts", "import { history } from './history'\nexport const matcher = history")
    _write(tmp_path / "src/history.ts", "export const history = true")
    for index in range(5):
        _write(tmp_path / f"src/runtime/core{index}.ts", f"export class Core{index} {{}}")
    _write(
        tmp_path / "src/experimental/index.ts",
        "\n".join(f"export {{ feature{index} }} from './feature{index}'" for index in range(5)),
    )
    _write(
        tmp_path / "src/unplugin/index.ts",
        "\n".join(f"export {{ context{index} }} from './core/context{index}'" for index in range(5)),
    )
    for index in range(5):
        _write(tmp_path / f"src/experimental/feature{index}.ts", f"export class Feature{index} {{}}")
        _write(tmp_path / f"src/unplugin/core/context{index}.ts", f"export class Context{index} {{}}")
    for adapter in ("vite", "webpack", "rollup", "rolldown", "esbuild", "rspack", "farm", "parcel", "metro"):
        _write(tmp_path / f"src/unplugin/{adapter}.ts", f"export const {adapter} = true")
    _write(tmp_path / "src/volar/sfc-route-blocks.ts", "export const volar = true")

    paths = [file.path for file in select_core_files(tmp_path)]

    assert {
        "src/index.ts",
        "src/experimental/index.ts",
        "src/unplugin/index.ts",
        "src/router.ts",
        "src/matcher.ts",
        "src/history.ts",
        *(f"src/runtime/core{index}.ts" for index in range(5)),
    } <= set(paths)
    assert "src/unplugin/vite.ts" not in paths


def test_typescript_type_only_module_does_not_displace_runtime_dependency(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", json.dumps({"name": "demo"}))
    _write(
        tmp_path / "src/index.ts",
        "export * from './globalExtensions'\nexport { runtime } from './runtime'",
    )
    _write(tmp_path / "src/globalExtensions.ts", "declare module 'demo' { interface Options {} }\nexport {}")
    _write(tmp_path / "src/runtime.ts", "import { engine } from './zengine'\nexport const runtime = engine")
    _write(tmp_path / "src/zengine.ts", "export const engine = true")

    paths = [file.path for file in select_core_files(tmp_path, max_files=3)]

    assert "src/runtime.ts" in paths
    assert "src/zengine.ts" in paths
    assert "src/globalExtensions.ts" not in paths


def test_auxiliary_helper_does_not_displace_deeper_runtime_module(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", json.dumps({"name": "demo"}))
    _write(
        tmp_path / "src/index.ts",
        "export { mapState } from './mapHelpers'\nexport { store } from './store'",
    )
    _write(tmp_path / "src/mapHelpers.ts", "export const mapState = () => true")
    _write(tmp_path / "src/store.ts", "import { subscribe } from './subscriptions'\nexport const store = subscribe")
    _write(tmp_path / "src/subscriptions.ts", "export const subscribe = () => true")

    paths = [file.path for file in select_core_files(tmp_path, max_files=3)]

    assert "src/store.ts" in paths
    assert "src/subscriptions.ts" in paths
    assert "src/mapHelpers.ts" not in paths


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
