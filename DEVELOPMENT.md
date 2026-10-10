# Knowledge Agent — 开发文档

> 技术栈、配置、API 参考等。项目展示见 [README.md](README.md)

企业 RAG 知识库问答管理系统。统一流式入口支持自动、标准和 Agentic 三种执行策略。

已打通完整链路：知识库管理、文档解析切块、向量索引、语义检索、流式问答、多轮对话、引用追溯、质量反馈、Agentic 自主检索（查询分析→检索→评估→改写重试→Web 搜索回退）。前端统一对话界面，仪表盘首页，全局错误提示，可复现三模式 RAG 对比评测。

## 系统架构

```mermaid
flowchart LR
    subgraph 用户
        B[浏览器]
    end

    subgraph 前端[Nginx + Vue 3]
        F[静态资源]
        P[API 代理]
    end

    subgraph 后端[FastAPI]
        R[routers]
        S[services]
        DB[(SQLite)]
    end

    subgraph 向量
        CH[(ChromaDB)]
    end

    subgraph 模型
        OL[OpenAI-compatible APIs]
    end

    B --> F
    B --> P
    P --> R
    R --> S
    S --> DB
    S --> CH
    S --> OL
```

## 技术栈

- Frontend: Vue 3 + TypeScript + Vite + Ant Design Vue
- Backend: FastAPI + SQLite
- Vector DB: ChromaDB（嵌入模式，PersistentClient）
- Agent 框架: LangGraph StateGraph（8 个上下文准备节点 / 3 组条件路由）
- 关键词检索: rank-bm25（中文 bigram 分词，pickle 持久化）
- Cross-encoder 重排: BGE-Reranker-v2-m3（硅基流动云端 API / 本地 HuggingFace）
- Web 搜索回退: DuckDuckGo（ddgs）
- Document parsing: Markdown / Text / PDF（pdfplumber 表格提取）/ DOCX
- Embedding: OpenAI-compatible API，推荐本地 Ollama `nomic-embed-text`
- LLM: OpenAI-compatible API，支持流式输出 + JSON mode
- 评测: 固定 18 题基准（确定性检索/引用指标 + LLM Judge）

## 已实现功能

### 知识库管理
- 知识库创建、列表、更新、删除
- 文档上传（魔术字节校验）、列表（搜索/筛选/分页）、删除
- 文档解析：段落感知定长切块，PDF 表格提取（pdfplumber），支持 MD/TXT/PDF/DOCX
- embedding 分批请求，避免超时
- SQLite 持久化任务队列，解析/索引异步执行；pending 任务可跨重启继续处理

### 检索与问答
- 混合检索：向量 Top-K + BM25 关键词，RRF 融合排序
- Chroma 向量索引与 Top-K 语义检索（分数色条可视化）
- Cross-encoder 重排（可选）：候选 4 倍扩召回，BGE-Reranker 精排取 Top-K，支持本地 HuggingFace / 硅基流动云端 API
- 重排后保留 BM25 首位精确匹配，避免单个重排器误删强词法证据
- 流式 SSE 问答（逐 token 渲染）
- 统一对话界面：多轮上下文自动传递，默认自动选择标准或 Agentic 策略
- 检索结果默认折叠，回答区左右分栏（左回答 / 右引用来源）
- **来源过滤**：只展示 LLM 实际引用的来源（如 `[1][4]` 只显示 2 个），未采用的不占空间
- 引用双向联动（回答引文 ↔ 来源卡片 hover 高亮 + click 滚动）
- 回答质量反馈（👍/👎 评分持久化）

### Agentic RAG
- **查询分析**：LLM 判断查询复杂度，复杂问题自动拆分为原子性子问题
- **并行首轮检索**：多子问题的首轮检索+评估通过 ThreadPoolExecutor 并行执行，
  各线程独立 LLM/Embedding provider；单子问题与简单查询仍走串行 LangGraph 图
- **自纠正检索**：每个子问题独立评估与改写（最多 3 轮），整个请求最多 8 次知识库检索
- **Web 搜索回退**：知识库检索耗尽后，可选启用 DuckDuckGo 外部搜索补充上下文
- **LangGraph 状态图**：8 个上下文准备节点、3 组条件路由，图外统一流式生成一次最终答案
- **自动策略**：确定性结构规则结合 LLM 分析进行路由；简单问题走 Standard，
  复杂问题进入使用 2 轮 / 6 次预算的 Agentic 流程
