from scr.infrastructure.product_market_router import AmazonFirstMarketData


class Provider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def fetch(self, kind, keyword, marketplace, params):
        self.calls.append((kind, keyword, marketplace, params))
        return self.result


def test_marketplace_research_always_uses_amazon():
    amazon = Provider({"available": True, "source": "Amazon search page"})
    supplier = Provider({"available": True, "source": "supplier"})
    router = AmazonFirstMarketData(amazon, supplier)

    result = router.fetch("market_overview", "pet fountain", "US", {})

    assert result["source"] == "Amazon search page"
    assert len(amazon.calls) == 1
    assert supplier.calls == []


def test_supplier_search_keeps_its_separate_provider_route():
    amazon = Provider({"available": True, "source": "Amazon"})
    supplier = Provider({"available": False, "source": "supplier primary"})
    alternate = Provider({"available": True, "source": "supplier alternate"})
    router = AmazonFirstMarketData(amazon, supplier, alternate)

    result = router.fetch("supplier_search", "pet fountain", "US", {})

    assert result["source"] == "supplier alternate"
    assert len(supplier.calls) == 1
    assert len(alternate.calls) == 1
    assert amazon.calls == []
