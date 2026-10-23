"""Google Trends adapter based on the supplied provider example.

This is an infrastructure adapter: it makes one best-effort request, does not
retry rate limits, and returns unavailable instead of inventing observations.
"""
from __future__ import annotations

import os
import statistics
from typing import Any

from scr.domain.models import utc_now


MARKET_CONFIG = {
    "US": {"geo": "", "hl": "en-US", "label": "United States"},
    "UK": {"geo": "GB", "hl": "en-GB", "label": "United Kingdom"},
    "DE": {"geo": "DE", "hl": "de-DE", "label": "Germany"},
    "JP": {"geo": "JP", "hl": "ja-JP", "label": "Japan"},
    "CA": {"geo": "CA", "hl": "en-CA", "label": "Canada"},
}
TIMEFRAMES = {"3m": "today 3-m", "6m": "today 6-m", "12m": "today 12-m", "5y": "today 5-y"}


class GoogleTrendsProvider:
    def fetch(self, keyword: str, marketplace: str = "US", timeframe: str = "12m") -> dict[str, Any]:
        market = MARKET_CONFIG.get(marketplace)
        if not market:
            return self._empty("Google Trends does not support this marketplace.")
        pytrends_timeframe = TIMEFRAMES.get(timeframe, TIMEFRAMES["12m"])
        try:
            from pytrends.request import TrendReq

            proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            request_args = {"proxies": {"https": proxy, "http": proxy}} if proxy else {}
            client = TrendReq(
                hl=market["hl"], tz=0, timeout=15,
                retries=0, backoff_factor=0, requests_args=request_args,
            )
            client.build_payload([keyword], cat=0, timeframe=pytrends_timeframe, geo=market["geo"], gprop="")
            frame = client.interest_over_time()
            if frame is None or frame.empty or keyword not in frame.columns:
                return self._empty("Google Trends returned no usable series.")
            series = frame[keyword]
            if "isPartial" in frame.columns:
                series = series[~frame["isPartial"].astype(bool)]
            monthly = series.groupby(series.index.to_period("M")).mean().dropna()
            if monthly.empty:
                return self._empty("Google Trends returned no usable monthly points.")

            points = [{"date": str(period), "value": round(float(value), 1)} for period, value in monthly.items()]
            values = [point["value"] for point in points]
            midpoint = len(values) // 2
            earlier = values[:midpoint] if midpoint else values
            recent = values[midpoint:] if midpoint else values
            earlier_avg = statistics.mean(earlier) if earlier else 0.0
            recent_avg = statistics.mean(recent) if recent else 0.0
            growth = round((recent_avg - earlier_avg) / earlier_avg * 100, 1) if earlier_avg else None
            direction = "up" if growth is not None and growth > 10 else "down" if growth is not None and growth < -10 else "stable"
            yoy_growth = None
            if len(values) >= 24:
                last_year, previous_year = values[-12:], values[-24:-12]
                previous_avg = statistics.mean(previous_year)
                yoy_growth = round((statistics.mean(last_year) / previous_avg - 1) * 100, 1) if previous_avg else None
            peaks = sorted(points, key=lambda point: point["value"], reverse=True)[:3]
            peak_months = [{"rank": index, "month": int(point["date"].split("-")[1]),
                            "year": int(point["date"].split("-")[0]), "label": point["date"], "value": point["value"]}
                           for index, point in enumerate(peaks, 1)]
            evidence = [f"Google Trends returned {len(points)} monthly interest values (0-100 relative index, not search volume)",
                        f"First-half and second-half averages: {earlier_avg:.1f} -> {recent_avg:.1f}; period change {growth if growth is not None else 'unavailable'}%"]
            if yoy_growth is not None:
                evidence.append(f"Latest 12-month average compared with the prior 12 months: {yoy_growth}%")
            return {
                "available": True,
                "items": {"direction": direction, "growth_rate": growth, "period_growth": growth,
                          "yoy_growth": yoy_growth, "peak_months": peak_months,
                          "trend_data": values, "points": points, "data": points,
                          "formula": f"(second-half average {recent_avg:.1f} - first-half average {earlier_avg:.1f}) / first-half average * 100"},
                "source": f"Google Trends ({market['label']}, {timeframe})", "confidence": "Medium",
                "evidence": evidence, "data_timestamp": utc_now(),
                "note": "Interest is a relative index for the selected region and timeframe, not search volume. Period change compares the averages of the first and second halves; it is not year-over-year growth. Google Trends may sample results; wait before retrying after HTTP 429.",
            }
        except ImportError:
            return self._empty("pytrends is not installed in the active environment.")
        except Exception as exc:
            # Exception strings can include proxy credentials or request URLs; expose type only.
            return self._empty(f"Google Trends is unavailable ({type(exc).__name__}); no trend values were generated.")

    @staticmethod
    def _empty(note: str) -> dict[str, Any]:
        return {"available": False, "items": {}, "source": "Google Trends", "confidence": "Low",
                "evidence": [], "data_timestamp": utc_now(), "note": note}
