from pathlib import Path
from typing import Any

import yaml


CASES_DIR = Path(__file__).resolve().parents[1] / "cases"


def load_yaml_cases(path: str | Path) -> list[dict[str, Any]]:
    case_path = Path(path)
    if not case_path.is_absolute():
        case_path = CASES_DIR / case_path

    data = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("YAML 顶层必须是列表")

    seen_ids: set[str] = set()
    for case in data:
        if not isinstance(case, dict):
            raise ValueError("每条用例必须是对象")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("每条用例必须包含非空 id")
        if case_id in seen_ids:
            raise ValueError("用例 id 不能重复")
        seen_ids.add(case_id)

    return data
