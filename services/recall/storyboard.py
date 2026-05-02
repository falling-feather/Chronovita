from __future__ import annotations

import uuid

from .controlnet import build_control_signals
from .models import Shot, Storyboard, StoryboardRequest
from .prompt_chain import build_prompt_chain, run_prompt_chain


_SCENE_TEMPLATES = [
    ("起势", "中景固定", "中景"),
    ("承接", "缓慢推镜", "近景"),
    ("转折", "侧移跟随", "全景"),
    ("收束", "拉远定格", "远景"),
]


def _pick_scene(index: int) -> tuple[str, str, str]:
    return _SCENE_TEMPLATES[index % len(_SCENE_TEMPLATES)]


def _heuristic_flags(text: str) -> tuple[bool, bool]:
    has_character = any(token in text for token in ["人", "王", "帝", "将", "士", "民", "禹", "舜", "尧"])
    has_architecture = any(token in text for token in ["城", "宫", "阙", "台", "堤", "坝", "庙", "渠"])
    return has_character, has_architecture


def generate_storyboard(req: StoryboardRequest) -> Storyboard:
    scan_text = req.history_context + req.title + "、".join(req.keywords)
    has_character, has_architecture = _heuristic_flags(scan_text)
    shots: list[Shot] = []
    for i in range(req.target_shot_count):
        beat, camera, shot_size = _pick_scene(i)
        scene_text = f"{req.title} · {beat}"
        steps = build_prompt_chain(
            history_context=req.history_context,
            scene=scene_text,
            keywords=req.keywords,
            character="主要历史人物" if has_character else "",
            posture="庄重" if has_character else "",
            camera=camera,
            shot_size=shot_size,
            style=req.style,
        )
        prompt_result = run_prompt_chain(steps)
        controls = build_control_signals(
            scene=scene_text,
            has_character=has_character,
            has_architecture=has_architecture,
        )
        shots.append(
            Shot(
                index=i,
                duration_sec=4.0,
                summary=f"{beat}：{scene_text}",
                prompt=prompt_result,
                control_signals=controls,
                voiceover=f"（旁白占位 · 第{i + 1}镜）",
            )
        )
    return Storyboard(
        storyboard_id=f"sb_{uuid.uuid4().hex[:10]}",
        chapter_id=req.chapter_id,
        title=req.title,
        style=req.style,
        shots=shots,
    )
