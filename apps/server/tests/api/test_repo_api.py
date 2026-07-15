from typing import Any

import allure
import pytest

from tests.api.clients.repo_client import RepoClient
from tests.api.utils.yaml_loader import load_yaml_cases


pytestmark = pytest.mark.api


def _case_params(filename: str) -> list[Any]:
    params = []
    for case in load_yaml_cases(filename):
        marks = [getattr(pytest.mark, name) for name in case.get("marks", [])]
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


def _assert_error_code(response: Any, expected: dict[str, Any]) -> None:
    if "error_code" in expected:
        assert response.json()["error"]["code"] == expected["error_code"]


@allure.feature("仓库")
@allure.story("解析仓库地址")
@pytest.mark.parametrize("case", _case_params("repo_parse.yaml"))
def test_parse_repo(repo_client: RepoClient, case: dict[str, Any]) -> None:
    response = repo_client.parse_repo(case["request"]["repo_url"])
    expected = case["expected"]

    assert response.status_code == expected["status_code"]
    if "body" in expected:
        assert response.json() == expected["body"]
    _assert_error_code(response, expected)


@allure.feature("仓库")
@allure.story("扫描仓库")
@pytest.mark.parametrize("case", _case_params("repo_scan.yaml"))
def test_scan_repo(repo_client: RepoClient, case: dict[str, Any]) -> None:
    response = repo_client.scan_repo(case["request"]["repo_url"])
    expected = case["expected"]

    assert response.status_code == expected["status_code"]
    if response.status_code == 200:
        body = response.json()
        assert body["owner"] == expected["owner"]
        assert body["repo"] == expected["repo"]
        assert isinstance(body["file_tree"], list)
        assert isinstance(body["basic_files"], list)
    _assert_error_code(response, expected)
