# -*- coding: utf-8 -*-
"""
悬停轻量缓存：仅 ``space_id`` + ``face_type`` + 离开防抖帧计数。

禁止缓存 ``HoverHitResult`` / ``Panel`` / OCC face / AIS node 等对象引用；
split 后旧对象失效会导致例如 RIGHT 面永久无法悬停。
"""

from __future__ import annotations

from dataclasses import dataclass

from core.space.enums import FaceType


@dataclass
class HoverCache:
    last_space_id: str | None = None
    last_face_type: FaceType | None = None
    leave_pending_frames: int = 0

    def clear(self) -> None:
        self.last_space_id = None
        self.last_face_type = None
        self.leave_pending_frames = 0


__all__ = ["HoverCache"]