- **统一入口**：`/questions/stream` 同时支持 `auto | standard | agentic`
- **可复现评测**：修复后 Auto 文档召回率 0.967、答案正确性 0.986，平均延迟 41.72s
  （并行首轮优化前的数据，后续可重新跑基准对比）

### 对话管理
- **对话持久化**：`conversations` 表 + CRUD API，Q&A 关联 `conversation_id`，页面刷新不丢对话
- **对话列表**（ChatGPT 风格）：侧栏显示所有对话，第一条问题自动做标题，一键切换/删除
- **历史恢复**：进入知识库自动加载最近对话，多轮上下文完整保留

### 工程质量
- JWT 认证（单管理员模型，环境变量配置）+ API Token 向后兼容脚本调用（时序安全比较）
- API 限流（滑动窗口 IP 限流，默认 60 req/min）
- 结构化日志（JSON 格式 + X-Request-ID 全链路追踪）
- Agentic 流程每步实时日志输出
- 全局错误提示：axios 拦截器 + ErrorToast 组件，区分网络/5xx/业务错误
- 服务启动时保留 pending 任务，并将中断在 running 状态的任务标记为 failed
- 健康检查覆盖数据库、ChromaDB、LLM 连通性
- CORS 可配置（`CORS_ORIGINS` 环境变量）
- Docker Compose 部署（需配置外部聊天模型，或另行拉取本地聊天模型）
- CI：GitHub Actions 自动测试 + 类型检查 + 构建
- 后端 128 个单元测试（检索、分词、RRF、问答、任务队列、Agentic 图、检索预算、并行编排、评测等）
- 前端 22 个单元测试（useKnowledgeBases 过滤/空值保护、useDocuments 状态过滤/搜索/计算属性）
- 设计决策文档（`docs/decisions.md`）+ 设计规范文档（`DESIGN.md`）
- 固定语料三模式对比评测结果（Standard vs Agentic vs Auto）

### 性能优化
- BM25 索引 pickle 持久化，重启秒加载，免全量重建
- Embedding 向量 SQLite 缓存，相同文本不重复调 API
- 任务队列 Event 唤醒替代轮询，无任务时零 CPU 消耗
- 前端组件异步懒加载，首屏体积优化

## 项目结构

