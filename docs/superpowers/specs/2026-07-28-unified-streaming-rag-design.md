# 统一流式 RAG 执行设计

## 目标

将标准 RAG 和 Agentic RAG 收敛到一个流式问答入口。两种策略共享同一套最终答案生成逻辑，避免当前 Agentic 流式端点先完整生成一次答案、再重新流式生成一次的重复调用。

系统默认自动选择执行策略，同时保留强制选择标准或 Agentic 策略的调试能力。

## 范围

本阶段包括：

- 统一标准 RAG 与 Agentic RAG 的流式执行入口；
- 支持 `auto`、`standard`、`agentic` 三种执行策略；
- 将检索与规划结果收敛为统一的 `PreparedAnswer`；
- 保证每个问答请求只执行一次最终答案生成；
- 删除无外部调用方的非流式 Agentic 端点；
- 普通界面使用 `auto`，Debug Panel 可强制指定策略；
- Agentic 准备阶段失败时降级到标准策略；
- 补充策略路由、上下文准备、降级和单次生成测试。

本阶段不包括：

- 修改混合检索、RRF 或 Cross-encoder 算法；
- 重做 RAGAS 评测系统；
- 修改页面视觉设计；
- 引入新的任务队列或外部基础设施；
- 重构文档索引生命周期。

## 执行模型

统一的数据流为：

```text
用户问题
  → 解析执行策略
  → 准备检索上下文
  → PreparedAnswer
  → 单次流式生成
  → 持久化问答记录
```

### 策略

#### `standard`

执行一次现有的混合检索与可选重排，然后进入答案生成。适合简单、明确的问题，延迟与成本最低。

#### `agentic`

执行查询分析、子问题拆解、检索、上下文评估、查询改写和可选 Web 搜索回退。所有步骤只负责准备回答所需的上下文，不生成最终答案。

#### `auto`

默认策略。复用查询复杂度分析结果：

- 简单问题进入 `standard`；
- 复杂问题进入 `agentic`；
- 路由判断失败时进入 `standard`。

`auto` 不向普通用户暴露为选择负担。Debug Panel 可强制指定 `standard` 或 `agentic`，用于调试、演示和消融评测。

## 核心数据结构

引入统一的 `PreparedAnswer`，作为准备阶段和生成阶段之间的 seam。它至少包含：

```text
question
conversation_history
sources
web_contexts
strategy_used
retrieval_trace
```

其中：

- `sources` 保存知识库检索结果及稳定的引用编号；
- `web_contexts` 保存真实的 Web 搜索标题、URL 和摘要，不使用空白占位；
- `strategy_used` 表示实际执行的策略；
- `retrieval_trace` 保存子问题、查询改写、检索轮数、上下文评分和降级信息。

最终生成 Module 只接收 `PreparedAnswer`，不重新执行检索或重建 Agent 状态。

## 后端接口

保留一个流式问答端点。请求包含：

```json
{
  "question": "用户问题",
  "strategy": "auto",
  "top_k": 5,
  "conversation_history": [],
  "conversation_id": null,
  "enable_web_search": false
}
```

`strategy` 允许 `auto | standard | agentic`，默认值为 `auto`。

流式事件保持现有 SSE 传输方式，并统一为：

- `status`：当前阶段与实际采用的策略；
- `trace`：子问题、检索轮次、上下文评分或降级原因；
- `sources`：最终知识库和 Web 来源；
- `token`：最终答案 token；
- `error`：无法恢复的错误；
- `done`：回答 ID 与结束状态。

删除无人使用的非流式 Agentic 端点。标准和 Agentic 不再拥有两套答案生成入口。

## 错误与降级

- `auto` 的复杂度判断失败：使用 `standard`；
- Agentic 准备阶段失败，且尚未开始输出答案：记录降级原因并执行 `standard`；
- reranker 失败：记录 trace，沿用融合排序结果；
- Web 搜索失败：保留知识库上下文继续回答，并在 trace 中记录失败；
- 最终流式生成开始后发生错误：发送 `error` 事件并终止，不重新生成，避免重复内容；
- 问答记录持久化失败：记录服务端错误，但不破坏已经完成的客户端回答。

## 前端行为

- 普通问答界面不再展示标准/Agentic 主切换按钮；
- 默认发送 `strategy: "auto"`；
- Debug Panel 提供 `auto | standard | agentic` 强制选择；
- 界面展示实际采用的策略，而不是用户请求的策略；
- Agentic 路径可展示子问题数量、检索轮次、上下文评分和是否发生降级；
- 所有模式使用相同的 token、sources 和 done 事件处理逻辑。

## 测试要求

### 后端

- `standard` 只检索一次并只生成一次；
- `agentic` 可以多次检索，但只生成一次；
- `auto` 对简单问题选择 `standard`；
- `auto` 对复杂问题选择 `agentic`；
- 路由判断失败时降级为 `standard`；
- Agentic 准备失败时降级为 `standard`；
- Web 搜索结果的真实标题、URL 和摘要进入 `PreparedAnswer`；
- 流式端点不调用旧的非流式答案生成；
- SSE 事件顺序满足 `status/trace → sources → token* → done`；
- 流式中断后不进行第二次生成；
- 最终持久化内容与客户端收到的完整 token 内容一致。

### 前端

- 默认请求发送 `strategy: "auto"`；
- Debug Panel 可覆盖策略；
- 三种策略共用同一 SSE 解析路径；
- 前端展示后端返回的实际策略和降级状态；
- 旧模式切换状态移除后，不影响对话恢复与历史记录。

## 迁移顺序

1. 定义 `PreparedAnswer` 和统一策略类型；
2. 将标准检索封装为准备函数；
3. 让 Agentic 图停止在上下文准备阶段；
4. 让统一流式生成消费 `PreparedAnswer`；
5. 将路由切换到统一执行入口；
6. 增加 `auto` 路由和降级；
7. 更新前端与 Debug Panel；
8. 删除非流式 Agentic 端点和重复生成实现；
9. 补齐回归测试和文档。

## 完成标准

- 一个用户问题最多执行一次最终答案生成；
- `auto`、`standard`、`agentic` 都通过同一个流式端点工作；
- 标准与 Agentic 使用相同的答案生成 Module；
- Web fallback 上下文不会在流式路径中丢失；
- Agentic 失败可以在生成前自动降级；
- 当前对话持久化、引用展示和历史恢复行为保持可用；
- 自动化测试能证明单次生成和策略选择行为。
