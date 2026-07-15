from typing import Any

import allure
import pytest

from tests.api.clients.history_client import HistoryClient
from tests.api.utils.yaml_loader import load_yaml_cases


pytestmark = pytest.mark.api


@allure.feature("历史记录")
@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["id"]) for case in load_yaml_cases("history.yaml")],
)
def test_history(history_client: HistoryClient, case: dict[str, Any]) -> None:
    if case["operation"] == "list":
        response = history_client.list_history()
    elif case["operation"] == "delete":
        response = history_client.delete_history(case["history_id"])
    else:
        raise AssertionError(f"不支持的历史记录操作: {case['operation']}")

    expected = case["expected"]
    assert response.status_code == expected["status_code"]
    if response.status_code == 200:
        assert isinstance(response.json()["records"], list)
    else:
        assert response.json()["error"]["code"] == expected["error_code"]