```text
.
├── .github/workflows/
│   └── ci.yml                 # CI：自动测试 + 类型检查 + 构建
├── backend/
│   ├── app/
│   │   ├── agent/                   # Agentic RAG — LangGraph 状态图
│   │   │   ├── state.py             #   AgenticState 定义
│   │   │   ├── nodes.py             #   8 个上下文准备节点（分析/检索/评估/改写/回退）
│   │   │   └── graph.py             #   StateGraph 构建 + 条件路由 + run_agentic_qa()
│   │   ├── routers/
│   │   │   ├── knowledge_bases.py   # 知识库 CRUD
│   │   │   ├── documents.py         # 文档上传/解析/索引 + 任务处理器
│   │   │   ├── qa.py                # 检索 + 问答 + 流式 SSE（传统模式）
│   │   │   ├── history.py           # 问答历史查询/评分/删除
│   │   │   ├── conversations.py     # 对话 CRUD（列表/切换/删除）
│   │   │   └── auth.py             # 认证端点（POST /login 签发 JWT, GET /me）
│   │   ├── repositories/     # SQLite 数据访问（知识库/文档/切块/问答）
│   │   ├── services/         # 解析、切块、索引、检索、问答、LLM/Embedding、关键词检索
│   │   │   ├── retrieval.py         #   混合检索：向量+BM25+RRF+重排
│   │   │   ├── answering.py         #   答案生成（流式 + 非流式）
│   │   │   ├── indexing.py          #   索引编排（向量化 + BM25 重建）
│   │   │   ├── chunker.py           #   段落感知定长切块
│   │   │   ├── document_parser.py   #   文档解析（MD/TXT/PDF/DOCX）
│   │   │   ├── document_storage.py  #   文件存储（上传校验、路径构建）
│   │   │   ├── keyword_search.py    #   BM25 关键词检索 + 中文 bigram 分词
│   │   │   ├── vector_store.py      #   ChromaDB PersistentClient 封装
│   │   │   ├── embeddings.py        #   Embedding API 封装 + 分批请求
│   │   │   ├── llm.py               #   LLM 调用（urllib，流式 + 非流式）
│   │   │   ├── llm_agent.py         #   Agentic LLM（openai SDK，JSON mode）
│   │   │   ├── query_analysis.py    #   查询复杂度分析 + 子问题拆解
│   │   │   ├── self_corrective.py   #   上下文评估 + 查询改写
│   │   │   ├── web_search.py        #   DuckDuckGo Web 搜索回退
│   │   │   ├── embedding_cache.py   #   Embedding 向量 SQLite 缓存
│   │   │   └── reranker.py          #   Cross-encoder 重排（本地/云端）
│   │   ├── auth.py           # JWT + API Token 双轨认证（require_auth 始终强制鉴权）
│   │   ├── config.py         # 环境变量配置（pydantic-settings, 含 JWT/Agentic 开关）
│   │   ├── rate_limit.py     # 滑动窗口 IP 限流中间件
│   │   ├── database.py       # SQLite 初始化
│   │   ├── dependencies.py   # 依赖注入工厂（keyword_engine / task_queue）
│   │   ├── task_queue.py     # SQLite 持久化任务队列（含重试）
│   │   ├── schemas.py        # Pydantic 请求/响应模型（含 Agentic 类型）
│   │   ├── logging_config.py # 结构化日志（JSON / 文本 + request_id）
│   │   └── main.py           # FastAPI app（CORS、X-Request-ID、上传限制、健康检查、启动恢复）
│   ├── tests/                # 128 个单元测试（检索、分词、RRF、问答、任务队列、Agentic 图、并行编排、评测等）
│   ├── eval/                 # 固定数据集 + 三模式评测 + 历史评测脚本
│   ├── data/                 # 本地数据库、上传文件、Chroma 数据
│   └── requirements.txt
├── frontend/
│   ├── e2e/                   # Playwright e2e 冒烟测试
│   │   └── smoke.spec.ts      #   欢迎页 / 创建KB / 问答 / 文档管理 / 响应式
│   ├── playwright.config.ts   # Playwright 配置（自动启动前后端）
│   ├── src/
│   │   ├── router/index.ts   # vue-router 路由配置（/login, /, /{kb_id} 问答, /{kb_id}/documents + 守卫）
│   │   ├── views/            # LoginView(登录) / WelcomeView(仪表盘) / KbWorkspaceView(问答) / KbDocumentsView(文档管理)
│   │   ├── App.vue           # 管理台外壳（侧栏 + ErrorToast + router-view; public 路由绕过 shell）
│   │   ├── components/       # Sidebar / DocumentPanel / DebugPanel / ConversationPanel / HistoryPanel / ErrorToast
│   │   ├── composables/      # useAuth(登录/JWT) / useKnowledgeBases / useDocuments / useQA / useConversation(含Agentic)
│   │   ├── composables/*.test.ts  # vitest 单测（useKnowledgeBases 9 + useDocuments 13 = 22 个）
│   │   ├── utils/            # api(JWT拦截+401重定向) / authStorage(localStorage叶子) / citations / format / retrieval / sse
│   │   ├── types/            # 类型定义
│   │   ├── assets/
│   │   ├── main.ts
│   │   └── style.css
│   └── package.json
├── docs/
│   ├── decisions.md          # 设计决策记录（为什么选 RRF、为什么 SQLite 队列等）
│   └── superpowers/          # 产品设计文档
├── DESIGN.md                 # 设计规范（颜色/字体/组件/布局/动效/响应式等 9 章）
├── docker-compose.yml
└── README.md
```

## 环境准备

需要本机已有：

- Python 3.12+
- Node.js 20+
- Ollama，本地 embedding 推荐使用

安装本地 embedding 模型：

```bash
ollama pull nomic-embed-text
```

可选：如果要用本地大模型回答问题，可以准备一个 chat 模型，例如：

```bash
ollama pull qwen2.5:7b
```

## 配置

在项目根目录创建 `.env`：

