"""Route marketplace research to Amazon and supplier research to its adapter."""
from __future__ import annotations

from typing import Any


class AmazonFirstMarketData:
    """Use Amazon for marketplace research and optional providers for suppliers."""

    def __init__(self, amazon: Any, supplier_data: Any | None = None,
                 alternate_supplier_data: Any | None = None) -> None:
        self.amazon = amazon
        self.supplier_data = supplier_data
        self.alternate_supplier_data = alternate_supplier_data
        self.cache_scope = ":".join(("amazon-live-v1",
            f"supplier-{type(supplier_data).__name__ if supplier_data else 'none'}",
            f"alternate-{type(alternate_supplier_data).__name__ if alternate_supplier_data else 'none'}"))

    def fetch(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any]) -> dict[str, Any]:
        if kind != "supplier_search" or self.supplier_data is None:
            return self.amazon.fetch(kind, keyword, marketplace, params)
        result = self.supplier_data.fetch(kind, keyword, marketplace, params)
        if result.get("available") or self.alternate_supplier_data is None:
            return result
        return self.alternate_supplier_data.fetch(kind, keyword, marketplace, params)
