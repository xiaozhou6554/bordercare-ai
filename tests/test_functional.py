from pydantic import ValidationError
import pytest
import json

from scr.application.agent import ResearchAgent, classify_intent
from scr.domain.services import calculate_profit, calculate_score
from scr.interfaces.http import routes
from scr.interfaces.http.schemas import CandidateRequest, ProfitRequest
from tests.support import make_agent


def agent():
    return make_agent()


def test_intent_routes_and_extracts_market() -> None:
    assert classify_intent("帮我分析宠物饮水机的市场机会").intent == "full_pipeline"
    assert classify_intent("calculate profit", requested_intent="profit").marketplace == "US"
    assert classify_intent("计算 $39.99 利润", marketplace="DE").additional_params["selling_price"] == 39.99
    assert classify_intent("查一下德国站的宠物饮水机趋势").marketplace == "DE"
    assert classify_intent("这个赛道怎么做品牌").intent == "qna"


def test_full_pipeline_and_report_provenance() -> None:
    body = agent().research("分析宠物饮水机", "US").to_dict()
    assert len(body["stages"]) == 9
    for stage in body["stages"].values():
        assert {"source", "confidence", "evidence", "data_timestamp", "note"} <= stage["data"].keys()
    assert "来源" in body["report_markdown"] and "置信度" in body["report_markdown"]
    breakdown = body["stages"]["product_scorer"]["data"]["score_breakdown"]
    assert breakdown["market_demand"] == 70
    assert breakdown["trend"] == 80


def test_unknown_keyword_does_not_claim_live_results() -> None:
    body = agent().research("分析折叠电动滑板车").to_dict()
    overview = body["stages"]["market_overview"]["data"]
    assert overview["total_product_count"] == 0
    assert overview["confidence"] == "Low"
    assert "未接入实时平台数据" in overview["note"]
    assert "price_stddev" in overview and overview["price_stddev"] is None
    keyword = agent().research("研究折叠电动滑板车关键词", intent="keyword").stages["keyword_research"].data
    assert keyword["source"] == "预设关键词扩展（非实时）"
    assert keyword["keywords"] and set(keyword["groups"]) == {"core", "long_tail", "low_competition"}
    assert all(item["search_volume"] is None and item["suggested_cpc"] is None for item in keyword["keywords"])


def test_category_depth_and_node_selection() -> None:
    result = agent().research("Pet Supplies", intent="category", params={"depth": 1}).stages["category_explorer"].data
    assert "BSR" in result["note"] and "未作估算" in result["note"]
    assert result["tree"][0]["name"] == "Pet Supplies"
    assert result["tree"][0]["children"]
    assert all(not child["children"] for child in result["tree"][0]["children"])
    selected = agent().research("Water Fountains", intent="category", params={"category_name": "Water Fountains"}).stages["category_explorer"].data
    assert selected["tree"][0]["node_id"] == "water-fountains"


def test_profit_calculation_rejects_markets_without_fee_schedules() -> None:
    de = agent().research("计算利润", marketplace="DE", intent="profit").stages["profit_calculator"]
    us_result = agent().research("calculate profit", intent="profit").stages["profit_calculator"]
    assert us_result.success, us_result.error
    us = us_result.data
    assert not de.success
    assert "仅支持美国站 USD" in de.error
    assert us["currency"] == "USD"
    with pytest.raises(ValueError, match="仅支持 USD"):
        calculate_profit(currency="CAD")
    with pytest.raises(ValidationError):
        ProfitRequest(currency="CAD")


def test_profit_endpoint_and_validation() -> None:
    data = routes.profit(ProfitRequest(selling_price=29.99, cost_price=8.50))
    assert data["referral_fee"] == 4.5
    assert data["net_profit"] > 0
    assert data["profit_margin"] == round(data["net_profit"] / 29.99 * 100, 2)
    with pytest.raises(ValidationError):
        ProfitRequest(selling_price=0)
    with pytest.raises(ValidationError):
        ProfitRequest(selling_price=10, size_tier="unknown")


