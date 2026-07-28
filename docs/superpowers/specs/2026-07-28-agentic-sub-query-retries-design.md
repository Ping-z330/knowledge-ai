# Agentic 子问题检索与重试设计

## 目标

修正复杂问题的 Agentic 检索行为，使每个子问题都能独立完成检索、上下文评估和查询改写，而不是只有最后一个子问题能够重试。

系统同时限制单个子问题和整个请求的检索次数，在检索质量、响应延迟和调用成本之间取得平衡。

## 范围

本阶段包括：

- 每个子问题独立评估检索结果；
- 每个子问题最多执行 3 次检索；
- 整个请求最多执行 8 次知识库检索；
- 为每个子问题记录查询、评分、轮数和完成原因；
- 所有子问题完成后合并、去重证据；
- 全局预算耗尽后按配置决定是否执行 Web fallback；
- 将新的 trace 信息通过统一 SSE `trace` 事件返回；
- 补充状态节点、路由和预算测试。

本阶段不包括：

- 修改混合检索、RRF 或 Cross-encoder 算法；
- 修改查询拆分 prompt；
- 重做 RAG 评测数据集；
- 修改最终答案生成 Module；
- 增加并行子问题检索；
- 改变 `PreparedAnswer` 的生成次数约束。

## 执行流程

```text
分析原始问题
  → 简单问题：将原始问题作为唯一检索问题
  → 复杂问题：得到有序子问题列表
  → 选择当前子问题
  → 检索当前查询
  → 合并到当前子问题上下文并去重
  → 只根据当前子问题评估当前上下文
      ├── 评分足够
      │     → 完成当前子问题
      │     → 进入下一子问题或结束
      ├── 评分不足且局部、全局预算均充足
      │     → 改写当前查询
      │     → 重试当前子问题
      └── 任一预算耗尽
            → 以预算耗尽原因完成当前子问题
            → 全局预算未耗尽时进入下一子问题
            → 全局预算耗尽时结束知识库检索
  → 合并所有子问题证据
  → 必要时执行 Web fallback
  → PreparedAnswer
  → 单次流式生成
```

## 预算规则

### 局部预算

每个子问题最多执行 3 次检索，包括第一次原始查询：

```text
第 1 次：原始子问题
第 2 次：第一次改写
第 3 次：第二次改写
```

第三次检索后即使评分仍然不足，也不再改写当前子问题。

### 全局预算

整个请求最多执行 8 次知识库检索。每次调用检索 Module 都消耗一次全局预算。

全局预算优先级高于局部预算。一旦达到 8 次：

- 不再开始新的子问题检索；
- 当前已经召回的证据继续保留；
- 尚未执行的子问题在 trace 中标记为 `global_budget_exhausted`；
- 如果启用了 Web 搜索，则执行一次 Web fallback；
- 否则直接使用已有证据准备答案。

Web 搜索不计入知识库检索的 8 次预算，但 trace 会单独记录是否调用。

## 状态模型

在 `AgenticState` 中引入：

```text
current_sub_query_rounds: int
total_retrieval_calls: int
current_sub_query_chunks: list[dict]
queries_tried: list[str]
sub_query_traces: list[dict]
max_total_retrieval_calls: int = 8
```

现有 `retrieved_chunks_json` 继续保存整个请求的累计证据。

### `current_sub_query_chunks`

只保存当前子问题各轮检索累计得到的证据。上下文评估只能读取这个字段，不能读取整个问题的累计证据，避免其他子问题的上下文抬高当前评分。

进入下一个子问题时清空。

### `queries_tried`

保存当前子问题已经尝试过的查询。查询改写 prompt 使用该列表，避免重复生成相同查询。

进入下一个子问题时清空。

### `sub_query_traces`

每个已结束或被跳过的子问题保存一条 trace：

```json
{
  "sub_query": "子问题文本",
  "queries_tried": ["原始查询", "改写查询"],
  "retrieval_calls": 2,
  "final_score": 4,
  "completion_reason": "sufficient",
  "chunk_count": 5
}
```

`completion_reason` 允许：

- `sufficient`
- `local_budget_exhausted`
- `global_budget_exhausted`
- `retrieval_failed`
- `rewrite_failed`

## 节点职责

### `prepare_retrieval`