```bash
# JWT 认证（单管理员模型，首次启动必填）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<你的强密码>
JWT_SECRET=<随机字符串，可用 python -c "import secrets;print(secrets.token_urlsafe(48))" 生成>
JWT_EXPIRE_HOURS=24

# API Token（可选，向后兼容脚本调用；留空则脚本必须通过 /api/auth/login 获取 JWT）
API_TOKEN=

# 上传文件大小限制（默认 50 MB）
MAX_UPLOAD_BYTES=52428800

# 日志格式（true 输出 JSON 行日志，方便日志采集）
LOG_JSON=false

# CORS 跨域白名单（逗号分隔，默认 *）
CORS_ORIGINS=*

# 限流（0 关闭限流）
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW=60

DATABASE_URL=sqlite:////home/zyp13/projects/Knowledge AI/backend/data/knowledge_agent.db
STORAGE_DIR=/home/zyp13/projects/Knowledge AI/backend/data/uploads
CHROMA_DIR=/home/zyp13/projects/Knowledge AI/backend/data/chroma

# Embedding 模型（OpenAI-compatible API）
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BATCH_SIZE=20

# LLM 模型（OpenAI-compatible API，支持流式）
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b

# Cross-encoder 重排（可选，开启后候选扩 4 倍再精筛）
CROSS_ENCODER_ENABLED=false
CROSS_ENCODER_PROVIDER=siliconflow
CROSS_ENCODER_MODEL=BAAI/bge-reranker-v2-m3
SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

说明：

- **JWT 认证**：`ADMIN_USERNAME`/`ADMIN_PASSWORD` 配置单管理员凭据，`JWT_SECRET` 用于签发和验证 JWT（HS256）。前端登录后存储 JWT 到 localStorage，每次请求携带 `Authorization: Bearer <jwt>`。未配置 `ADMIN_PASSWORD` 时登录端点返回 400 友好提示。
- `API_TOKEN` 向后兼容脚本/外部调用：设了值则脚本可继续用 `Authorization: Bearer <api_token>` 访问；留空则脚本必须先调 `/api/auth/login` 拿 JWT。`require_auth` 始终强制鉴权，不再有"token 为空则放行"的后门。
- `CORS_ORIGINS` 控制跨域白名单，默认 `*`（开发用）。生产部署时设为具体域名，逗号分隔。
- `LOG_JSON` 设为 `true` 输出 JSON 行日志（含 `request_id`），方便日志采集系统解析。
- `MAX_UPLOAD_BYTES` 限制单次请求体大小，防止上传超大文件。
- `EMBEDDING_*` 用于文档索引和检索查询向量化。`EMBEDDING_BATCH_SIZE` 控制每批发送的文本数（默认 `20`）。
- `LLM_*` 用于问答生成和 Agentic 流程（查询分析/评估/改写均调用 LLM）；只做上传、解析、索引、检索时可以暂时不填。
- `RATE_LIMIT_REQUESTS` 每个 IP 每分钟最大请求数（默认 `60`），设为 `0` 关闭限流。
- `RATE_LIMIT_WINDOW` 限流滑动窗口秒数（默认 `60`）。
- `CROSS_ENCODER_ENABLED` 启用跨编码器重排（默认 `false`），开启后检索候选数自动扩大 4 倍再精筛。
- `CROSS_ENCODER_PROVIDER` 重排后端：`siliconflow`（推荐，云端 API）或 `local`（本地 HuggingFace 模型）。
- `CROSS_ENCODER_MODEL` 重排模型名（默认 `BAAI/bge-reranker-v2-m3`）。
- `SILICONFLOW_API_KEY` 硅基流动 API Key（使用云端重排时必填）。
- `SILICONFLOW_BASE_URL` 硅基流动 API 地址（默认 `https://api.siliconflow.cn/v1`）。
- `.env` 已加入 `.gitignore`，不要提交真实密钥。
- 后端对本地 OpenAI-compatible 请求会禁用系统代理，避免访问 `127.0.0.1:11434` 时被代理转发导致 502。
- 服务启动时会将卡在 `running` 状态的文档和任务标记为 `failed`；原有
  `pending` 任务保留并继续处理。

## 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

后端默认地址：

```text
http://127.0.0.1:8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

Vite 已配置 `/api` 代理到 `http://127.0.0.1:8000`。

## MVP 使用流程

