# ADR-0014 AI 回合证据与兼容回放

- 状态：接受
- 日期：2026-07-15
- 决策人：核心开发组
- 计划版本：V0.8.x（具体补丁版本待项目负责人收口确认）

## 背景

`AI-001` 已经完成服务端行动归类、固定/自由输入接口分离和 revision/CAS 单赢家，但 `TurnV1` 仍只有宽松的 `narrative_metadata` 字典，无法严格保存分类依据、叙事白名单和输出校验信息。当前 replay 还会重新执行 `SituationEngineV1` 并逐字段比较整个会话；若回合保存了合法的模型叙事，重新执行只能得到规则文本，因而既不能复现模型文本，也不能在离线环境验证它来自哪个固定规则结果。

直接给现有 Turn 增加默认字段也会破坏旧会话。`PersistedGameSessionV1` 当前先把原始 JSON 解析成最新 `GameSessionV1`，再用补齐默认值后的模型计算 checksum；新增默认字段后，旧记录即使原始内容没有变化也会被误判损坏。因此，证据契约、离线回放和持久信封兼容必须作为同一边界冻结。

## 决策

### 1. 会话显式区分证据版本

- `GameSessionV1` 增加 `ai_evidence_version`，只允许 `0` 或 `1`。
- 版本 `0` 表示历史兼容会话。其 Turn 可以没有类型化 AI 证据，但只允许 `narrative_source=rules`，且文本必须与固定场景重新计算的规则叙事完全一致。
- 版本 `1` 表示新编排会话。每个 applied Turn 必须同时保存 `ActionClassificationEvidenceV1` 与 `NarrativeEvidenceV1`，缺失、空对象或跨字段不一致均失败关闭。
- 新创建的服务会话使用版本 `1`。已经持久化且产生过回合的版本 `0` 会话继续按规则叙事推进，不在中途伪造缺失的历史证据，也不静默升级整段历史。

### 2. 分类证据使用严格对象

`ActionClassificationEvidenceV1` 至少保存：

- `source`：`fixed|exact|llm`。
- `reason_code`：`fixed_action|exact_match|semantic_match`。
- 分类 policy 版本。
- 分类前由服务端计算的可用行动 ID，顺序保持规则引擎顺序。
- 实际送入分类上下文的已审 fact ID。
- 分类 basis checksum。
- LLM 来源的 provider、model 和规范模型输出 checksum。

固定行动由服务端生成 `fixed/fixed_action` 证据，不把客户端字段写入证据。自由输入的 `exact` 和 `llm` 证据必须与 `raw_input`、`action_source`、`classified_action_id`、置信度和该回合开始前的可用行动完全一致。

### 3. 叙事证据使用严格对象

`NarrativeEvidenceV1` 至少保存：

- `source`：`rules|llm|fallback`，必须与 Turn 的 `narrative_source` 一致。
- 叙事 policy 版本、规则结算 basis checksum 和叙事文本 output checksum。
- 允许及实际使用的 fact ID 与 source ID。
- LLM 来源的 provider/model。
- fallback 来源的稳定原因码。

`narrative_model` 暂时保留为兼容镜像，必须等于叙事证据中的 model。元数据不得保存 prompt、原始供应商响应、思维链、HTTP body、密钥、教师备注或资料文件路径。

### 4. basis 与输出 checksum 的边界

- 分类 basis 固定课程/关卡 checksum、会话 ID、revision、节点、规则状态摘要、学生原始输入和当次可用行动。
- 叙事 basis 固定分类证据、行动反馈、规则状态差、NPC 变化、事件、facts、结局和确定性规则叙事。
- output checksum 对规范 UTF-8 叙事文本计算；模型输出中的引用 ID 必须是证据白名单的子集。
- 这些 checksum 用于发现存储漂移和跨字段不一致，不是数字签名。拥有数据库写权限且能重算整个信封的攻击者不在本任务覆盖范围内。

### 5. 新写入使用持久信封 V2

- 新会话和任何后续成功 CAS 写入统一保存为 `persisted-game-session/v2`。
- V2 checksum 对当前规范化 Session 与可选 release identity 计算。
- 读取 V1 时，必须先对原始 JSON 中的原始 `session` 和 `release_identity` 按旧算法校验 checksum，再解析为当前模型并映射为 `ai_evidence_version=0`。禁止先补默认字段再核对旧 checksum。
- V1 会话下一次成功推进或卷宗挂接时，由同一次 CAS 原子写成 V2；release identity 原样保留。不执行启动时全库批量迁移。
- envelope schema 缺失、未知版本、重复 key、checksum 不符或身份漂移继续失败关闭。

