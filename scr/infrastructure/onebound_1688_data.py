"""Third-party 1688 product search adapter using Onebound's documented API."""
from __future__ import annotations

import re
from typing import Any

import httpx

from scr.domain.models import utc_now


class Onebound1688SearchData:
    """Search public 1688 product listings through Onebound.

    This is a paid third-party data source. Its API key and secret are separate
    from Alibaba/TOP credentials and should only be configured by the user.
    """

    ENDPOINT = "https://api-gw.onebound.cn/1688/item_search_new/"

    def __init__(self, api_key: str = "", api_secret: str = "", timeout: float = 15, client: httpx.Client | None = None) -> None:
        self.api_key, self.api_secret = api_key.strip(), api_secret.strip()
        self.client = client or httpx.Client(timeout=timeout)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def fetch(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any]) -> dict[str, Any]:
        if kind != "supplier_search":
            return self._empty("1688 supplier listings are available only for supplier search.")
        if not self.configured:
            return self._empty("Set ONEBOUND_API_KEY and ONEBOUND_API_SECRET to enable the paid 1688 search provider.", "Onebound 1688 API (not configured)")
        try:
            response = self.client.get(
                self.ENDPOINT,
                params={
                    "key": self.api_key,
                    "secret": self.api_secret,
                    "q": keyword[:100],
                    "page": max(1, min(100, int(params.get("page", 1)))),
                    "sort": str(params.get("sort", "normal")),
                    "cache": "yes",
                    "result_type": "json",
                    "lang": "cn",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("error_code", "")) != "0000":
                code = str(payload.get("error_code", "unknown"))
                return self._empty(f"Onebound 1688 search returned provider error code {code}.", "Onebound 1688 API")

            rows = payload.get("item") or payload.get("items") or []
            if isinstance(rows, dict):
                rows = [rows]
            suppliers = [mapped for row in rows if isinstance(row, dict) and (mapped := self._map_offer(row))]
            if not suppliers:
                return self._empty("Onebound returned no matching 1688 product listings.", "Onebound 1688 API")

            prices = [row["price"] for row in suppliers if row.get("price") is not None]
            data = {
                "suppliers": suppliers,
                "supplier_count": len(suppliers),
                "total_offer_count": payload.get("total_results") or payload.get("total"),
                "price_range": [min(prices), max(prices)] if prices else None,
            }
            return {
                "available": True,
                "items": data,
                "source": "Onebound 1688 Product Search API",
                "confidence": "Medium",
                "evidence": [f"Onebound returned {len(suppliers)} 1688 listings", "Third-party API; cached results may be returned"],
                "data_timestamp": utc_now(),
                "note": "Supplier listing and prices are third-party sourced 1688 data. Platform-reported sales are shown as supplied and are not independently verified or overseas retail demand.",
            }
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            # Do not include request URLs: the query string contains the secret.
            return self._empty(f"Onebound 1688 API request failed ({type(exc).__name__}). Check provider credentials, quota, and network.", "Onebound 1688 API")

    @staticmethod
    def _map_offer(row: dict[str, Any]) -> dict[str, Any] | None:
        title = str(row.get("title") or row.get("subject") or "").strip()
        detail_url = row.get("detail_url")
        if not title or not detail_url or "/offer/.html" in str(detail_url):
            return None
        raw_price = str(row.get("promotion_price") or row.get("price") or "")
        match = re.search(r"\d+(?:\.\d+)?", raw_price.replace(",", ""))
        try:
            price = float(match.group()) if match else None
        except (TypeError, ValueError):
            price = None
        return {
            "name": row.get("seller_nick") or row.get("company_name") or "1688 supplier",
            "platform": "1688",
            "listing_id": str(row.get("num_iid") or row.get("id") or "") or None,
            "product_name": title,
            "price": price,
            "currency": "CNY",
            "min_order_qty": row.get("min_num"),
            "booked_count": None,
            "platform_sales_text": row.get("sales"),
            "store_rating": None,
            "total_revenue": None,
            "contact_info": None,
            "region": row.get("area"),
            "product_url": detail_url,
            "image_url": row.get("pic_url"),
        }

    @staticmethod
    def _empty(note: str, source: str = "Onebound 1688 API") -> dict[str, Any]:
        return {"available": False, "items": {}, "source": source, "confidence": "Low", "evidence": [], "data_timestamp": utc_now(), "note": note}
