"""Respectful public-page adapters. No CAPTCHA, proxy rotation, or block evasion."""
from __future__ import annotations

import json
import random
import re
import statistics
import time
from typing import Any
from urllib.parse import quote_plus
import threading

import httpx
from lxml import html

from scr.domain.models import utc_now
from scr.infrastructure.google_trends import GoogleTrendsProvider

DOMAINS = {"US": "www.amazon.com", "UK": "www.amazon.co.uk", "DE": "www.amazon.de", "JP": "www.amazon.co.jp", "CA": "www.amazon.ca"}


class RespectfulCrawler:
    def __init__(self, timeout: float = 12, delay: float = 2.0, retries: int = 3) -> None:
        self.timeout, self.delay, self.retries = timeout, delay, retries
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ProductResearchAgent/1.0; +local-research)",
            "Accept-Language": "en-US,en;q=0.8",
        })
        self._last_request = 0.0
        self._request_lock = threading.Lock()
        self.last_status: int | None = None
        self.last_response_bytes = 0
        self.last_final_url = ""
        self.last_error = ""
        self.request_attempts = 0

    def get(self, url: str) -> str | None:
        self.last_error = ""
        self.last_status = None
        self.last_response_bytes = 0
        self.last_final_url = ""
        self.request_attempts = 0
        for attempt in range(self.retries):
            try:
                with self._request_lock:
                    wait = self.delay + random.random() * 0.25 - (time.monotonic() - self._last_request)
                    if wait > 0:
                        time.sleep(wait)
                    response = self.client.get(url)
                    self._last_request = time.monotonic()
                    self.request_attempts += 1
                    self.last_status = response.status_code
                    self.last_response_bytes = len(response.content)
                    self.last_final_url = str(response.url)
                    if response.status_code in (403, 404):
                        self.last_error = f"HTTP {response.status_code}"
                        return None
                    if response.status_code == 429 or response.status_code >= 500:
                        self.last_error = f"HTTP {response.status_code}"
                        if attempt + 1 < self.retries:
                            time.sleep(2 ** attempt)
                            continue
                        return None
                    response.raise_for_status()
                    if re.search(r"captcha|robot check|validatecaptcha", response.text[:30000], re.I):
                        self.last_error = "Amazon returned a CAPTCHA or Robot Check page"
                        return None
                    return response.text
            except httpx.HTTPError as exc:
                self.last_error = type(exc).__name__
                if attempt + 1 == self.retries:
                    return None
                time.sleep(2 ** attempt)
        return None


