from __future__ import annotations

import sys
import types

import pandas as pd

from scr.infrastructure.google_trends import GoogleTrendsProvider


def test_google_trends_provider_maps_market_timeframe_and_returns_real_series(monkeypatch):
    seen = {}

    class FakeTrendReq:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        def build_payload(self, keywords, **kwargs):
            seen["payload"] = (keywords, kwargs)

        def interest_over_time(self):
            dates = pd.date_range("2024-01-01", periods=24, freq="MS")
            return pd.DataFrame({"pet fountain": [20] * 12 + [40] * 12, "isPartial": [False] * 24}, index=dates)

    request_module = types.ModuleType("pytrends.request")
    request_module.TrendReq = FakeTrendReq
    package = types.ModuleType("pytrends")
    package.request = request_module
    monkeypatch.setitem(sys.modules, "pytrends", package)
    monkeypatch.setitem(sys.modules, "pytrends.request", request_module)

    result = GoogleTrendsProvider().fetch("pet fountain", "UK", "5y")

    assert seen["init"]["hl"] == "en-GB"
    assert seen["init"]["retries"] == 0
    assert seen["payload"] == (["pet fountain"], {"cat": 0, "timeframe": "today 5-y", "geo": "GB", "gprop": ""})
    assert result["available"] is True
    assert result["items"]["direction"] == "up"
    assert result["items"]["period_growth"] == 100.0
    assert result["items"]["yoy_growth"] == 100.0
    assert len(result["items"]["points"]) == 24
    assert result["items"]["peak_months"][0]["value"] == 40.0
    assert "429" in result["note"]


def test_google_trends_provider_returns_unavailable_instead_of_fabricating(monkeypatch):
    class EmptyTrendReq:
        def __init__(self, **kwargs):
            pass

        def build_payload(self, *args, **kwargs):
            pass

        def interest_over_time(self):
            return pd.DataFrame()

    request_module = types.ModuleType("pytrends.request")
    request_module.TrendReq = EmptyTrendReq
    package = types.ModuleType("pytrends")
    package.request = request_module
    monkeypatch.setitem(sys.modules, "pytrends", package)
    monkeypatch.setitem(sys.modules, "pytrends.request", request_module)

    result = GoogleTrendsProvider().fetch("unknown term", "US", "12m")
    assert result["available"] is False
    assert result["items"] == {}
    assert result["confidence"] == "Low"
