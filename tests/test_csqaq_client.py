from unittest.mock import MagicMock

import requests

from sequoia_x.csqaq.client import CSQAQClient


def test_rank_list_request_uses_expected_path_and_headers() -> None:
    client = CSQAQClient(api_token="token-123", timeout=9.0, min_interval_seconds=0)
    client.session.request = MagicMock(
        return_value=MagicMock(
            json=lambda: {"code": 200, "data": {"data": []}},
            raise_for_status=lambda: None,
        )
    )

    client.get_rank_list(
        page_index=1,
        page_size=15,
        filters={"排序": ["价格_售价减求购价(百分比)_升序(BUFF)"]},
    )

    call = client.session.request.call_args
    assert call.kwargs["method"] == "POST"
    assert call.kwargs["url"].endswith("/info/get_rank_list")
    assert call.kwargs["json"]["page_size"] == 15
    assert client.session.headers["ApiToken"] == "token-123"


def test_client_retries_on_429(monkeypatch) -> None:
    client = CSQAQClient(
        api_token="token-123",
        timeout=9.0,
        min_interval_seconds=0,
        retry_count=2,
    )
    first = MagicMock(
        status_code=429,
        headers={},
        raise_for_status=MagicMock(side_effect=None),
        json=lambda: {"code": 429, "msg": "too many requests"},
    )
    second = MagicMock(
        status_code=200,
        headers={},
        raise_for_status=MagicMock(side_effect=None),
        json=lambda: {"code": 200, "data": {"data": []}},
    )
    client.session.request = MagicMock(side_effect=[first, second])
    monkeypatch.setattr("time.sleep", lambda _: None)

    payload = client.get_rank_list(page_index=1, page_size=10, filters={})

    assert payload["code"] == 200
    assert client.session.request.call_count == 2


def test_client_retries_on_502(monkeypatch) -> None:
    client = CSQAQClient(
        api_token="token-123",
        timeout=9.0,
        min_interval_seconds=0,
        retry_count=2,
    )
    first = MagicMock(
        status_code=502,
        headers={},
        raise_for_status=MagicMock(side_effect=requests.HTTPError("502 Server Error: Bad Gateway")),
        json=lambda: {"code": 502, "msg": "bad gateway"},
    )
    second = MagicMock(
        status_code=200,
        headers={},
        raise_for_status=MagicMock(side_effect=None),
        json=lambda: {"code": 200, "data": {"data": []}},
    )
    client.session.request = MagicMock(side_effect=[first, second])
    monkeypatch.setattr("time.sleep", lambda _: None)

    payload = client.get_rank_list(page_index=1, page_size=10, filters={})

    assert payload["code"] == 200
    assert client.session.request.call_count == 2


def test_client_retries_on_500(monkeypatch) -> None:
    client = CSQAQClient(
        api_token="token-123",
        timeout=9.0,
        min_interval_seconds=0,
        retry_count=2,
    )
    first = MagicMock(
        status_code=500,
        headers={},
        raise_for_status=MagicMock(side_effect=requests.HTTPError("500 Server Error: Internal Server Error")),
        json=lambda: {"code": 500, "msg": "internal server error"},
    )
    second = MagicMock(
        status_code=200,
        headers={},
        raise_for_status=MagicMock(side_effect=None),
        json=lambda: {"code": 200, "data": {"data": []}},
    )
    client.session.request = MagicMock(side_effect=[first, second])
    monkeypatch.setattr("time.sleep", lambda _: None)

    payload = client.get_good(23847)

    assert payload["code"] == 200
    assert client.session.request.call_count == 2
