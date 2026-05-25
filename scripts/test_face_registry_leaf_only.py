# -*- coding: utf-8 -*-
"""Face registry：仅 FREE 可交互叶注册面；root / occupied leaf 不得注册。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory
from commands.undo_stack import UndoStack
from core.space.face_registry import rebuild_face_registry
from core.space.space_face_occupancy import (
    FaceType,
    get_face_occupancy_manager,
    is_interactable_space,
)
from core.space.space_models import Space
from core.space.splitter import METADATA_ZONE_ROLE, ZONE_OCCUPIED, ZONE_REMAIN
from core.space.tree import iter_leaves


def _make_ctx(root: Space) -> dict:
    return {
        "project": type("P", (), {"root_space": root})(),
        "root_space": root,
    }


def _has_face_cache(mgr, space_id: str, ft: FaceType) -> bool:
    return mgr.read_face_occupancy_cache(str(space_id), ft) is not None


def main() -> None:
    root = Space(id="root", x=0, y=0, z=0, width=1000, height=720, depth=400)
    ctx = _make_ctx(root)
    stack = UndoStack(maxlen=8)
    fm = get_face_occupancy_manager()

    cmd = CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT)
    assert stack.push(cmd)

    assert not root.is_leaf
    rebuild_face_registry(root)

    assert not root.face_occupancy, f"root: {root.face_occupancy}"
    assert not _has_face_cache(fm, root.id, FaceType.LEFT)

    leaves = list(iter_leaves(root))
    assert len(leaves) == 2
    occupied = next(
        c for c in leaves if c.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    )
    remain = next(
        c for c in leaves if c.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    )

    from core.space.space_occupancy import leaf_topology_occupied

    assert leaf_topology_occupied(occupied)
    assert not is_interactable_space(occupied)
    assert not _has_face_cache(fm, occupied.id, FaceType.LEFT)
    assert not _has_face_cache(fm, occupied.id, FaceType.RIGHT)

    assert not leaf_topology_occupied(remain)
    assert is_interactable_space(remain)
    assert remain.left_face is not None
    assert remain.right_face is not None
    assert remain.left_face.face_type is FaceType.LEFT
    assert remain.right_face.face_type is FaceType.RIGHT
    assert _has_face_cache(fm, remain.id, FaceType.LEFT)
    assert _has_face_cache(fm, remain.id, FaceType.RIGHT)

    print("PASS: face registry only on FREE interactable remain leaf")


if __name__ == "__main__":
    main()
