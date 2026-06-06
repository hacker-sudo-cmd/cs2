"""Feishu notifications for CSQAQ picks."""

from __future__ import annotations

import json
from datetime import date

import requests

from sequoia_x.core.logger import get_logger
from sequoia_x.csqaq.selector import SelectedGood

logger = get_logger(__name__)


class CSQAQFeishuNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def _build_card(self, goods: list[SelectedGood], title_suffix: str = "") -> dict:
        today = date.today().strftime("%Y-%m-%d")
        item_lines = []
        for item in goods:
            reasons = ", ".join(item.reasons[:4]) if item.reasons else "rule score"
            item_lines.append(
                (
                    f"[{item.name}]({item.url})\n"
                    f"score={item.score} sell={item.sell_price} buy={item.buy_price} "
                    f"spread={item.spread_pct}% sell_count={item.sell_count} "
                    f"buy_count={item.buy_count}\n{reasons}"
                )
            )

        body = "\n\n".join(item_lines) if item_lines else "No picks"
        title = "CSQAQ Picks"
        if title_suffix:
            title = f"{title} | {title_suffix}"

        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title,
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**date** {today}\n**count** {len(goods)}",
                        },
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": body,
                        },
                    },
                ],
            },
        }

    def send(self, goods: list[SelectedGood], title_suffix: str = "") -> None:
        payload = self._build_card(goods, title_suffix=title_suffix)
        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response_json = response.json()
            if response.status_code != 200 or response_json.get("code") != 0:
                logger.error("CSQAQ Feishu push failed: %s", response.text)
        except requests.RequestException as exc:
            logger.error("CSQAQ Feishu request failed: %s", exc)

