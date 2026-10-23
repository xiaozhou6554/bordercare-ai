"""Official TOP adapter for the public 1688 consignment-market search API."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from scr.domain.models import utc_now


class Alibaba1688ConsignmentData:
    """Search 1688 consignment offers via Alibaba's documented TOP API.

    The API is documented as free and not requiring seller authorization, but
    callers still need an Alibaba Open Platform app key and app secret.
    """

    API_METHOD = "alibaba.open.search.daixiao.offer.get"
    ENDPOINT = "https://eco.taobao.com/router/rest"

    def __init__(self, app_key: str = "", app_secret: str = "", timeout: float = 15, client: httpx.Client | None = None) -> None:
        self.app_key, self.app_secret = app_key.strip(), app_secret.strip()
        self.client = client or httpx.Client(timeout=timeout)

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def fetch(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any]) -> dict[str, Any]:
        if kind != "supplier_search":
            return self._empty("1688 source is for supplier and consignment-offer research; it does not represent overseas retail demand.")
        if not self.configured:
            return self._empty("Set ALIBABA_APP_KEY and ALIBABA_APP_SECRET to enable the official 1688 API.", "1688 Open Platform (not configured)")
        try:
            request_data = {
                "current_page": max(1, min(100, int(params.get("page", 1)))),
                "descend_order": True,
                "keywords": keyword[:100],
                "page_size": max(1, min(20, int(params.get("limit", 10)))),
                "sort_type": str(params.get("sort_type", "booked")),
            }
            query = self._common_params(request_data)
            response = self.client.post(self.ENDPOINT, data=query, headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
            response.raise_for_status()
            payload = response.json()
            if "error_response" in payload:
                return self._empty("1688 API rejected the request; verify app access, credentials, signature, and request limits.", "1688 Open Platform")
            wrapper = payload.get("alibaba_open_search_daixiao_offer_get_response", payload)
            if not wrapper.get("is_success"):
                return self._empty("1688 API returned an unsuccessful response.", "1688 Open Platform")
            result = wrapper.get("result") or {}
            offer_list = result.get("offer_list") or {}
            rows = offer_list.get("isv_offer_model") or []
            if isinstance(rows, dict):
                rows = [rows]
            suppliers = [item for row in rows if (item := self._map_offer(row))]
            if not suppliers:
                return self._empty("1688 returned no matching consignment offers.", "1688 Open Platform")
            prices = [row["price"] for row in suppliers if row.get("price") is not None]
            data = {
                "suppliers": suppliers,
                "supplier_count": len(suppliers),
                "total_offer_count": result.get("count"),
                "price_range": [min(prices), max(prices)] if prices else None,
            }
            return {
                "available": True, "items": data, "source": "1688 Open Platform · Consignment Search",
                "confidence": "Medium", "evidence": [f"1688 returned {len(suppliers)} supplier offers", "Official TOP API"],
                "data_timestamp": utc_now(),
                "note": "This is 1688 consignment supply-side data (supplier offer, quoted price, and platform-provided booked count where present). It is not overseas marketplace demand or independently verified sales volume.",
            }
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return self._empty(f"1688 API request failed ({type(exc).__name__}); check credentials, network, app permissions, and API availability.", "1688 Open Platform")

    def _common_params(self, request_data: dict[str, Any]) -> dict[str, str]:
        params = {
            "app_key": self.app_key,
            "format": "json",
            "method": self.API_METHOD,
            "sign_method": "hmac",
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
            "v": "2.0",
            "isv_daixiao_offer_request": json.dumps(request_data, ensure_ascii=False, separators=(",", ":")),
        }
        canonical = "".join(key + params[key] for key in sorted(params))
        signature = hmac.new(self.app_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.md5).hexdigest().upper()
        return {**params, "sign": signature}

    @staticmethod
    def _map_offer(row: dict[str, Any]) -> dict[str, Any] | None:
        title = str(row.get("subject") or "").strip()
        if not title:
            return None
        raw_price = str(row.get("price") or "")
        match = re.search(r"\d+(?:\.\d+)?", raw_price.replace(",", ""))
        try:
            price = float(match.group()) if match else None
        except (TypeError, ValueError):
            price = None
        try:
            booked_count = int(row["booked_count"]) if row.get("booked_count") is not None else None
        except (TypeError, ValueError):
            booked_count = None
        return {
            "name": row.get("company_name") or "1688 supplier",
            "platform": "1688",
            "listing_id": str(row.get("id")) if row.get("id") is not None else None,
            "product_name": title,
            "price": price,
            "currency": "CNY",
            "min_order_qty": None,
            "booked_count": booked_count,
            "store_rating": None,
            "total_revenue": None,
            "contact_info": None,
            "product_url": row.get("detail_url"),
            "image_url": row.get("image_url"),
            "posted_at": row.get("gmt_post"),
        }

    @staticmethod
    def _empty(note: str, source: str = "1688 Open Platform") -> dict[str, Any]:
        return {"available": False, "items": {}, "source": source, "confidence": "Low", "evidence": [], "data_timestamp": utc_now(), "note": note}
