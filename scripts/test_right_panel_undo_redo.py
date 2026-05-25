# -*- coding: utf-8 -*-
"""RIGHT 侧板 undo/redo 回归（无 Qt）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.command_factory import CommandFactory
from commands.undo_stack import UndoStack
from core.cabinet.cabinet_model import Cabinet
from core.panel.side_panel_spec import spec_for_face
from core.space.space_face_occupancy import FaceType, get_face_occupancy_manager
from core.space.space_models import Space


from core.space.tree import walk_dfs


class _FakeView:
    _display_panels: list | None = None

    def append_display_panels(self, panels, *, target_space=None):
        existing = list(self._display_panels or [])
        known = {str(getattr(p, "id", "") or "") for p in existing}
        for p in panels:
            pid = str(getattr(p, "id", "") or "")
            if pid and pid not in known:
                existing.append(p)
                known.add(pid)
        self._display_panels = existing

    def remove_display_panels_by_ids(self, panel_ids):
        drop = {str(x) for x in panel_ids if x}
        remaining = [
            p
            for p in (self._display_panels or [])
            if str(getattr(p, "id", "") or "") not in drop
        ]
        self._display_panels = remaining if remaining else None


def _make_ctx(root: Space) -> dict:
    view = _FakeView()
    return {
        "project": Cabinet(root_space=root),
        "root_space": root,
        "canvas": type("C", (), {"_3d_view": view})(),
    }


def _panel_count_subtree(space: Space) -> int:
    n = 0
    for node in walk_dfs(space):
        for g in getattr(node, "panel_groups", None) or []:
            n += len(getattr(g, "panels", None) or [])
    return n


def _panels_in_subtree(space: Space) -> list:
    out = []
    for node in walk_dfs(space):
        for g in getattr(node, "panel_groups", None) or []:
            out.extend(getattr(g, "panels", None) or [])
    return out


def _right_strip_space(root: Space) -> Space | None:
    return root.right_space


def _right_face_occupied(root: Space, fm) -> bool:
    strip = _right_strip_space(root)
    if strip is not None and fm.is_face_occupied(str(strip.id), FaceType.RIGHT):
        return True
    return fm.is_face_occupied(str(root.id), FaceType.RIGHT)


def _panels_on(space: Space) -> list:
    return _panels_in_subtree(space)


def main() -> None:
    root = Space(id="root", x=0, y=0, z=0, width=600, height=720, depth=400)
    ctx = _make_ctx(root)
    stack = UndoStack(maxlen=64)
    fm = get_face_occupancy_manager()
    view = ctx["canvas"]._3d_view

    proj = ctx["project"]
    cmd = CommandFactory.create_add_panel_command(ctx, face=FaceType.RIGHT)
    assert stack.push(cmd)
    pid = str(cmd._panel.id)
    view.append_display_panels(_panels_on(root), target_space=root)
    assert _panel_count_subtree(root) == 1 and _right_face_occupied(root, fm)
    assert len(root.children) == 2
    assert len(view._display_panels or []) == 1
    assert cmd._panel in proj.boards

    for i in range(30):
        assert stack.undo_last(), f"undo {i}"
        view.remove_display_panels_by_ids([pid])
        assert _panel_count_subtree(root) == 0
        assert not _right_face_occupied(root, fm)
        assert len(root.children) == 0
        assert len(view._display_panels or []) == 0
        assert cmd._panel not in proj.boards
        assert len(proj.boards) == 0

        assert stack.redo_last(), f"redo {i}"
        view.append_display_panels(_panels_on(root), target_space=root)
        assert _panel_count_subtree(root) == 1
        assert _right_face_occupied(root, fm)
        assert len(root.children) == 2
        assert len(view._display_panels or []) == 1
        assert cmd._panel in proj.boards

    print("PASS: 30× undo/redo (occupancy, panel, display dedup)")


if __name__ == "__main__":
    main()
