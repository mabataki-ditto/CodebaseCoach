import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "evals" / "file-selection.golden.json"


def test_file_selection_golden_covers_publishable_packages_within_top_12_budget() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    repositories = {item["repo_url"]: item for item in golden["repositories"]}

    assert {
        "https://github.com/vuejs/router",
        "https://github.com/encode/httpx",
        "https://github.com/pytest-dev/pytest",
    } <= repositories.keys()

    pinia_core = _paths(repositories["https://github.com/vuejs/pinia"]["expected_core_files"])
    assert "packages/testing/src/testing.ts" in pinia_core
    assert "packages/nuxt/src/module.ts" in pinia_core
    assert "packages/nuxt/src/runtime/plugin.vue3.ts" in pinia_core

    smolagents_core = _paths(repositories["https://github.com/huggingface/smolagents"]["expected_core_files"])
    assert "src/smolagents/vision_web_browser.py" in smolagents_core
    assert "src/smolagents/prompts/structured_code_agent.yaml" not in smolagents_core

    for repository in repositories.values():
        entry_paths = _paths(repository["expected_entry_files"])
        core_paths = _paths(repository["expected_core_files"])
        assert len(entry_paths | core_paths) <= 12


def _paths(items: list[dict[str, str]]) -> set[str]:
    return {item["path"] for item in items}
