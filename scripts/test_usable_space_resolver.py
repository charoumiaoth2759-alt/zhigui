# -*- coding: utf-8 -*-
"""板件命令目标须为 remain usable 叶，禁止对已 SPLIT 的 root 直接加板。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory, resolve_attachment_space
from commands.undo_stack import UndoStack
from core.space.face_selection_snapshot import FaceSelectionSnapshot
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space
from core.space.splitter import METADATA_ZONE_ROLE, ZONE_REMAIN
from core.space.usable_space_resolver import resolve_panel_operating_space


def _make_ctx(root: Space) -> dict:
    return {
        "project": type("P", (), {"root_space": root})(),
        "root_space": root,
    }


def main() -> None:
    root = Space(id="root", x=0, y=0, z=0, width=1000, height=720, depth=400)
    ctx = _make_ctx(root)
    stack = UndoStack(maxlen=8)

    assert resolve_panel_operating_space(root) is root
    assert resolve_attachment_space(ctx) is root

    assert stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT))
    assert not root.is_leaf
    assert len(root.children) == 2

    remain = next(
        c
        for c in root.children
        if c.metadata.get(METADATA_ZONE_ROLE) == ZONE_REMAIN
    )
    assert remain.is_leaf

    assert resolve_attachment_space(ctx) is root

    snap_r = FaceSelectionSnapshot.from_pick(
        space_id=str(remain.id),
        face_type=FaceType.RIGHT,
    )
    cmd_r = CommandFactory.create_add_panel_command(ctx, face_snapshot=snap_r)
    assert cmd_r._space is remain, "RIGHT must use face_snapshot space_id, not root redirect"

    print("PASS: panel ops resolve to remain usable space, not split root")


if __name__ == "__main__":
    main()
