from concurrent.futures import ThreadPoolExecutor
import time

from scr.application.agent import ResearchAgent
from scr.infrastructure.cache import MemoryTTLCache
from tests.support import make_agent


def test_parallel_local_agent_calls_100_unique_requests() -> None:
    agent = make_agent()
    agent.registry.cache.clear()
    def request(index: int) -> int:
        intent = "full_pipeline" if index % 2 else "profit"
        result = agent.research(f"分析宠物饮水机并发样本 {index}", intent=intent)
        assert result.stages
        assert not any(stage.cached for stage in result.stages.values())
        return len(result.stages)
    with ThreadPoolExecutor(max_workers=16) as pool:
        completed = list(pool.map(request, range(100)))
    assert len(completed) == 100 and all(count >= 1 for count in completed)


def test_cache_ttl_expiration_and_concurrent_access() -> None:
    cache = MemoryTTLCache()
    cache.set("short", {"ok": True}, 1)
    assert cache.get("short") == {"ok": True}
    time.sleep(1.05)
    assert cache.get("short") is None
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: cache.set(str(index), index, 60), range(100)))
    assert cache.stats()["entries"] == 100
