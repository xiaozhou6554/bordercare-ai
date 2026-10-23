# 跨境电商选品调研 Agent

本地运行的选品调研工作台，包含意图识别、九阶段 Agent 调研、市场/趋势/竞品/评论/关键词/供应商分析、利润估算、五维评分、报告和 SSE 进度。

## 环境

- Windows
- Anaconda `model` 环境（或 `C:\Users\123\anaconda3\envs\model\python.exe`）
- DeepSeek API Key（可选；未配置时采用本地规则识别意图）
- 外部数据接口凭证按需配置，详细边界见 [`docs/data-sources.md`](docs/data-sources.md)

## 启动步骤

项目有两种启动方式：Docker 一键启动所有服务，或让 Docker 只运行 MySQL/Redis、再用 Conda 执行 `python main.py` 启动 API。请任选一种，完整命令、端口和停止方式见下方[容器部署与两种启动方式](#容器部署)。已有 `.env` 时不要重新复制模板覆盖；首次配置时仅在 `.env` 不存在的情况下复制 `.env.example`。

## 跨境数据源

Live product and competitor searches use Amazon public pages. Google Trends supplies trend signals when available. Supplier leads use a separate provider; see docs/data-sources.md for source limits.

## 架构

项目采用 DDD 四层 + Agent 编排：

```text
scr/interfaces/       Interface：HTTP JSON/SSE、Pydantic DTO、Web 工作台、CLI
scr/application/      Application：ResearchAgent、九阶段 Pipeline、工具注册与编排
scr/domain/           Domain：业务模型、数据端口、利润和评分规则
scr/infrastructure/   Infrastructure：DeepSeek 网关、数据源适配器、TTL 缓存、依赖装配
```

Agent 调用应用层工具，应用层依赖 Domain 端口，Infrastructure 提供端口实现；接口层通过组合根装配应用，不在 Domain 层耦合 FastAPI、HTTP SDK 或具体缓存实现。

## 常用接口

- `GET /api/health`：仅返回公共服务状态和首次工作区初始化所需标记；依赖、凭证和缓存详情不对外返回
- `GET /api/tools`：工具及 Pipeline 阶段
- `POST /api/research`：完整调研报告
- `POST /api/research/stream`：SSE 阶段进度和结果
- `POST /api/profit`：参数化利润测算
- `GET/DELETE /api/cache`：查看/清理进程内缓存

## 安全、幂等与记忆

- 用户输入和会话历史作为不可信数据传给模型；常见提示词注入请求会被拦截，模型工具/意图结果限制在允许列表中。
- 报告 AI 摘要中的数字会与来源数据进行核对；出现来源中不存在的数字时丢弃该摘要，保留下方的结构化来源报告。
- API 可使用 `Idempotency-Key` 请求头；同 key、同请求体重放已完成结果，同 key 换请求体返回 `409`。
- 浏览器生成并保存会话 ID；Redis/内存保存最近 100 条消息 30 天，模型上下文最多使用最近 12 条。可用 `DELETE /api/session/{session_id}` 删除一段会话记忆。
- 默认使用进程内 TTL 缓存。设置 `REDIS_URL=redis://localhost:6379/0` 并安装依赖后，工具缓存、记忆和幂等结果使用 Redis；缓存组件可回退本机内存，但 `/api/health/ready` 会报告 Redis 不可用，生产环境不会把降级视为就绪。
- 调用幂等接口示例：`curl -H "Idempotency-Key: request-20261022-001" -H "Content-Type: application/json" -d '{"message":"分析便携咖啡机","session_id":"你的UUID"}' http://127.0.0.1:8000/api/research`。

登录开启时，会话键按工作区和用户隔离。持久化历史按工作区过滤；匿名开发模式不提供多租户保护。

## 测试

在项目目录和 `model` 环境中执行：

```powershell
python -m pytest -q
```

测试覆盖冒烟、功能、定向回归、性能、并发压力及全量回归。压力和性能门槛针对本地模拟链路，不代表外部平台或模型服务的 SLA。无需真实平台凭证；外部接口使用模拟响应验证请求和字段映射。


## 企业工作区能力

- `DATABASE_URL` 支持 MySQL 8.4（`mysql+pymysql`）、PostgreSQL 或 SQLite，用于用户、组织成员、项目、调研任务、报告版本/审核、商品候选快照、合规评估、反馈和审计记录；未配置时使用进程内存任务存储。启动通过 `scr/infrastructure/schema_migrations.py` 执行版本化迁移，不再用 `create_all` 作为运行时迁移策略。
- `AUTH_ENABLED=true` 启用登录和工作区隔离。数据库没有账号时，登录页会显示一次性“初始化工作区”入口以创建首个管理员；首个账号创建后，只有设置 `AUTH_ALLOW_SIGNUP=true` 才允许继续注册。`AUTH_SECRET` 必须为至少 32 字符的随机密钥，不要提交到 Git。
- `REDIS_URL` 配置后，缓存、会话、任务队列和跨进程请求限流可共享 Redis。生产/预发要求 Redis 可用；不可用时 Worker 启动失败，API readiness 报告降级，不会静默改用单机队列。
- `POST /api/tasks` 提交后台调研，`GET /api/tasks/{task_id}` 查询进度；任务支持取消、失败重试、收藏和 Markdown 导出。Redis Streams 支持消费组确认、租约心跳、崩溃后 pending reclaim、3 次自动重试、死信元数据与积压/pending 统计。开发模式不配置 Redis 时使用进程内线程，进程退出后不能恢复未持久化任务。
- 工作区 API：`/api/projects`、`/api/members`、`/api/candidates`、`/api/compliance-assessments`、`/api/feedback`、`/api/tasks/{task_id}/reviews` 和 `/api/tasks/{task_id}/report-versions`。合规评估默认“需人工复核”，不构成法律意见。
- `API_RATE_LIMIT_PER_MINUTE` 和 `AUTH_RATE_LIMIT_PER_MINUTE` 分别配置普通 API 及登录/注册限流。无 Redis 时，计数仅在当前进程共享。
- 请求记录使用关联 ID 和耗时，不记录查询正文。调研证据保留数据来源、站点、采集时间、有效期和原始链接。

### 容器部署

Compose 默认使用 MySQL 8.4、Redis 和强随机 `AUTH_SECRET`。在 `.env` 中设置 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD` 与 `AUTH_SECRET`；真实密钥不得写入 compose 文件或 Git。MySQL 映射到本机 3307 端口，Redis 映射到 6380 端口，避免占用常见默认端口。容器会把 API 与后台 Worker 分开运行，启动时自动应用数据库迁移：

### 启动方式一：全部通过 Docker 启动

适合希望 API、后台 Worker、MySQL 和 Redis 全部由 Docker 管理的情况。先确认 Docker Desktop 已运行，并已在 `.env` 配好数据库密码和 `AUTH_SECRET`，然后在项目目录执行：

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
docker compose up -d --build
docker compose ps
```

确认 `api`、`worker`、`mysql`、`redis` 状态正常后，访问 `http://127.0.0.1:<API_PORT>`。`API_PORT` 读取自 `.env`，未设置时默认为 `8000`。查看 API/Worker 日志可运行 `docker compose logs -f api worker`。停止服务使用 `docker compose stop`；这会保留容器和数据卷。不要使用 `docker compose down -v` 清除数据库卷。

### 启动方式二：Docker 只运行数据库和 Redis，Python 启动 API

适合希望在本机 Conda 环境运行和调试 API 的情况。确保 `.env` 中 `DATABASE_URL` 指向本机 MySQL 映射端口（默认 `127.0.0.1:3307`）、`REDIS_URL` 指向本机 Redis 映射端口（默认 `127.0.0.1:6380`），并配置好数据库密码和 `AUTH_SECRET`。然后执行：

```powershell
docker compose up -d mysql redis
conda activate model
python .\main.py
```

`main.py` 会读取 `.env` 的 `API_PORT`，未设置时使用 `8000`。看到 Uvicorn 显示启动成功后，访问 `http://127.0.0.1:<API_PORT>`。保持该 PowerShell 窗口运行；停止时按 `Ctrl+C`。此方式不要再启动 Compose 的 `api` 和 `worker` 服务，以免运行两份 API/Worker。

两种方式任选一种。当前本机 `.env` 若将 `API_PORT` 设为 `8001`，访问地址就是 `http://127.0.0.1:8001`。设置 `APP_ENV=production` 时需启用认证、使用至少 32 字符随机 `AUTH_SECRET`，并按需配置模型和授权数据源凭证。端口默认只绑定本机；对外提供服务前应在可信反向代理配置 HTTPS、访问控制和备份。

### 数据库备份与恢复

备份示例使用容器环境变量传递口令，不把口令写进命令行参数或 Shell 历史：

```powershell
docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysqldump -u"$MYSQL_USER" "$MYSQL_DATABASE"' > research.sql
Get-Content research.sql | docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u"$MYSQL_USER" "$MYSQL_DATABASE"'
```

请将备份放到受控的加密存储并定期做恢复演练；恢复前停止 API/Worker，确认目标库与备份时间，再启动服务。保留期限应由业务方确认。数据库迁移在应用启动时顺序执行；回滚版本前先备份并按迁移脚本编写反向恢复步骤，目前没有自动降级迁移。

### 健康检查、SLO 假设与故障排查

- `GET /api/health/live` 只检查进程存活；`GET /api/health/ready` 检查数据库与 Redis 就绪；公共健康响应不返回依赖状态、供应商配置、凭证状态或缓存指标。
- 初始容量假设（需业务确认，不是 SLA）：单实例 API 2 个 Worker、每 Worker 最多处理 1 项，先按 5 个并发用户/分钟的轻负载验证；本地模拟请求 p95 目标暂定 2 秒，不含外部模型/数据源耗时。没有生产观测数据前不承诺可用性百分比。
- 本地性能记录（2026-10-23，Conda `model` / Python 3.10.21 / Windows 10）：30 个唯一关键词的完整九阶段本地模拟 Pipeline、16 个并发线程、冷缓存，0 错误，119.32 请求/秒，P50 8.21ms、P95 54.11ms、P99 71.05ms，Python 堆峰值 0.53MiB；压力回归另覆盖 100 个混合请求/16 线程，0 错误。该结果只代表进程内模拟适配器，不含 HTTP、真实模型、平台 API、PostgreSQL、Redis、容器及网络延迟，不能外推为线上吞吐或 SLA。
- 查不到数据时先看结果卡片的实际来源、错误分类和时间；检查授权、额度和站点。健康接口不判断外部平台授权状态。
- API 无法启动时检查配置校验与数据库迁移日志；任务停留排队时检查 Redis 健康状态和 Worker 日志；数据库故障先恢复连接再检查队列任务状态。不要通过抓取受限页面绕过平台访问规则。
