# 需求追踪与验收状态

状态定义：**通过**=实现和本地自动化测试已覆盖；**部分**=本地能力存在，但至少一个规定场景/真实数据源/生产语义未实现；**待验收**=必须由真实外部凭证或目标环境验证。模拟 Provider 测试不算真实平台连通。

## 原始需求 FR-001 至 FR-018

| ID | 需求 | 实现位置 / API / UI | 测试证据 | 状态与边界 |
|---|---|---|---|---|
| FR-001 | 意图识别 | `scr/application/agent.py`；Web 输入框 | `tests/test_functional.py`、`tests/test_regression.py` | 通过；无模型时用规则回退 |
| FR-002 | 意图路由 | `scr/application/agent.py`、工具注册表 | `tests/test_functional.py` | 通过 |
| FR-003 | 完整调研 Pipeline | Application Pipeline；`POST /api/tasks`、`GET /api/tasks/{id}`；Web 阶段卡片 | `tests/test_functional.py`、`tests/test_regression.py` | 部分；流程与阶段失败降级已测，真实来源覆盖受凭证和平台限制 |
| FR-004 | Market overview | Amazon Provider | `tests/test_live_adapter.py` | Partial; visible public listing samples are not total market size or sales volume |
| FR-005 | 趋势分析 | 趋势 Provider、分析工具 | `tests/test_functional.py`、`tests/test_live_adapter.py` | 部分；相对趋势不等于绝对搜索量，实时调用待外部服务验收 |
| FR-006 | 类目穿透 | 类目工具和本地树 | `tests/test_functional.py` | 部分；本地规则树不是平台实时类目/BSR规模 |
| FR-007 | Competitor analysis | Amazon Provider and competitor tool | `tests/test_live_adapter.py`, `tests/test_regression.py` | Partial; public listing samples are not sales data |
| FR-008 | 评论分析 | 评论工具和适配器 | `tests/test_functional.py`、`tests/test_regression.py` | 部分；能否获得评论取决于公开页面字段和站点限制 |
| FR-009 | 关键词研究 | 关键词工具、趋势 Provider | `tests/test_functional.py` | 部分；绝对搜索量/CPC 缺失时不伪造 |
| FR-010 | 利润测算 | `scr/domain/services.py`；`POST /api/profit` | `tests/test_functional.py` | 部分；仅美国站 USD 使用已实现费用假设，其他站点明确拒绝测算；实际物流、关税和平台费需要用户输入/权威费率 |
| FR-011 | 供应商寻源 | 1688/Onebound Adapter；Supplier 卡片 | `tests/test_alibaba1688_data.py`、`tests/test_live_adapter.py` | 待验收；官方 1688 新接入权限受限，Onebound 1688 返回 4005/未开通、淘宝关键词曾返回 5000；零售线索不能称为已核验批发供应商 |
| FR-012 | 综合评分 | Domain 评分服务、Product Scorer | `tests/test_functional.py` | 通过规则测试；评分证据质量取决于各 Provider 的真实数据完整度 |
| FR-013 | 报告生成 | 报告编排、任务结果；`GET /api/tasks/{id}/export` | `tests/test_enterprise_features.py`、`tests/test_functional.py` | 通过格式和证据来源测试；模型摘要可选，报告不是法律或投资结论 |
| FR-014 | 通用问答 | Agent Q&A、LLM Gateway | `tests/test_functional.py`、`tests/test_safety_memory.py` | 部分；模型凭证/可用性未作为离线测试通过的前提 |
| FR-015 | 多站点 | `ResearchRequest.marketplace`（US/UK/DE/JP/CA） | `tests/test_functional.py` | 部分；研究站点枚举可用，Provider 覆盖不一；利润测算仅支持美国站 USD，其他站点不套用美国费用 |
| FR-016 | 结果缓存 | Memory/Redis TTL cache | `tests/test_enterprise_features.py`、`tests/test_regression.py` | 部分；本机内存可用，Redis 多实例连接和生产失效策略仍需部署验收 |
| FR-017 | UI | `scr/interfaces/web/index.html`, `app.js`; `/` | `tests/test_smoke.py` | HTML/JS 静态契约和可访问性语义有自动检查；本次浏览器动态查询因本机浏览器/服务启动受阻未验证；生产身份流程仍需部署验收 |
| FR-018 | 配置管理 | `scr/config.py`、`.env.example`、启动校验 | `tests/test_smoke.py` | 部分；生产必需配置已校验，密钥轮换/集中式密钥管理尚未集成 |

## 企业扩展和生产要求

