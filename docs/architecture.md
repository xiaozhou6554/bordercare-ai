# 跨境电商选品调研 Agent 架构

## 架构边界

项目按 DDD 四层组织，并在 Application 层编排 Agent。依赖从外向内：Interface 调用 Application，Application 面向 Domain 模型和端口，Infrastructure 实现 Domain 端口并由组合根注入。Domain 不依赖 FastAPI、HTTP 客户端、模型 SDK 或缓存实现。

```text
用户 / 浏览器 / CLI
        |
Interface：HTTP、SSE、DTO、Web 工作台、CLI
        |
Application：ResearchAgent、九阶段 Pipeline、工具注册
        |
Domain：业务模型、数据端口、利润与评分规则
        ^
        |
Infrastructure：DeepSeek 网关、市场数据适配器、TTL 缓存
        |
组合根：Infrastructure Container 注入应用端口实现
```

## 分层目录和职责

| 层 | 目录 | 职责 |
|---|---|---|
| Interface | `scr/interfaces/http` | FastAPI 路由、请求/响应 DTO、健康检查、JSON 和 SSE |
| Interface | `scr/interfaces/web` | 按产品原型实现的浏览器工作台 |
| Application | `scr/application/agent.py` | 意图识别、单工具路由、调研阶段调度、流程提前终止、报告编排 |
| Application | `scr/application/tool_registry.py` | 工具边界、缓存键、错误收敛和分析工具执行 |
| Domain | `scr/domain/models.py` | 意图、任务、消息、工具输出、AgentState 和报告模型 |
| Domain | `scr/domain/ports.py` | 市场数据、模型和缓存抽象端口 |
| Domain | `scr/domain/services.py` | FBA 费用估算、净利润和五维评分规则 |
| Infrastructure | `scr/infrastructure` | 授权数据适配、DeepSeek 网关、TTL 缓存、SQLAlchemy Repository、schema 迁移和后台队列 |
| Infrastructure | `scr/infrastructure/container.py` | Agent/Provider 组合根；HTTP 当前仍在路由模块中装配持久化和队列，属于待消除的分层耦合 |

## 护栏、幂等与记忆

- `scr/application/guardrails.py` 在 Application 边界过滤常见直接提示注入，限制历史角色和长度，并检查 AI 摘要是否引入来源中不存在的数字。模型输出不是市场数据事实源，事实表以工具结构化结果和来源为准。
- 意图与参数经过枚举、长度和字段名校验；Agent 工具由固定注册表执行，模型不能任意调用代码或 SQL。
- `scr/application/idempotency.py` 对同一 key 串行处理、重放缓存响应；同 key 搭配不同请求体返回冲突。Redis 后端提供跨进程处理锁。
- `scr/infrastructure/session_memory.py` 保存每个 UUID 会话 30 天的有限对话档案，模型只读取最近 12 条消息；档案上限 100 条，并可通过会话删除接口清除。
- `scr/infrastructure/cache.py` 是内存后备；配置 Redis 后由 `scr/infrastructure/redis_cache.py` 提供共享 TTL 工具缓存、记忆和幂等结果。
- 开启认证后，会话键包含工作区和用户标识，持久化查询按工作区过滤；不做跨会话用户画像。系统提示注入检测是规则型基础防护，不能保证识别所有变体；语义事实蕴含也未做自动判定。

## Agent 流程

```text
自然语言
  -> 意图识别（完整调研 / 单工具 / 通用问答）
  -> AgentState 跟踪会话、用户偏好、当前任务和阶段结果
  -> 市场 -> 趋势 -> 类目 -> 竞品 -> 评论 -> 关键词 -> 利润 -> 供应商 -> 评分
  -> 趋势下行或利润率低于目标时按业务规则提前结束
  -> 报告和来源证据
```

每个分析工具返回来源、证据、置信度、数据时间和缺失值说明。Agent 不直接访问平台 API 或数据库；它通过 Application 工具调用 Domain 端口的 Infrastructure 实现。DeepSeek 用于意图识别和报告辅助，不会代替平台返回市场事实。

## 数据适配规则

- 1688 Open Platform 适配器只服务供应商搜索，使用官方 TOP HTTPS API `alibaba.open.search.daixiao.offer.get`。请求签名、响应字段映射和失败结果在 Infrastructure 内处理。
- Amazon public pages 用于海外平台商品和价格样本；商品列表不等于成交数据。
- Amazon 公开页面和 Google Trends 的可用数据作为海外市场的尽力读取来源，失败时保留空值和原因。
- 不存在真实来源、权限或字段时，不填充虚构销量、评价、品牌、起订量或营收。
- 1688 结果是供给侧线索，不应混入海外消费需求统计；来源与凭证状态分别展示。

## 测试边界

适配器单测通过模拟 HTTP 响应验证参数、签名和映射，不要求真实平台账户。真实平台调用还受凭证、应用权限、配额、网络和平台当前政策影响。测试覆盖冒烟、功能、定向回归、性能、并发压力和全量回归。


## 异步任务、租户和可观测

HTTP 中间件为每个请求生成或接受关联 ID，记录路径、状态码和耗时，且不记录输入正文。配置 Redis 时使用共享队列与限流计数；无 Redis 时为本地线程和内存限流。

任务和证据可存入共享 SQL 数据库；组织 ID 作为任务查询和会话键的隔离边界。账号使用 PBKDF2-SHA256 密码哈希和标准 HS256 JWT；每个请求会重查成员身份、角色和会话版本。迁移记录保存在 `schema_migrations`，生产数据库支持 MySQL 8.4 与 PostgreSQL，当前 Compose 默认 MySQL。Redis Streams 提供消费组确认、pending reclaim、数据库原子认领、心跳租约、有限重试、退避、死信记录和积压统计。该链路按至少一次投递设计，不宣称 exactly-once；多 Worker 崩溃与真实 MySQL/Redis 环境仍需部署验收。HTTP 组合根注入 Application RuntimeServices，路由不直接导入基础设施实现；Domain/Application 不依赖具体数据库、缓存、HTTP SDK 或 FastAPI。状态见[需求追踪矩阵](requirements-traceability.md)。

`GET /api/health/live` 与 `GET /api/health/ready` 分离存活和依赖就绪。容器部署定义在根目录 `Dockerfile` 和 `docker-compose.yml`，包括单独的 API 和 Worker 进程、MySQL、Redis 及健康检查。
