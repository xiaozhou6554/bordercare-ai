"""Third-party Taobao keyword search used as an alternate product-lead source."""
from __future__ import annotations

import re
from typing import Any

import httpx

from scr.domain.models import utc_now


class OneboundTaobaoSearchData:
    """Search public Taobao listings through Onebound.

    Taobao listings are retail product leads. They are not equivalent to 1688
    wholesale offers and do not provide verified supplier MOQ or wholesale price.
    """

    ENDPOINT = "https://api-gw.onebound.cn/taobao/item_search/"

    def __init__(self, api_key: str = "", api_secret: str = "", timeout: float = 15, client: httpx.Client | None = None) -> None:
        self.api_key, self.api_secret = api_key.strip(), api_secret.strip()
        self.client = client or httpx.Client(timeout=timeout)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def fetch(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any]) -> dict[str, Any]:
        if kind != "supplier_search":
            return self._empty("Taobao listings are available only as alternate product leads for supplier search.")
        if not self.configured:
            return self._empty("Set Onebound credentials to enable Taobao product search.", "Onebound Taobao API (not configured)")
        try:
            response = self.client.get(
                self.ENDPOINT,
                params={
                    "key": self.api_key,
                    "secret": self.api_secret,
                    "q": keyword[:100],
                    "page": max(1, min(100, int(params.get("page", 1)))),
                    "sort": str(params.get("sort", "")),
                    "cache": "yes",
                    "result_type": "json",
                    "lang": "cn",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("error_code", "")) != "0000":
                code = str(payload.get("error_code", "unknown"))
                return self._empty(f"Onebound Taobao search returned provider error code {code}.", "Onebound Taobao API")

            result = payload.get("items") or payload.get("item") or []
            if isinstance(result, dict):
                rows = result.get("item") or result.get("items") or [result]
            else:
                rows = result
            listings = [mapped for row in rows if isinstance(row, dict) and (mapped := self._map_item(row))]
            if not listings:
                return self._empty("Onebound returned no matching Taobao product listings.", "Onebound Taobao API")

            prices = [row["price"] for row in listings if row.get("price") is not None]
            nested = payload.get("items") if isinstance(payload.get("items"), dict) else {}
            total = payload.get("total_results") or payload.get("real_total_results") or nested.get("total_results") or nested.get("real_total_results")
            return {
                "available": True,
                "items": {
                    "suppliers": listings,
                    "supplier_count": len(listings),
                    "total_offer_count": total,
                    "price_range": [min(prices), max(prices)] if prices else None,
                },
                "source": "Onebound Taobao Item Search API",
                "confidence": "Medium",
                "evidence": [f"Onebound returned {len(listings)} Taobao product listings", "Third-party API; cached results may be returned"],
                "data_timestamp": utc_now(),
                "note": "These are Taobao public product-listing leads and prices, not 1688 wholesale quotes or verified supplier offers. MOQ and supplier credentials are not verified; displayed sales text is not independently audited.",
            }
        except (httpx.HTTPError, ValueError, TypeError):
            # Do not include request URLs: the query string contains the secret.
            return self._empty("Onebound Taobao search request failed. Check provider credentials, quota, and network.", "Onebound Taobao API")

    @staticmethod
    def _map_item(row: dict[str, Any]) -> dict[str, Any] | None:
        title = str(row.get("title") or row.get("subject") or "").strip()
        detail_url = row.get("detail_url")
        if not title or not detail_url:
            return None
        raw_price = str(row.get("promotion_price") or row.get("price") or "")
        match = re.search(r"\d+(?:\.\d+)?", raw_price.replace(",", ""))
        try:
            price = float(match.group()) if match else None
        except (TypeError, ValueError):
            price = None
        return {
            "name": row.get("seller_nick") or row.get("nick") or row.get("seller") or "Taobao seller",
            "platform": "Taobao",
            "listing_id": str(row.get("num_iid") or row.get("id") or "") or None,
            "product_name": title,
            "price": price,
            "currency": "CNY",
            "min_order_qty": None,
            "booked_count": None,
            "platform_sales_text": row.get("sales") or row.get("sales_text"),
            "store_rating": None,
            "total_revenue": None,
            "contact_info": None,
            "region": row.get("area") or row.get("location"),
            "product_url": detail_url,
            "image_url": row.get("pic_url"),
        }

    @staticmethod
    def _empty(note: str, source: str = "Onebound Taobao API") -> dict[str, Any]:
        return {"available": False, "items": {}, "source": source, "confidence": "Low", "evidence": [], "data_timestamp": utc_now(), "note": note}
