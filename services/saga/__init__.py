"""Saga 引擎 · 互动小说式「练」模块

参考 Tome（falling-feather/Tome · 不存在之书 Inkless）的精华：
  - 多层记忆压缩（这里精简为：scene + summary + 最近 N 段历史）
  - LLM 输出协议化（正文 + [META] JSON）
  - 实体/标志增量提取
  - 流式叙事（前端逐字播放）

教育目标定位：在不偏离史实底线的前提下，由 LLM 动态续写一段历史小说，
玩家通过候选行动或自由输入推进剧情。
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from services import llm


# ---------- 课程级 Saga 模板（先秦第 1 课 5 节） ----------

@dataclass
class SagaTemplate:
    lesson_id: str
    title: str
    era: str
    setting: str        # 时代/场景设定（系统注入）
    facts: list[str]    # 史实底线（不得违反）
    persona: str        # 玩家代入身份
    opening: str        # 开场白（首段叙事，由模板提供以保证稳定首屏）
    initial_choices: list[str]
    keywords: list[str]


SAGA_TEMPLATES: dict[str, SagaTemplate] = {
    "L101": SagaTemplate(
        lesson_id="L101",
        title="夏朝的建立与家天下",
        era="约公元前 2070 年 · 黄河中游 · 阳城（今河南登封）",
        setting=(
            "禹治水有功被推举为部落联盟首领，年迈将逝。按旧例当从贤者中推举继承人，"
            "但其子启已掌握部落联盟相当兵力，旧贵族伯益是法定继承人。"
            "氏族大会即将召开，公天下与家天下的分野，就在这几日。"
        ),
        facts=[
            "禹是夏朝奠基者，禹死后其子启继位，开启王位世袭",
            "夏朝都城在阳城（今河南登封一带），后迁斟鄩（今偃师二里头）",
            "禅让制被世袭制取代，史称『公天下』变为『家天下』",
            "伯益曾被推举为禹的继承人，但被启所败",
            "夏启与有扈氏在甘地（今陕西户县）发生甘之战",
        ],
        persona="你是夏后氏部族中的一名年轻祭司之子，名唤伯阳。你既目睹禹的功业，也看到启在私下结好诸侯。",
        opening=(
            "黄河水患初平的第三个秋天。\n\n"
            "你站在阳城的夯土高台上，望着台下聚集的氏族首领。禹的灵柩停在中央，"
            "白幡在风里翻卷。按部落古老的法度，今日要在伯益与启之间推举新的共主。"
            "可你昨夜在城墙下，亲眼看见启的甲士悄悄入城，甲胄上的青铜在火光里映出冷光。\n\n"
            "你怀里揣着父亲留下的卜辞——一片刻满裂纹的龟甲，上面写着两个字："
            "「家」与「公」。父亲临终前说，这个秋天之后，天下将再不一样。"
        ),
        initial_choices=[
            "走向伯益，把龟甲交给他，劝他当机立断公开召集氏族",
            "走向启，质问他甲士入城所为何事",
            "保持沉默，先观察其他氏族首领的态度",
        ],
        keywords=["世袭", "家天下", "禅让", "伯益", "甘之战"],
    ),
    "L102": SagaTemplate(
        lesson_id="L102",
        title="商朝的兴衰与甲骨文",
        era="约公元前 1300 年 · 殷地（今河南安阳）",
        setting=(
            "盘庚迁殷不久，新都还未完全安定。商王武丁正欲征伐西方鬼方，"
            "贞人在龟甲上灼出兆纹，准备占卜出兵之吉凶。你是新入贞人之列的史官学徒。"
        ),
        facts=[
            "盘庚迁殷后商朝才稳定下来，殷在今河南安阳",
            "甲骨文是占卜记录，主要发现于殷墟",
            "武丁中兴是商朝强盛期，曾征伐鬼方",
            "商朝末代君王为纣（帝辛），被周武王伐于牧野",
            "贞人是占卜与刻写卜辞的官员",
        ],
        persona="你是新入贞人之列的史官学徒，名唤子戊，掌管整理武丁王所用的牛肩胛骨与龟甲。",
        opening=(
            "殷都的清晨，宗庙前的青铜鼎里燃起松脂。\n\n"
            "贞人争先把灼烫的木枝按在准备好的龟腹甲上，「咔」的一声，裂纹蜿蜒。"
            "今日要为武丁王征鬼方一事进行占卜。你跪在席上，手中握着青铜刻刀，"
            "等候记录卜辞。师兄低声告诉你：「兆若呈横纹，便是吉，纵裂则凶。」\n\n"
            "你忽然发现，刚才那块龟甲的兆纹有些蹊跷——它既不是横，也不是纵，"
            "而像是一道分叉。师兄没有看见，他正在恭敬地起身向武丁王禀报「大吉」。"
        ),
        initial_choices=[
            "如实告诉师兄，兆纹有分叉，请他重新查看",
            "暂且不说，先按师兄的话刻下「大吉」，回去再查典籍",
            "请求亲自向武丁王禀报兆纹的异样",
        ],
        keywords=["盘庚迁殷", "甲骨文", "贞人", "鬼方", "武丁"],
    ),
    "L104": SagaTemplate(
        lesson_id="L104",
        title="西周分封与宗法",
        era="约公元前 1042 年 · 镐京（今陕西西安西南）",
        setting=(
            "周武王灭商不久，旋即病重。周公旦与召公辅政。东方殷遗民未服，"
            "管叔、蔡叔与武庚有异动。封建诸侯的大典即将在岐山召开，"
            "你作为太史寮的小吏，要起草一份《分封诏》。"
        ),
        facts=[
            "西周以分封制和宗法制为核心政治制度",
            "周公东征平定三监之乱（管叔、蔡叔、霍叔与武庚）",
            "鲁、齐、燕、卫、晋等是西周主要分封国",
            "宗法制以嫡长子继承为核心，确立大宗、小宗之别",
            "礼乐制度是西周政治的精神支柱",
        ],
        persona="你是太史寮中的一名小吏，名唤史佚之徒『史辛』，负责誊抄分封诏书。",
        opening=(
            "镐京的太史寮，烛火摇曳。\n\n"
            "案上摊着一卷未干的青简——周公旦亲笔起草的《分封诏》。"
            "他要把姜尚封到东方营丘，姬奭封到燕，伯禽（周公之子）封到鲁。"
            "你正要誊抄第二份副本，却发现周公在「召公奭于燕」一句后，"
            "又添了一行小字：「使其子留辅成王」。\n\n"
            "你抬头时，恰好看见周公站在门口，目光凝重。他说："
            "「史辛，此简之末，可还有空隙？」"
        ),
        initial_choices=[
            "答「尚有」，请周公续写",
            "答「已无」，提议另起一简",
            "斗胆问周公：「为何要让召公之子留辅成王？」",
        ],
        keywords=["分封制", "宗法制", "嫡长子", "三监之乱", "礼乐"],
    ),
    "L105": SagaTemplate(
        lesson_id="L105",
        title="春秋五霸·礼崩乐坏",
        era="约公元前 656 年 · 召陵（今河南郾城）",
        setting=(
            "齐桓公九合诸侯，率联军南下伐楚，在召陵与楚国使者屈完对峙。"
            "你是齐桓公帐下的一名年轻外交官，奉命陪同管仲出使。"
        ),
        facts=[
            "齐桓公任用管仲改革，成为春秋第一霸",
            "公元前 656 年召陵之盟，齐楚和议",
            "尊王攘夷是齐桓公的政治旗号",
            "葵丘会盟标志齐桓公霸业巅峰",
            "春秋五霸常说为齐桓、晋文、楚庄、秦穆、宋襄（一说越王勾践、吴王阖闾）",
        ],
        persona="你是齐桓公帐下的年轻外交官，名唤鲍叔之孙『鲍俨』。",
        opening=(
            "召陵的旷野上，齐与楚的旌旗对峙了七日。\n\n"
            "管仲让你随他登上望楼，远观楚军阵容。楚国使者屈完独自驾车前来，"
            "气定神闲。管仲低声对你说：「楚人不弱，硬攻必有损伤。」\n\n"
            "你看到屈完手中持着一卷竹简——那是楚国的国书。管仲转过身，"
            "把一支玉玦放在你掌心：「这是齐侯的信物，等会儿如何与屈完答话，由你来开口。"
            "记住：尊王攘夷是我们的旗号，但今日要的是体面退兵，不是真打。」"
        ),
        initial_choices=[
            "援引「包茅不入」的旧账，先发制人指责楚国",
            "客气地问候楚成王，先示好缓和气氛",
            "直接把齐侯的玉玦递出，请楚国当面立誓",
        ],
        keywords=["齐桓公", "管仲", "尊王攘夷", "包茅不入", "召陵之盟"],
    ),
    "L103": SagaTemplate(
        lesson_id="L103",
        title="商鞅变法·战国转型",
        era="公元前 359 年 · 栎阳（秦国旧都）",
        setting=(
            "秦孝公下《求贤令》，卫国人公孙鞅入秦三年。第一次变法草案已经拟成，"
            "要在朝会上与守旧贵族对辩。你是孝公身边的一名书记侍从。"
        ),
        facts=[
            "秦孝公任用商鞅（公孙鞅）开始变法",
            "商鞅变法核心：废井田、开阡陌、奖军功、设郡县、连坐制",
            "立木为信是商鞅取信于民的著名典故",
            "守旧派代表为甘龙、杜挚等老臣",
            "商鞅最终被车裂，但秦法不废",
        ],
        persona="你是秦孝公身边的书记侍从，名唤『景监之侄·景渊』，与商鞅相熟。",
        opening=(
            "栎阳宫的朝会大殿，铜镜里映出诸大夫的身影。\n\n"
            "公孙鞅一袭青衫立于阶下，怀中抱着一卷新法草案。守旧老臣甘龙拄杖而立，"
            "目光森冷。你侍立在孝公身侧，案上摆着待批的简牍。\n\n"
            "孝公低声问你：「景渊，你以为公孙鞅之法，可施行否？」"
            "他的声音很轻，但殿内寂静无声，每个字都听得清清楚楚。"
            "甘龙的目光转了过来。公孙鞅也抬起了头。"
        ),
        initial_choices=[
            "回答「臣以为可行」，明确支持商鞅",
            "回答「臣以为时机未到」，倾向守旧派",
            "委婉答「此事关乎社稷，臣不敢妄言」",
        ],
        keywords=["商鞅", "立木为信", "井田制", "郡县制", "连坐"],
    ),
}


# ---------- Saga 运行时状态 ----------

@dataclass
class SagaState:
    saga_id: str
    lesson_id: str
    template: SagaTemplate
    history: list[dict] = field(default_factory=list)  # {role, text}
    summary: str = ""
    flags: dict = field(default_factory=dict)
    entities: dict = field(default_factory=dict)
    choices: list[str] = field(default_factory=list)
    step: int = 0
    ended: bool = False
    created_at: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "lesson_id": self.lesson_id,
            "title": self.template.title,
            "era": self.template.era,
            "persona": self.template.persona,
            "history": self.history,
            "summary": self.summary,
            "choices": self.choices,
            "flags": self.flags,
            "entities": list(self.entities.values()),
            "step": self.step,
            "ended": self.ended,
            "keywords": self.template.keywords,
        }


_SAGAS: dict[str, SagaState] = {}


def list_templates() -> list[dict]:
    return [
        {"lesson_id": t.lesson_id, "title": t.title, "era": t.era,
         "persona": t.persona, "keywords": t.keywords}
        for t in SAGA_TEMPLATES.values()
    ]


def start(lesson_id: str) -> SagaState | None:
    tpl = SAGA_TEMPLATES.get(lesson_id)
    if not tpl:
        return None
    sid = uuid.uuid4().hex[:12]
    state = SagaState(
        saga_id=sid,
        lesson_id=lesson_id,
        template=tpl,
        history=[{"role": "narrator", "text": tpl.opening}],
        choices=list(tpl.initial_choices),
        step=0,
    )
    _SAGAS[sid] = state
    return state


def get(saga_id: str) -> SagaState | None:
    return _SAGAS.get(saga_id)


# ---------- LLM Prompt 装配 ----------

_SYSTEM_PROMPT = """你是一位历史互动小说作家，正在与一名中学生玩家共同推演真实的中国历史。
你的任务：根据玩家的行动，续写下一段叙事，并保证教育性与可读性。

