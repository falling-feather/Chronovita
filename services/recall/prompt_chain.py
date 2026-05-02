from __future__ import annotations

import uuid
from typing import Iterable

from .models import PromptChainResult, PromptStep


_SYSTEM_TEMPLATE = (
    "你是一名严谨的历史可视化分镜师，需要严格遵循史实，"
    "在风格化基础上避免错位的服饰、器物、建筑形制。"
)

_HISTORY_TEMPLATE = "历史背景：{history_context}"
_SCENE_TEMPLATE = "场景：{scene}，关键元素：{keywords}"
_CHARACTER_TEMPLATE = "人物：{character}，姿态与情绪：{posture}"
_CAMERA_TEMPLATE = "镜头：{camera}，景别：{shot_size}"
_STYLE_TEMPLATE = "美术风格：{style}，色调：{palette}"

_DEFAULT_NEGATIVE = (
    "现代物品, 现代建筑, 文字水印, 多余手指, 比例失调, 朝代混搭, 卡通脸"
)


def build_prompt_chain(
    history_context: str,
    scene: str,
    keywords: Iterable[str],
    character: str = "",
    posture: str = "",
    camera: str = "中景固定",
    shot_size: str = "中景",
    style: str = "工笔淡彩",
    palette: str = "藏青朱砂",
) -> list[PromptStep]:
    keywords_text = "、".join(keywords) if keywords else "无"
    return [
        PromptStep(role="system", template=_SYSTEM_TEMPLATE, rendered=_SYSTEM_TEMPLATE),
        PromptStep(
            role="history_context",
            template=_HISTORY_TEMPLATE,
            rendered=_HISTORY_TEMPLATE.format(history_context=history_context),
        ),
        PromptStep(
            role="scene",
            template=_SCENE_TEMPLATE,
            rendered=_SCENE_TEMPLATE.format(scene=scene, keywords=keywords_text),
        ),
        PromptStep(
            role="character",
            template=_CHARACTER_TEMPLATE,
            rendered=_CHARACTER_TEMPLATE.format(
                character=character or "无明确主体", posture=posture or "自然"
            ),
        ),
        PromptStep(
            role="camera",
            template=_CAMERA_TEMPLATE,
            rendered=_CAMERA_TEMPLATE.format(camera=camera, shot_size=shot_size),
        ),
        PromptStep(
            role="style",
            template=_STYLE_TEMPLATE,
            rendered=_STYLE_TEMPLATE.format(style=style, palette=palette),
        ),
    ]


def run_prompt_chain(steps: list[PromptStep]) -> PromptChainResult:
    rendered_parts = [step.rendered for step in steps if step.rendered]
    final_prompt = "\n".join(rendered_parts)
    return PromptChainResult(
        chain_id=f"chain_{uuid.uuid4().hex[:10]}",
        steps=steps,
        final_prompt=final_prompt,
        negative_prompt=_DEFAULT_NEGATIVE,
    )
