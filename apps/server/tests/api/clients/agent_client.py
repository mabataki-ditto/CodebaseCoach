from typing import Any

from tests.api.clients.api_client import ApiClient


class AgentClient:
    def __init__(self, api_client: ApiClient) -> None:
        self._api_client = api_client

    def create_job(self, repo_url: str) -> Any:
        return self._api_client.post("/api/agent/analyze/jobs", json={"repo_url": repo_url})

    def analyze_repo(self, repo_url: str, *, timeout: float) -> Any:
        return self._api_client.post(
            "/api/agent/analyze",
            json={"repo_url": repo_url},
            timeout=timeout,
        )

    def get_job(self, job_id: str) -> Any:
        return self._api_client.get(f"/api/agent/analyze/jobs/{job_id}")

    def get_events(self, job_id: str, after: int = 0) -> Any:
        return self._api_client.get(
            f"/api/agent/analyze/jobs/{job_id}/events",
            params={"after": after},
            stream=True,
        )

    def cancel_job(self, job_id: str) -> Any:
        return self._api_client.post(f"/api/agent/analyze/jobs/{job_id}/cancel")
