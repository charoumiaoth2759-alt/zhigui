# -*- coding: utf-8 -*-
"""
悬停会话：``HoverHitResult`` + ``FaceType``（UI 瞬态，**非**命令事务态）。

由 ``PreviewManager`` 设置 ``target_face``；Viewport 不维护拾取会话。
点击加板须在边界处复制为 ``FaceSelectionSnapshot``；禁止把 ``session.hit`` / ``active_face``
传入 ``AddBoardCommand`` 或 ``create_add_panel_command``。
"""

from __future__ import annotations

from dataclasses import dataclass

from view.interaction.face_type import FaceType
from view.interaction.hover_hit_result import HoverHitResult


@dataclass
class SpaceFaceHoverSession:
    """逻辑空间某一 ``FaceType`` 的悬停 ghost 会话。"""

    target_face: FaceType | None
    hit: HoverHitResult | None = None
    stack_offset_mm: float | None = None
    ghost_draw_logged: bool = False

    @property
    def active(self) -> bool:
        if self.hit is None:
            return False
        if self.target_face is None:
            return True
        return self.hit.face == self.target_face

    @property
    def active_face(self) -> FaceType | None:
        """仅用于预览 / 盒体着色；不得传入命令管线。"""
        return self.hit.face if self.active else None


def update_session_from_hit(
    session: SpaceFaceHoverSession,
    hit: HoverHitResult | None,
    *,
    stack_offset_mm: float,
) -> tuple[bool, bool]:
    """
    用 ``HoverDetector`` 已产出的命中刷新会话。

    Returns
    -------
    (changed, entered)
    """
    if (
        hit is not None
        and session.target_face is not None
        and hit.face != session.target_face
    ):
        hit = None
    prev_active = session.active
    nh = hit is not None

    if nh == prev_active:
        if nh and stack_offset_mm != session.stack_offset_mm:
            session.stack_offset_mm = stack_offset_mm
            return True, False
        return False, False

    session.hit = hit
    if nh and not prev_active:
        session.stack_offset_mm = stack_offset_mm
        session.ghost_draw_logged = False
        return True, True
    if prev_active and not nh:
        session.stack_offset_mm = None
        session.ghost_draw_logged = False
        return True, False
    return True, False


def clear_session(session: SpaceFaceHoverSession) -> bool:
    """清空会话；返回此前是否在悬停。"""
    was = session.active
    session.hit = None
    session.stack_offset_mm = None
    session.ghost_draw_logged = False
    return was


__all__ = [
    "SpaceFaceHoverSession",
    "clear_session",
    "update_session_from_hit",
]
