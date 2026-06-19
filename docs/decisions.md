# 设计决策记录

记录项目中的关键技术选择及其理由。每个决策包含背景、备选方案、最终选择及原因。

---

## 1. 混合检索融合：RRF vs 线性加权

**背景：** 系统同时使用向量检索（语义相似度）和 BM25 关键词检索，需要将两套分数的结果合并为一个排序列表。

**备选方案：**
- A) 线性加权：`final_score = α × vector_score + (1-α) × keyword_score`，需要调 α
- B) Reciprocal Rank Fusion（RRF）：`rrf_score = Σ 1/(k + rank)`，无参数

**选择：B — RRF**

**理由：**
- 向量分数（cosine 0.2-1.0）和 BM25 分数不在同一量纲上，线性加权必须先做分数校准（如 min-max 归一化），引入额外复杂度和假设
- RRF 只关心排序位置，天然免疫量纲差异。两套系统各自产出 Top-K，RRF 合并排名即可
- RRF 唯一的参数 `k=60` 是学术界验证的稳定常量，不需要调参
- 实现仅 30 行代码（`_rrf_fusion`），比加权方案更易理解和维护

---

## 2. 任务队列：SQLite 持久化 vs Redis/Celery

**背景：** 文档解析和索引是耗时操作，需要异步执行。FastAPI 内置的 `BackgroundTasks` 在服务重启时会丢失未完成的任务。

**备选方案：**
- A) Celery + Redis：成熟的分布式任务队列
- B) arq：Python 异步任务队列，依赖 Redis
- C) SQLite 自建队列：利用已有数据库，轻量实现

**选择：C — SQLite 自建队列**

**理由：**
- 当前是单进程部署，不需要分布式 worker。Celery 的进程管理、序列化、中间件开销是过度设计
- SQLite 已是项目的主数据库，不需要引入 Redis 作为额外依赖，降低部署复杂度
- 任务持久化在 SQLite 中，服务重启后自动恢复（`_recover_stuck_documents` 把 `running` 状态标记为 `failed`）
- 内置 3 次重试机制，覆盖临时故障（如 embedding 服务短暂不可用）
- 代价：不支持优先级队列、不支持水平扩展 — 但这些是生产化阶段才需要的，当前阶段引入不会提升实际价值

---

## 3. 流式问答：fetch SSE vs EventSource vs WebSocket

**背景：** LLM 生成回答需要逐 token 推送到前端，实现打字机效果。

**备选方案：**
- A) `EventSource` 浏览器 API：原生 SSE 客户端
- B) `fetch` + `ReadableStream`：手动解析 SSE 流
- C) WebSocket：双向通信

**选择：B — fetch + ReadableStream**

**理由：**
- 需求是单向流（服务端→客户端），WebSocket 的双向能力是用不到的，反而增加连接管理复杂度
- `EventSource` 不支持自定义 HTTP 头（无法携带 `Authorization: Bearer <token>`），只能依赖 cookie，与项目的 token 认证方案冲突
- `fetch` 可以设置自定义请求头，同时通过 `response.body.getReader()` 逐块读取 SSE 事件
- 代价：需要手动解析 `data: {...}\n\n` 格式的 SSE 帧，约 30 行代码。复用 `@antfu/utils` 等库可以简化，但手写的灵活性和体积更优

---

## 4. 向量数据库：嵌入式 Chroma vs 独立服务

**背景：** 存储文档 embedding 向量并执行近似最近邻检索。

**备选方案：**
- A) 嵌入式 Chroma（`chromadb` Python 包，`PersistentClient`）
- B) Chroma 独立服务（Docker 容器，HTTP API）
- C) Pinecone / Weaviate / Qdrant 等云端向量数据库

**选择：A — 嵌入式 Chroma**

**理由：**
- 零配置：`pip install chromadb` 即可，数据存储在本地目录（`CHROMA_DIR`），无独立进程
- 与 docker-compose 的一键部署兼容：不需要额外的 service 定义
- 当前数据量（< 100k 向量）下，嵌入式 Chroma 的 HNSW 索引性能足够
- 代价：不支持集群、不支持高可用。生产化时切到独立 Chroma 服务或 Qdrant 是既定的演进路径（已在 README "下一步" 中列出）

---

## 5. 前端状态管理：Vue Composables vs Pinia

**背景：** 管理知识库列表、文档状态、问答面板等多组件的共享状态。

**备选方案：**
- A) Pinia（Vue 官方状态管理库）
- B) Vue 3 Composables（`ref` + `computed` + `watch`）
- C) Vuex（已过时）

**选择：B — Composables**

**理由：**
- 项目的状态是按知识库实例隔离的（每个 KB 有独立的文档列表、问答历史），不是全局单例。Composables 天然支持按需创建多个实例（`useDocuments(kbId)`、`useQA(kbId)`），Pinia 的 store 是全局的，需要手动传参和清理
- vue-router 已接管 URL 相关的状态（选中哪个 KB、当前 tab），composable 只管理页面内的业务状态，职责清晰
- 减少依赖：项目已经用了 Vue 3 + Ant Design Vue + vue-router + axios，不再引入额外库
- 代价：composable 之间没有共享订阅/通知机制。当前通过 `App.vue`/`KbWorkspaceView.vue` 手动协调（如切换 KB 时清空 QA 状态），随着交互变复杂可能需要引入 `mitt` 等事件总线
