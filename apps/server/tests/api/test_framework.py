import logging
from datetime import timedelta
from pathlib import Path

import pytest

from tests.api.clients.agent_client import AgentClient
from tests.api.clients.api_client import ApiClient
from tests.api.clients.docs_client import DocsClient
from tests.api.clients.history_client import HistoryClient
from tests.api.clients.repo_client import RepoClient
from tests.api.utils.yaml_loader import load_yaml_cases


pytestmark = pytest.mark.unit


class FakeResponse:
    status_code = 200
    text = '{"ok": true}'
    elapsed = timedelta(milliseconds=12)


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return FakeResponse()

    def close(self) -> None:
        self.closed = True


class CapturingApiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, path: str, **kwargs) -> FakeResponse:
        self.calls.append(("GET", path, kwargs))
        return FakeResponse()

    def post(self, path: str, **kwargs) -> FakeResponse:
        self.calls.append(("POST", path, kwargs))
        return FakeResponse()

    def delete(self, path: str, **kwargs) -> FakeResponse:
        self.calls.append(("DELETE", path, kwargs))
        return FakeResponse()


def test_load_yaml_cases_returns_valid_case_list(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(
        "- id: valid\n  request:\n    repo_url: https://github.com/vuejs/core\n",
        encoding="utf-8",
    )

    cases = load_yaml_cases(path)

    assert cases == [{"id": "valid", "request": {"repo_url": "https://github.com/vuejs/core"}}]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("id: not-a-list\n", "顶层必须是列表"),
        ("- request: {}\n", "必须包含非空 id"),
        ("- id: duplicate\n- id: duplicate\n", "id 不能重复"),
    ],
)
def test_load_yaml_cases_rejects_invalid_structure(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_yaml_cases(path)


def test_api_client_builds_url_and_applies_default_timeout() -> None:
    session = FakeSession()
    client = ApiClient("http://127.0.0.1:8000/", timeout=15, session=session)

    response = client.post("/api/repo/parse", json={"repo_url": "owner/repo"})

    assert response.status_code == 200
    assert session.calls == [
        (
            "POST",
            "http://127.0.0.1:8000/api/repo/parse",
            {"json": {"repo_url": "owner/repo"}, "timeout": 15},
        )
    ]


def test_api_client_preserves_explicit_timeout_and_closes_session() -> None:
    session = FakeSession()
    client = ApiClient("http://127.0.0.1:8000", timeout=15, session=session)

    client.get("/health", timeout=2)
    client.close()

    assert session.calls[0][2]["timeout"] == 2
    assert session.closed


def test_api_client_default_session_ignores_environment_proxy() -> None:
    client = ApiClient("http://127.0.0.1:8000")

    assert client._session.trust_env is False
    client.close()


def test_api_client_logs_method_path_status_and_duration(caplog: pytest.LogCaptureFixture) -> None:
    client = ApiClient("http://127.0.0.1:8000", session=FakeSession())

    with caplog.at_level(logging.INFO):
        client.get("/health")

    assert "GET /health -> 200" in caplog.text


def test_repo_client_maps_repo_endpoints() -> None:
    api_client = CapturingApiClient()
    client = RepoClient(api_client)

    client.parse_repo("owner/repo")
    client.scan_repo("owner/repo")

    assert api_client.calls == [
        ("POST", "/api/repo/parse", {"json": {"repo_url": "owner/repo"}}),
        ("POST", "/api/repo/scan", {"json": {"repo_url": "owner/repo"}}),
    ]


def test_agent_client_maps_job_endpoints() -> None:
    api_client = CapturingApiClient()
    client = AgentClient(api_client)

    client.create_job("owner/repo")
    client.get_job("job-1")
    client.get_events("job-1", after=3)
    client.cancel_job("job-1")

    assert api_client.calls == [
        ("POST", "/api/agent/analyze/jobs", {"json": {"repo_url": "owner/repo"}}),
        ("GET", "/api/agent/analyze/jobs/job-1", {}),
        ("GET", "/api/agent/analyze/jobs/job-1/events", {"params": {"after": 3}, "stream": True}),
        ("POST", "/api/agent/analyze/jobs/job-1/cancel", {}),
    ]


def test_history_and_docs_clients_map_endpoints() -> None:
    api_client = CapturingApiClient()
    history = HistoryClient(api_client)
    docs = DocsClient(api_client)

    history.list_history()
    history.delete_history("history-1")
    docs.get_docs("history-1")

    assert api_client.calls == [
        ("GET", "/api/history", {}),
        ("DELETE", "/api/history/history-1", {}),
        ("GET", "/api/docs/history-1", {}),
    ]