# 史实底线（不可违反）
{facts}

# 时代与场景
{era}
{setting}

# 玩家身份
{persona}

# 写作风格
- 第二人称「你」叙述，沉浸式，每段 220-380 字
- 必要时穿插历史人物的真实姓名与典故
- 关键术语首次出现时可用括号简注：如「分封制（封建诸侯，授土授民）」
- 不得引入魔法/穿越/超自然元素
- 玩家行动若严重偏离史实底线，应让 NPC 阻止或后果惩罚，引导回到正轨

# 输出协议（必须严格遵守）
先输出叙事正文（纯中文段落，可以多段，使用空行分隔），然后另起一行输出：

[META]{{"choices":["选项1","选项2","选项3"],"summary_delta":"本段一句话摘要","entities_delta":[{{"name":"人名","type":"人物|地点|物品|事件","desc":"一句话简介"}}],"flags_delta":{{"key":"value"}},"ended":false}}

要求：
- choices 给 2-4 个，每个 8-22 字，要有不同后果倾向
- summary_delta 一句话总结本段（≤30 字），用于后续记忆压缩
- entities_delta 仅列出本段「新出现」的实体，已出现的不要重复
- flags_delta 是本段产生的剧情标志（可空 {{}}）
- ended: 当剧情走到课程史实结局或玩家身亡时为 true
- [META] 这一行外，正文内不得出现 [META] 字样"""


def _build_messages(state: SagaState, player_action: str) -> list[dict]:
    tpl = state.template
    sys = _SYSTEM_PROMPT.format(
        facts="\n".join(f"- {f}" for f in tpl.facts),
        era=tpl.era,
        setting=tpl.setting,
        persona=tpl.persona,
    )
    msgs = [{"role": "system", "content": sys}]

    # 历史摘要（L3）
    if state.summary:
        msgs.append({"role": "system", "content": f"# 此前剧情摘要\n{state.summary}"})

    # 已知实体（L4）
    if state.entities:
        ent_text = "\n".join(
            f"- {e['name']}（{e['type']}）：{e['desc']}"
            for e in state.entities.values()
        )
        msgs.append({"role": "system", "content": f"# 已出场实体\n{ent_text}"})

    # 最近 N 段叙事（L1-L2，原文）
    recent = state.history[-6:]
    for h in recent:
        role = "assistant" if h["role"] == "narrator" else "user"
        msgs.append({"role": role, "content": h["text"]})

    # 玩家行动
    msgs.append({"role": "user", "content": f"【我的行动】{player_action}\n\n请按输出协议续写下一段。"})
    return msgs


_META_RE = re.compile(r"\[META\]\s*(\{.*\})\s*$", re.DOTALL)


def _parse_meta(full_text: str) -> tuple[str, dict]:
    """从完整 LLM 输出里切出正文与 meta JSON。"""
    m = _META_RE.search(full_text)
    if not m:
        return full_text.strip(), {}
    narrative = full_text[: m.start()].rstrip()
    try:
        meta = json.loads(m.group(1))
    except Exception:
        meta = {}
    return narrative, meta


def _apply_meta(state: SagaState, narrative: str, meta: dict) -> None:
    state.history.append({"role": "narrator", "text": narrative})
    if meta.get("summary_delta"):
        state.summary = (state.summary + " " + str(meta["summary_delta"])).strip()
        # 软上限：超长时截断头部
        if len(state.summary) > 800:
            state.summary = state.summary[-800:]
    for ent in meta.get("entities_delta", []) or []:
        name = (ent or {}).get("name")
        if name and name not in state.entities:
            state.entities[name] = {
                "name": name,
                "type": ent.get("type", "其他"),
                "desc": ent.get("desc", ""),
            }
    if isinstance(meta.get("flags_delta"), dict):
        state.flags.update(meta["flags_delta"])
    if isinstance(meta.get("choices"), list) and meta["choices"]:
        state.choices = [str(c) for c in meta["choices"][:4]]
    if meta.get("ended"):
        state.ended = True
    state.step += 1


# ---------- 流式接口 ----------

async def act_stream(saga_id: str, player_action: str) -> AsyncIterator[str]:
    """SSE 风格：逐段产出叙事文本（不含 [META] 行）；末尾产出一行 `[META]{...json...}`。"""
    state = _SAGAS.get(saga_id)
    if not state:
        yield "[ERR]saga 不存在"
        return
    if state.ended:
        yield "[ERR]剧情已结束"
        return

    # 先把玩家行动入历史（用于持久态展示）
    state.history.append({"role": "player", "text": player_action})

    messages = _build_messages(state, player_action)
    buffer = ""
    sent_until = 0  # 已发送给前端的字符位置（避免把 [META] 提前透传）

    async for chunk in llm.stream_chat(messages):
        buffer += chunk
        # 检测 [META] 是否已开始出现
        meta_pos = buffer.find("[META]")
        if meta_pos >= 0:
            # 把 [META] 之前还没发的内容发出去
            if sent_until < meta_pos:
                yield buffer[sent_until:meta_pos]
                sent_until = meta_pos
            # 等流结束再处理 meta
            continue
        # 还没出现 [META]，可以安全往外吐到 buffer 末尾「之前 6 个字符」
        # （留缓冲避免「[ME」被截断）
        safe_end = max(sent_until, len(buffer) - 6)
        if safe_end > sent_until:
            yield buffer[sent_until:safe_end]
            sent_until = safe_end

    # 流结束，把残余 narrative 部分吐完
    narrative, meta = _parse_meta(buffer)
    if len(narrative) > sent_until:
        yield narrative[sent_until:]

    _apply_meta(state, narrative, meta)
    # 最后输出一个 META 信封给前端
    yield "\n\n[META]" + json.dumps({
        "choices": state.choices,
        "entities": list(state.entities.values()),
        "summary": state.summary,
        "flags": state.flags,
        "step": state.step,
        "ended": state.ended,
    }, ensure_ascii=False)
