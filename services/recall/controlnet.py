from __future__ import annotations

from .models import ControlSignal


def build_control_signals(
    scene: str,
    has_character: bool,
    has_architecture: bool,
    reference_uri: str | None = None,
) -> list[ControlSignal]:
    signals: list[ControlSignal] = []
    if has_character:
        signals.append(
            ControlSignal(kind="pose", weight=0.85, note=f"姿态约束 · 场景「{scene}」")
        )
    if has_architecture:
        signals.append(
            ControlSignal(kind="lineart", weight=0.7, note="建筑线稿约束 · 形制锁定")
        )
        signals.append(
            ControlSignal(kind="depth", weight=0.55, note="景深约束 · 透视稳定")
        )
    if reference_uri:
        signals.append(
            ControlSignal(
                kind="reference",
                weight=0.5,
                source_uri=reference_uri,
                note="参考图风格迁移",
            )
        )
    if not signals:
        signals.append(
            ControlSignal(kind="scribble", weight=0.4, note="松约束 · 仅勾稿引导")
        )
    return signals
