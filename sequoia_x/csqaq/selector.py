"""Rule-based CSQAQ item selection with investment-style indicators."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Optional

from sequoia_x.csqaq.client import CSQAQAPIError, CSQAQClient


DEFAULT_SORT = (
    "\u4ef7\u683c_\u552e\u4ef7\u51cf\u6c42\u8d2d\u4ef7(\u767e\u5206\u6bd4)_\u5347\u5e8f(BUFF)"
)
ProgressCallback = Callable[[str, dict[str, Any]], None]


@dataclass
class SelectorRequest:
    profile: str = "trend_follow"
    search: str = ""
    page_index: int = 1
    page_size: int = 30
    top_k: int = 10
    all_pages: bool = False
    max_pages: Optional[int] = None
    item_types: Optional[list[str]] = None
    categories: Optional[list[str]] = None
    qualities: Optional[list[str]] = None
    exteriors: Optional[list[str]] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_sell_count: int = 0
    min_buy_count: int = 0
    sort_key: str = DEFAULT_SORT
    show_recently_price: bool = False
    require_uptrend: bool = True
    min_trend_7: float = 0.5
    min_trend_30: float = 2.0
    min_trend_90: float = -3.0
    max_spread_pct: float = 18.0
    min_turnover_number: int = 1
    min_demand_ratio: float = 0.03


@dataclass
class SelectedGood:
    good_id: int
    name: str
    score: float
    sell_price: float
    buy_price: float
    sell_count: int
    buy_count: int
    turnover_number: int
    spread_pct: float
    demand_ratio: float
    trend_1: float
    trend_7: float
    trend_15: float
    trend_30: float
    trend_90: float
    trend_180: float
    momentum_score: float
    liquidity_score: float
    risk_penalty: float
    rank_num: Optional[int]
    reasons: list[str]

    @property
    def url(self) -> str:
        return f"https://csqaq.com/goods/{self.good_id}"


@dataclass
class ListedGood:
    good_id: int
    name: str
    sell_price: float
    buy_price: float
    sell_count: int
    buy_count: int
    spread_pct: float

    @property
    def url(self) -> str:
        return f"https://csqaq.com/goods/{self.good_id}"


def _coalesce_number(data: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(number):
            return number
    return 0.0


def _coalesce_int(data: dict[str, Any], *keys: str) -> int:
    return int(round(_coalesce_number(data, *keys)))


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_filters(request: SelectorRequest, *, include_sort: bool) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if include_sort:
        filters["\u6392\u5e8f"] = [request.sort_key]
    if request.item_types:
        filters["\u7c7b\u578b"] = request.item_types
    if request.categories:
        filters["\u7c7b\u522b"] = request.categories
    if request.qualities:
        filters["\u54c1\u8d28"] = request.qualities
    if request.exteriors:
        filters["\u78e8\u635f"] = request.exteriors
    if request.min_price is not None:
        filters["\u4ef7\u683c\u6700\u4f4e\u4ef7"] = request.min_price
    if request.max_price is not None:
        filters["\u4ef7\u683c\u6700\u9ad8\u4ef7"] = request.max_price
    if request.min_sell_count > 0:
        filters["\u5728\u552e\u6700\u5c11"] = request.min_sell_count
    if request.min_buy_count > 0:
        filters["\u6c42\u8d2d\u6700\u5c11"] = request.min_buy_count
    return filters


def _spread_pct(sell_price: float, buy_price: float) -> float:
    if sell_price <= 0 or buy_price <= 0:
        return 100.0
    return max(0.0, (sell_price - buy_price) / sell_price * 100.0)


def _extract_price_fields(goods_info: dict[str, Any]) -> tuple[float, float, int, int]:
    sell_price = _coalesce_number(
        goods_info,
        "buff_sell_price",
        "yyyp_sell_price",
        "c5_sell_price",
        "igxe_sell_price",
        "eco_sell_price",
        "steam_sell_price",
    )
    buy_price = _coalesce_number(
        goods_info,
        "buff_buy_price",
        "yyyp_buy_price",
        "c5_buy_price",
        "igxe_buy_price",
        "eco_buy_price",
        "steam_buy_price",
    )
    sell_count = _coalesce_int(
        goods_info,
        "buff_sell_num",
        "yyyp_sell_num",
        "c5_sell_num",
        "igxe_sell_num",
        "eco_sell_num",
        "steam_sell_num",
    )
    buy_count = _coalesce_int(
        goods_info,
        "buff_buy_num",
        "yyyp_buy_num",
        "c5_buy_num",
        "igxe_buy_num",
        "eco_buy_num",
        "steam_buy_num",
    )
    return sell_price, buy_price, sell_count, buy_count


def _trend(goods_info: dict[str, Any], days: int) -> float:
    return _coalesce_number(
        goods_info,
        f"sell_price_rate_{days}",
        f"yyyp_sell_price_rate_{days}",
    )


def score_good(goods_info: dict[str, Any]) -> SelectedGood:
    sell_price, buy_price, sell_count, buy_count = _extract_price_fields(goods_info)
    turnover_number = _coalesce_int(goods_info, "turnover_number")
    trend_1 = _trend(goods_info, 1)
    trend_7 = _trend(goods_info, 7)
    trend_15 = _trend(goods_info, 15)
    trend_30 = _trend(goods_info, 30)
    trend_90 = _trend(goods_info, 90)
    trend_180 = _trend(goods_info, 180)
    rank_num = goods_info.get("rank_num")
    rank_value = int(rank_num) if rank_num is not None else None

    spread_pct = _spread_pct(sell_price, buy_price)
    demand_ratio = buy_count / max(sell_count, 1)

    trend_alignment_bonus = 0.0
    if trend_7 > 0 and trend_30 > 0:
        trend_alignment_bonus += 6.0
    if trend_30 > 0 and trend_90 > 0:
        trend_alignment_bonus += 6.0
    if trend_7 > trend_30 / 4 and trend_30 > trend_90 / 3:
        trend_alignment_bonus += 4.0

    momentum_score = 0.0
    momentum_score += _clip(trend_1, -4.0, 4.0) * 0.5
    momentum_score += _clip(trend_7, -10.0, 15.0) * 1.3
    momentum_score += _clip(trend_15, -15.0, 20.0) * 0.9
    momentum_score += _clip(trend_30, -20.0, 30.0) * 1.0
    momentum_score += _clip(trend_90, -20.0, 25.0) * 0.7
    momentum_score += _clip(trend_180, -15.0, 30.0) * 0.25
    momentum_score += trend_alignment_bonus

    liquidity_score = 0.0
    liquidity_score += min(turnover_number, 40) * 0.7
    liquidity_score += min(buy_count, 30) * 0.45
    liquidity_score += min(sell_count, 60) * 0.1
    liquidity_score += min(demand_ratio, 0.5) * 28.0
    liquidity_score += max(0.0, 16.0 - spread_pct) * 1.0

    risk_penalty = 0.0
    if spread_pct > 12.0:
        risk_penalty += (spread_pct - 12.0) * 1.2
    if trend_7 > 14.0:
        risk_penalty += (trend_7 - 14.0) * 1.2
    if trend_30 > 35.0:
        risk_penalty += (trend_30 - 35.0) * 0.8
    if trend_1 < -3.5:
        risk_penalty += abs(trend_1 + 3.5) * 1.5
    if sell_count < 5:
        risk_penalty += (5 - sell_count) * 1.3
    if buy_count <= 0:
        risk_penalty += 10.0
    if rank_value is not None and rank_value > 1000:
        risk_penalty += min(8.0, (rank_value - 1000) / 250.0)

    total_score = momentum_score + liquidity_score - risk_penalty

    reasons: list[str] = []
    if trend_7 > 0 and trend_30 > 0 and trend_90 > 0:
        reasons.append("aligned 7/30/90d uptrend")
    elif trend_7 > 0 and trend_30 > 0:
        reasons.append("aligned 7/30d uptrend")
    if demand_ratio >= 0.1:
        reasons.append(f"demand {demand_ratio:.2f}")
    if spread_pct <= 12:
        reasons.append(f"spread {spread_pct:.1f}%")
    if turnover_number > 0:
        reasons.append(f"turnover {turnover_number}")
    if trend_7 > trend_30 / 4 and trend_30 > trend_90 / 3:
        reasons.append("momentum acceleration")

    return SelectedGood(
        good_id=int(goods_info["id"]),
        name=str(goods_info["name"]),
        score=round(total_score, 2),
        sell_price=round(sell_price, 2),
        buy_price=round(buy_price, 2),
        sell_count=sell_count,
        buy_count=buy_count,
        turnover_number=turnover_number,
        spread_pct=round(spread_pct, 2),
        demand_ratio=round(demand_ratio, 3),
        trend_1=round(trend_1, 2),
        trend_7=round(trend_7, 2),
        trend_15=round(trend_15, 2),
        trend_30=round(trend_30, 2),
        trend_90=round(trend_90, 2),
        trend_180=round(trend_180, 2),
        momentum_score=round(momentum_score, 2),
        liquidity_score=round(liquidity_score, 2),
        risk_penalty=round(risk_penalty, 2),
        rank_num=rank_value,
        reasons=reasons,
    )


def _score_trend_follow(good: SelectedGood) -> float:
    return round(good.momentum_score + good.liquidity_score - good.risk_penalty, 2)


def _score_low_base_launch(good: SelectedGood) -> float:
    base_quality = 0.0
    base_quality += max(0.0, 12.0 - abs(good.trend_30 - 4.0) * 1.4)
    base_quality += max(0.0, 10.0 - abs(good.trend_90 - 2.0) * 0.8)
    base_quality += max(0.0, 8.0 - abs(good.trend_180) * 0.25)

    ignition = 0.0
    ignition += _clip(good.trend_7, -2.0, 10.0) * 2.2
    ignition += _clip(good.trend_15, -2.0, 12.0) * 1.3
    ignition += max(0.0, good.trend_7 - good.trend_30 / 3.0) * 1.8

    liquidity = 0.0
    liquidity += min(good.turnover_number, 30) * 0.7
    liquidity += min(good.buy_count, 20) * 0.5
    liquidity += min(good.demand_ratio, 0.4) * 32.0
    liquidity += max(0.0, 14.0 - good.spread_pct) * 1.1

    overheat_penalty = 0.0
    if good.trend_7 > 10.0:
        overheat_penalty += (good.trend_7 - 10.0) * 2.4
    if good.trend_15 > 15.0:
        overheat_penalty += (good.trend_15 - 15.0) * 1.8
    if good.trend_30 > 14.0:
        overheat_penalty += (good.trend_30 - 14.0) * 1.4
    if good.trend_90 > 18.0:
        overheat_penalty += (good.trend_90 - 18.0) * 1.0
    if good.trend_1 < -2.5:
        overheat_penalty += abs(good.trend_1 + 2.5) * 1.8

    return round(base_quality + ignition + liquidity - overheat_penalty, 2)


def _score_7_day_hold(good: SelectedGood) -> float:
    base_quality = 0.0
    base_quality += max(0.0, 14.0 - abs(good.trend_30 - 5.0) * 1.5)
    base_quality += max(0.0, 10.0 - abs(good.trend_90 - 4.0) * 0.8)
    base_quality += max(0.0, 6.0 - abs(good.trend_180 - 6.0) * 0.25)

    continuation = 0.0
    continuation += _clip(good.trend_1, -1.5, 3.0) * 0.4
    continuation += _clip(good.trend_7, 0.0, 8.0) * 1.8
    continuation += _clip(good.trend_15, 0.0, 12.0) * 1.2
    continuation += _clip(good.trend_30, -2.0, 14.0) * 0.6
    if good.trend_7 > 0 and good.trend_15 > 0 and good.trend_30 > 0:
        continuation += 6.0
    if good.trend_7 <= good.trend_15 + 2.0:
        continuation += 3.0

    liquidity = 0.0
    liquidity += min(good.turnover_number, 25) * 0.8
    liquidity += min(good.buy_count, 20) * 0.6
    liquidity += min(good.sell_count, 40) * 0.12
    liquidity += min(good.demand_ratio, 0.25) * 45.0
    liquidity += max(0.0, 10.0 - good.spread_pct) * 1.4

    carry_penalty = 0.0
    if good.trend_1 > 3.5:
        carry_penalty += (good.trend_1 - 3.5) * 2.5
    if good.trend_1 < -2.5:
        carry_penalty += abs(good.trend_1 + 2.5) * 2.0
    if good.trend_7 > 8.0:
        carry_penalty += (good.trend_7 - 8.0) * 3.0
    if good.trend_15 > 12.0:
        carry_penalty += (good.trend_15 - 12.0) * 2.2
    if good.trend_30 > 14.0:
        carry_penalty += (good.trend_30 - 14.0) * 1.5
    if good.trend_90 > 16.0:
        carry_penalty += (good.trend_90 - 16.0) * 1.2
    if good.spread_pct > 10.0:
        carry_penalty += (good.spread_pct - 10.0) * 1.5
    if good.turnover_number < 4:
        carry_penalty += (4 - good.turnover_number) * 2.0
    if good.buy_count < 3:
        carry_penalty += (3 - good.buy_count) * 2.5

    return round(base_quality + continuation + liquidity - carry_penalty, 2)


def _score_7_day_hold_aggressive(good: SelectedGood) -> float:
    base_quality = 0.0
    base_quality += max(0.0, 12.0 - abs(good.trend_30 - 7.0) * 1.2)
    base_quality += max(0.0, 8.0 - abs(good.trend_90 - 7.0) * 0.7)
    base_quality += max(0.0, 5.0 - abs(good.trend_180 - 8.0) * 0.2)

    continuation = 0.0
    continuation += _clip(good.trend_1, -1.5, 4.5) * 0.5
    continuation += _clip(good.trend_7, 0.0, 10.5) * 2.1
    continuation += _clip(good.trend_15, 0.0, 14.0) * 1.4
    continuation += _clip(good.trend_30, 0.0, 16.0) * 0.75
    if good.trend_7 > 0 and good.trend_15 > 0 and good.trend_30 > 0:
        continuation += 7.0
    if good.trend_7 <= good.trend_15 + 3.0:
        continuation += 3.0
    if good.trend_15 >= good.trend_30 * 0.7:
        continuation += 2.0

    liquidity = 0.0
    liquidity += min(good.turnover_number, 28) * 0.75
    liquidity += min(good.buy_count, 22) * 0.6
    liquidity += min(good.sell_count, 40) * 0.1
    liquidity += min(good.demand_ratio, 0.3) * 42.0
    liquidity += max(0.0, 11.0 - good.spread_pct) * 1.2

    carry_penalty = 0.0
    if good.trend_1 > 5.0:
        carry_penalty += (good.trend_1 - 5.0) * 2.4
    if good.trend_1 < -3.0:
        carry_penalty += abs(good.trend_1 + 3.0) * 1.8
    if good.trend_7 > 10.5:
        carry_penalty += (good.trend_7 - 10.5) * 2.6
    if good.trend_15 > 14.0:
        carry_penalty += (good.trend_15 - 14.0) * 2.0
    if good.trend_30 > 18.0:
        carry_penalty += (good.trend_30 - 18.0) * 1.4
    if good.trend_90 > 20.0:
        carry_penalty += (good.trend_90 - 20.0) * 1.0
    if good.spread_pct > 11.5:
        carry_penalty += (good.spread_pct - 11.5) * 1.3
    if good.turnover_number < 3:
        carry_penalty += (3 - good.turnover_number) * 2.0
    if good.buy_count < 3:
        carry_penalty += (3 - good.buy_count) * 2.2

    return round(base_quality + continuation + liquidity - carry_penalty, 2)


def _apply_profile(good: SelectedGood, request: SelectorRequest) -> SelectedGood:
    good.reasons = list(good.reasons)

    if request.profile == "low_base_launch":
        good.score = _score_low_base_launch(good)
        good.reasons.insert(0, "low-base launch")
        if good.trend_7 > 0 and good.trend_30 <= 8:
            good.reasons.append("early breakout")
        if -8 <= good.trend_90 <= 12:
            good.reasons.append("base still compressed")
        return good

    if request.profile == "7_day_hold":
        good.score = _score_7_day_hold(good)
        good.reasons.insert(0, "7-day hold")
        if 1.0 <= good.trend_7 <= 8.0 and 1.0 <= good.trend_15 <= 12.0:
            good.reasons.append("carry-friendly 7/15d trend")
        if good.spread_pct <= 10.0:
            good.reasons.append("tight spread")
        if good.demand_ratio >= 0.08:
            good.reasons.append("stable demand")
        return good

    if request.profile == "7_day_hold_aggressive":
        good.score = _score_7_day_hold_aggressive(good)
        good.reasons.insert(0, "7-day hold aggressive")
        if 2.0 <= good.trend_7 <= 10.5 and 2.0 <= good.trend_15 <= 14.0:
            good.reasons.append("strong 7/15d continuation")
        if good.turnover_number >= 5:
            good.reasons.append("active turnover")
        if good.demand_ratio >= 0.07:
            good.reasons.append("supported demand")
        return good

    good.score = _score_trend_follow(good)
    good.reasons.insert(0, "trend follow")
    return good


def _extract_listed_good(row: dict[str, Any]) -> ListedGood:
    sell_price, buy_price, sell_count, buy_count = _extract_price_fields(row)
    spread_pct = _spread_pct(sell_price, buy_price)

    return ListedGood(
        good_id=int(row["id"]),
        name=str(row["name"]),
        sell_price=round(sell_price, 2),
        buy_price=round(buy_price, 2),
        sell_count=sell_count,
        buy_count=buy_count,
        spread_pct=round(spread_pct, 2),
    )


def _fetch_candidate_page(
    client: CSQAQClient,
    request: SelectorRequest,
    page_index: int,
) -> list[dict[str, Any]]:
    if request.search:
        response = client.get_page_list(
            page_index=page_index,
            page_size=request.page_size,
            search=request.search,
            filters=build_filters(request, include_sort=False),
        )
    else:
        response = client.get_rank_list(
            page_index=page_index,
            page_size=request.page_size,
            filters=build_filters(request, include_sort=True),
            show_recently_price=request.show_recently_price,
        )
    return list(response["data"]["data"])


def list_candidates(client: CSQAQClient, request: SelectorRequest) -> list[dict[str, Any]]:
    return _list_candidates_internal(client, request, progress_callback=None)


def _list_candidates_internal(
    client: CSQAQClient,
    request: SelectorRequest,
    progress_callback: Optional[ProgressCallback],
) -> list[dict[str, Any]]:
    page_index = request.page_index
    pages_fetched = 0
    seen_ids: set[int] = set()
    rows: list[dict[str, Any]] = []

    while True:
        page_rows = _fetch_candidate_page(client, request, page_index)
        if not page_rows:
            break

        for row in page_rows:
            row_id = int(row["id"])
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            rows.append(row)

        if progress_callback is not None:
            progress_callback(
                "page_loaded",
                {
                    "page_index": page_index,
                    "page_count": len(page_rows),
                    "total_candidates": len(rows),
                },
            )

        pages_fetched += 1
        if not request.all_pages:
            break
        if request.max_pages is not None and pages_fetched >= request.max_pages:
            break
        if len(page_rows) < request.page_size:
            break
        page_index += 1

    return rows


def list_goods(
    client: CSQAQClient,
    request: SelectorRequest,
    progress_callback: Optional[ProgressCallback] = None,
) -> list[ListedGood]:
    goods = [
        _extract_listed_good(row)
        for row in _list_candidates_internal(client, request, progress_callback)
    ]
    goods.sort(key=lambda item: (item.sell_price, item.good_id))
    return goods


def _passes_investment_rules(good: SelectedGood, request: SelectorRequest) -> bool:
    if request.min_price is not None and good.sell_price < request.min_price:
        return False
    if request.max_price is not None and good.sell_price > request.max_price:
        return False
    if good.sell_count < request.min_sell_count:
        return False
    if good.buy_count < request.min_buy_count:
        return False

    if request.profile == "low_base_launch":
        if good.sell_price <= 0 or good.buy_price <= 0:
            return False
        if good.spread_pct > min(request.max_spread_pct, 14.0):
            return False
        if good.turnover_number < request.min_turnover_number:
            return False
        if good.demand_ratio < max(0.02, request.min_demand_ratio * 0.75):
            return False
        if good.trend_1 < -3.0:
            return False
        if good.trend_7 < max(0.8, request.min_trend_7):
            return False
        if good.trend_7 > 10.5:
            return False
        if good.trend_15 < 1.0:
            return False
        if good.trend_15 > 16.0:
            return False
        if good.trend_30 < -4.0 or good.trend_30 > 12.0:
            return False
        if good.trend_90 < -12.0 or good.trend_90 > 18.0:
            return False
        if good.trend_180 < -20.0 or good.trend_180 > 25.0:
            return False
        return True

    if request.profile == "7_day_hold":
        if good.sell_price <= 0 or good.buy_price <= 0:
            return False
        if good.sell_count < max(6, request.min_sell_count):
            return False
        if good.buy_count < max(3, request.min_buy_count):
            return False
        if good.spread_pct > min(request.max_spread_pct, 10.0):
            return False
        if good.turnover_number < max(4, request.min_turnover_number):
            return False
        if good.demand_ratio < max(0.08, request.min_demand_ratio):
            return False
        if good.trend_1 < -2.5 or good.trend_1 > 4.0:
            return False
        if good.trend_7 < max(1.0, request.min_trend_7):
            return False
        if good.trend_7 > 8.0:
            return False
        if good.trend_15 < 1.0:
            return False
        if good.trend_15 > 12.0:
            return False
        if good.trend_30 < 0.5 or good.trend_30 > 14.0:
            return False
        if good.trend_90 < -6.0 or good.trend_90 > 16.0:
            return False
        if good.trend_180 < -20.0 or good.trend_180 > 24.0:
            return False
        return True

    if request.profile == "7_day_hold_aggressive":
        if good.sell_price <= 0 or good.buy_price <= 0:
            return False
        if good.sell_count < max(5, request.min_sell_count):
            return False
        if good.buy_count < max(3, request.min_buy_count):
            return False
        if good.spread_pct > min(request.max_spread_pct, 11.5):
            return False
        if good.turnover_number < max(3, request.min_turnover_number):
            return False
        if good.demand_ratio < max(0.07, request.min_demand_ratio):
            return False
        if good.trend_1 < -3.0 or good.trend_1 > 5.0:
            return False
        if good.trend_7 < max(1.5, request.min_trend_7):
            return False
        if good.trend_7 > 10.5:
            return False
        if good.trend_15 < 1.5:
            return False
        if good.trend_15 > 14.0:
            return False
        if good.trend_30 < 1.0 or good.trend_30 > 18.0:
            return False
        if good.trend_90 < -8.0 or good.trend_90 > 20.0:
            return False
        if good.trend_180 < -22.0 or good.trend_180 > 28.0:
            return False
        return True

    if not request.require_uptrend:
        return True

    if good.sell_price <= 0 or good.buy_price <= 0:
        return False
    if good.trend_7 < request.min_trend_7:
        return False
    if good.trend_30 < request.min_trend_30:
        return False
    if good.trend_90 < request.min_trend_90:
        return False
    if good.spread_pct > request.max_spread_pct:
        return False
    if good.turnover_number < request.min_turnover_number:
        return False
    if good.demand_ratio < request.min_demand_ratio:
        return False
    return True


def select_goods(
    client: CSQAQClient,
    request: SelectorRequest,
    progress_callback: Optional[ProgressCallback] = None,
) -> list[SelectedGood]:
    candidates = _list_candidates_internal(client, request, progress_callback)
    selected: list[SelectedGood] = []
    total_candidates = len(candidates)

    if progress_callback is not None:
        progress_callback(
            "scan_start",
            {
                "total_candidates": total_candidates,
            },
        )

    for index, candidate in enumerate(candidates, start=1):
        good_id = int(candidate["id"])
        name = str(candidate.get("name", ""))
        if progress_callback is not None:
            progress_callback(
                "candidate_scoring",
                {
                    "index": index,
                    "total_candidates": total_candidates,
                    "good_id": good_id,
                    "name": name,
                },
            )
        try:
            detail = client.get_good(good_id)
            scored = _apply_profile(score_good(detail["data"]["goods_info"]), request)
        except (CSQAQAPIError, KeyError, TypeError, ValueError) as exc:
            if progress_callback is not None:
                progress_callback(
                    "candidate_skipped",
                    {
                        "index": index,
                        "total_candidates": total_candidates,
                        "good_id": good_id,
                        "name": name,
                        "error": str(exc),
                    },
                )
            continue
        if _passes_investment_rules(scored, request):
            selected.append(scored)
            if progress_callback is not None:
                progress_callback(
                    "candidate_selected",
                    {
                        "index": index,
                        "total_candidates": total_candidates,
                        "selected_count": len(selected),
                        "good_id": scored.good_id,
                        "name": scored.name,
                        "score": scored.score,
                        "trend_7": scored.trend_7,
                        "trend_30": scored.trend_30,
                        "spread_pct": scored.spread_pct,
                    },
                )

    selected.sort(key=lambda item: item.score, reverse=True)
    if progress_callback is not None:
        progress_callback(
            "scan_complete",
            {
                "total_candidates": total_candidates,
                "selected_count": len(selected),
            },
        )
    if request.top_k <= 0:
        return selected
    return selected[: request.top_k]
