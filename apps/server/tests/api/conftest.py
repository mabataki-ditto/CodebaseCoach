import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv

from tests.api.clients.agent_client import AgentClient
from tests.api.clients.api_client import ApiClient
from tests.api.clients.docs_client import DocsClient
from tests.api.clients.history_client import HistoryClient
from tests.api.clients.repo_client import RepoClient


load_dotenv(".env.api-test", override=False)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-api",
        action="store_true",
        default=False,
        help="运行需要已启动 HTTP 服务的接口自动化测试",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-api"):
        return
    skip_api = pytest.mark.skip(reason="需要 --run-api 并启动后端服务")
    for item in items:
        if item.get_closest_marker("api") is not None:
            item.add_marker(skip_api)


@pytest.fixture(scope="session")
def api_client() -> Generator[ApiClient, None, None]:
    client = ApiClient(
        base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        timeout=float(os.getenv("API_TIMEOUT", "10")),
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def repo_client(api_client: ApiClient) -> RepoClient:
    return RepoClient(api_client)


@pytest.fixture(scope="session")
def agent_client(api_client: ApiClient) -> AgentClient:
    return AgentClient(api_client)


@pytest.fixture(scope="session")
def history_client(api_client: ApiClient) -> HistoryClient:
    return HistoryClient(api_client)


@pytest.fixture(scope="session")
def docs_client(api_client: ApiClient) -> DocsClient:
    return DocsClient(api_client)
