from typing import Any

import allure
import pytest

from tests.api.clients.docs_client import DocsClient
from tests.api.utils.yaml_loader import load_yaml_cases


pytestmark = pytest.mark.api


@allure.feature("分析文档")
@allure.story("读取文档")
@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case["id"]) for case in load_yaml_cases("docs.yaml")],
)
def test_missing_docs(docs_client: DocsClient, case: dict[str, Any]) -> None:
    response = docs_client.get_docs(case["history_id"])
    expected = case["expected"]

    assert response.status_code == expected["status_code"]
    assert response.json()["error"]["code"] == expected["error_code"]