### 6. 规则先结算，叙事后生成，一次提交

- 服务端先从固定 revision 计算纯规则候选结果；模型不能返回或修改状态、事件、NPC 数值、节点、结局和可用行动。
- 叙事器只读取不可变规则投影与同一课程快照中的已审白名单，调用位于数据库事务和状态锁之外。
- 叙事完成后重新读取相同 revision；未变化时把规则结果、叙事和证据通过一次 CAS 提交，完成态卷宗仍在同一事务中物化。
- revision 在叙事期间变化时返回冲突，不把旧叙事套到新状态，也不自动重新调用模型。
- 叙事不可用、结构非法、引用越界或超限时，使用原样 `render_rule_narrative()`，记录 `source=fallback` 与稳定原因码，合法规则回合仍可提交。

### 7. 回放只使用固定制品与持久证据

- replay 不调用分类器、叙事器或任何供应商。
- 服务端重新推导每回合规则状态、事件、NPC、结局和规则叙事，再核对分类 basis、叙事 basis、引用白名单、output checksum 和全部证据形状。
- LLM 叙事文本在证据校验后直接复用，不尝试由模型再次生成。
- `history` 必须严格等于 opening 加每回合 `raw_input/narrative` 投影；会话 summary 和卷宗 consequence 必须与最后叙事和真实 Turn 保持一致。
- 版本 `0` 的非规则叙事、版本 `1` 的缺证据叙事、篡改文本后只重算外层会话 checksum 等情况全部拒绝。

## 后果

正面：

- 新模型叙事可以跨重启恢复和离线回放，不依赖供应商可用性或模型版本稳定性。
- 分类、规则与叙事三层权威边界可由 Pydantic 和确定性 checksum 自动验证。
- 旧会话不因增加默认字段集体失效，也不会被假装成拥有从未记录过的 AI 证据。

代价：

- 持久信封出现 V1/V2 双读和一次 CAS 迁移逻辑，测试必须覆盖原始旧 checksum。
- 版本 `0` 历史会话继续使用规则叙事，不能中途获得无法补证的 LLM 历史回合。
- CAS 决出唯一赢家前仍可能发生重复叙事调用；状态正确性由单写保证，供应商请求租约另行规划。

## 被拒绝的方案

- **继续把证据塞进宽松字典**：无法表达列表白名单或稳定跨字段约束，拒绝。
- **只给模型叙事保存文本**：无法离线判断引用与规则依据，拒绝。
- **回放时再次调用模型**：输出不可重复且依赖外部服务，拒绝。
- **给旧 Turn 自动补一份“看起来合理”的证据**：历史事实不存在，拒绝。
- **先提交规则回合，再第二次更新叙事**：会产生短暂不一致和第二次覆盖风险，拒绝。

## 验收反例

- 原始 V1 无新字段记录可读取，并在下一次成功 CAS 后写成 V2；旧 checksum 或 release identity 篡改仍失败。
- V1 兼容会话出现非规则叙事时失败关闭。
- V1 新证据会话缺分类/叙事对象、引用越界、basis/output checksum 漂移、provider/model 形状矛盾时失败关闭。
- 叙事期间发生并发回合时只有数据库赢家，旧叙事不落库。
- 无 key、超时、限流、非法 JSON 和引用越界均提交完全相同的规则状态与 fallback 文本。
- 应用重启和 replay 使用持久叙事，不调用 fake provider；修改 history、summary 或卷宗 consequence 后重算外层 checksum 仍失败。

## 相关

- [ADR-0012 看练问创闭环与史实护栏](ADR-0012-看练问创闭环与史实护栏.md)
- [ADR-0013 课时到关卡的发布身份交接](ADR-0013-课时到关卡的发布身份交接.md)
- [02-项目规划与设计总纲 AI-001](../02-项目规划与设计总纲.md#104-待认领开发任务)
- `services/contracts/v1.py`
- `services/game_runtime/store.py`
- `services/game_runtime/service.py`
- `services/ai/`
