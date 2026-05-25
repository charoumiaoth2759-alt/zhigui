# -*- coding: utf-8 -*-
"""
面占用缓存 — ``occupancy_cache[space_id][face]``。

**禁止**全量 ``rebuild_faces`` + ``reset`` 作为增量路径的唯一刷新手段；
增量写入经 ``SpaceFaceOccupancyManager.update_face_occupancy_cache``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FaceOccupancyCacheEntry:
    """单面占用快照（供拾取 / 约束 / 校验读取）。"""

    state: Any
    occupied: bool
    blocked: bool
    element_count: int = 0


class FaceOccupancyCache:
    """``occupancy_cache[space_id][face_type]`` 容器。"""

    def __init__(self) -> None:
        self._data: dict[str, dict[Any, FaceOccupancyCacheEntry]] = {}

    @property
    def occupancy_cache(self) -> dict[str, dict[Any, FaceOccupancyCacheEntry]]:
        """只读视图（勿在外部就地修改内层 dict）。"""
        return self._data

    def get(
        self, space_id: str, face_type: Any
    ) -> FaceOccupancyCacheEntry | None:
        return self._data.get(str(space_id), {}).get(face_type)

    def set(
        self,
        space_id: str,
        face_type: Any,
        entry: FaceOccupancyCacheEntry,
    ) -> None:
        sid = str(space_id)
        bucket = self._data.setdefault(sid, {})
        bucket[face_type] = entry

    def clear(self) -> None:
        self._data.clear()

    def clear_space(self, space_id: str) -> None:
        self._data.pop(str(space_id), None)


def entry_from_face(face: object) -> FaceOccupancyCacheEntry:
    """由 ``SpaceFace`` 当前挂载推导缓存项。"""
    from .space_face_occupancy import FaceState

    state = getattr(face, "state", FaceState.FREE)
    elements = getattr(face, "mounted_elements", None) or []
    count = len(elements)
    if state is FaceState.FREE:
        return FaceOccupancyCacheEntry(
            state=state,
            occupied=False,
            blocked=False,
            element_count=count,
        )
    if state is FaceState.BLOCKED:
        return FaceOccupancyCacheEntry(
            state=state,
            occupied=True,
            blocked=True,
            element_count=count,
        )
    occupied = count > 0
    if hasattr(face, "is_free") and face.is_free():
        occupied = False
    return FaceOccupancyCacheEntry(
        state=state,
        occupied=occupied,
        blocked=False,
        element_count=count,
    )


__all__ = [
    "FaceOccupancyCache",
    "FaceOccupancyCacheEntry",
    "entry_from_face",
]
