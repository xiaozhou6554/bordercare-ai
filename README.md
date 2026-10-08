# BorderCare AI

跨境电商智能客服与运营助手的本地模拟项目。

这个项目不连接真实店铺、支付平台或物流平台，先用本地模拟数据跑通完整业务链路：

```text
用户问题 → 意图识别 → 查询知识库或业务数据 → 权限/业务规则校验 → 结构化回答
```

## 当前模板包含

- FastAPI 服务
- `GET /health` 健康检查
- `POST /chat` 最小客服接口
- SQLite 模拟用户、商品、订单、库存和物流数据
- 基础订单查询、物流查询、商品咨询和政策咨询
- 企业可演进架构：模块化单体 + 清晰的依赖边界
- Agent 路由、有限状态入口和只读订单工具
- 最小 API 测试
- Git 工程实践贯穿开发、测试、合并和版本发布

当前版本是第 1～4 天的起步模板，暂未接入真实 LLM、RAG、微调和 vLLM。

更完整的企业级架构说明见 [docs/企业级架构说明.md](docs/企业级架构说明.md)。

项目全流程、每个文件的作用、数据流和 40 天每日状态见 [docs/项目全流程与40天进度.md](docs/项目全流程与40天进度.md)。

## 项目采用的架构：模块化单体 + 分层边界

这个项目按实际企业应用的演进方式设计：第一阶段采用模块化单体，先保证本地开发和部署简单；代码内部按业务模块和依赖方向组织，未来可以根据业务边界拆分服务。

当前确定的架构原则：

- 按业务模块组织：客服、订单、商品库存、物流、知识库、运营分析。
- 每个模块内部保持接口、应用、业务规则和基础设施边界。
- Agent 属于客服模块的应用编排，不是全系统的万能控制器。
- RAG 属于知识库模块，客服模块通过应用接口调用，不直接操作向量数据库。
- LLM、Embedding、数据库和外部平台都通过适配器接入。
- 第一阶段不提前拆微服务；等出现明确的性能、团队或部署边界后再拆分。

```text
API / 管理后台 / 定时任务
        ↓
模块化单体应用
        ↓
客服模块的 ChatUseCase（应用层）
        ↓
CustomerAgent（路由和工具编排）
        ↓
OrderTool（受控工具）
        ↓
订单模块的权限规则 + Order/Shipment（业务规则层）
        ↓
OrderRepository（数据访问抽象）
        ↓
SQLite / PostgreSQL 等基础设施适配器
```

## 完整目录结构

下面是当前起步模板的目录结构，以及它向企业级模块化单体演进时的目标方向。注释中的“负责”表示该目录应该放什么；不要为了方便把所有代码都塞进 `api.py`。