1. 打开前端仪表盘（首页）。
2. 创建知识库 → 自动跳转到对话界面。
3. 点击"管理文档 →"进入文档管理页。
4. 上传 Markdown、TXT、PDF 或 DOCX 文档。
5. 点击解析，生成文本切块。
6. 点击索引，调用 embedding 模型并写入 Chroma。
7. 返回对话界面，输入问题开始提问或对话。
8. 回答中点击 `[1][2]` 查看来源，hover 高亮对应卡片。

## API 概览

```text
# 认证
POST   /api/auth/login                      # 用户名+密码 → JWT
GET    /api/auth/me                         # 验证 JWT，返回当前用户

# 知识库
GET    /api/knowledge-bases
POST   /api/knowledge-bases
GET    /api/knowledge-bases/{knowledge_base_id}
PATCH  /api/knowledge-bases/{knowledge_base_id}
DELETE /api/knowledge-bases/{knowledge_base_id}

# 文档
GET    /api/knowledge-bases/{knowledge_base_id}/documents                ?limit=&offset=
POST   /api/knowledge-bases/{knowledge_base_id}/documents
DELETE /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}

# 解析 / 索引
POST   /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse
POST   /api/knowledge-bases/{knowledge_base_id}/documents/parse-pending
GET    /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunks
POST   /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index
POST   /api/knowledge-bases/{knowledge_base_id}/documents/index-pending
POST   /api/knowledge-bases/{knowledge_base_id}/documents/reindex-all

# 检索 / 问答
POST   /api/knowledge-bases/{knowledge_base_id}/retrieve
POST   /api/knowledge-bases/{knowledge_base_id}/questions
POST   /api/knowledge-bases/{knowledge_base_id}/questions/stream           (SSE)

# 问答历史 / 反馈
GET    /api/knowledge-bases/{knowledge_base_id}/question-answers          ?limit=&offset=
PATCH  /api/knowledge-bases/{knowledge_base_id}/question-answers/{id}/rating
DELETE /api/knowledge-bases/{knowledge_base_id}/question-answers/{id}

# 对话
POST   /api/knowledge-bases/{knowledge_base_id}/conversations
GET    /api/knowledge-bases/{knowledge_base_id}/conversations
GET    /api/knowledge-bases/{knowledge_base_id}/conversations/{conv_id}
PATCH  /api/knowledge-bases/{knowledge_base_id}/conversations/{conv_id}
DELETE /api/knowledge-bases/{knowledge_base_id}/conversations/{conv_id}
```

## Docker 部署

```bash
# 启动 Ollama、后端和前端（首次会自动拉取 embedding 模型）
docker compose up -d

# 本地回答还需要单独拉取聊天模型；使用外部 LLM 时可跳过
docker compose exec ollama ollama pull qwen2.5:7b

# 查看启动日志
docker compose logs -f

# 打开浏览器
# http://localhost:8080
```

如需使用外部 LLM（如 DeepSeek），在 `.env` 或命令行指定：

```bash
LLM_BASE_URL=https://api.deepseek.com/v1 \
LLM_API_KEY=sk-xxx \
LLM_MODEL=deepseek-chat \
docker compose up -d
```

用 Ollama 运行本地 chat 模型：

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

## Agentic RAG 使用

Agentic RAG 让 LLM 自主决定检索策略，而非一次性检索后直接生成。

### 两种模式对比

| | 标准 RAG | Agentic RAG |
|---|---|---|
| 检索次数 | 1 次 | 每个子问题最多 3 轮、全局最多 8 次 |
| 检索不足 | 不重试，证据不足时拒答 | 评估上下文并改写查询重试 |
| 复杂问题 | 当整体搜 | 自动拆子问题分别搜 |
| Web 补充 | 无 | 可选 DuckDuckGo 回退 |
| 固定基准平均延迟 | 11.65s | 65.36s |
| 策略参数 | `standard` | `agentic` |

### Agentic 流程图

```
用户问题
  → 查询分析（复杂则拆成原子子问题）
  → 多子问题：首轮检索+评估并行执行（ThreadPoolExecutor，各子问题独立）
    单子问题：串行图执行
  → 合并去重（按 vector_id 全局去重）
      ├── 某子问题评分 <3 分且有预算 → 串行重试：LLM 改写查询 → 重新检索
      ├── 预算耗尽 → 剩余子问题标记 global_budget_exhausted
      └── 仍有不足且允许 Web → DuckDuckGo 回退
  → 图外统一生成一次带引用的流式答案
```