- 选择当前子问题；
- 第一次进入子问题时设置原始查询；
- 保留查询改写节点产生的新查询；
- 不修改累计证据。

### `retrieve`

- 执行一次知识库检索；
- 同时增加 `current_sub_query_rounds` 和 `total_retrieval_calls`；
- 将新结果写入临时字段；
- 检索失败仍计入预算，并记录失败状态。

### `merge_and_dedup`

- 将新结果去重后同时写入：
  - 当前子问题的 `current_sub_query_chunks`；
  - 全局的 `retrieved_chunks_json`；
- 不让不同子问题重复相同 chunk。

### `evaluate_context`

- 使用当前子问题作为评估问题；
- 只读取 `current_sub_query_chunks`；
- 不读取其他子问题的累计上下文。

### `rewrite_query`

- 使用当前子问题作为原始问题；
- 将完整 `queries_tried` 传给改写 Module；
- 将新查询追加到 `queries_tried`；
- 如果改写结果与已有查询重复，则当前子问题以局部预算耗尽处理，避免无效循环。

### `complete_sub_query`

新增节点，负责：

- 写入当前子问题 trace；
- 推进 `current_sub_query_idx`；
- 清空当前子问题局部状态；
- 根据剩余子问题和全局预算决定继续或结束。

## 路由优先级

上下文评估后的路由必须按以下顺序判断：

1. 当前子问题评分是否达到阈值；
2. 全局预算是否耗尽；
3. 当前子问题局部预算是否耗尽；
4. 是否可以改写并重试。

具体行为：

```text
score >= 3
  → complete_sub_query(reason=sufficient)

score < 3 and total_retrieval_calls >= 8
  → complete_sub_query(reason=global_budget_exhausted)
  → 结束知识库检索

score < 3 and current_sub_query_rounds >= 3
  → complete_sub_query(reason=local_budget_exhausted)
  → 下一个子问题

otherwise
  → rewrite_query
  → 重试当前子问题
```

所有子问题完成后：

- 如果至少一个子问题的最终评分不足且启用了 Web 搜索，执行 Web fallback；
- 否则结束准备阶段。

## SSE Trace

统一流式端点的 `trace` 事件增加：

```json
{
  "retrieval_rounds": 6,
  "total_retrieval_calls": 6,
  "context_score": 4,
  "sub_queries": ["问题一", "问题二"],
  "sub_query_traces": [],
  "web_search_used": false
}
```

保留 `retrieval_rounds` 作为兼容字段，但其值改为整个请求的总知识库检索次数。新增代码优先读取 `total_retrieval_calls`。

## 错误处理

- 查询分析失败：沿用统一执行 Module 的 standard 降级；
- 单次检索失败：消耗一次预算，允许在预算内改写重试；
- 上下文评估失败：沿用当前默认评分 3 的降级行为，并在 trace 记录 `evaluation_skipped`；
- 查询改写失败：完成当前子问题并记录 `rewrite_failed`；
- 所有子问题均无可用证据：按配置执行 Web fallback，否则生成无上下文回答；
- 最终生成行为不变，每个请求最多生成一次答案。

## 测试要求

- 第一个子问题评分不足时能够改写并重试；
- 每个子问题最多执行 3 次检索；
- 整个请求最多执行 8 次知识库检索；
- 当前子问题的评估看不到其他子问题的 chunk；
- 切换子问题后局部轮数、局部 chunk 和查询历史被清空；
- 全局累计证据和全局调用次数不会被清空；
- 重复的改写查询不会形成循环；
- 全局预算耗尽后不会开始新的知识库检索；
- 未执行子问题具有 `global_budget_exhausted` trace；
- SSE trace 返回每个子问题的查询、评分、调用次数和完成原因；
- Web fallback 不计入知识库检索预算；
- 最终答案仍然只生成一次。

## 完成标准

- 每个复杂问题的子问题都具有独立的检索、评估和重试生命周期；
- 前几个子问题不再无条件跳过重试；
- 单个子问题不超过 3 次检索；
- 整个请求不超过 8 次知识库检索；
- trace 能准确解释每一次查询改写和预算终止原因；
- 所有原有测试和新增状态机测试通过；
- 前端构建通过；
- `PreparedAnswer` 与统一单次流式生成行为保持不变。
