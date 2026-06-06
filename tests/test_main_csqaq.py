from __future__ import annotations

import main_csqaq


class _Settings:
    csqaq_api_token = "token"
    csqaq_request_timeout = 9.0
    csqaq_min_interval_seconds = 0.0
    csqaq_retry_count = 2
    csqaq_auto_bind_ip = False
    csqaq_feishu_webhook_url = None


def test_main_retries_full_run_once_on_502(monkeypatch, capsys) -> None:
    attempts = {"count": 0}
    rendered = {"goods": None}

    monkeypatch.setattr(main_csqaq, "CSQAQSettings", lambda: _Settings())
    monkeypatch.setattr(main_csqaq, "Console", lambda *args, **kwargs: type("ConsoleStub", (), {"print": lambda self, *a, **k: None})())
    monkeypatch.setattr(main_csqaq, "_render_scored_goods", lambda goods: rendered.__setitem__("goods", goods))
    monkeypatch.setattr(main_csqaq, "_render_listed_goods", lambda goods: rendered.__setitem__("goods", goods))
    monkeypatch.setattr(main_csqaq, "CSQAQFeishuNotifier", lambda *args, **kwargs: None)

    def fake_run_once(args, settings, request, progress_console):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise main_csqaq.CSQAQAPIError("502 Server Error: Bad Gateway")
        return []

    monkeypatch.setattr(main_csqaq, "_run_once", fake_run_once)
    monkeypatch.setattr(main_csqaq.sys, "argv", ["main_csqaq.py"])

    result = main_csqaq.main()

    assert result == 0
    assert attempts["count"] == 2
    assert rendered["goods"] == []
    assert capsys.readouterr().err == ""


def test_main_retries_full_run_once_on_500(monkeypatch, capsys) -> None:
    attempts = {"count": 0}
    rendered = {"goods": None}

    monkeypatch.setattr(main_csqaq, "CSQAQSettings", lambda: _Settings())
    monkeypatch.setattr(main_csqaq, "Console", lambda *args, **kwargs: type("ConsoleStub", (), {"print": lambda self, *a, **k: None})())
    monkeypatch.setattr(main_csqaq, "_render_scored_goods", lambda goods: rendered.__setitem__("goods", goods))
    monkeypatch.setattr(main_csqaq, "_render_listed_goods", lambda goods: rendered.__setitem__("goods", goods))
    monkeypatch.setattr(main_csqaq, "CSQAQFeishuNotifier", lambda *args, **kwargs: None)

    def fake_run_once(args, settings, request, progress_console):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise main_csqaq.CSQAQAPIError("500 Server Error: Internal Server Error")
        return []

    monkeypatch.setattr(main_csqaq, "_run_once", fake_run_once)
    monkeypatch.setattr(main_csqaq.sys, "argv", ["main_csqaq.py"])

    result = main_csqaq.main()

    assert result == 0
    assert attempts["count"] == 2
    assert rendered["goods"] == []
    assert capsys.readouterr().err == ""


def test_main_does_not_retry_non_502_errors(monkeypatch) -> None:
    attempts = {"count": 0}

    monkeypatch.setattr(main_csqaq, "CSQAQSettings", lambda: _Settings())
    monkeypatch.setattr(main_csqaq, "Console", lambda *args, **kwargs: type("ConsoleStub", (), {"print": lambda self, *a, **k: None})())

    def fake_run_once(args, settings, request, progress_console):
        attempts["count"] += 1
        raise main_csqaq.CSQAQAPIError("403 Forbidden")

    monkeypatch.setattr(main_csqaq, "_run_once", fake_run_once)
    monkeypatch.setattr(main_csqaq.sys, "argv", ["main_csqaq.py"])

    result = main_csqaq.main()

    assert result == 1
    assert attempts["count"] == 1
