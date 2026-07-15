import os
from typing import Any

import allure
import pytest

from tests.api.clients.agent_client import AgentClient
from tests.api.utils.yaml_loader import load_yaml_cases


def _case_params() -> list[Any]:
    params = []
    for case in load_yaml_cases("agent_llm.yaml"):
        marks = [getattr(pytest.mark, name) for name in case.get("marks", [])]
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


@allure.feature("分析任务")
@allure.story("真实大模型分析")
@pytest.mark.api
@pytest.mark.parametrize("case", _case_params())
def test_real_llm_analysis(agent_client: AgentClient, case: dict[str, Any]) -> None:
    response = agent_client.analyze_repo(
        case["request"]["repo_url"],
        timeout=float(os.getenv("API_LLM_TIMEOUT", "600")),
    )
    expected = case["expected"]

    assert response.status_code == expected["status_code"]
    body = response.json()
    assert body["mock_mode"] is expected["mock_mode"]
    assert body["documents"]
    assert body["core_files"]
