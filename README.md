# Knowledge Agent — 项目展示

> 企业 RAG 知识库问答系统 · Vue 3 + FastAPI + LangGraph  
> 统一流式入口自动选择标准 RAG 或 Agentic 自主检索，完整链路可部署

---

## 项目概览

Knowledge Agent 是一个面向企业知识场景的 RAG 问答平台。上传文档后，系统
完成解析、切块、Embedding 和混合索引；用户提问时自动选择 Standard 或
Agentic 检索路径，并返回带来源引用的流式答案。

**测试** 128 个后端单元测试 + 22 个前端单元测试 + 7 个 E2E · **技术栈**
Vue 3 / FastAPI / LangGraph / ChromaDB / SQLite / OpenAI-compatible API

---

## 功能亮点

### 知识库管理
- 创建/编辑/删除知识库，侧栏搜索筛选
- 支持 MD、TXT、PDF（表格提取）、DOCX 四种文档格式
- 段落感知定长切块，SQLite 持久化异步任务；服务重启后保留待处理任务，
  并将中断任务标记为失败以便重新执行

### 混合检索 + Cross-encoder 重排 + 流式问答
- 向量语义检索 + BM25 关键词检索，RRF 融合排序
- 可选 Cross-encoder 重排（本地 / 硅基流动云端），候选 4 倍扩召回再精筛
- 最终上下文保留 BM25 首位精确匹配，降低重排器误删技术术语证据的风险
- SSE 流式逐 token 输出，多轮对话上下文自动传递
- 引用双向联动：点击 `[1]` → 右侧来源卡片高亮
- 来源过滤：只展示 LLM 实际引用的片段

### Agentic RAG（自主检索）
- LLM 分析查询复杂度，复杂问题自动拆子问题
- 多子问题首轮检索+评估并行执行（ThreadPoolExecutor），延迟显著低于串行流程
- 强制 Agentic 模式每个子问题最多 3 轮、全局最多 8 次检索
- Auto 结合确定性结构规则和 LLM 分析进行路由；Agentic 路径使用 2 轮 /
  6 次检索预算控制延迟
- DuckDuckGo Web 搜索回退
- LangGraph 8 节点上下文准备图，最终答案只流式生成一次
- 可复现 18 题基准：固定语料、三模式对比、确定性指标与 LLM Judge

### 对话管理
- ChatGPT 风格对话列表，多轮对话持久化
- 新建/切换/删除对话，刷新页面自动恢复
- 回答质量反馈（👍👎）

### 工程质量
- JWT 认证（单用户，环境变量配置）+ API Token 向后兼容脚本调用 + IP 限流
- BM25 索引持久化 + Embedding 缓存
- 结构化日志 + X-Request-ID 全链路追踪
- 健康检查覆盖数据库 / ChromaDB / LLM
- CI：128 后端单元测试 + 22 前端单元测试 + 7 e2e 冒烟测试 + 类型检查
- Docker Compose 部署（外部聊天模型或本地 Ollama 二选一）

---

## 系统截图

### 仪表盘首页
![仪表盘](docs/images/dashboard.png)

### 对话问答
![对话问答](docs/images/conversation.png)

### 对话列表
![对话列表](docs/images/conversations.png)

### 文档管理
![文档管理](docs/images/documents.png)

### Agentic 检索流程
![Agentic](docs/images/agentic.png)

---

## 系统架构

```
浏览器 (Vue 3 + Ant Design)
    │
    ├─ Nginx / Vite proxy
    │
    ▼
FastAPI 后端
    ├─ 文档管线：解析 → 段落切块 → Embedding
    ├─ 检索管线：ChromaDB + BM25 → RRF → Cross-encoder
    ├─ 执行策略：Standard / LangGraph Agentic / Auto 路由
    └─ SQLite：知识库、文档、对话、任务队列、Embedding 缓存
         │
         ├─ OpenAI-compatible API：LLM / Embedding
         └─ 可选 SiliconFlow / 本地 HuggingFace 重排
```

---

## 可复现 RAG 评测

使用固定的 5 文档语料和 18 道人工标注题，主实验禁用 Web 搜索。
Standard、Agentic 为 2026-07-29 三模式基线；Auto 为 2026-07-30 修复
BM25 评测初始化和重排误杀保护后的回归结果。

| 指标 | Standard | Agentic | Auto |
|------|---------:|--------:|-----:|
| 文档召回率 | 0.767 | 0.933 | **0.967** |
| 必要事实覆盖率 | 0.601 | 0.798 | **0.847** |
| Faithfulness | 0.967 | **0.994** | 0.986 |
| Answer correctness | 0.556 | 0.936 | **0.986** |
| 无答案正确率 | 1.000 | 1.000 | 1.000 |
| 平均延迟 | **11.65s** | 65.36s | 41.72s |

Auto 将 9/18 题送入 Agentic。修复后单文档正确性从 0.738 提升到 0.983，
多文档正确性达到 0.975，平均延迟从 55.28 秒降至 41.72 秒。18 道题全部
成功；Judge 成功解析 14/18，道题级确定性指标覆盖 18/18。Agentic 串行
调用仍是复杂题的主要性能瓶颈。
详见 [`backend/eval/README.md`](backend/eval/README.md) 和评测汇总。

---

## 快速开始

Docker Compose 会自动拉取 `nomic-embed-text` Embedding 模型。回答问题还
需要聊天模型，二选一配置：

```bash
# 方案 A：使用 OpenAI-compatible 外部模型，在项目根 .env 中填写
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=<your-api-key>
LLM_MODEL=<chat-model>

# 方案 B：使用 Docker 内的 Ollama
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:7b
```

还需要配置 JWT 认证（单管理员模型）：

```bash
# 在项目根 .env 中填写（首次启动必填）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<你的强密码>
JWT_SECRET=<随机字符串，可用 python -c "import secrets;print(secrets.token_urlsafe(48))" 生成>
JWT_EXPIRE_HOURS=24
# API_TOKEN 可选，留空则脚本必须通过 /api/auth/login 获取 JWT
```

完成配置后：

```bash
# 1. 启动全部服务
docker compose up -d

# 2. 打开浏览器
# http://localhost:8080 — 首次访问会跳转到登录页

# 3. 查看服务状态
docker compose ps
docker compose exec backend curl -f http://localhost:8000/health
```

本地开发、环境变量和评测复现详见 [DEVELOPMENT.md](DEVELOPMENT.md)。
