"""Composition root: wire application ports to infrastructure adapters."""
from scr.application.agent import ResearchAgent
from scr.application.idempotency import IdempotencyService
from scr.application.identity import IdentityService
from scr.application.research_task import ResearchTaskProcessor
from scr.application.runtime import RuntimeServices
from scr.application.tool_registry import ToolRegistry
from scr.config import settings
from scr.infrastructure.cache import MemoryTTLCache
from scr.infrastructure.llm import LLMGateway
from scr.infrastructure.market_data import HonestDemoMarketData
from scr.infrastructure.amazon_data import LiveMarketData, RespectfulCrawler
from scr.infrastructure.product_market_router import AmazonFirstMarketData
from scr.infrastructure.alibaba1688_data import Alibaba1688ConsignmentData
from scr.infrastructure.onebound_1688_data import Onebound1688SearchData
from scr.infrastructure.onebound_taobao_data import OneboundTaobaoSearchData
from scr.infrastructure.auth import hash_password, issue_token, verify_password, verify_token
from scr.infrastructure.persistence import PersistenceStore
from scr.infrastructure.rate_limit import RequestRateLimiter
from scr.infrastructure.session_memory import SessionMemory
from scr.infrastructure.task_queue import ResearchTaskQueue
import logging

logger = logging.getLogger(__name__)


def build_container() -> tuple[ResearchAgent, ToolRegistry, LLMGateway]:
    cache = MemoryTTLCache()
    if settings.redis_url:
        try:
            from scr.infrastructure.redis_cache import RedisTTLCache
            cache = RedisTTLCache(settings.redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable; using process-local cache error_type=%s", type(exc).__name__)
    crawler = RespectfulCrawler(settings.crawler_timeout_seconds, settings.crawler_delay_seconds, settings.crawler_max_retries)
    if settings.data_mode == "demo":
        market_data = HonestDemoMarketData()
    else:
        public_sources = LiveMarketData(crawler)
        taobao_search = OneboundTaobaoSearchData(settings.onebound_api_key, settings.onebound_api_secret, settings.crawler_timeout_seconds)
        if settings.alibaba_app_key and settings.alibaba_app_secret:
            supplier_data = Alibaba1688ConsignmentData(settings.alibaba_app_key, settings.alibaba_app_secret, settings.crawler_timeout_seconds)
            alternate_supplier_data = taobao_search
        elif settings.onebound_1688_enabled:
            supplier_data = Onebound1688SearchData(settings.onebound_api_key, settings.onebound_api_secret, settings.crawler_timeout_seconds)
            alternate_supplier_data = taobao_search
        else:
            # Use the verified Taobao keyword API directly; Onebound 1688 access is opt-in.
            supplier_data = taobao_search
            alternate_supplier_data = None
        market_data = AmazonFirstMarketData(public_sources, supplier_data, alternate_supplier_data)
    registry = ToolRegistry(cache, market_data, settings.cache_ttl_seconds)
    llm = LLMGateway()
    agent = ResearchAgent(registry, llm, settings.default_marketplace, settings.default_profit_target, settings.data_mode, settings.default_currency)
    return agent, registry, llm


def build_http_runtime() -> RuntimeServices:
    """Single composition root for the HTTP application and its background worker."""
    agent, registry, llm = build_container()
    memory = SessionMemory(registry.cache, settings.session_memory_ttl_seconds)
    idempotency = IdempotencyService(registry.cache, settings.idempotency_ttl_seconds)
    persistence = None
    if settings.database_url:
        try:
            persistence = PersistenceStore(settings.database_url)
        except Exception as exc:
            logger.error("Database initialization failed error_type=%s", type(exc).__name__)
    processor = ResearchTaskProcessor(agent, memory, settings.auth_enabled)
    queue = ResearchTaskQueue(processor, persistence, settings.redis_url, settings.task_queue_workers,
        allow_local_fallback=settings.app_env not in {"production", "staging"},
        task_timeout_seconds=settings.task_timeout_seconds)
    identity = IdentityService(persistence, hash_password, verify_password, issue_token, verify_token,
        settings.auth_secret, settings.auth_token_ttl_seconds, settings.auth_allow_signup)
    rate_limiter = RequestRateLimiter(settings.redis_url)
    return RuntimeServices(identity, agent, registry, llm, memory, idempotency, persistence, queue, rate_limiter)
