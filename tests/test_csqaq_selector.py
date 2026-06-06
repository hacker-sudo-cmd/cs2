from sequoia_x.csqaq.client import CSQAQAPIError
from sequoia_x.csqaq.selector import (
    DEFAULT_SORT,
    SelectorRequest,
    build_filters,
    list_candidates,
    list_goods,
    score_good,
    select_goods,
)


def test_build_filters_only_includes_configured_values() -> None:
    request = SelectorRequest(
        item_types=["knife"],
        categories=["unusual"],
        exteriors=["factory_new"],
        min_price=100.0,
        max_price=5000.0,
        min_sell_count=5,
        min_buy_count=2,
    )

    filters = build_filters(request, include_sort=True)

    assert filters == {
        "\u6392\u5e8f": [DEFAULT_SORT],
        "\u7c7b\u578b": ["knife"],
        "\u7c7b\u522b": ["unusual"],
        "\u78e8\u635f": ["factory_new"],
        "\u4ef7\u683c\u6700\u4f4e\u4ef7": 100.0,
        "\u4ef7\u683c\u6700\u9ad8\u4ef7": 5000.0,
        "\u5728\u552e\u6700\u5c11": 5,
        "\u6c42\u8d2d\u6700\u5c11": 2,
    }


def test_score_good_prefers_stronger_momentum_and_liquidity() -> None:
    weak = {
        "id": 1,
        "name": "weak",
        "buff_sell_price": 1000.0,
        "buff_buy_price": 700.0,
        "buff_sell_num": 90,
        "buff_buy_num": 2,
        "turnover_number": 1,
        "sell_price_rate_1": -4.5,
        "sell_price_rate_7": -2.0,
        "sell_price_rate_15": -4.0,
        "sell_price_rate_30": -8.0,
        "sell_price_rate_90": -12.0,
        "sell_price_rate_180": -5.0,
        "rank_num": 1400,
    }
    strong = {
        "id": 2,
        "name": "strong",
        "buff_sell_price": 1000.0,
        "buff_buy_price": 930.0,
        "buff_sell_num": 40,
        "buff_buy_num": 12,
        "turnover_number": 18,
        "sell_price_rate_1": 1.5,
        "sell_price_rate_7": 6.0,
        "sell_price_rate_15": 9.0,
        "sell_price_rate_30": 11.0,
        "sell_price_rate_90": 16.0,
        "sell_price_rate_180": 24.0,
        "rank_num": 120,
    }

    weak_scored = score_good(weak)
    strong_scored = score_good(strong)

    assert strong_scored.score > weak_scored.score
    assert strong_scored.momentum_score > weak_scored.momentum_score
    assert strong_scored.liquidity_score > weak_scored.liquidity_score
    assert "aligned 7/30/90d uptrend" in strong_scored.reasons


class _PagedClient:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
        self.calls.append(page_index)
        pages = {
            1: {"code": 200, "data": {"data": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]}},
            2: {"code": 200, "data": {"data": [{"id": 3, "name": "c"}]}},
            3: {"code": 200, "data": {"data": []}},
        }
        return pages[page_index]


def test_list_candidates_fetches_multiple_pages_when_enabled() -> None:
    client = _PagedClient()
    request = SelectorRequest(page_size=2, all_pages=True)

    rows = list_candidates(client, request)

    assert [row["id"] for row in rows] == [1, 2, 3]
    assert client.calls == [1, 2]


def test_list_goods_returns_flat_goods_view() -> None:
    class _ListClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {
                    "data": [
                        {
                            "id": 7,
                            "name": "item-7",
                            "buff_sell_price": 1200,
                            "buff_buy_price": 1110,
                            "buff_sell_num": 10,
                            "buff_buy_num": 4,
                        }
                    ]
                },
            }

    goods = list_goods(_ListClient(), SelectorRequest())

    assert len(goods) == 1
    assert goods[0].good_id == 7
    assert goods[0].name == "item-7"
    assert goods[0].spread_pct > 0


def test_list_goods_emits_page_progress_events() -> None:
    class _ListClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {"data": [{"id": 7, "name": "item-7", "buff_sell_price": 1200}]},
            }

    events: list[tuple[str, dict]] = []
    list_goods(_ListClient(), SelectorRequest(), progress_callback=lambda event, payload: events.append((event, payload)))

    assert events
    assert events[0][0] == "page_loaded"


