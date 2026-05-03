"""决策沙盘 · 通用引擎 + 先秦剧本

数据结构：
- Scenario：剧本头（id/title/intro/start）
- Node：场景节点（id/title/narration/choices）
- Choice：选项（label/next/effect/feedback）

引擎：传入 scenario_id + 当前节点 + 选择 → 返回下一节点 + 反馈 + 状态。
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Choice(BaseModel):
    key: str
    label: str
    next: str
    feedback: str
    delta: dict[str, int] = {}   # 国力/民心/贵族支持等


class Node(BaseModel):
    id: str
    title: str
    narration: str
    choices: list[Choice] = []
    ending: Optional[str] = None  # 终局文本（叶子节点）


class Scenario(BaseModel):
    id: str
    title: str
    intro: str
    start: str
    init_state: dict[str, int]
    nodes: dict[str, Node]


# ---------- 商鞅变法 ----------
SHANG_YANG = Scenario(
    id="shang-yang-reform",
    title="商鞅变法 · 你是秦孝公的谋臣",
    intro="公元前 361 年，年仅 21 岁的秦孝公即位。秦地处西陲，被东方六国轻视为「夷狄」。"
          "你将以孝公谋臣的身份做出一连串决策，决定秦国能否走上强国之路。",
    start="N0",
    init_state={"国力": 30, "民心": 50, "贵族支持": 70},
    nodes={
        "N0": Node(
            id="N0",
            title="开篇 · 君前对策",
            narration="孝公召集群臣求富国强兵之策。卫国人卫鞅献上变法主张，旧贵族甘龙、杜挚激烈反对。你建议孝公如何取舍？",
            choices=[
                Choice(key="A", label="维持祖宗成法，徐图缓进",
                       next="N1A",
                       feedback="谨慎，但秦国错失转型时机，被魏国压制更甚。",
                       delta={"国力": -5, "贵族支持": +5}),
                Choice(key="B", label="支持卫鞅变法，全面推行",
                       next="N1B",
                       feedback="孝公赞许，决心变法。但旧贵族开始酝酿反对。",
                       delta={"国力": +5, "贵族支持": -10}),
            ],
        ),
        "N1A": Node(
            id="N1A",
            title="保守路线 · 几年后",
            narration="秦国按旧制运转，魏军屡次进犯，国库渐空。",
            choices=[
                Choice(key="A", label="再向卫鞅请教",
                       next="N1B", feedback="亡羊补牢。卫鞅再次入秦主政。",
                       delta={"国力": -5}),
            ],
        ),
        "N1B": Node(
            id="N1B",
            title="徙木立信",
            narration="新法即将颁布，民众多疑。卫鞅在国都南门立木一根，悬赏迁木者赏金。",
            choices=[
                Choice(key="A", label="赏金五十金 · 兑现承诺",
                       next="N2",
                       feedback="百姓信服，新法得以推行。",
                       delta={"民心": +10}),
                Choice(key="B", label="赏金过高 · 改为口头表彰",
                       next="N2DOUBT",
                       feedback="民众讥笑官府言而无信，新法推行困难。",
                       delta={"民心": -15}),
            ],
        ),
        "N2DOUBT": Node(
            id="N2DOUBT",
            title="政令难行",
            narration="新法颁布数月，民间观望，地方官阳奉阴违。",
            choices=[
                Choice(key="A", label="重整旗鼓，重新树信",
                       next="N2", feedback="补救尚可，但已错失先机。",
                       delta={"民心": +5}),
            ],
        ),
        "N2": Node(
            id="N2",
            title="军功爵制 · 触动旧贵族",
            narration="新法规定按战功授爵，宗室无军功不得列入族谱。太子犯法，太傅公子虔与太师公孙贾被告发包庇。",
            choices=[
                Choice(key="A", label="法不容情，处置太子之师",
                       next="N3",
                       feedback="「太子，君嗣也，不可施刑」，遂刑其傅公子虔，黥其师公孙贾。法令大行。",
                       delta={"民心": +10, "贵族支持": -15}),
                Choice(key="B", label="法外开恩，姑息处理",
                       next="N3WEAK",
                       feedback="贵族窃喜，民众失望，法令威信扫地。",
                       delta={"民心": -20, "贵族支持": +10}),
            ],
        ),
        "N3WEAK": Node(
            id="N3WEAK",
            title="变法名存实亡",
            narration="十年后，秦国虽有改革之名，实力未有质变，被山东六国继续压制。",
            ending="结局 · 半途而废：你保住了一时的安稳，却让秦国错失了走上强国之路的机会。"
                   "历史上真实的商鞅，正是因为坚持「法不阿贵」才让变法立住根基。",
        ),
        "N3": Node(
            id="N3",
            title="孝公之死 · 旧贵族反扑",
            narration="变法推行二十余年，秦民富强，乡邑大治。然而秦孝公病逝，太子即位，旧贵族联名诬告商鞅谋反。",
            choices=[
                Choice(key="A", label="保护商鞅，与新君力争",
                       next="ENDA",
                       feedback="新君年少势孤，难以违众。商鞅仍难逃车裂，但变法成果保全。",
                       delta={"国力": +5}),
                Choice(key="B", label="顺应新君，依法处置",
                       next="ENDB",
                       feedback="商鞅车裂于市，但新君继承变法成果，未废其法。",
                       delta={}),
            ],
        ),
        "ENDA": Node(
            id="ENDA",
            title="结局 · 法存人亡",
            narration="商鞅虽死，新法不废。秦国延续军功爵与县制，国力日强。",
            ending="结局 · 法存人亡：「及孝公、商君死，惠王即位，秦法未败。」"
                   "百年之后，正是这套制度让秦王嬴政得以统一六国。",
        ),
        "ENDB": Node(
            id="ENDB",
            title="结局 · 法存人亡（顺势版）",
            narration="商鞅以谋反罪车裂于咸阳，但新法保留下来。",
            ending="结局 · 法存人亡：你选择了风险更小的路径，结局与历史相同 ——"
                   "「秦人不怜」，但「秦法未败」。",
        ),
    },
)


SCENARIOS: dict[str, Scenario] = {SHANG_YANG.id: SHANG_YANG}


def get_scenario(sid: str) -> Optional[Scenario]:
    return SCENARIOS.get(sid)


def list_scenarios() -> list[dict]:
    return [{"id": s.id, "title": s.title, "intro": s.intro} for s in SCENARIOS.values()]


def step(scenario_id: str, node_id: str, choice_key: str,
         state: dict[str, int]) -> Optional[dict]:
    """根据选择推进到下一节点，返回 {next_node, feedback, state, ending}。"""
    sc = get_scenario(scenario_id)
    if not sc:
        return None
    node = sc.nodes.get(node_id)
    if not node:
        return None
    chosen = next((c for c in node.choices if c.key == choice_key), None)
    if not chosen:
        return None
    new_state = dict(state)
    for k, v in chosen.delta.items():
        new_state[k] = max(0, min(100, new_state.get(k, 0) + v))
    nxt = sc.nodes.get(chosen.next)
    return {
        "feedback": chosen.feedback,
        "state": new_state,
        "next_node": nxt.model_dump() if nxt else None,
        "ending": nxt.ending if nxt else None,
    }
