#!/opt/select/Sequoia-X-master/.venv/bin/python

"""CLI entrypoint for CSQAQ item selection."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from sequoia_x.csqaq.client import CSQAQAPIError, CSQAQClient
from sequoia_x.csqaq.notify import CSQAQFeishuNotifier
from sequoia_x.csqaq.selector import DEFAULT_SORT, SelectorRequest, list_goods, select_goods
from sequoia_x.csqaq.settings import CSQAQSettings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select CS2 items from CSQAQ data.")
    parser.add_argument(
        "--profile",
        choices=["trend-follow", "low-base-launch", "7-day-hold", "7-day-hold-aggressive"],
        default="trend-follow",
        help="Selection profile",
    )
    parser.add_argument("--search", default="", help="Search keyword. Example: Butterfly")
    parser.add_argument("--page-index", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--all-pages", action="store_true", help="Fetch all pages from the list API")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional safety cap when using --all-pages")
    parser.add_argument("--list-only", action="store_true", help="Show the fetched goods list directly without detail scoring")
    parser.add_argument("--sort", default=DEFAULT_SORT)
    parser.add_argument("--type", dest="item_types", action="append")
    parser.add_argument("--category", dest="categories", action="append")
    parser.add_argument("--quality", dest="qualities", action="append")
    parser.add_argument("--exterior", dest="exteriors", action="append")
    parser.add_argument("--min-price", type=float, default=None)
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument("--min-sell-count", type=int, default=0)
    parser.add_argument("--min-buy-count", type=int, default=0)
    parser.add_argument("--allow-sideways", action="store_true", help="Disable the default uptrend filter")
    parser.add_argument("--min-trend-7", type=float, default=0.5)
    parser.add_argument("--min-trend-30", type=float, default=2.0)
    parser.add_argument("--min-trend-90", type=float, default=-3.0)
    parser.add_argument("--max-spread-pct", type=float, default=18.0)
    parser.add_argument("--min-turnover", type=int, default=1)
    parser.add_argument("--min-demand-ratio", type=float, default=0.03)
    parser.add_argument("--show-recently-price", action="store_true")
    parser.add_argument("--no-bind-ip", action="store_true")
    parser.add_argument("--notify", action="store_true")
    return parser


def _format_price_cell(sell_price: float, buy_price: float) -> str:
    if sell_price > 0 and buy_price > 0:
        return f"{sell_price:.2f}/{buy_price:.2f}"
    if sell_price > 0:
        return f"{sell_price:.2f}"
    if buy_price > 0:
        return f"-/{buy_price:.2f}"
    return "-"


def _render_scored_goods(goods) -> None:
    console = Console()
    table = Table(title="CSQAQ Picks", expand=True)
    table.add_column("Rank", justify="right")
    table.add_column("Name", min_width=38, ratio=6, overflow="fold")
    table.add_column("Price", justify="right", width=13)
    table.add_column("Score", justify="right", width=7)
    table.add_column("7d %", justify="right", width=6)
    table.add_column("Bid/Ask", justify="right", width=7)
    table.add_column("Turnover", justify="right", width=5)
    table.add_column("Spread %", justify="right", width=6)
    table.add_column("30d %", justify="right", width=6)
    table.add_column("90d %", justify="right", width=6)
    table.add_column("Mom", justify="right", width=6)
    table.add_column("Liq", justify="right", width=6)
    table.add_column("Risk", justify="right", width=6)
    table.add_column("Signal", min_width=12, ratio=1, overflow="ellipsis")
    table.add_column("URL", max_width=12, overflow="ellipsis")

    for index, item in enumerate(goods, start=1):
        table.add_row(
            str(index),
            item.name,
            _format_price_cell(item.sell_price, item.buy_price),
            f"{item.score:.2f}",
            f"{item.trend_7:.2f}",
            f"{item.demand_ratio:.2f}",
            str(item.turnover_number),
            f"{item.spread_pct:.2f}",
            f"{item.trend_30:.2f}",
            f"{item.trend_90:.2f}",
            f"{item.momentum_score:.2f}",
            f"{item.liquidity_score:.2f}",
            f"{item.risk_penalty:.2f}",
            ", ".join(item.reasons[:3]),
            item.url,
        )

    console.print(table)


def _render_listed_goods(goods) -> None:
    console = Console()
    table = Table(title="CSQAQ Goods List", expand=True)
    table.add_column("Index", justify="right")
    table.add_column("Name", min_width=42, ratio=6, overflow="fold")
    table.add_column("Price", justify="right", width=13)
    table.add_column("Spread %", justify="right", width=6)
    table.add_column("Sell#", justify="right", width=6)
    table.add_column("Buy#", justify="right", width=6)
    table.add_column("URL", max_width=12, overflow="ellipsis")

    for index, item in enumerate(goods, start=1):
        table.add_row(
            str(index),
            item.name,
            _format_price_cell(item.sell_price, item.buy_price),
            f"{item.spread_pct:.2f}",
            str(item.sell_count),
            str(item.buy_count),
            item.url,
        )

    console.print(table)


def _make_progress_callback(console: Console):
    def _callback(event: str, payload: dict[str, Any]) -> None:
        if event == "page_loaded":
            console.print(
                f"[cyan]Loaded page {payload['page_index']}[/cyan] "
                f"page_count={payload['page_count']} total_candidates={payload['total_candidates']}"
            )
            return
        if event == "scan_start":
            console.print(
                f"[cyan]Scoring candidates[/cyan] total={payload['total_candidates']}"
            )
            return
        if event == "candidate_scoring":
            console.print(
                f"[white]Analyzing[/white] "
                f"{payload['index']}/{payload['total_candidates']} "
                f"{payload['name']}"
            )
            return
        if event == "candidate_selected":
            console.print(
                f"[green]Selected[/green] "
                f"#{payload['selected_count']} "
                f"{payload['name']} "
                f"score={payload['score']:.2f} "
                f"7d={payload['trend_7']:.2f}% "
                f"30d={payload['trend_30']:.2f}% "
                f"spread={payload['spread_pct']:.2f}%"
            )
            return
        if event == "candidate_skipped":
            console.print(
                f"[yellow]Skipped[/yellow] "
                f"{payload['index']}/{payload['total_candidates']} "
                f"{payload['name']} "
                f"error={payload['error']}"
            )
            return
        if event == "scan_complete":
            console.print(
                f"[cyan]Scan complete[/cyan] "
                f"candidates={payload['total_candidates']} selected={payload['selected_count']}"
            )

    return _callback


def _is_retryable_server_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "500" in message
        or "502" in message
        or "503" in message
        or "internal server error" in message
        or "bad gateway" in message
        or "service unavailable" in message
    )


def _build_request(args: argparse.Namespace) -> SelectorRequest:
    return SelectorRequest(
        profile=args.profile.replace("-", "_"),
        search=args.search,
        page_index=args.page_index,
        page_size=args.page_size,
        top_k=args.top_k,
        all_pages=args.all_pages,
        max_pages=args.max_pages,
        item_types=args.item_types,
        categories=args.categories,
        qualities=args.qualities,
        exteriors=args.exteriors,
        min_price=args.min_price,
        max_price=args.max_price,
        min_sell_count=args.min_sell_count,
        min_buy_count=args.min_buy_count,
        require_uptrend=not args.allow_sideways,
        min_trend_7=args.min_trend_7,
        min_trend_30=args.min_trend_30,
        min_trend_90=args.min_trend_90,
        max_spread_pct=args.max_spread_pct,
        min_turnover_number=args.min_turnover,
        min_demand_ratio=args.min_demand_ratio,
        sort_key=args.sort,
        show_recently_price=args.show_recently_price,
    )


def _run_once(
    args: argparse.Namespace,
    settings: CSQAQSettings,
    request: SelectorRequest,
    progress_console: Console,
):
    client = CSQAQClient(
        api_token=settings.csqaq_api_token,
        timeout=settings.csqaq_request_timeout,
        min_interval_seconds=settings.csqaq_min_interval_seconds,
        retry_count=settings.csqaq_retry_count,
    )

    if settings.csqaq_auto_bind_ip and not args.no_bind_ip:
        client.bind_local_ip()
    if args.list_only:
        return list_goods(
            client,
            request,
            progress_callback=_make_progress_callback(progress_console),
        )
    return select_goods(
        client,
        request,
        progress_callback=_make_progress_callback(progress_console),
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    progress_console = Console(stderr=True)

    try:
        settings = CSQAQSettings()
    except ValidationError as exc:
        print("Missing CSQAQ settings. Set CSQAQ_API_TOKEN in .env or environment.", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    request = _build_request(args)

    try:
        for attempt in range(2):
            try:
                goods = _run_once(args, settings, request, progress_console)
                break
            except (CSQAQAPIError, ValueError, KeyError) as exc:
                if attempt == 0 and _is_retryable_server_error(exc):
                    progress_console.print("[yellow]Detected transient CSQAQ server error, retrying the full run once...[/yellow]")
                    continue
                print(f"CSQAQ request failed: {exc}", file=sys.stderr)
                return 1
    except (CSQAQAPIError, ValueError, KeyError) as exc:
        print(f"CSQAQ request failed: {exc}", file=sys.stderr)
        return 1

    if args.list_only:
        _render_listed_goods(goods)
    else:
        _render_scored_goods(goods)

    if args.notify and not args.list_only:
        if not settings.csqaq_feishu_webhook_url:
            print("Skipping Feishu push: CSQAQ_FEISHU_WEBHOOK_URL is not configured.", file=sys.stderr)
        else:
            notifier = CSQAQFeishuNotifier(settings.csqaq_feishu_webhook_url)
            title_suffix = args.search or args.sort
            notifier.send(goods, title_suffix=title_suffix)
    elif args.notify and args.list_only:
        print("Skipping Feishu push: --notify only works with scored selection mode.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
