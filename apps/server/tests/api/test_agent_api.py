from typing import Any

import allure
import pytest

from tests.api.clients.agent_client import AgentClient
from tests.api.utils.yaml_loader import load_yaml_cases


pytestmark = pytest.mark.api


@allure.feature("分析任务")
@allure.story("不存在的任务")
@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["id"]) for case in load_yaml_cases("agent_jobs.yaml")],
)
def test_missing_analysis_job(agent_client: AgentClient, case: dict[str, Any]) -> None:
    operation = case["operation"]
    job_id = case["job_id"]
    if operation == "get":
        response = agent_client.get_job(job_id)
    elif operation == "events":
        response = agent_client.get_events(job_id)
    else:
        response = agent_client.cancel_job(job_id)

    expected = case["expected"]
    assert response.status_code == expected["status_code"]
    assert response.json()["error"]["code"] == expected["error_code"]
