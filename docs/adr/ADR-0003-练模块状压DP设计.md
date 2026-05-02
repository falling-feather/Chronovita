# ADR-0003 · 练模块状压 DP 与 DAG 推演设计

- 状态：Accepted
- 时间：v1.2.0
- 关联：Development_Spec.md 第 7 章

## 1. 背景

练模块要求学生在「大禹治水」等历史关键节点上做出抉择，并以剧情/数值同时反映抉择代价。该问题等价于在有限状态空间上的有向无环图（DAG）推演：节点 = 历史情境，边 = 选择 + 状态变换。

## 2. 决策

- **状态变量按位编码**：每个变量声明 `bits`，按声明顺序左移拼接为一个整数，方便用作 `lru_cache` key。
- **DAG 静态注册**：v1.2.0 阶段使用 Python `dict` 静态注册剧本，未引入数据库；后续阶段再迁至 PostgreSQL `scenarios / dag_nodes / dag_edges` 三表。
- **记忆化 DP**：`_branches_cached(scenario_id, node_id, state_bits)` 缓存「当前状态下可达分支与新状态」，避免相同情境重复计算条件求值。
- **不预算分支收益**：v1.2.0 不做剪枝/最优策略求解；推演由人主导，DP 只负责"同状态下分支结果一致"。
- **进展持久化**：`PlaythroughSnapshot` 模块级 `_PLAYTHROUGHS` 字典；v1.3.0 替换为 Redis + Postgres。

## 3. 数据模型摘要

```
StateVar(key, label, kind, bits, initial)
DagNode(node_id, title, narrative, is_terminal)
Effect(var, op[set/inc/dec], value)
Condition(var, op[eq/ne/ge/le/gt/lt], value)
DagEdge(edge_id, from_node, to_node, label, conditions[], effects[], fallback_narrative)
Scenario(scenario_id, title, period, summary, state_vars[], nodes[], edges[], start_node)
```

## 4. 首发剧本「大禹治水」

变量布局（合计 9 bit）：

| 变量 | 位宽 | 含义 |
| --- | --- | --- |
| strategy | 2 | 0 未定 / 1 承父之堵 / 2 改弦疏导 / 3 堵疏并举 |
| morale | 3 | 民心 0~7 |
| flood | 3 | 河患 0~7 |
| nine_zhou | 1 | 九州划定与否 |

节点 8 个、边 9 条；终局两个：「溃堤之变」与「开夏之基」。

## 5. 风险与后续

- 缓存失效：v1.2.0 重启 reload 会失效；v1.3 引入 Redis 持久化后需基于剧本版本号清缓存。
- LLM 叙事：当前节点叙事为静态文本，下一阶段接入 `services.recall.prompt_chain` 改为动态生成并配套 RAG 校验。
- 编辑器：DAG 节点目前无可视化编辑界面，仅前端只读消费；v1.3 后引入 react-flow 等画布。
