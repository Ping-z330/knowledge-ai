# Knowledge Agent

企业 RAG 知识库问答管理系统 MVP。

当前版本优先打通一整套通用链路：创建知识库、上传文档、解析切块、向量索引、语义检索、基于引用来源问答。权限、多租户、审计、异步任务队列等企业增强能力后续再接入。

## 技术栈

- Frontend: Vue 3 + TypeScript + Vite + Ant Design Vue
- Backend: FastAPI + SQLite
- Vector DB: Chroma
- Document parsing: Markdown / Text / PDF
- Embedding: OpenAI-compatible API，当前推荐本地 Ollama `nomic-embed-text`
- LLM: OpenAI-compatible API，可接 Ollama、DeepSeek、OpenAI 等

## 已实现功能

- 知识库创建、列表、更新、删除
- 文档上传、列表、删除
- 文档解析与文本切块
- Chroma 向量索引
- Top-K 向量检索
- RAG 问答与来源引用展示
- 前端 MVP 管理台
- `.env` 配置加载
- 后端单元测试覆盖核心链路

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── routers/          # FastAPI API 路由
│   │   ├── repositories/     # SQLite 数据访问
│   │   ├── services/         # 解析、切块、索引、检索、问答
│   │   ├── config.py         # 环境变量配置
│   │   ├── database.py       # SQLite 初始化
│   │   └── main.py           # FastAPI app
│   ├── tests/                # 后端测试
│   ├── data/                 # 本地数据库、上传文件、Chroma 数据
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue           # MVP 管理台
│   │   ├── main.ts
│   │   └── style.css
│   └── package.json
├── docs/
│   └── superpowers/specs/    # MVP 设计说明
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
GET    /api/knowledge-bases
POST   /api/knowledge-bases
GET    /api/knowledge-bases/{knowledge_base_id}
PATCH  /api/knowledge-bases/{knowledge_base_id}
DELETE /api/knowledge-bases/{knowledge_base_id}

GET    /api/knowledge-bases/{knowledge_base_id}/documents
POST   /api/knowledge-bases/{knowledge_base_id}/documents
DELETE /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}

POST   /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse
GET    /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunks
POST   /api/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index

POST   /api/knowledge-bases/{knowledge_base_id}/retrieve
POST   /api/knowledge-bases/{knowledge_base_id}/questions
```

## 测试

后端测试：

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover backend/tests
```

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

- 前端问答体验细化
- 后端任务异步化，避免解析和索引长请求阻塞
- 文档解析增强，支持更多格式和更稳定的结构抽取
- 用户、角色、知识库权限
- 引用高亮与回答可追溯性增强
- 生产环境数据库和对象存储适配
