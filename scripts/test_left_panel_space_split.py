# -*- coding: utf-8 -*-
"""LEFT_SIDE 添加后 root 须切分为 occupied zone + usable 子空间。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory
from commands.undo_stack import UndoStack
from core.space.enums import SplitDirection
from core.space.space_face_occupancy import FaceType, get_face_occupancy_manager
from core.space.space_models import Space
from core.space.splitter import METADATA_ZONE_ROLE, ZONE_OCCUPIED, ZONE_REMAIN


def _make_ctx(root: Space) -> dict:
    return {
        "project": type("P", (), {"root_space": root})(),
        "root_space": root,
    }


def main() -> None:
    root = Space(id="root", x=0, y=0, z=0, width=1000, height=720, depth=400)
    ctx = _make_ctx(root)
    stack = UndoStack(maxlen=8)
    fm = get_face_occupancy_manager()

    cmd = CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT)
    assert stack.push(cmd), "execute failed"

    assert len(root.children) == 2, f"expected 2 children, got {len(root.children)}"
    assert root.split_direction is SplitDirection.SPLIT_X

    assert root.left_space is not None and root.right_space is not None
    assert root.children == [root.left_space, root.right_space]
    left, right = root.left_space, root.right_space
    assert abs(left.width - 18.0) < 0.01, f"strip width={left.width}"
    assert abs(right.width - 982.0) < 0.01, f"usable width={right.width}"
    assert left.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    assert right.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    assert left.parent is root and right.parent is root

    mount = cmd._mount_space
    assert mount is not None and mount is left
    assert len(getattr(left, "panel_groups", []) or []) == 1
    assert len(getattr(root, "panel_groups", []) or []) == 0

    assert fm.is_face_occupied(str(left.id), FaceType.LEFT)

    stack.undo_last()
    assert len(root.children) == 0
    assert root.left_space is None and root.right_space is None
    assert root.split_direction is SplitDirection.NONE
    assert not fm.is_face_occupied(str(left.id), FaceType.LEFT)

    assert stack.redo_last()
    assert len(root.children) == 2

    print("PASS: root 1000 → LEFT 18 + usable 982, children on space.children")


if __name__ == "__main__":
    main()