def test_select_goods_filters_out_non_uptrend_items_by_default() -> None:
    class _SelectClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {"data": [{"id": 1, "name": "weak"}, {"id": 2, "name": "strong"}]},
            }

        def get_good(self, good_id: int):
            if good_id == 1:
                return {
                    "code": 200,
                    "data": {
                        "goods_info": {
                            "id": 1,
                            "name": "weak",
                            "buff_sell_price": 1000,
                            "buff_buy_price": 850,
                            "buff_sell_num": 20,
                            "buff_buy_num": 1,
                            "turnover_number": 0,
                            "sell_price_rate_7": -1.0,
                            "sell_price_rate_30": -3.0,
                            "sell_price_rate_90": -2.0,
                        }
                    },
                }
            return {
                "code": 200,
                "data": {
                    "goods_info": {
                        "id": 2,
                        "name": "strong",
                        "buff_sell_price": 1000,
                        "buff_buy_price": 940,
                        "buff_sell_num": 24,
                        "buff_buy_num": 8,
                        "turnover_number": 7,
                        "sell_price_rate_1": 0.8,
                        "sell_price_rate_7": 4.0,
                        "sell_price_rate_15": 7.0,
                        "sell_price_rate_30": 8.0,
                        "sell_price_rate_90": 10.0,
                    }
                },
            }

    goods = select_goods(_SelectClient(), SelectorRequest(top_k=10))

    assert [item.good_id for item in goods] == [2]


def test_select_goods_supports_low_base_launch_profile() -> None:
    class _SelectClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {
                    "data": [
                        {"id": 11, "name": "overheated"},
                        {"id": 12, "name": "low-base"},
                    ]
                },
            }

        def get_good(self, good_id: int):
            if good_id == 11:
                return {
                    "code": 200,
                    "data": {
                        "goods_info": {
                            "id": 11,
                            "name": "overheated",
                            "buff_sell_price": 1000,
                            "buff_buy_price": 950,
                            "buff_sell_num": 20,
                            "buff_buy_num": 8,
                            "turnover_number": 12,
                            "sell_price_rate_1": 2.0,
                            "sell_price_rate_7": 15.0,
                            "sell_price_rate_15": 22.0,
                            "sell_price_rate_30": 28.0,
                            "sell_price_rate_90": 34.0,
                            "sell_price_rate_180": 40.0,
                        }
                    },
                }
            return {
                "code": 200,
                "data": {
                    "goods_info": {
                        "id": 12,
                        "name": "low-base",
                        "buff_sell_price": 1000,
                        "buff_buy_price": 930,
                        "buff_sell_num": 24,
                        "buff_buy_num": 6,
                        "turnover_number": 5,
                        "sell_price_rate_1": 0.5,
                        "sell_price_rate_7": 4.2,
                        "sell_price_rate_15": 5.6,
                        "sell_price_rate_30": 3.4,
                        "sell_price_rate_90": 1.8,
                        "sell_price_rate_180": -4.0,
                    }
                },
            }

    goods = select_goods(
        _SelectClient(),
        SelectorRequest(profile="low_base_launch", top_k=10),
    )

    assert [item.good_id for item in goods] == [12]
    assert goods[0].reasons[0] == "low-base launch"


