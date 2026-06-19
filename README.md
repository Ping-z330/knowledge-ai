# Knowledge Agent

企业 RAG 知识库问答管理系统。

已打通完整链路：知识库管理、文档解析切块、向量索引、语义检索、流式问答、多轮对话、引用追溯、质量反馈。

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
        OL[Ollama]
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
- Vector DB: Chroma
- Document parsing: Markdown / Text / PDF（pdfplumber 表格提取）/ DOCX
- Embedding: OpenAI-compatible API，推荐本地 Ollama `nomic-embed-text`
- LLM: OpenAI-compatible API，支持流式输出

## 已实现功能

- 知识库创建、列表、更新、删除
- 文档上传（魔术字节校验）、列表（搜索/筛选/分页）、删除
- 文档解析：段落感知语义切块，PDF 表格提取（pdfplumber）
- embedding 分批请求，避免超时
- SQLite 持久化任务队列，解析/索引异步执行，服务重启不丢任务
- 混合检索：向量 Top-K + BM25 关键词，RRF 融合排序
- 检索质量评估脚本（Recall@k + MRR）
- Chroma 向量索引与 Top-K 语义检索（分数色条可视化）
- 流式 SSE 问答（逐 token 渲染）
- 多轮对话（上下文历史传递、气泡 UI）
- 引用双向联动（回答引文 ↔ 来源卡片相互定位）
- 检索结果引用对比（已引用/未采用标记）
- 回答质量反馈（👍/👎 评分持久化）
- API Token 认证（时序安全比较）
- 结构化日志（JSON 格式 + X-Request-ID 全链路追踪）
- 服务启动时自动恢复卡住的异步任务
- CORS 可配置（`CORS_ORIGINS` 环境变量）
- Docker Compose 一键部署
- 前端管理台：vue-router URL 路由、组件化架构、对话面板、调试面板
- `.env` 配置加载
- CI：GitHub Actions 自动测试 + 类型检查 + 构建
- 后端 49 个单元测试覆盖核心链路（检索、分词、RRF、问答、任务队列等）
- 设计决策文档（`docs/decisions.md`）

## 项目结构

```text
.
├── .github/workflows/
│   └── ci.yml                 # CI：自动测试 + 类型检查 + 构建
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   │   ├── knowledge_bases.py   # 知识库 CRUD
│   │   │   ├── documents.py         # 文档上传/解析/索引 + 任务处理器
│   │   │   ├── qa.py                # 检索 + 问答 + 流式 SSE
│   │   │   └── history.py           # 问答历史查询/评分/删除
│   │   ├── repositories/     # SQLite 数据访问（知识库/文档/切块/问答）
│   │   ├── services/         # 解析、切块、索引、检索、问答、LLM/Embedding、关键词检索
│   │   ├── auth.py           # API token 认证（时序安全比较）
│   │   ├── config.py         # 环境变量配置
│   │   ├── database.py       # SQLite 初始化
│   │   ├── dependencies.py   # 依赖注入工厂（keyword_engine / task_queue）
│   │   ├── task_queue.py     # SQLite 持久化任务队列（含重试）
│   │   ├── schemas.py        # Pydantic 请求/响应模型
│   │   ├── logging_config.py # 结构化日志（JSON / 文本 + request_id）
│   │   └── main.py           # FastAPI app（CORS、X-Request-ID、上传限制、健康检查、启动恢复）
│   ├── tests/                # 49 个单元测试（检索、分词、RRF、问答、任务队列等）
│   ├── eval/                 # 检索质量评估（Recall@k + MRR）
│   ├── data/                 # 本地数据库、上传文件、Chroma 数据
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── router/index.ts   # vue-router 路由配置
│   │   ├── views/            # WelcomeView / KbWorkspaceView
│   │   ├── App.vue           # 管理台外壳（侧栏 + router-view）
│   │   ├── components/       # Sidebar / DocumentPanel / DebugPanel / ConversationPanel / HistoryPanel / WelcomeCard
│   │   ├── composables/      # useKnowledgeBases / useDocuments / useQA / useConversation
│   │   ├── utils/            # api / citations / format / retrieval
│   │   ├── types/            # 类型定义
│   │   ├── assets/
│   │   ├── main.ts
│   │   └── style.css
│   └── package.json
├── docs/
│   ├── decisions.md          # 设计决策记录（为什么选 RRF、为什么 SQLite 队列等）
│   └── superpowers/          # 产品设计文档
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
# API 认证（留空则不启用认证）
API_TOKEN=

# 上传文件大小限制（默认 50 MB）
MAX_UPLOAD_BYTES=52428800

DATABASE_URL=sqlite:////home/zyp13/projects/Knowledge AI/backend/data/knowledge_agent.db
STORAGE_DIR=/home/zyp13/projects/Knowledge AI/backend/data/uploads
CHROMA_DIR=/home/zyp13/projects/Knowledge AI/backend/data/chroma

EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text

LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
```

