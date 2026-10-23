from scr.application.agent import ResearchAgent
from scr.application.tool_registry import ToolRegistry
from scr.infrastructure.cache import MemoryTTLCache
from scr.infrastructure.market_data import HonestDemoMarketData


class OfflineLLM:
    available = False

    def complete(self, *args, **kwargs):
        raise RuntimeError("offline")


def make_agent() -> ResearchAgent:
    cache = MemoryTTLCache()
    registry = ToolRegistry(cache, HonestDemoMarketData(), 21600)
    return ResearchAgent(registry, OfflineLLM())


def make_registry() -> ToolRegistry:
    return ToolRegistry(MemoryTTLCache(), HonestDemoMarketData(), 21600)
