from statistics import median
from time import perf_counter

from scr.application.agent import ResearchAgent
from tests.support import make_agent


def test_local_pipeline_performance() -> None:
    agent = make_agent()
    agent.registry.cache.clear()
    samples = []
    queries = [f"分析宠物饮水机性能样本 {index}" for index in range(30)]
    for query in queries:
        start = perf_counter()
        result = agent.research(query)
        samples.append((perf_counter() - start) * 1000)
        assert len(result.stages) == 9
        assert not any(stage.cached for stage in result.stages.values())
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 1000, f"本地模拟 Pipeline P95 {p95:.1f}ms 超过 1000ms"
    assert median(samples) < 500