```text
bordercare-ai/
│
├── app/                                      # 应用主代码：所有运行时业务代码都放在这里
│   ├── __init__.py                           # Python 包标识文件
│   ├── api.py                                # 接口层入口：创建 FastAPI 应用和 HTTP 路由
│   ├── config.py                             # 配置层：项目路径、数据库地址和环境变量
│   ├── schemas.py                            # 接口 DTO：定义 API 请求和响应的数据结构
│   ├── database.py                           # 数据库基础连接：创建 SQLite 连接和初始化表结构
│   ├── chat_service.py                       # 兼容入口：把旧调用转交给 ChatUseCase
│   │
│   ├── application/                          # 应用层：编排一个完整业务用例
│   │   ├── __init__.py                       # 应用层 Python 包标识文件
│   │   ├── chat_use_case.py                  # 客服用例：组装 Agent、工具和仓储并执行请求
│   │   │
│   │   ├── agents/                           # Agent 编排：决定下一步做什么
│   │   │   ├── __init__.py                   # Agent 包标识文件
│   │   │   ├── router.py                     # 意图路由：把用户问题分成订单、物流、退款等类型
│   │   │   └── customer_agent.py             # 客服 Agent：选择工具、控制流程和组织最终回答
│   │   │
│   │   └── tools/                            # 业务工具：给 Agent 使用的受控能力
│   │       ├── __init__.py                   # 工具包标识文件
│   │       └── order_tool.py                 # 订单工具：查询订单、物流，并执行用户权限校验
│   │
│   ├── domain/                               # 业务规则层：稳定的电商业务概念和规则
│   │   ├── __init__.py                       # 领域包标识文件
│   │   ├── entities.py                       # 业务模型：Order、Shipment 等核心业务对象
│   │   ├── repositories.py                   # 数据访问抽象：只定义需要的数据能力，不写 SQL
│   │   └── services.py                       # 业务规则/策略：例如订单归属和访问权限规则
│   │
│   └── infrastructure/                       # 基础设施层：数据库、模型和外部系统适配器
│       ├── __init__.py                       # 基础设施包标识文件
│       └── persistence/                      # 持久化适配器：把领域接口连接到具体数据库
│           ├── __init__.py                   # 持久化包标识文件
│           └── sqlite_order_repository.py    # SQLite 仓储实现：执行订单和物流查询 SQL
│
├── data/                                     # 项目数据：模拟业务数据、知识库和评测数据
│   ├── raw/                                  # 原始业务资料：后续由清洗和 RAG 流程处理
│   │   ├── products/                         # 商品目录、SKU 和商品属性
│   │   │   └── products.csv                  # 模拟商品主数据
│   │   ├── policies/                         # 各市场退货、退款和配送政策
│   │   │   ├── return_policy_us.md           # 美国市场模拟退货政策
│   │   │   ├── return_policy_de.md           # 德国市场模拟退货政策
│   │   │   └── shipping_policy.md            # 模拟配送政策
│   │   ├── faq/                              # 常见问题和客服话术资料
│   │   │   └── faq_cn.md                     # 中文 FAQ 示例
│   │   └── logistics/                        # 物流状态和承运商规则
│   │       └── carrier_rules.md              # 模拟物流状态说明
│   ├── seed/                                 # 数据初始化相关文件
│   │   └── .gitkeep                          # 保留空目录，后续可放 SQL 或 JSON 种子数据
│   └── eval/                                 # 评测集：RAG、意图分类和安全测试样本
│       └── .gitkeep                          # 保留空目录，后续放 JSONL 评测数据
│
├── database/                                 # 本地运行产生的数据库文件
│   ├── .gitkeep                              # 保留数据库目录
│   └── bordercare.db                         # 执行 seed_db.py 后生成，不提交到 Git
│
├── scripts/                                  # 一次性脚本和开发辅助脚本
│   ├── __init__.py                           # 脚本包标识文件
│   └── seed_db.py                            # 清空并生成模拟用户、商品、订单和物流数据
│
├── tests/                                    # 自动化测试：接口、领域规则和安全场景
│   └── test_api.py                            # 健康检查、缺少订单号和越权查询测试
│
├── docs/                                     # 项目设计文档
│   ├── 企业级架构说明.md                      # 企业级模块化单体和 Agent 边界说明
│   ├── architecture.md                       # 架构说明兼容版
│   └── 项目全流程与40天进度.md                 # 文件说明、数据流和每日进度主文档
├── requirements.txt                          # Python 依赖清单
├── .gitignore                                # Git 忽略规则：虚拟环境、缓存和本地数据库
└── README.md                                 # 项目入口说明、启动方式和学习路线
```

### 企业级目标目录结构

当客服、订单和知识库功能继续增加时，代码按业务模块演进为：

```text
app/
├── interfaces/http/                         # 对外 HTTP 接口、鉴权、异常处理
├── modules/                                  # 业务模块，模块之间不直接访问对方数据库表
│   ├── customer_service/                    # 客服会话、Agent、人工接管
│   │   ├── application/                     # 客服用例和 Agent 编排
│   │   ├── domain/                          # 会话、意图、转人工规则
│   │   └── infrastructure/                 # 模型和工具适配器
│   ├── order/                               # 订单、支付、退款
│   │   ├── application/                     # 订单查询和退款申请用例
│   │   ├── domain/                          # 状态、权限、幂等规则
│   │   └── infrastructure/                 # 数据库和支付适配器
│   ├── catalog/                             # 商品和库存
│   ├── logistics/                           # 物流和承运商
│   ├── knowledge/                           # 文档、检索、RAG 评测
│   └── analytics/                           # 运营指标和只读分析
├── shared/                                  # 日志、配置、错误、权限、事件等公共能力
└── infrastructure/                          # 数据库、缓存、向量库、LLM 网关、外部 API
```

