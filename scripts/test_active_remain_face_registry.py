# -*- coding: utf-8 -*-
"""LEFT + RIGHT 后 FACE 仅注册在最深 remain 叶；occupied 窄条与旧 remain 父无缓存。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory, resolve_attachment_space
from commands.undo_stack import UndoStack
from core.space.face_registry import rebuild_face_registry
from core.space.space_face_occupancy import FaceType, get_face_occupancy_manager
from core.space.space_models import Space
from core.space.splitter import METADATA_ZONE_ROLE, ZONE_OCCUPIED, ZONE_REMAIN
from core.space.tree import iter_leaves
from core.space.usable_space_resolver import find_active_remain_leaf


def _make_ctx(root: Space) -> dict:
    return {"project": type("P", (), {"root_space": root})(), "root_space": root}


def _has_cache(mgr, sid: str, ft: FaceType) -> bool:
    return mgr.read_face_occupancy_cache(sid, ft) is not None


def main() -> None:
    root = Space(id="root", width=1000, height=720, depth=400)
    ctx = _make_ctx(root)
    stack = UndoStack(maxlen=8)
    fm = get_face_occupancy_manager()

    stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT))
    stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.RIGHT))
    rebuild_face_registry(root)

    active = find_active_remain_leaf(root)
    assert active is not None
    assert resolve_attachment_space(ctx) is root
    assert active is not root

    leaves = list(iter_leaves(root))
    assert len(leaves) == 3

    occupied = [
        c for c in leaves if c.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    ]
    assert len(occupied) == 2

    for occ in occupied:
        assert not _has_cache(fm, str(occ.id), FaceType.LEFT)

    # 首次 remain 在 RIGHT 后已成为 SPLIT 父，不应再挂 face
    remain_parents = [
        c
        for c in leaves
        if c.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    ]
    assert len(remain_parents) == 1
    inner = remain_parents[0]
    assert inner is active
    assert inner.left_face is not None and inner.right_face is not None
    assert inner.left_face.face_type is FaceType.LEFT
    assert inner.right_face.face_type is FaceType.RIGHT
    assert _has_cache(fm, str(inner.id), FaceType.LEFT)
    assert _has_cache(fm, str(inner.id), FaceType.RIGHT)

    print(f"PASS: face registry only on active remain id={inner.id}")


if __name__ == "__main__":
    main()
