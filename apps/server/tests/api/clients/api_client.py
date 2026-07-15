import json
import logging
from time import perf_counter
from typing import Any

import allure


logger = logging.getLogger(__name__)


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10,
        session: Any | None = None,
    ) -> None:
        if session is None:
            import requests

            session = requests.Session()
            session.trust_env = False
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", self._timeout)
        with allure.step(f"{method.upper()} {path}"):
            self._attach_request(kwargs)
            started_at = perf_counter()
            response = self._session.request(method, url, **kwargs)
            self._attach_response(response, streaming=kwargs.get("stream", False))
        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "%s %s -> %s (%.1f ms)",
            method.upper(),
            path,
            response.status_code,
            duration_ms,
        )
        return response

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self._session.close()

    @staticmethod
    def _attach_request(kwargs: dict[str, Any]) -> None:
        request_data = {key: kwargs[key] for key in ("params", "json") if key in kwargs}
        if request_data:
            allure.attach(
                json.dumps(request_data, ensure_ascii=False, indent=2, default=str),
                name="request",
                attachment_type=allure.attachment_type.JSON,
            )

    @staticmethod
    def _attach_response(response: Any, *, streaming: bool) -> None:
        body = "<streaming response body not consumed>" if streaming else response.text[:20_000]
        allure.attach(
            f"status: {response.status_code}\n\n{body}",
            name="response",
            attachment_type=allure.attachment_type.TEXT,
        )
