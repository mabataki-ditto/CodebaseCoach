from typing import Any

from tests.api.clients.api_client import ApiClient


class RepoClient:
    def __init__(self, api_client: ApiClient) -> None:
        self._api_client = api_client

    def parse_repo(self, repo_url: str) -> Any:
        return self._api_client.post("/api/repo/parse", json={"repo_url": repo_url})

    def scan_repo(self, repo_url: str) -> Any:
        return self._api_client.post("/api/repo/scan", json={"repo_url": repo_url})
