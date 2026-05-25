# -*- coding: utf-8 -*-
"""LEFT / RIGHT 侧板方向槽绝对规则 + active_leaf。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory
from commands.undo_stack import UndoStack
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space
from core.space.splitter import (
    METADATA_ZONE_ROLE,
    ZONE_OCCUPIED,
    ZONE_REMAIN,
    verify_x_split_face_zones,
    x_split_remain_directional_child,
)
from core.space.usable_space_resolver import (
    active_leaf_from_side_split,
    find_active_remain_leaf,
)


def main() -> None:
    root = Space(id="root", width=1000, height=720, depth=400)
    ctx = {"project": type("P", (), {"root_space": root})(), "root_space": root}
    stack = UndoStack(maxlen=4)

    cmd_l = CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT)
    stack.push(cmd_l)
    verify_x_split_face_zones(root)
    assert root.left_space.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    assert root.right_space.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    assert x_split_remain_directional_child(root) is root.right_space
    assert find_active_remain_leaf(root) is root.right_space
    assert active_leaf_from_side_split(FaceType.LEFT, cmd_l._split_record) is root.right_space

    cmd_r = CommandFactory.create_add_panel_command(ctx, face=FaceType.RIGHT)
    stack.push(cmd_r)
    remain_parent = root.right_space
    verify_x_split_face_zones(remain_parent)
    assert remain_parent.left_space.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    assert remain_parent.right_space.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    assert x_split_remain_directional_child(remain_parent) is remain_parent.left_space
    assert find_active_remain_leaf(root) is remain_parent.left_space
    assert active_leaf_from_side_split(FaceType.RIGHT, cmd_r._split_record) is remain_parent.left_space

    print("PASS: LEFT/RIGHT zone slots and active remain leaf")


if __name__ == "__main__":
    main()