def test_select_goods_supports_7_day_hold_profile() -> None:
    class _SelectClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {
                    "data": [
                        {"id": 21, "name": "spike"},
                        {"id": 22, "name": "carry"},
                    ]
                },
            }

        def get_good(self, good_id: int):
            if good_id == 21:
                return {
                    "code": 200,
                    "data": {
                        "goods_info": {
                            "id": 21,
                            "name": "spike",
                            "buff_sell_price": 1000,
                            "buff_buy_price": 955,
                            "buff_sell_num": 18,
                            "buff_buy_num": 6,
                            "turnover_number": 10,
                            "sell_price_rate_1": 2.8,
                            "sell_price_rate_7": 11.5,
                            "sell_price_rate_15": 15.0,
                            "sell_price_rate_30": 18.0,
                            "sell_price_rate_90": 21.0,
                            "sell_price_rate_180": 20.0,
                        }
                    },
                }
            return {
                "code": 200,
                "data": {
                    "goods_info": {
                        "id": 22,
                        "name": "carry",
                        "buff_sell_price": 1000,
                        "buff_buy_price": 935,
                        "buff_sell_num": 22,
                        "buff_buy_num": 7,
                        "turnover_number": 6,
                        "sell_price_rate_1": 0.6,
                        "sell_price_rate_7": 4.6,
                        "sell_price_rate_15": 6.8,
                        "sell_price_rate_30": 5.2,
                        "sell_price_rate_90": 3.5,
                        "sell_price_rate_180": 2.0,
                    }
                },
            }

    goods = select_goods(
        _SelectClient(),
        SelectorRequest(profile="7_day_hold", top_k=10),
    )

    assert [item.good_id for item in goods] == [22]
    assert goods[0].reasons[0] == "7-day hold"


def test_select_goods_supports_7_day_hold_aggressive_profile() -> None:
    class _SelectClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {
                    "data": [
                        {"id": 31, "name": "too-hot"},
                        {"id": 32, "name": "aggressive-carry"},
                    ]
                },
            }

        def get_good(self, good_id: int):
            if good_id == 31:
                return {
                    "code": 200,
                    "data": {
                        "goods_info": {
                            "id": 31,
                            "name": "too-hot",
                            "buff_sell_price": 1000,
                            "buff_buy_price": 960,
                            "buff_sell_num": 18,
                            "buff_buy_num": 6,
                            "turnover_number": 11,
                            "sell_price_rate_1": 3.2,
                            "sell_price_rate_7": 12.5,
                            "sell_price_rate_15": 16.0,
                            "sell_price_rate_30": 20.0,
                            "sell_price_rate_90": 24.0,
                            "sell_price_rate_180": 22.0,
                        }
                    },
                }
            return {
                "code": 200,
                "data": {
                    "goods_info": {
                        "id": 32,
                        "name": "aggressive-carry",
                        "buff_sell_price": 1000,
                        "buff_buy_price": 930,
                        "buff_sell_num": 20,
                        "buff_buy_num": 7,
                        "turnover_number": 5,
                        "sell_price_rate_1": 1.2,
                        "sell_price_rate_7": 7.8,
                        "sell_price_rate_15": 10.6,
                        "sell_price_rate_30": 9.4,
                        "sell_price_rate_90": 8.0,
                        "sell_price_rate_180": 6.0,
                    }
                },
            }

    goods = select_goods(
        _SelectClient(),
        SelectorRequest(profile="7_day_hold_aggressive", top_k=10),
    )

    assert [item.good_id for item in goods] == [32]
    assert goods[0].reasons[0] == "7-day hold aggressive"


def test_select_goods_skips_candidates_with_detail_errors() -> None:
    class _SelectClient:
        def get_rank_list(self, *, page_index: int, page_size: int, filters, show_recently_price=False):
            return {
                "code": 200,
                "data": {"data": [{"id": 1, "name": "broken"}, {"id": 2, "name": "strong"}]},
            }

        def get_good(self, good_id: int):
            if good_id == 1:
                raise CSQAQAPIError("500 Server Error: Internal Server Error")
            return {
                "code": 200,
                "data": {
                    "goods_info": {
                        "id": 2,
                        "name": "strong",
                        "buff_sell_price": 1000,
                        "buff_buy_price": 940,
                        "buff_sell_num": 24,
                        "buff_buy_num": 8,
                        "turnover_number": 7,
                        "sell_price_rate_1": 0.8,
                        "sell_price_rate_7": 4.0,
                        "sell_price_rate_15": 7.0,
                        "sell_price_rate_30": 8.0,
                        "sell_price_rate_90": 10.0,
                    }
                },
            }

    events: list[tuple[str, dict]] = []
    goods = select_goods(
        _SelectClient(),
        SelectorRequest(top_k=10),
        progress_callback=lambda event, payload: events.append((event, payload)),
    )

    assert [item.good_id for item in goods] == [2]
    assert any(event == "candidate_skipped" and payload["good_id"] == 1 for event, payload in events)