### 通过 API 调用

```bash
# 统一流式入口（默认 strategy=auto）
curl -N -X POST http://127.0.0.1:8000/api/knowledge-bases/{kb_id}/questions/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"TCP和UDP有什么区别？","strategy":"auto","max_retrieval_rounds":3}'

# 启用 Web 搜索回退
curl -N -X POST .../questions/stream \
  -d '{"question":"Python的GIL是什么？","strategy":"agentic","enable_web_search":true}'
```

### 前端切换

打开前端管理台 → 进入知识库。系统默认使用 `auto`；工具栏可在调试时强制选择标准或 Agentic 策略。

Agentic 模式下会显示：
- 实时状态：`⚡ 正在分析查询...` → `2 轮检索 · 评分 4/5`
- 子查询拆解详情（复杂查询时）
- 可选启用 Web 搜索回退复选框

### 配置

Agentic 行为通过每次问答请求控制：

- `strategy=auto|standard|agentic` 选择执行策略；
- `max_retrieval_rounds=1..3` 控制强制 Agentic 模式的单子问题轮数；
- `enable_web_search=true|false` 控制是否允许 DuckDuckGo 回退；
- Auto 路由到 Agentic 时固定使用 2 轮 / 6 次总检索预算。

如需避免 Agentic 调用，在 API 或前端调试选项中显式使用
`strategy=standard`。当前问答统一入口始终注册，不提供独立 Agentic 路由。

### 终端查看执行流程

后端启动时，Agentic 每步都会在终端输出实时日志：

```
========== Agentic RAG 开始 ==========
问题: TCP和UDP有什么区别？
  Step 1/5: 分析查询...
    → 复杂查询，拆为 2 个子问题: ['What is TCP?', 'What is UDP?']
  Step 2/5: 第 1 轮检索 query='What is TCP?'...
    -> 召回 5 个片段
  Step 3/5: 评估检索质量...
    -> 评分 4/5: Context clearly explains TCP...
  Step 5/5: 生成答案 (共 5 个上下文片段)...
========== Agentic RAG 结束 ==========
结果: 1 轮检索, 评分 4/5, 5 个来源
```

## 检索质量评估

### 固定语料三模式评估

评测入口：`backend/eval/benchmark_runner.py`；数据集：
`backend/eval/benchmark.jsonl`。18 道人工标注题覆盖单文档事实、多文档综合、
MDN/RFC 对照和无答案问题。主实验固定使用 5 份文档并关闭 Web 搜索。

**固定基线与 2026-07-30 Auto 修复回归：**

Standard、Agentic 为 2026-07-29 三模式基线；Auto 为修复命令行评测的
BM25 初始化、关键词来源元数据和重排误杀保护后的 2026-07-30 回归。

| Metric | Standard | Agentic | Auto |
|--------|---------:|--------:|-----:|
| document_recall | 0.767 | 0.933 | **0.967** |
| fact_coverage | 0.601 | 0.798 | **0.847** |
| citation_validity | 0.938 | 0.933 | **1.000** |
| unanswerable_correct | 1.000 | 1.000 | 1.000 |
| faithfulness | 0.967 | **0.994** | 0.986 |
| answer_correctness | 0.556 | 0.936 | **0.986** |
| answer_relevancy | 0.600 | 0.944 | **1.000** |
| mean latency | **11.65s** | 65.36s | 41.72s |

Auto 将 9/18 题路由到 Agentic。修复后单文档正确性从 0.738 提升到
0.983，多文档正确性达到 0.975，整体正确性达到 0.986，平均延迟从
55.28 秒降至 41.72 秒。18 道题全部成功；LLM Judge 成功解析 14/18，
确定性指标覆盖 18/18。以上为并行首轮优化前的基线数据；
Agentic 内部串行 LLM 调用已通过多子问题首轮并行化改善，
可用下方命令重新跑基准对比。

```bash
cd backend
.venv/bin/python eval/benchmark_runner.py \
  --kb-id <evaluation-kb-id> \
  --modes standard agentic auto
```

完整复现说明见 `backend/eval/README.md`。

## CI

每次 push 自动运行（`.github/workflows/ci.yml`）：

