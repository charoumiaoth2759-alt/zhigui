# -*- coding: utf-8 -*-
"""验证 [STATS] 叶空间计数：left=2, right=3, shelf=5。"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory
from commands.undo_stack import UndoStack
from core.constants.enums import PanelRole
from core.panel.panel_models import Panel
from core.space.space_face_occupancy import FaceType
from core.space.space_models import Space
from core.space.splitter import SpaceSplitter
from core.space.tree import iter_leaves
from ui.cabinet_debug_stats import print_cabinet_debug_stats


def _leaf_count(root: Space) -> int:
    return sum(1 for _ in iter_leaves(root))


def _run_stats(ctx: dict, root: Space, action: str) -> str:
    buf = StringIO()
    with patch("sys.stdout", buf):
        print_cabinet_debug_stats(ctx, root=root, action=action, assert_visual_match=False)
    return buf.getvalue()


def main() -> None:
    root = Space(id="root", width=1000, height=720, depth=400)
    ctx = {"project": type("P", (), {"root_space": root})(), "root_space": root}
    stack = UndoStack(maxlen=8)

    assert _leaf_count(root) == 1

    assert stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.LEFT))
    assert _leaf_count(root) == 2
    out = _run_stats(ctx, root, "add_left_panel")
    assert "add left panel" in out
    assert "spaces = 2" in out

    assert stack.push(CommandFactory.create_add_panel_command(ctx, face=FaceType.RIGHT))
    assert _leaf_count(root) == 3
    out = _run_stats(ctx, root, "add_right_panel")
    assert "add right panel" in out
    assert "spaces = 3" in out

    shelf = Panel(name="shelf1", role=PanelRole.SHELF, thickness=18.0)
    records = SpaceSplitter().split_shelf(root, shelf)
    assert len(records) == 2
    assert _leaf_count(root) == 5
    out = _run_stats(ctx, root, "add_shelf")
    assert "add shelf" in out
    assert "spaces = 5" in out

    print("PASS: stats sequence left=2 right=3 shelf=5")


if __name__ == "__main__":
    main()