| ID | 需求 | 实现位置 / API / UI | 测试证据 | 状态与边界 |
|---|---|---|---|---|
| ENT-01 | 用户、组织、RBAC、会话失效 | `scr/infrastructure/auth.py`、`persistence.py`；`/api/auth/*`、`/api/members` | `tests/test_enterprise_features.py`、`tests/test_safety_memory.py` | 部分；单用户账号的多组织登录选择和账号恢复流程有限 |
| ENT-02 | 工作区项目与隔离 | `research_projects`；`/api/projects`；任务可关联项目 | 持久化/租户回归测试 | 部分；组织过滤实施中，需继续加强跨租户负向 API 测试 |
| ENT-03 | 异步任务可恢复/取消/重试 | `scr/infrastructure/task_queue.py`；`PersistenceStore.claim_task`；`/api/tasks`、DELETE、retry、owner/admin 死信查看；运行时队列指标；`TASK_TIMEOUT_SECONDS` | `tests/test_enterprise_features.py`（自动重试、超时、原子认领、活租约恢复、死信脱敏）；MySQL/Redis 容器验收进行中 | 部分；Redis Streams 至少一次投递、120 秒心跳租约、原子任务认领、3 次有限退避重试、超时失败、脱敏死信记录/查看及积压/pending 指标已实现；真实 Redis/MySQL 多 Worker 崩溃演练待部署验收 |
| ENT-04 | 证据、报告版本、评论、审批 | evidence/report/review tables；`/report-versions`、`/reviews` | 持久化和报告回归测试 | 部分；没有独立审批通知与 UI 工作流 |
| ENT-05 | 候选档案与数据快照 | candidate/snapshot 表；`/api/candidates` | 持久化测试 | 部分；需要补齐对比 UI、供应商报价/样品/交期的专用领域实体 |
| ENT-06 | 合规风险与人工复核 | `compliance_assessments`；`/api/compliance-assessments` | Schema/持久化测试 | 部分；只保存来源、时间、风险发现并置为待人工复核，不含权威法律规则库 |
| ENT-07 | 经营反馈 | `business_feedback`；`/api/feedback` | 持久化测试 | 部分；提供可写入接口，暂未训练/校准模型 |
| ENT-08 | 版本化数据库迁移 | `scr/infrastructure/schema_migrations.py` | SQLite migration tests；MySQL 8.4 容器已执行迁移，`schema_migrations` 有 2 条记录 | 部分；基线与增量迁移支持 MySQL/PostgreSQL/SQLite，尚需执行备份恢复演练；尚无自动 downgrade |
| ENT-09 | 容器化 API/Worker | `Dockerfile`、`docker-compose.yml`、`scr/worker.py` | MySQL/Redis/API/Worker 容器已启动；API readiness healthy，Worker 稳定运行 | 部分；容器启动及依赖健康检查通过；仍需执行多 Worker 崩溃恢复演练 |
| ENT-10 | 健康、日志、追踪、指标 | `/api/health/live`、`/ready`；X-Request-ID、脱敏请求日志；队列积压/pending/死信计数 | `tests/test_smoke.py`、`tests/test_enterprise_features.py` | 部分；应用级队列指标已提供，尚未实现 OpenTelemetry Trace、Prometheus 导出和告警面板 |
| ENT-11 | 安全与提示注入护栏 | 输入 DTO、授权、限流、URL 来源边界、`guardrails.py` | `tests/test_safety_memory.py`、`tests/test_regression.py` | 部分；规则型防护不能保证拦截所有间接注入，尚无完整安全扫描 |
| ENT-12 | 性能、压力、端到端验收 | `tests/test_performance.py`、`tests/test_stress.py`、功能/安全回归、浏览器工作台 | 本次全量本地离线套件 68 项；100 个唯一请求的进程内并发模拟；30 个唯一关键词完整 Pipeline 冷缓存性能记录；前端动态浏览器查询未能启动 | 部分；本地测试结果不代表 HTTP/浏览器端到端容量、外部平台数据、生产 SLO 或真实数据库/Redis 多 Worker 故障恢复；需在具备浏览器和本地监听权限的环境验收 |

## 明确的资料冲突

原需求文档 V1.0 和由旧实现反向生成的技术说明将登录、持久化、多租户列入“当前版本不包含”。用户本次明确将这些列为企业扩展目标，因此本次追踪按扩展需求开发。旧技术文档还把 1688 标为模拟数据/无账号存储；当前实现有数据适配器和企业持久化，但实际权限和凭证必须分别验收。

本项目暂定的轻负载容量与 p95 假设见 [README](../README.md) 的“健康检查、SLO 假设与故障排查”。生产 SLO、数据保留时限、审批策略和并发目标需要业务方在真实部署前确认。
