from typing import Any

from tests.api.clients.api_client import ApiClient


class HistoryClient:
    def __init__(self, api_client: ApiClient) -> None:
        self._api_client = api_client

    def list_history(self) -> Any:
        return self._api_client.get("/api/history")

    def delete_history(self, history_id: str) -> Any:
        return self._api_client.delete(f"/api/history/{history_id}")
