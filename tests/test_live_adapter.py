from scr.infrastructure.amazon_data import LiveMarketData
from scr.infrastructure.cache import MemoryTTLCache
from scr.application.tool_registry import ToolRegistry


class FakeCrawler:
    def get(self, url: str) -> str:
        return """<html><div data-component-type='s-search-result' data-asin='B000000001'>
        <h2><span>Sample stainless pet fountain</span></h2>
        <span class='a-price'><span class='a-offscreen'>$29.99</span></span>
        <span class='a-icon-alt'>4.5 out of 5 stars</span>
        <span class='s-underline-text'>1,234</span></div></html>"""


def test_live_amazon_search_extracts_only_present_fields() -> None:
    provider = LiveMarketData(crawler=FakeCrawler())
    result = provider.fetch("market_overview", "pet fountain", "US", {})
    data = result["items"]
    assert result["available"]
    assert data["total_product_count"] == 1
    assert data["avg_price"] == 29.99
    assert data["avg_rating"] == 4.5
    assert data["avg_review_count"] == 1234
    assert data["price_stddev"] == 0.0
    assert data["rating_stddev"] == 0.0
    assert data["brand_count"] is None
    assert "未从页面取得" in result["note"]


def test_amazon_search_extracts_product_links_and_images_and_deduplicates_asins() -> None:
    class SearchCrawler:
        def get(self, url: str) -> str:
            card = """<div data-component-type='s-search-result' data-asin='B000000001'>
            <h2><a href='/dp/B000000001'><span>Sample product</span></a></h2>
            <img class='s-image' src='https://images.example/product.jpg'></div>"""
            return f"<html>{card}{card}</html>"

    result = LiveMarketData(crawler=SearchCrawler()).fetch("competitor_analysis", "sample", "US", {})
    products = result["items"]["competitors"]
    assert len(products) == 1
    assert products[0]["product_url"] == "https://www.amazon.com/dp/B000000001"
    assert products[0]["image_url"] == "https://images.example/product.jpg"
    assert products[0]["bsr"] is None
    assert products[0]["estimated_sales"] is None
    assert "销量未提供，未估算" in result["note"]


def test_live_market_data_delegates_trends_with_requested_timeframe() -> None:
    class Trends:
        def __init__(self):
            self.calls = []

        def fetch(self, keyword, marketplace, timeframe):
            self.calls.append((keyword, marketplace, timeframe))
            return {"available": True, "items": {"direction": "up", "points": []}, "source": "Google Trends",
                    "confidence": "Medium", "evidence": [], "data_timestamp": "now", "note": ""}

    trends = Trends()
    result = LiveMarketData(trends=trends).fetch("trend_analyzer", "pet fountain", "US", {"timeframe": "5y"})
    assert trends.calls == [("pet fountain", "US", "5y")]
    assert result["available"] is True


def test_unavailable_trends_remain_unknown_through_agent_tool():
    registry = ToolRegistry(MemoryTTLCache(), LiveMarketData(trends=type("Unavailable", (), {
        "fetch": lambda self, keyword, marketplace, timeframe: {
            "available": False, "items": {}, "source": "Google Trends", "confidence": "Low",
            "evidence": [], "data_timestamp": "now", "note": "temporarily unavailable",
        }
    })()), 60)
    result = registry.get("trend_analyzer").run("pet fountain", "US", {})
    assert result.success
    assert result.data["available"] is False
    assert result.data["direction"] is None
    assert result.data["growth_rate"] is None


def test_live_search_empty_response_is_not_filled_with_estimates() -> None:
    result = LiveMarketData(crawler=type("EmptyCrawler", (), {"get": lambda self, url: "<html></html>"})()).fetch("competitor_analysis", "unknown", "US", {})
    assert result["available"] is False
    assert result["confidence"] == "Low"


class ProductDetailCrawler:
    def get(self, url: str) -> str:
        return """<html><span id='productTitle'>Filtered Cat Fountain</span>
        <div id='corePrice_feature_div'><span class='a-offscreen'>$31.50</span></div>
        <span id='acrPopover' title='4.6 out of 5 stars'></span><span id='acrCustomerReviewText'>2,105 ratings</span>
        <a id='bylineInfo'>Visit the Aqua brand Store</a><div id='feature-bullets'><li>Quiet pump</li><li>Easy cleaning</li></div>
        <div id='altImages'><img/><img/><img/></div><div id='detailBullets_feature_div'>Best Sellers Rank: #1,234</div></html>"""


def test_explicit_asin_detail_extracts_visible_fields_and_never_invents_sales() -> None:
    result = LiveMarketData(crawler=ProductDetailCrawler()).fetch(
        "competitor_analysis", "cat fountain", "US", {"asins": ["B000000001"]}
    )
    product = result["items"]["competitors"][0]
    assert product["asin"] == "B000000001"
    assert product["price"] == 31.5
    assert product["rating"] == 4.6
    assert product["review_count"] == 2105
    assert product["bsr"] == 1234
    assert product["estimated_sales"] is None
    assert product["listing_quality_score"] == 60


def test_review_limit_is_honored() -> None:
    class ReviewsCrawler:
        def get(self, url: str) -> str:
            return """<div data-hook='review'><i data-hook='review-star-rating'>5.0 out of 5 stars</i><span data-hook='review-body'>Great</span></div>
            <div data-hook='review'><i data-hook='review-star-rating'>4.0 out of 5 stars</i><span data-hook='review-body'>Easy clean</span></div>
            <div data-hook='review'><i data-hook='review-star-rating'>1.0 out of 5 stars</i><span data-hook='review-body'>Broken pump</span></div>"""
    result = LiveMarketData(crawler=ReviewsCrawler()).fetch("review_miner", "fountain", "US", {"asins": ["B000000001"], "max_reviews": 2})
    assert result["items"]["review_count"] == 2
    assert result["items"]["avg_rating"] == 4.5
