import hashlib
import hmac
import json

from scr.infrastructure.alibaba1688_data import Alibaba1688ConsignmentData


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.kwargs = None

    def post(self, *args, **kwargs):
        self.kwargs = kwargs
        return FakeResponse(self.payload)


def test_1688_official_supplier_search_normalizes_offers_and_signs_request():
    client = FakeClient({"alibaba_open_search_daixiao_offer_get_response": {
        "is_success": True,
        "result": {"count": 20, "offer_list": {"isv_offer_model": [
            {"id": 123, "subject": "USB-C travel adapter", "company_name": "Shenzhen Supplier", "price": "12.50-18.00", "booked_count": 85, "detail_url": "https://detail.1688.com/offer/123.html"},
            {"id": 124, "subject": "Universal plug", "company_name": "Other Supplier", "price": "9.9"},
        ]}},
    }})
    adapter = Alibaba1688ConsignmentData("app-key", "app-secret", client=client)
    result = adapter.fetch("supplier_search", "travel adapter", "US", {"limit": 10})

    assert result["available"]
    assert result["source"].startswith("1688 Open Platform")
    assert result["items"]["total_offer_count"] == 20
    assert result["items"]["supplier_count"] == 2
    assert result["items"]["suppliers"][0]["price"] == 12.5
    assert result["items"]["suppliers"][0]["booked_count"] == 85
    assert result["items"]["suppliers"][0]["min_order_qty"] is None
    assert "not overseas marketplace demand" in result["note"]

    sent = client.kwargs["data"]
    assert sent["method"] == adapter.API_METHOD
    assert sent["sign_method"] == "hmac"
    unsigned = {key: value for key, value in sent.items() if key != "sign"}
    canonical = "".join(key + unsigned[key] for key in sorted(unsigned))
    expected = hmac.new(b"app-secret", canonical.encode(), hashlib.md5).hexdigest().upper()
    assert sent["sign"] == expected
    request = json.loads(sent["isv_daixiao_offer_request"])
    assert request["keywords"] == "travel adapter"
    assert request["page_size"] == 10


def test_1688_api_adapter_requires_credentials_and_only_serves_supplier_search():
    adapter = Alibaba1688ConsignmentData()
    missing = adapter.fetch("supplier_search", "charger", "US", {})
    assert not missing["available"]
    assert "ALIBABA_APP_KEY" in missing["note"]
    unsupported = Alibaba1688ConsignmentData("key", "secret").fetch("market_overview", "charger", "US", {})
    assert not unsupported["available"]
