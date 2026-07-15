import allure
import pytest

from tests.api.clients.api_client import ApiClient


pytestmark = [pytest.mark.api, pytest.mark.smoke]


@allure.feature("系统状态")
@allure.story("健康检查")
def test_health(api_client: ApiClient) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "codebase-coach-server",
        "version": "0.1.0",
    }
