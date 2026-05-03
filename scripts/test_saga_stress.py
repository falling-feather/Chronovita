"""V0.5.1 saga 压力测：单课多轮，验证记忆压缩、人物一致性、ended 判定。
用法: python scripts/test_saga_stress.py [lesson_id1 lesson_id2 ...] [--rounds N]
默认: L102 L901 L1402 L1502 ，每课最多 6 轮或直到 ended。
"""
import io
import json
import sys
import time
import urllib.request
import re

# 强制 stdout/stderr 用 UTF-8，避免 GBK 终端把 emoji/中文写文件时崩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000/api/v1"
MAX_ROUNDS = 7


def post(path, body=None):
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=180)


def post_stream(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=180)
    chunks = []
    while True:
        b = resp.read(4096)
        if not b:
            break
        chunks.append(b.decode("utf-8", errors="replace"))
    return "".join(chunks)


def parse_envelope(body):
    if "\n\n[META]" not in body:
        return body, None
    narrative, meta_str = body.split("\n\n[META]", 1)
    try:
        meta = json.loads(meta_str)
    except Exception:
        meta = None
    return narrative, meta


def stress_one(lid: str, max_rounds: int = MAX_ROUNDS):
    print(f"\n========== {lid} ==========")
    r = post("/practice/saga/start", {"lesson_id": lid})
    state = json.loads(r.read())
    saga_id = state["saga_id"]
    title = state["title"]
    persona = state.get("persona", "")
    persona_name = re.search(r"『.+?·([^』]+)』", persona)
    persona_name = persona_name.group(1) if persona_name else "?"
    choices = state["choices"]
    print(f"标题: {title}")
    print(f"扮演: {persona_name}")
    print(f"开篇 ({len(state['history'][-1]['text'])}B): {state['history'][-1]['text'][:80]}...")

    flags_history = []
    entities_history = []
    persona_appearances = 0  # 主角名字在 narrative 中出现次数
    summary_lengths = []
    ended_at = None
    total_act_time = 0.0

    for rnd in range(1, max_rounds + 1):
        if not choices:
            print(f"  ⚠ 第 {rnd} 轮无候选，提前结束")
            break
        action = choices[0]
        print(f"\n-- 轮次 {rnd} -- 行动: {action[:40]}...")
        t0 = time.time()
        body = post_stream(f"/practice/saga/{saga_id}/act", {"action": action})
        dt = time.time() - t0
        total_act_time += dt
        narrative, meta = parse_envelope(body)
        if meta is None:
            print(f"  ❌ META 解析失败 ({dt:.1f}s)")
            break

        if persona_name != "?" and persona_name in narrative:
            persona_appearances += 1

        flags = meta.get("flags", {}) or {}
        ents = meta.get("entities", []) or []
        summary = meta.get("summary", "") or ""
        ended = bool(meta.get("ended", False))
        new_choices = meta.get("choices", []) or []

        flags_history.append(len(flags))
        entities_history.append(len(ents))
        summary_lengths.append(len(summary))

        print(f"  narrative={len(narrative)}B  flags={len(flags)}  entities={len(ents)}  summary={len(summary)}B  ended={ended}  ({dt:.1f}s)")
        print(f"  narrative preview: {narrative.strip()[:120]}...")
        if summary:
            print(f"  summary: {summary[:120]}")
        if ended:
            ended_at = rnd
            break
        choices = new_choices

    print(f"\n  ━ 统计 ━")
    print(f"  共 {len(flags_history)} 轮，act 总耗时 {total_act_time:.1f}s")
    print(f"  flags 累积曲线: {flags_history}")
    print(f"  entities 累积曲线: {entities_history}")
    print(f"  summary 长度曲线: {summary_lengths}")
    print(f"  主角『{persona_name}』在 narrative 中出现轮数: {persona_appearances}/{len(flags_history)}")
    print(f"  ended: {'✅ 第 ' + str(ended_at) + ' 轮' if ended_at else '❌ 未结束'}")
    return {
        "lid": lid,
        "rounds": len(flags_history),
        "ended_at": ended_at,
        "persona_consistency": persona_appearances / max(len(flags_history), 1),
        "total_time": total_act_time,
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = args or ["L102", "L901", "L1402", "L1502"]
    results = []
    for lid in ids:
        try:
            results.append(stress_one(lid))
        except Exception as e:
            print(f"\n!!! {lid} 异常: {e}")
            results.append({"lid": lid, "error": str(e)})
    print("\n\n========== 总结 ==========")
    for r in results:
        if "error" in r:
            print(f"  {r['lid']}: ❌ {r['error']}")
        else:
            mark = "✅" if r["ended_at"] else "⏸"
            print(f"  {r['lid']}: {mark} {r['rounds']} 轮  ended={r['ended_at']}  人物一致={r['persona_consistency']:.0%}  总耗时{r['total_time']:.1f}s")
