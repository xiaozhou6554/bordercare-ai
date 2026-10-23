from __future__ import annotations

from typing import Any

from scr.domain.ports import MarketDataPort
from scr.domain.models import utc_now

DEMO_ALIASES = ("宠物饮水机", "pet water fountain", "cat water fountain", "cat fountain")


class HonestDemoMarketData:
    """Clearly labeled prototype fixture; never presented as live marketplace data."""
    cache_scope = "demo-fixtures-v1"

    def fetch(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any]) -> dict[str, Any]:
        if not any(alias.casefold() in keyword.casefold() for alias in DEMO_ALIASES):
            return {
                "available": False, "items": [], "note": "当前本地演示数据仅覆盖宠物饮水机示例；未接入实时平台数据。",
                "source": "本地演示数据（无匹配样本）", "confidence": "Low", "evidence": [], "data_timestamp": utc_now(),
            }
        samples = {
            "market_overview": {"total_product_count": 1240, "avg_price": 34.99, "median_price": 29.99, "min_price": 18.99, "max_price": 89.99, "avg_rating": 4.3, "avg_review_count": 8620, "brand_count": 86, "brand_concentration": 38, "new_product_ratio": 22, "top_brands": ["PETLIBRO", "Veken", "Catit"]},
            "trend_analyzer": {"direction": "up", "growth_rate": 18.6, "yoy_growth": 18.6, "peak_months": ["11月", "12月", "1月"], "trend_data": [38, 40, 42, 45, 44, 48, 52, 55, 58, 63, 71, 78]},
            "competitor_analysis": {"competitors": [
                {"asin": "DEMO-001", "title": "不锈钢循环宠物饮水机 2.5L", "price": 32.99, "rating": 4.4, "review_count": 12850, "bsr": 856, "estimated_sales": 3200, "brand": "演示品牌 A", "listing_quality_score": 88},
                {"asin": "DEMO-002", "title": "智能 LED 宠物饮水机 2.4L", "price": 26.99, "rating": 4.3, "review_count": 45200, "bsr": 312, "estimated_sales": 5800, "brand": "演示品牌 B", "listing_quality_score": 82},
                {"asin": "DEMO-003", "title": "静音花朵喷泉饮水机 3L", "price": 29.99, "rating": 4.5, "review_count": 22100, "bsr": 540, "estimated_sales": 4100, "brand": "演示品牌 C", "listing_quality_score": 76},
            ]},
            "review_miner": {"avg_rating": 4.3, "rating_distribution": {"5": 62, "4": 21, "3": 9, "2": 4, "1": 4}, "sentiment_scores": {"positive": 62, "neutral": 21, "negative": 17}, "top_praise_points": ["运行安静", "容量较大", "便于清洗"], "top_pain_points": ["水泵噪音", "指示灯过亮", "滤芯成本"], "improvement_suggestions": ["优化水泵降噪", "增加夜灯关闭选项", "提供滤芯组合装"], "review_count": 1850},
            "keyword_research": {"keywords": [
                {"keyword": "cat water fountain", "search_volume": 74000, "competition_level": "高", "suggested_cpc": 1.12, "is_long_tail": False},
                {"keyword": "stainless steel cat fountain", "search_volume": 12400, "competition_level": "低", "suggested_cpc": 0.38, "is_long_tail": True},
                {"keyword": "quiet cat water fountain", "search_volume": 9800, "competition_level": "低", "suggested_cpc": 0.42, "is_long_tail": True},
            ]},
            "supplier_search": {"suppliers": [
                {"name": "演示供应商 A（虚构）", "platform": "1688（演示）", "price": 48.0, "min_order_qty": 500, "store_rating": 4.8, "total_revenue": "演示数据", "contact_info": "无真实联系方式", "product_url": ""},
                {"name": "演示供应商 B（虚构）", "platform": "Alibaba（演示）", "price": 8.1, "min_order_qty": 500, "store_rating": 4.5, "total_revenue": "演示数据", "contact_info": "无真实联系方式", "product_url": ""},
            ]},
        }
        return {
            "available": True, "items": samples.get(kind, {}),
            "note": "仅用于界面与流程演示的预置样例，不是实时抓取或可用于采购决策的数据。",
            "source": "本地预置演示样例（非实时）", "confidence": "Low", "evidence": ["原型演示夹具"], "data_timestamp": utc_now(),
        }


