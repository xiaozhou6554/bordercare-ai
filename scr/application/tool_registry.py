from __future__ import annotations

import hashlib
import json
import logging
from time import perf_counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote_plus

from scr.domain.models import ToolOutput, utc_now
from scr.domain.ports import CachePort, MarketDataPort
from scr.domain.services import calculate_profit, calculate_score, group_keywords, keyword_competition

logger = logging.getLogger(__name__)


class BaseTool:
    name = ""

    def __init__(self, cache: CachePort, market_data: MarketDataPort, ttl_seconds: int) -> None:
        self.cache, self.market_data, self.ttl_seconds = cache, market_data, ttl_seconds

    def run(self, keyword: str, marketplace: str, params: dict[str, Any] | None = None) -> ToolOutput:
        params = params or {}
        payload = {"keyword": keyword, "marketplace": marketplace, "params": params,
                   "provider_scope": getattr(self.market_data, "cache_scope", "default")}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        key = f"{self.name}:{digest}"
        cached = self.cache.get(key)
        if cached is not None:
            logger.info("Research tool completed name=%s cached=true duration_ms=0", self.name)
            return ToolOutput(success=True, data=cached, cached=True)
        started = perf_counter()
        try:
            result = self.execute(keyword, marketplace, params)
            if result.success and result.data.get("available") is not False:
                self.cache.set(key, result.data, self.ttl_seconds)
            logger.info("Research tool completed name=%s success=%s cached=false duration_ms=%.1f", self.name, result.success, (perf_counter() - started) * 1000)
            return result
        except Exception as exc:
            logger.error("Research tool failed name=%s error_type=%s duration_ms=%.1f", self.name, type(exc).__name__, (perf_counter() - started) * 1000)
            return ToolOutput(success=False, data={"source": "本地计算", "confidence": "Low", "evidence": [], "data_timestamp": utc_now()}, error="本阶段暂不可用，请稍后重试。")

    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        raise NotImplementedError

    def metadata(self, data: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        fields = ("available", "source", "confidence", "evidence", "data_timestamp", "note", "marketplace", "source_url", "expires_at")
        return {**data, **{field: source[field] for field in fields if field in source}}


class ExternalDataTool(BaseTool):
    def load_sample(self, keyword: str, marketplace: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        source = self.market_data.fetch(self.name, keyword, marketplace, params)
        source = dict(source)
        source.setdefault("marketplace", marketplace)
        source.setdefault("expires_at", (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat(timespec="seconds"))
        source.setdefault("source_url", self._source_url(source, keyword, marketplace))
        return source.get("items", {}), source

    @staticmethod
    def _source_url(source: dict[str, Any], keyword: str, marketplace: str) -> str | None:
        items = source.get("items") or {}
        if isinstance(items, list):
            rows = items
        elif isinstance(items, dict):
            rows = next((items.get(key) for key in ("competitors", "suppliers", "raw_products") if isinstance(items.get(key), list)), [])
        else:
            rows = []
        if rows:
            first = rows[0]
            if isinstance(first, dict):
                url = first.get("item_url") or first.get("product_url") or first.get("detail_url")
                if url:
                    return str(url)
        query = quote_plus(keyword[:100])
        if "amazon" in str(source.get("source", "")).casefold():
            domains = {"US": "www.amazon.com", "UK": "www.amazon.co.uk", "DE": "www.amazon.de", "JP": "www.amazon.co.jp", "CA": "www.amazon.ca"}
            return f"https://{domains.get(marketplace, domains['US'])}/s?k={query}"
        if "google trends" in str(source.get("source", "")).casefold():
            geo = {"US": "US", "UK": "GB", "DE": "DE", "JP": "JP", "CA": "CA"}.get(marketplace, "")
            return f"https://trends.google.com/trends/explore?geo={geo}&q={query}"
        if "autocomplete" in str(source.get("source", "")).casefold():
            domains = {"US": "www.amazon.com", "UK": "www.amazon.co.uk", "DE": "www.amazon.de", "JP": "www.amazon.co.jp", "CA": "www.amazon.ca"}
            return f"https://{domains.get(marketplace, domains['US'])}/s?k={query}"
        return None


class MarketOverviewTool(ExternalDataTool):
    name = "market_overview"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        data, source = self.load_sample(keyword, marketplace, params)
        empty = {"total_product_count": 0, "avg_price": None, "median_price": None, "min_price": None, "max_price": None, "price_stddev": None, "avg_rating": None, "rating_stddev": None, "avg_review_count": None, "review_count_stddev": None, "brand_count": None, "brand_concentration": None, "top_brands": [], "new_product_count": None, "new_product_ratio": None}
        return ToolOutput(True, self.metadata({**empty, **data} if source["available"] and isinstance(data, dict) else empty, source))


class TrendAnalyzerTool(ExternalDataTool):
    name = "trend_analyzer"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        data, source = self.load_sample(keyword, marketplace, params)
        if not source["available"]:
            # A missing Trends response is unknown, not evidence of a stable market.
            data = {"direction": None, "growth_rate": None, "yoy_growth": None, "peak_months": [], "trend_data": [], "points": []}
        return ToolOutput(True, self.metadata(data, source))


class CategoryExplorerTool(BaseTool):
    name = "category_explorer"
    # Navigation taxonomy only. It is intentionally labelled as local reference
    # data; platform BSR and category-size estimates are not inferred here.
    TAXONOMIES = {
        "pet": {
            "aliases": ("宠物", "pet", "dog", "cat"),
            "root": {"name": "Pet Supplies", "children": [
                {"name": "Dog Supplies", "children": [{"name": "Fountains", "children": []}, {"name": "Feeders", "children": []}]},
                {"name": "Cat Supplies", "children": [{"name": "Water Fountains", "children": []}, {"name": "Litter", "children": []}]},
            ]},
        },
        "apparel": {
            "aliases": ("服装", "女装", "女性服装", "男装", "clothing", "apparel"),
            "root": {"name": "Clothing, Shoes & Jewelry", "children": [
                {"name": "Women's Clothing", "children": [{"name": "Dresses", "children": []}, {"name": "Tops, Tees & Blouses", "children": []}, {"name": "Activewear", "children": []}]},
                {"name": "Men's Clothing", "children": [{"name": "Shirts", "children": []}, {"name": "Pants", "children": []}]},
            ]},
        },
        "snacks": {
            "aliases": ("零食", "小吃", "snack", "chips", "cookies"),
            "root": {"name": "Grocery & Gourmet Food", "children": [
                {"name": "Snack Foods", "children": [{"name": "Chips & Crisps", "children": []}, {"name": "Cookies", "children": []}, {"name": "Nuts & Seeds", "children": []}]},
                {"name": "Candy & Chocolate", "children": [{"name": "Chocolate", "children": []}, {"name": "Candy", "children": []}]},
            ]},
        },
    }

    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        max_depth = max(1, min(5, int(params.get("depth", 3))))
        requested = str(params.get("category_name", params.get("node_name", ""))).casefold().strip()

        def find(node: dict[str, Any], name: str) -> dict[str, Any] | None:
            if node["name"].casefold() == name:
                return node
            for child in node.get("children", []):
                found = find(child, name)
                if found:
                    return found
            return None

        roots = [taxonomy["root"] for taxonomy in self.TAXONOMIES.values()]
        selected = next((found for root in roots if requested and (found := find(root, requested))), None)
        taxonomy_key = next((key for key, taxonomy in self.TAXONOMIES.items()
                             if any(alias.casefold() in keyword.casefold() for alias in taxonomy["aliases"])), None)
        root = self.TAXONOMIES[taxonomy_key]["root"] if taxonomy_key else None
        if selected is None and root is not None and not requested:
            selected = root
        if selected is None:
            return ToolOutput(False, {
                "tree": [], "note": "没有匹配的本地分类参考；当前未接入平台实时类目接口。",
                "source": "类目数据未接入", "confidence": "Low", "evidence": [], "data_timestamp": utc_now(),
            }, error="未找到可用的类目数据，请明确类目关键词或配置类目数据源。")

        def enrich(node: dict[str, Any], level: int) -> dict[str, Any]:
            node_id = "-".join(node["name"].casefold().split())
            children = [enrich(child, level + 1) for child in node.get("children", [])] if level < max_depth else []
            return {"node_id": node_id, "name": node["name"], "level": level,
                    "bsr_benchmark": None, "estimated_category_size": None, "children": children}

        return ToolOutput(True, {
            "tree": [enrich(selected, 0)],
            "note": "这是本地维护的分类导航参考，不代表平台实时类目；BSR 基准与类目规模未接入，未作估算。",
            "source": "本地分类参考（非平台实时数据）", "confidence": "Low", "marketplace": marketplace,
            "source_url": None, "expires_at": utc_now(), "evidence": ["本地分类配置"], "data_timestamp": utc_now(),
        })


class CompetitorAnalysisTool(ExternalDataTool):
    name = "competitor_analysis"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        data, source = self.load_sample(keyword, marketplace, params)
        rows = data.get("competitors", []) if source["available"] else []
        asins = {str(asin).upper() for asin in params.get("asins", [])}
        if asins:
            rows = [row for row in rows if str(row.get("asin") or row.get("listing_id") or "").upper() in asins]
        prices = [float(row["price"]) for row in rows if row.get("price") is not None]
        ratings = [float(row["rating"]) for row in rows if row.get("rating") is not None]
        stats = {"min": min(prices), "max": max(prices)} if prices else None
        return ToolOutput(True, self.metadata({"competitors": rows, "competitor_count": len(rows), "price_range": stats, "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None}, source))


class ReviewMinerTool(ExternalDataTool):
    name = "review_miner"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        data, source = self.load_sample(keyword, marketplace, params)
        if not source["available"]:
            data = {"avg_rating": None, "rating_distribution": {}, "sentiment_scores": {}, "top_praise_points": [], "top_pain_points": [], "improvement_suggestions": [], "review_count": 0}
        suggestions = {"noise": "优化运行降噪与隔振", "noisy": "改进电机与结构降噪", "leak": "加强密封结构与出厂检漏", "filter": "降低滤芯成本并提供替换装", "broken": "提升关键部件耐久度", "噪音": "优化运行降噪与隔振", "漏水": "加强密封结构与出厂检漏"}
        pains = data.get("top_pain_points", []) if isinstance(data, dict) else []
        mapped = [suggestion for pain in pains for key, suggestion in suggestions.items() if key.casefold() in str(pain).casefold()]
        if mapped:
            data["improvement_suggestions"] = list(dict.fromkeys([*data.get("improvement_suggestions", []), *mapped]))
        return ToolOutput(True, self.metadata(data, source))


class KeywordResearchTool(ExternalDataTool):
    name = "keyword_research"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        data, source = self.load_sample(keyword, marketplace, params)
        items = data.get("keywords", []) if source["available"] and isinstance(data, dict) else []
        if not items:
            candidates = [keyword, f"best {keyword}", f"{keyword} reviews", f"{keyword} buying guide"]
            items = [{"keyword": term, "search_volume": None, "competition_level": keyword_competition(term), "suggested_cpc": None, "is_long_tail": len(term.split()) >= 3} for term in dict.fromkeys(candidates)]
            source = {**source, "available": True, "source": "预设关键词扩展（非实时）", "confidence": "Low", "evidence": [], "note": "未获取到 Amazon 搜索建议；以下为本地规则扩展词，搜索量和 CPC 未提供。"}
        for item in items:
            levels = {"高": "high", "中": "medium", "低": "low", "未知": keyword_competition(item["keyword"])}
            item["competition_level"] = levels.get(item.get("competition_level"), item.get("competition_level")) or keyword_competition(item["keyword"])
            item.setdefault("search_volume", None)
            item.setdefault("suggested_cpc", None)
            item["is_long_tail"] = item.get("is_long_tail", len(item["keyword"].split()) >= 3)
        limit = max(1, min(100, int(params.get("max_keywords", 50))))
        selected = items[:limit]
        return ToolOutput(True, self.metadata({"keywords": selected, "groups": group_keywords(selected)}, source))


class ProfitCalculatorTool(BaseTool):
    name = "profit_calculator"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        if marketplace != "US":
            return ToolOutput(False, {
                "available": False,
                "marketplace": marketplace,
                "currency": None,
                "source": "本地计算",
                "confidence": "Low",
                "evidence": [],
                "note": "当前仅配置美国站 USD 简化费率；此站点未返回利润估算。",
                "data_timestamp": utc_now(),
            }, error="仅支持美国站 USD 利润测算；请勿将其他站点费用按美元费率换算。")
        defaults = {"selling_price": 29.99, "cost_price": 8.50, "weight_lb": 1.5, "length_in": 10, "width_in": 7, "height_in": 5, "shipping": 1.20, "tax_rate": 0.05, "size_tier": "large_standard", "currency": "USD"}
        defaults.update(params)
        data = calculate_profit(**{k: defaults[k] for k in ("selling_price", "cost_price", "weight_lb", "length_in", "width_in", "height_in", "shipping", "tax_rate", "size_tier", "currency")})
        return ToolOutput(True, {**data, "source": "技术设计说明书 FBA 费率示例与公式", "confidence": "Medium", "evidence": ["平台佣金=max(售价×15%, $0.30)", "配送费=拣配费+重量×重量处理费", "利润率=净利润/售价"], "data_timestamp": utc_now(), "note": "FBA 费率为简化估算，实际费用因平台、类目和尺寸政策变化。"})


class SupplierSearchTool(ExternalDataTool):
    name = "supplier_search"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        data, source = self.load_sample(keyword, marketplace, params)
        suppliers = data.get("suppliers", []) if source["available"] and isinstance(data, dict) else []
        platform = str(params.get("platform", "")).casefold()
        min_price, max_price = params.get("min_price"), params.get("max_price")
        min_moq = params.get("min_order_qty")
        suppliers = [row for row in suppliers if (not platform or platform in str(row.get("platform", "")).casefold())
                     and (min_price is None or row.get("price", 0) >= float(min_price))
                     and (max_price is None or row.get("price", float("inf")) <= float(max_price))
                     and (min_moq is None or row.get("min_order_qty", 0) >= int(min_moq))]
        suppliers.sort(key=lambda item: item.get("price", float("inf")))
        return ToolOutput(True, self.metadata({"suppliers": suppliers, "supplier_count": len(suppliers), "price_range": [suppliers[0]["price"], suppliers[-1]["price"]] if suppliers else None}, source))


class ProductScorerTool(BaseTool):
    name = "product_scorer"
    def execute(self, keyword: str, marketplace: str, params: dict[str, Any]) -> ToolOutput:
        scores = params.get("scores", {})
        result = calculate_score(scores)
        missing = result["missing_dimensions"]
        note = (
            f"当前仅覆盖 {result['score_coverage']:.0f}% 的评分维度；缺少 {', '.join(missing)}，不生成等级或建议。"
            if missing else "评分基于本次调研的可用数据映射，仍需结合来源证据复核。"
        )
        return ToolOutput(True, {
            **result,
            "source": "五维加权评分模型",
            "confidence": "Low" if missing else "Medium",
            "evidence": ["需求30%、竞争25%、利润20%、趋势15%、供应链10%"],
            "data_timestamp": utc_now(),
            "note": note,
        })


class ToolRegistry:
    def __init__(self, cache: CachePort, market_data: MarketDataPort, ttl_seconds: int) -> None:
        self.cache = cache
        classes = [MarketOverviewTool, TrendAnalyzerTool, CategoryExplorerTool, CompetitorAnalysisTool, ReviewMinerTool, KeywordResearchTool, ProfitCalculatorTool, SupplierSearchTool, ProductScorerTool]
        self.tools = {tool.name: tool(cache, market_data, ttl_seconds) for tool in classes}

    def get(self, name: str) -> BaseTool | None:
        return self.tools.get(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.tools)

    @property
    def cache_backend(self) -> str:
        return str(getattr(self.cache, "backend", "memory"))

    def cache_stats(self) -> dict[str, Any]:
        return self.cache.stats()

    def clear_cache(self) -> None:
        self.cache.clear()