当前目录中的 `app/application`、`app/domain` 和 `app/infrastructure` 是第 1～4 天的可运行起步结构。随着业务模块增加，再按上面的目标结构迁移，避免一开始为了形式引入微服务复杂度。

### 各层之间怎么依赖

```text
API / 管理后台 / 定时任务
    ↓ 调用
模块化单体中的 Application Use Case
    ↓ 编排
customer_agent.py（Agent 路由和工具编排）
    ↓ 使用
order_tool.py（受控业务工具）
    ↓ 依赖抽象
repositories.py（数据访问抽象）
    ↓ 由基础设施实现
SQLite / PostgreSQL 等基础设施适配器
```

需要特别注意：

- `api.py` 只处理 HTTP，不直接写订单业务规则或 SQL。
- `CustomerAgent` 只负责路由和编排，不能自行绕过权限规则。
- `domain/` 不应该导入 FastAPI、SQLite 或具体大模型 SDK。
- `repositories.py` 只定义“需要什么数据”，具体 SQL 放到 `infrastructure/`。
- Agent 只负责编排流程，不能绕过权限、退款和库存等业务规则。
- 将来接入 PostgreSQL、RAG、真实物流 API 或 vLLM 时，优先替换基础设施实现，不修改核心业务规则。
- 第一阶段使用模块化单体；只有出现明确的业务、团队、部署或性能边界时，才考虑拆分微服务。

## 环境要求

- Python 3.10+
- Windows、macOS 或 Linux 均可

## 启动项目

在当前目录执行：

```powershell
cd bordercare-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\seed_db.py
uvicorn app.api:app --reload
```

运行测试：

```powershell
python -m pytest -q
```

启动后打开：

- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

## 示例请求

### 查询订单物流

```json
{
  "user_id": "U1001",
  "message": "我的订单 BC10001 到哪里了？"
}
```

### 查询退货政策

```json
{
  "user_id": "U1001",
  "message": "德国用户可以退货吗？"
}
```

## 示例账号和订单

| 用户 | 市场 | 订单 |
|---|---|---|
| `U1001` | US | `BC10001`、`BC10002` |
| `U1002` | DE | `BC10003` |
| `U1003` | UK | `BC10004` |

## 当前模板对应的学习阶段

当前模板对应第 1～4 天：先完成项目边界、业务模型、模块化单体的第一阶段骨架、模拟数据库和最小客服流程。后续功能应该按业务模块增加，而不是把代码全部继续写进 `api.py`。

## Git 使用方式

Git 不单独作为一天的理论任务，而是每天开发的固定流程：

```text
main
  ↓
创建 feat/day-XX-功能名 或 fix/day-XX-问题名
  ↓
完成一个可运行的小改动并提交
  ↓
运行测试、检查敏感信息和临时文件
  ↓
合并阶段成果并创建版本 Tag
```

当前本地项目已经初始化 Git，并配置了 `.gitignore`。没有远程 Git 平台时先进行本地分支和提交练习；以后接入 GitHub、GitLab 或企业 Git 平台，再增加 Pull Request、代码评审和 CI，不改变本地提交习惯。

## 下一步学习顺序

1. 第 5 天：接入统一的 LLM Client 和结构化输出。
2. 第 9～15 天：将 `data/raw/` 建成 RAG 知识库。
3. 第 16～22 天：增加意图路由、权限、人工接管和工具调用。
4. 第 23～29 天：增加运营查询和只读 NL2SQL。
5. 第 30 天以后：再考虑微调、Docker 和 vLLM。
