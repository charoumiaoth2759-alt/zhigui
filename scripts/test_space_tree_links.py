# -*- coding: utf-8 -*-
"""切分后 parent ↔ child 双向引用与空间树结构。"""

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
    verify_split_tree,
    verify_x_split_face_zones,
    x_split_remain_directional_child,
)
from core.space.usable_space_resolver import find_active_remain_leaf
from core.space.tree import walk_dfs
from core.space.validators import check_tree_links


def _assert_tree(root: Space) -> None:
    for parent in walk_dfs(root):
        if len(parent.children) == 2:
            verify_split_tree(parent)
    result = check_tree_links(root)
    assert not result.errors, result.errors


def main() -> None:
    root = Space(id="root", width=1000, height=720, depth=400)
    ctx = {"project": type("P", (), {"root_space": root})(), "root_space": root}
    stack = UndoStack(maxlen=8)

    stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT))
    _assert_tree(root)
    assert root.left_space is not None and root.right_space is not None
    assert root.children == [root.left_space, root.right_space]
    occ, rem = root.left_space, root.right_space
    assert occ.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    assert rem.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    assert occ.parent is root and rem.parent is root

    stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.RIGHT))
    _assert_tree(root)
    remain_parent = root.right_space
    assert remain_parent is not None
    assert remain_parent.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    assert not remain_parent.is_leaf
    verify_split_tree(remain_parent)
    verify_x_split_face_zones(remain_parent)
    assert remain_parent.left_space is not None
    assert remain_parent.right_space is not None
    assert remain_parent.left_space.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    assert remain_parent.right_space.metadata.get(METADATA_ZONE_ROLE) == ZONE_OCCUPIED
    active = find_active_remain_leaf(root)
    assert active is remain_parent.left_space
    assert x_split_remain_directional_child(remain_parent) is remain_parent.left_space

    stack.undo_last()
    _assert_tree(root)
    stack.undo_last()
    _assert_tree(root)
    assert len(root.children) == 0

    print("PASS: split tree parent-child bidirectional links")


if __name__ == "__main__":
    main()
