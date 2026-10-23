from scr.application.agent import PIPELINE, ResearchAgent
from scr.application.tool_registry import ToolRegistry
from scr.domain.models import ToolOutput
from tests.support import make_agent, make_registry


class StubTool:
    def __init__(self, output: ToolOutput) -> None:
        self.output = output
    def run(self, *args, **kwargs) -> ToolOutput:
        return self.output


def test_downward_trend_stops_following_stages() -> None:
    agent = make_agent()
    agent.registry.tools["trend_analyzer"] = StubTool(ToolOutput(True, {"direction": "down", "source": "fixture", "confidence": "High", "evidence": [], "data_timestamp": "now", "note": ""}))
    events = list(agent.stream("分析测试品类"))
    complete = next(event["data"] for event in events if event["type"] == "complete")
    assert complete["aborted"]
    assert list(complete["stages"]) == PIPELINE[:2]
    assert len([event for event in events if event["type"] == "stage_skip"]) == len(PIPELINE) - 2


def test_low_profit_stops_before_supplier_and_score() -> None:
    agent = make_agent()
    agent.registry.tools["profit_calculator"] = StubTool(ToolOutput(True, {"profit_margin": 10, "source": "fixture", "confidence": "High", "evidence": [], "data_timestamp": "now", "note": ""}))
    result = agent.research("分析测试品类").to_dict()
    assert result["aborted"] and list(result["stages"])[-1] == "profit_calculator"


def test_failed_tool_does_not_abort_pipeline() -> None:
    agent = make_agent()
    agent.registry.tools["market_overview"] = StubTool(ToolOutput(False, {}, "synthetic failure"))
    result = agent.research("分析宠物饮水机").to_dict()
    assert not result["aborted"] and len(result["stages"]) == 9


def test_cache_key_separates_market_and_parameters() -> None:
    tool = make_registry().get("profit_calculator")
    first = tool.run("fountain", "US", {"selling_price": 20})
    other_price = tool.run("fountain", "US", {"selling_price": 30})
    other_market = tool.run("fountain", "DE", {"selling_price": 20})
    assert not first.cached and not other_price.cached and not other_market.cached
    assert first.data["selling_price"] != other_price.data["selling_price"]