说明：

- `API_TOKEN` 设置后，所有 `/api/` 请求需要携带 `Authorization: Bearer <token>` 头。留空则不启用认证。
- `CORS_ORIGINS` 控制跨域白名单，默认 `*`（开发用）。生产部署时设为具体域名，逗号分隔。
- `LOG_JSON` 设为 `true` 输出 JSON 行日志（含 `request_id`），方便日志采集系统解析。
- `MAX_UPLOAD_BYTES` 限制单次请求体大小，防止上传超大文件。
- `EMBEDDING_*` 用于文档索引和检索查询向量化。
- `LLM_*` 用于最终问答生成；只做上传、解析、索引、检索时可以暂时不填。
- `.env` 已加入 `.gitignore`，不要提交真实密钥。
- 后端对本地 OpenAI-compatible 请求会禁用系统代理，避免访问 `127.0.0.1:11434` 时被代理转发导致 502。
- 服务启动时会自动将卡在 `running` 状态的文档标记为 `failed`，防止重启导致任务丢失。

## 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
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

1. 打开前端管理台。
2. 创建一个知识库。
3. 上传 Markdown、TXT 或 PDF 文档。
4. 点击解析，生成文本切块。
5. 点击索引，调用 embedding 模型并写入 Chroma。
6. 输入问题进行检索或问答。
7. 在回答下方查看引用来源。

## API 概览

```text
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
POST   /api/knowledge-bases/{knowledge_base_id}/questions/stream          (SSE)

# 问答历史 / 反馈
GET    /api/knowledge-bases/{knowledge_base_id}/question-answers          ?limit=&offset=
PATCH  /api/knowledge-bases/{knowledge_base_id}/question-answers/{id}/rating
DELETE /api/knowledge-bases/{knowledge_base_id}/question-answers/{id}
```

## Docker 部署

```bash
# 启动全部服务（Ollama + 后端 + 前端）
docker compose up -d

# 首次启动会自动拉取 embedding 模型 nomic-embed-text
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

## 检索质量评估

针对预定义的测试问题集，自动解析文档 → 索引 → 检索，计算 Recall@k 和 MRR：

```bash
cd backend
PYTHONPATH=. python eval/run.py
```

测试问题涵盖文档格式、embedding 配置、API 认证、模型支持等场景，见 `backend/eval/questions.py`。

## CI

每次 push 自动运行（`.github/workflows/ci.yml`）：

| Job | 内容 |
|-----|------|
| backend | Python 3.12 + pip install + 49 个单元测试 |
| frontend | Node 20 + npm ci + vue-tsc 类型检查 + vite build |

## 测试

后端 49 个单元测试：

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover backend/tests
```

覆盖：知识库 CRUD、文档上传/解析/索引、向量检索、BM25 分词与搜索、RRF 融合排序、问答生成、任务队列、API 端点。

前端构建：

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

**近期（低投入、高收益）：**
- 文档解析增强：旧 `.doc`、PPTX、HTML
- 多轮对话持久化（`conversation_id` 关联多轮 Q&A）
- 文档列表后端搜索（模糊匹配 + 分页）
- SSE 请求 AbortController（防止快速切换知识库时流冲突）
- 前端 e2e 冒烟测试（Playwright）

**中期（需要一定重构）：**
- 用户、角色、知识库级权限
- Embedding 模型本地缓存，避免重复请求
- 混合检索结果重排（rerank）与相关性调优

**远期（生产化）：**
- 生产环境：PostgreSQL、S3/MinIO 对象存储
- 监控告警、自动扩缩容