| Job | 内容 |
|-----|------|
| backend | Python 3.12 + pip install + 128 个单元测试 |
| frontend | Node 20 + npm ci + vitest 22 个单元测试 + vue-tsc 类型检查 + vite build |
| e2e | Playwright Chromium 冒烟测试（登录 → 创建知识库 → 问答页 → 文档管理 → 响应式） |

## 测试

**后端 128 个单元测试：**

```bash
cd backend && .venv/bin/python -m unittest discover tests
```

覆盖：知识库 CRUD、文档上传/解析/索引、向量检索、BM25 分词与搜索、RRF
融合排序、问答生成、任务队列、Agentic 状态图（查询分析、检索、评估、
改写、去重和 Web 回退）、评测及 API 端点。

**前端 22 个单元测试（vitest）：**

```bash
cd frontend && npx vitest run
```

覆盖：useKnowledgeBases（过滤、空值保护、大小写、选中态）、useDocuments（状态过滤、搜索、计算属性、filterOptions 统计）。

**前端 e2e 冒烟测试（Playwright）：**

```bash
cd frontend
npx playwright test
```

覆盖：登录页加载、创建知识库、问答面板默认 tab、对话记录切换、文档管理页导航、移动端侧栏交互。

**前端构建：**

```bash
cd frontend
npm run build
```

## 常见问题

### 上传后索引报 `Embedding provider is not configured`

检查 `.env` 中是否设置：

```bash
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text
```

修改 `.env` 后重启后端。

### 索引报 `model "nomic-embed-text" not found`

本地 Ollama 还没有下载 embedding 模型：

```bash
ollama pull nomic-embed-text
```

### 索引报 `Embedding request failed: 502`

通常是本地模型请求被系统代理影响。当前代码已经对 embedding 和 LLM 请求显式禁用代理；如果仍出现，确认后端已重启并加载最新代码。

### 问答报 `LLM provider is not configured`

索引和检索只需要 embedding；问答还需要配置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。

本地 Ollama 示例：

```bash
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
```

## 下一步

**近期：**
- ~~多轮对话持久化（`conversation_id` 关联多轮 Q&A）~~ ✅
- ~~侧栏知识库列表显示文档数量~~ ✅ 仪表盘
- ~~Embedding 模型本地缓存，避免重复请求~~ ✅ SQLite 缓存
- ~~混合检索结果重排（cross-encoder reranker）~~ ✅ 硅基流动云端 + 本地 HuggingFace
- ~~JWT 真鉴权（单管理员模型，替换前端打包 token 的安全剧场）~~ ✅
- ~~流式中断持久化（SSE 中断时仍保存已生成部分答案）~~ ✅
- ~~前端 composables 单测（vitest，空值保护/过滤/状态逻辑）~~ ✅
- ~~config.py 改用 pydantic-settings（友好错误，类型校验）~~ ✅
- 移动端响应式适配（DESIGN.md 已定义断点，CSS 部分实现）

**中期：**
- ~~用户、角色、知识库级权限~~ 单用户 JWT 已实现；多用户/RBAC 待定
- 语义分块（基于 embedding 相似度边界检测，替代固定大小切块）— 当前段落感知定长切块在 18 题基准已表现良好（召回 0.967、正确性 0.986），优先级低
- 增量索引（文档更新后只重新索引变化部分）
- ~~Agentic 首轮检索并行化~~ ✅ 多子问题首轮检索+评估 ThreadPoolExecutor 并行执行，
  retry 仍串行；预期将 Agentic 延迟从 ~41s 降至 ~20-25s（待重新跑基准验证）

**远期（生产化，按需触发，不提前优化）：**
- PostgreSQL + pgvector 迁移 — **触发条件**：多实例部署 / 文档向量达百万级 ChromaDB 性能衰退 / 需按 JSON 字段复杂查询。当前 SQLite + ChromaDB（31MB 数据）完全够用，单实例无瓶颈，迁移为增加运维成本
- Redis — **触发条件**：多实例水平扩展（共享限流/任务队列）/ 需主动让 JWT 失效（多用户场景）/ 观察到重复提问值得加答案缓存。单实例下 SQLite 任务队列 + 内存限流已足够
- S3/MinIO 对象存储 — **触发条件**：文档量超出本地磁盘或需跨节点共享
- 监控告警、自动扩缩容
