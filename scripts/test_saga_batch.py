"""V0.3.1 saga 模板批量验证：每节课启动 saga + 执行第一个候选行动，校验 META 协议。"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"

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
        b = resp.read(2048)
        if not b:
            break
        chunks.append(b.decode("utf-8", errors="replace"))
    return "".join(chunks)

def test_lesson(lid):
    t0 = time.time()
    r = post(f"/practice/saga/start", {"lesson_id": lid})
    state = json.loads(r.read())
    saga_id = state["saga_id"]
    title = state["title"]
    opening = state["history"][-1]["text"][:60] + "..."
    choices = state["choices"]
    t_start = time.time() - t0
    print(f"\n=== {lid} | {title} ===")
    print(f"  start ok ({t_start:.1f}s) saga_id={saga_id[:8]}")
    print(f"  开篇: {opening}")
    print(f"  候选: {len(choices)} 个 → {choices[0][:30]}...")

    if not choices:
        print("  ❌ 无候选行动")
        return False

    t1 = time.time()
    body = post_stream(f"/practice/saga/{saga_id}/act", {"action": choices[0]})
    t_act = time.time() - t1
    if "\n\n[META]" not in body:
        print(f"  ❌ 无 META 信封 ({t_act:.1f}s, {len(body)}B)")
        print(f"  body 末尾: ...{body[-200:]}")
        return False
    narrative, meta_str = body.split("\n\n[META]", 1)
    try:
        meta = json.loads(meta_str)
    except Exception as e:
        print(f"  ❌ META 解析失败: {e}")
        print(f"  meta_str: {meta_str[:300]}")
        return False
    print(f"  act ok ({t_act:.1f}s) narrative={len(narrative)}B")
    print(f"    新 choices: {len(meta.get('choices', []))}")
    print(f"    entities: {len(meta.get('entities', []))}")
    print(f"    flags: {meta.get('flags', {})}")
    print(f"    summary: {meta.get('summary', '')[:60]}...")
    print(f"    ended: {meta.get('ended', False)}")
    return True

if __name__ == "__main__":
    ids = sys.argv[1:] or ["L102", "L103", "L104", "L105"]
    ok = 0
    for lid in ids:
        try:
            if test_lesson(lid):
                ok += 1
        except Exception as e:
            print(f"\n=== {lid} ===\n  ❌ 异常: {e}")
    print(f"\n通过 {ok}/{len(ids)}")
