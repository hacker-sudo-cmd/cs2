"""Thin client around the CSQAQ open API."""

from __future__ import annotations

import time
from typing import Any, Optional

import requests


class CSQAQAPIError(RuntimeError):
    """Raised when the CSQAQ API returns an error response."""


class CSQAQClient:
    base_url = "https://api.csqaq.com/api/v1"
    retryable_status_codes = frozenset({429, 500, 502, 503})

    def __init__(
        self,
        api_token: str,
        timeout: float = 15.0,
        *,
        min_interval_seconds: float = 1.1,
        retry_count: int = 3,
    ) -> None:
        self.timeout = timeout
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.retry_count = max(1, retry_count)
        self._last_request_at = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "ApiToken": api_token,
                "Content-Type": "application/json",
            }
        )

    def _wait_for_rate_limit(self) -> None:
        if self.min_interval_seconds <= 0:
            return

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)

    @staticmethod
    def _retry_delay(response: Optional[requests.Response], attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(1.0, float(retry_after))
                except ValueError:
                    pass
        return min(8.0, float(attempt))

    @staticmethod
    def _format_response_error(
        response: Optional[requests.Response],
        *,
        payload: Optional[dict[str, Any]] = None,
        fallback: Optional[str] = None,
    ) -> str:
        parts: list[str] = []

        if response is not None:
            parts.append(f"HTTP {response.status_code}")

        code = payload.get("code") if payload else None
        if code is not None:
            parts.append(f"API code {code}")

        message = ""
        if payload:
            message = str(payload.get("msg") or "").strip()
        if not message and fallback:
            message = fallback.strip()
        if message:
            parts.append(message)

        if payload:
            data = payload.get("data")
            if data not in (None, "", [], {}):
                parts.append(f"data={data}")
        elif response is not None:
            body = response.text.strip()
            if body:
                parts.append(f"body={body[:300]}")

        return " | ".join(parts) if parts else "Unknown CSQAQ API error"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retry_count + 1):
            self._wait_for_rate_limit()
            response: Optional[requests.Response] = None

            try:
                response = self.session.request(
                    method=method,
                    url=f"{self.base_url}{path}",
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
                self._last_request_at = time.monotonic()

                if response.status_code in self.retryable_status_codes and attempt < self.retry_count:
                    time.sleep(self._retry_delay(response, attempt))
                    continue

                payload = response.json()
                if response.status_code >= 400:
                    error = CSQAQAPIError(
                        self._format_response_error(
                            response,
                            payload=payload,
                            fallback=response.reason,
                        )
                    )
                    if attempt < self.retry_count and response.status_code in self.retryable_status_codes:
                        last_error = error
                        time.sleep(self._retry_delay(response, attempt))
                        continue
                    raise error
            except ValueError as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self._retry_delay(response, attempt))
                    continue
                raise CSQAQAPIError(
                    self._format_response_error(
                        response,
                        fallback=f"Invalid JSON response: {exc}",
                    )
                ) from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self._retry_delay(response, attempt))
                    continue
                raise CSQAQAPIError(
                    self._format_response_error(response, fallback=str(exc))
                ) from exc

            if payload.get("code") == 200:
                return payload
            if payload.get("code") == 429 and attempt < self.retry_count:
                time.sleep(self._retry_delay(response, attempt))
                continue
            raise CSQAQAPIError(
                self._format_response_error(response, payload=payload)
            )

        raise CSQAQAPIError(str(last_error) if last_error else "Unknown CSQAQ API error")


    def bind_local_ip(self) -> dict[str, Any]:
        return self._request("POST", "/sys/bind_local_ip")

    def get_rank_list(
        self,
        *,
        page_index: int,
        page_size: int,
        filters: dict[str, Any],
        show_recently_price: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/info/get_rank_list",
            json_body={
                "page_index": page_index,
                "page_size": page_size,
                "show_recently_price": show_recently_price,
                "filter": filters,
            },
        )

    def get_page_list(
        self,
        *,
        page_index: int,
        page_size: int,
        search: str = "",
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "page_index": page_index,
            "page_size": page_size,
            "search": search,
        }
        if filters:
            body["filter"] = filters
        return self._request("POST", "/info/get_page_list", json_body=body)

    def get_good(self, good_id: int) -> dict[str, Any]:
        return self._request("GET", "/info/good", params={"id": good_id})