class LiveMarketData:
    def __init__(self, crawler: RespectfulCrawler | None = None, trends: GoogleTrendsProvider | None = None) -> None:
        self.crawler = crawler or RespectfulCrawler()
        self.trends = trends or GoogleTrendsProvider()

    def fetch(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any]) -> dict[str, Any]:
        if marketplace not in DOMAINS:
            return self._empty("不支持的站点标识")
        if kind in {"market_overview", "competitor_analysis"}:
            return self._search(kind, keyword, marketplace, params)
        if kind == "keyword_research":
            return self._suggestions(keyword, marketplace)
        if kind == "trend_analyzer":
            return self._trend(keyword, marketplace, params)
        if kind == "review_miner":
            return self._reviews(params.get("asins", []), marketplace, params.get("max_reviews", 50))
        if kind == "supplier_search":
            return self._empty("未配置经授权的 1688/Alibaba 供应商 API；未抓取或生成供应商信息。", "供应商数据源未配置")
        return self._empty("该阶段没有配置可用的实时数据提供方。")

    @staticmethod
    def _envelope(items: Any, source: str, evidence: list[str], confidence: str = "Medium", note: str = "") -> dict[str, Any]:
        return {"available": True, "items": items, "source": source, "confidence": confidence, "evidence": evidence, "data_timestamp": utc_now(), "note": note}

    @staticmethod
    def _empty(note: str, source: str = "实时数据不可用") -> dict[str, Any]:
        return {"available": False, "items": {}, "source": source, "confidence": "Low", "evidence": [], "data_timestamp": utc_now(), "note": note}

    def _search(self, kind: str, keyword: str, marketplace: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        domain = DOMAINS[marketplace]
        explicit_asins = [str(value).upper() for value in (params or {}).get("asins", []) if re.fullmatch(r"[A-Z0-9]{10}", str(value).upper())]
        if kind == "competitor_analysis" and explicit_asins:
            products = [product for asin in dict.fromkeys(explicit_asins[:20]) if (product := self._product_detail(asin, domain))]
            if not products:
                return self._empty("Specified ASIN pages returned no parseable product details.", "Amazon ASIN detail pages")
            return self._envelope({"competitors": products, "competitor_count": len(products)}, "Amazon ASIN 商品详情页", [f"解析指定 ASIN {len(products)} 个", "销量未提供，未估算"], "Medium", "BSR 仅在页面明确提供时填入；当前未获得可验证的销量数据，未进行估算。Listing 质量分是可见内容完整度估计值。")
        url = f"https://{domain}/s?k={quote_plus(keyword)}"
        page = self.crawler.get(url)
        if not page:
            diagnostic = self._crawler_diagnostic()
            note = "Amazon 页面未返回可用数据（可能是网络不可达或平台拒绝请求）。"
            if diagnostic:
                note += f" 采集诊断：{diagnostic}"
            return self._empty(note, "Amazon 搜索结果页")
        try:
            doc = html.fromstring(page)
            products = []
            seen_asins: set[str] = set()
            for card in doc.xpath("//*[@data-component-type='s-search-result'] | //div[contains(@class,'s-result-item') and @data-asin]"):
                asin = card.get("data-asin", "").strip()
                if not asin or asin in seen_asins:
                    continue
                seen_asins.add(asin)
                title = " ".join(card.xpath(".//h2//span//text()" )).strip()
                price_text = "".join(card.xpath(".//*[contains(@class,'a-price')]//*[contains(@class,'a-offscreen')]/text()"))
                rating_text = " ".join(card.xpath(".//*[contains(@class,'a-icon-alt')]/text()"))
                reviews_text = " ".join(card.xpath(".//*[contains(@class,'s-underline-text')]/text()"))
                try:
                    price = float("".join(ch for ch in price_text if ch.isdigit() or ch in ".," ).replace(",", ""))
                except ValueError:
                    price = None
                try:
                    rating = float(rating_text.split(" ")[0].replace(",", "."))
                except (ValueError, IndexError):
                    rating = None
                try:
                    review_count = int("".join(ch for ch in reviews_text if ch.isdigit()))
                except ValueError:
                    review_count = None
                if asin and title:
                    href = next(iter(card.xpath(".//h2//a/@href")), "")
                    image_url = next(iter(card.xpath(".//img[contains(@class,'s-image')]/@src | .//img[contains(@class,'s-image')]/@data-src")), "")
                    product_url = f"https://{domain}{href}" if href.startswith("/") else href or f"https://{domain}/dp/{asin}"
                    products.append({"asin": asin, "title": title, "price": price, "rating": rating, "review_count": review_count,
                                     "image_url": image_url or None, "product_url": product_url,
                                     "bsr": None, "estimated_sales": None, "brand": None, "listing_quality_score": None})
            if not products:
                return self._empty("Amazon 返回页面但未解析到商品条目；页面结构可能变化，未填充估算结果。", "Amazon 搜索结果页")
            if kind == "competitor_analysis":
                return self._envelope(
                    {"competitors": products, "competitor_count": len(products)},
                    "Amazon 搜索结果页",
                    [f"解析到 {len(products)} 条商品卡片", f"站点 {marketplace}", "销量未提供，未估算"],
                    note="销量未提供，未估算。BSR 和品牌仅在页面明确提供时展示。",
                )
            prices = [p["price"] for p in products if p["price"] is not None]
            ratings = [p["rating"] for p in products if p["rating"] is not None]
            reviews = [p["review_count"] for p in products if p["review_count"] is not None]
            data = {"total_product_count": len(products), "avg_price": round(statistics.mean(prices), 2) if prices else None,
                    "median_price": round(statistics.median(prices), 2) if prices else None, "min_price": min(prices) if prices else None,
                    "max_price": max(prices) if prices else None, "price_stddev": round(statistics.pstdev(prices), 2) if len(prices) > 1 else (0.0 if prices else None),
                    "avg_rating": round(statistics.mean(ratings), 2) if ratings else None,
                    "rating_stddev": round(statistics.pstdev(ratings), 2) if len(ratings) > 1 else (0.0 if ratings else None),
                    "avg_review_count": round(statistics.mean(reviews)) if reviews else None,
                    "review_count_stddev": round(statistics.pstdev(reviews), 2) if len(reviews) > 1 else (0.0 if reviews else None), "brand_count": None,
                    "brand_concentration": None, "new_product_ratio": None, "top_brands": [],
                    "raw_products": products}
            return self._envelope(data, "Amazon 搜索结果页（当前页可见商品）", [f"实际解析商品 {len(products)} 条", "均值和中位数基于当前页面可见字段"], "Medium", "品牌集中度、新品占比、BSR 与销量未从页面取得，未推算填充。")
        except (ValueError, TypeError):
            return self._empty("Amazon 页面解析失败；未填充估算结果。", "Amazon 搜索结果页")

    def _product_detail(self, asin: str, domain: str) -> dict[str, Any] | None:
        page = self.crawler.get(f"https://{domain}/dp/{asin}")
        if not page:
            return None
        try:
            doc = html.fromstring(page)
            def first(xpath: str) -> str | None:
                values = doc.xpath(xpath)
                value = " ".join(str(item).strip() for item in values if str(item).strip())
                return value or None
            title = first("//*[@id='productTitle']/text()")
            if not title:
                return None
            price_text = first("//*[@id='corePrice_feature_div']//*[contains(@class,'a-offscreen')]/text() | //*[@id='priceblock_ourprice']/text()") or ""
            rating_text = first("//*[@id='acrPopover']/@title | //*[@data-hook='rating-out-of-text']/text()") or ""
            review_text = first("//*[@id='acrCustomerReviewText']/text()") or ""
            brand = first("//*[@id='bylineInfo']/text() | //*[@id='brand']/text()")
            bsr_text = " ".join(doc.xpath("//text()"))
            bullets = doc.xpath("//*[@id='feature-bullets']//li[not(contains(@class,'aok-hidden'))]")
            images = doc.xpath("//*[@id='altImages']//img | //*[@id='landingImage']")
            has_video = bool(doc.xpath("//*[contains(@class,'videoBlock') or contains(@class,'video-block') or @data-video-url]"))
            has_aplus = bool(doc.xpath("//*[contains(@id,'aplus') or contains(@class,'aplus')]"))
            try:
                price = float("".join(char for char in price_text if char.isdigit() or char in ".,").replace(",", ""))
            except ValueError:
                price = None
            rating_match = re.search(r"\d+(?:[.,]\d+)?", rating_text)
            review_match = re.search(r"[\d,]+", review_text)
            bsr_match = re.search(r"#([\d,]+)", bsr_text)
            score_parts = [bool(title), bool(bullets), len(images) >= 3, has_video, has_aplus]
            return {"asin": asin, "title": title.strip(), "price": price,
                    "rating": float(rating_match.group(0).replace(",", ".")) if rating_match else None,
                    "review_count": int(review_match.group(0).replace(",", "")) if review_match else None,
                    "bsr": int(bsr_match.group(1).replace(",", "")) if bsr_match else None,
                    "estimated_sales": None, "brand": brand,
                    "listing_quality_score": round(sum(score_parts) / len(score_parts) * 100),
                    "listing_quality_signals": {"title": bool(title), "bullets": bool(bullets), "images": len(images), "video": has_video, "aplus": has_aplus}}
        except (ValueError, TypeError):
            return None

    def _suggestions(self, keyword: str, marketplace: str) -> dict[str, Any]:
        domain = DOMAINS[marketplace]
        url = f"https://completion.{domain}/api/2017/suggestions?limit=10&prefix={quote_plus(keyword)}&mid=1"
        page = self.crawler.get(url)
        if not page:
            return self._empty("Amazon 搜索建议当前不可用。", "Amazon Autocomplete")
        try:
            payload = json.loads(page.lstrip("\ufeff"))
            suggestions = payload[1] if len(payload) > 1 else []
            items = [{"keyword": row[0], "search_volume": None, "competition_level": "未知", "suggested_cpc": None, "is_long_tail": len(row[0].split()) >= 3} for row in suggestions if row]
            return self._envelope({"keywords": items}, "Amazon Autocomplete", [f"返回建议词 {len(items)} 条"], "Medium", "搜索量和 CPC 不由 Autocomplete 提供，未推算填充。") if items else self._empty("Amazon 搜索建议为空。", "Amazon Autocomplete")
        except (ValueError, TypeError, IndexError):
            return self._empty("Amazon 搜索建议响应无法解析。", "Amazon Autocomplete")

    def _trend(self, keyword: str, marketplace: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        timeframe = str((params or {}).get("timeframe", "12m"))
        return self.trends.fetch(keyword, marketplace, timeframe)

    def _crawler_diagnostic(self) -> str:
        fields = ("last_status", "last_response_bytes", "request_attempts", "last_error")
        details = [f"{name}={getattr(self.crawler, name)}" for name in fields if getattr(self.crawler, name, None) not in (None, "", 0)]
        return ", ".join(details)

    def _reviews(self, asins: list[str], marketplace: str, max_reviews: int = 50) -> dict[str, Any]:
        if not asins:
            return self._empty("没有可用于评论查询的竞品 ASIN。", "Amazon 商品评论页")
        domain = DOMAINS[marketplace]
        reviews: list[tuple[int, str]] = []
        limit = max(1, min(500, int(max_reviews)))
        for asin in asins[:5]:
            page = self.crawler.get(f"https://{domain}/product-reviews/{quote_plus(asin)}?reviewerType=all_reviews&sortBy=recent")
            if not page:
                continue
            try:
                doc = html.fromstring(page)
                for card in doc.xpath("//*[@data-hook='review']"):
                    rating_text = " ".join(card.xpath(".//*[@data-hook='review-star-rating']//text() | .//*[@data-hook='cmps-review-star-rating']//text()"))
                    body = " ".join(card.xpath(".//*[@data-hook='review-body']//text()" )).strip()
                    try:
                        rating = int(float(rating_text.split(" ")[0].replace(",", ".")))
                    except (ValueError, IndexError):
                        continue
                    if body:
                        reviews.append((rating, body[:1200]))
                        if len(reviews) >= limit:
                            break
            except (ValueError, TypeError):
                continue
            if len(reviews) >= limit:
                break
        if not reviews:
            return self._empty("Amazon 评论页未返回可解析评论。", "Amazon 商品评论页")
        positives = [text for rating, text in reviews if rating >= 4]
        negatives = [text for rating, text in reviews if rating <= 2]
        positive_hits = [word for word in ("quiet", "easy", "great", "easy to clean", "静音", "方便") if any(word in t.lower() for t in positives)]
        negative_hits = [word for word in ("noise", "broken", "leak", "filter", "noisy", "噪音", "漏水") if any(word in t.lower() for t in negatives)]
        distribution = {str(score): round(sum(1 for rating, _ in reviews if rating == score) / len(reviews) * 100) for score in range(5, 0, -1)}
        return self._envelope({"avg_rating": round(statistics.mean(rating for rating, _ in reviews), 2), "rating_distribution": distribution,
                               "sentiment_scores": {"positive": round(len(positives) / len(reviews) * 100), "neutral": round(sum(1 for r, _ in reviews if r == 3) / len(reviews) * 100), "negative": round(len(negatives) / len(reviews) * 100)},
                               "top_praise_points": positive_hits, "top_pain_points": negative_hits, "improvement_suggestions": [], "review_count": len(reviews)},
                              "Amazon 商品评论页", [f"解析评论 {len(reviews)} 条", "情绪按星级粗略分组"], "Low", "关键词标签为简单词匹配，不等同于完整语义情感分析。")
