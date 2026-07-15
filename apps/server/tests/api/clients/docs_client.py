from typing import Any

from tests.api.clients.api_client import ApiClient


class DocsClient:
    def __init__(self, api_client: ApiClient) -> None:
        self._api_client = api_client

    def get_docs(self, history_id: str) -> Any:
        return self._api_client.get(f"/api/docs/{history_id}")