def test_candidate_payload_rejects_excessive_json_nesting() -> None:
    nested = "value"
    for _ in range(14):
        nested = {"child": nested}
    with pytest.raises(ValidationError, match="nested too deeply"):
        CandidateRequest(external_key="candidate-1", title="Test", source="test", data=nested)


def test_profit_minimum_commission_and_size_tiers() -> None:
    result = calculate_profit(selling_price=1, cost_price=0, size_tier="small_standard")
    assert result["referral_fee"] == 0.3
    assert calculate_profit(size_tier="large_oversize")["fba_fulfillment"] > calculate_profit(size_tier="small_standard")["fba_fulfillment"]


def test_weighted_score_grade_and_recommendation() -> None:
    top = calculate_score({key: 100 for key in ("market_demand", "competition", "profitability", "trend", "supply_chain")})
    assert top["overall_score"] == 100 and (top["grade"], top["recommendation"]) == ("A", "go")
    bottom = calculate_score({key: 0 for key in ("market_demand", "competition", "profitability", "trend", "supply_chain")})
    assert bottom["recommendation"] == "abandon"


def test_incomplete_score_does_not_issue_a_grade_or_recommendation() -> None:
    partial = calculate_score({"market_demand": 70, "profitability": None})
    assert partial["overall_score"] is None
    assert partial["grade"] == "待评估"
    assert partial["recommendation"] == "证据不足"
    assert partial["score_breakdown"]["market_demand"] == 70
    assert partial["score_breakdown"]["profitability"] is None
    assert set(partial["missing_dimensions"]) == {"competition", "profitability", "trend", "supply_chain"}


def test_llm_intent_classifier_validates_schema_and_keeps_explicit_intent() -> None:
    class ClassifierLLM:
        available = True
        def __init__(self, response): self.response = response
        def complete(self, *args, **kwargs): return self.response

    current = agent()
    current.llm = ClassifierLLM(json.dumps({"intent":"trend","keyword":"desk lamp","marketplace":"UK","additional_params":{}}))
    events = list(current.stream("Is this category growing?"))
    assert events[0]["data"]["intent"] == "trend"
    assert events[0]["data"]["marketplace"] == "UK"
    assert events[0]["data"]["session_id"]
    assert list(current.stream("Is this category growing?", marketplace="DE"))[0]["data"]["marketplace"] == "DE"

    current.llm = ClassifierLLM("not json")
    assert list(current.stream("What does BSR mean?"))[0]["data"]["intent"] == "qna"
    assert list(current.stream("What does BSR mean?", requested_intent="profit"))[0]["data"]["intent"] == "profit"


def test_llm_cannot_downgrade_broad_market_research_to_single_stage() -> None:
    class ClassifierLLM:
        available = True
        def complete(self, *args, **kwargs):
            return json.dumps({"intent": "market_overview", "keyword": "宠物饮水机", "marketplace": "US", "additional_params": {}})

    current = agent()
    current.llm = ClassifierLLM()
    events = list(current.stream("帮我分析美国宠物饮水机的市场情况。"))
    assert events[0]["data"]["intent"] == "full_pipeline"
    assert sum(event["type"] == "stage_done" for event in events) == 9


def test_qna_offline_fallback_follows_user_language() -> None:
    current = agent()
    assert "I can help" in current._answer_question("How do I choose a product?")
    assert "我可以协助" in current._answer_question("如何选择产品？")


def test_qna_model_failure_fallback_follows_user_language() -> None:
    class FailingLLM:
        available = True

        @staticmethod
        def complete(*args, **kwargs):
            raise RuntimeError("provider unavailable")

    current = agent()
    current.llm = FailingLLM()
    assert "I can help" in current._answer_question("How do I choose a product?")
    assert "我可以协助" in current._answer_question("如何选择产品？")


def test_cache_hit_and_clear() -> None:
    routes.clear_cache()
    current = agent()
    first = current.research("计算 $29.99 利润", intent="profit").to_dict()
    second = current.research("计算 $29.99 利润", intent="profit").to_dict()
    assert next(iter(first["stages"].values()))["cached"] is False
    assert next(iter(second["stages"].values()))["cached"] is True
    assert routes.clear_cache()["status"] == "cleared"
