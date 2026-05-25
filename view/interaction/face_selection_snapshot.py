# -*- coding: utf-8 -*-
"""Re-export：点击快照定义在 ``core.space.face_selection_snapshot``。"""

from __future__ import annotations

from core.space.face_selection_snapshot import (
    FACE_SELECTION_PAYLOAD_KEY,
    FaceSelectionSnapshot,
    face_snapshot_from_payload,
)
from .hover_hit_result import HoverHitResult


def snapshot_from_hover(hover: HoverHitResult) -> FaceSelectionSnapshot:
    """从悬停命中复制一次；调用后不得再读 ``hover`` / ``PreviewManager.hit``。"""
    sid = str(getattr(getattr(hover, "space", None), "id", "") or "").strip()
    if not sid:
        raise ValueError("hover.space.id is required for FaceSelectionSnapshot")
    return FaceSelectionSnapshot.from_pick(space_id=sid, face_type=hover.face)


__all__ = [
    "FACE_SELECTION_PAYLOAD_KEY",
    "FaceSelectionSnapshot",
    "face_snapshot_from_payload",
    "snapshot_from_hover",
]
