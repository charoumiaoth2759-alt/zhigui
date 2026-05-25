# -*- coding: utf-8 -*-
"""
将板件挂到 ``Space`` 的实现（纯数据，无 UI）。

侧板（LEFT / RIGHT）经 ``side_panel_spec.SidePanelSpec`` 统一管道；
``build_*`` / ``mount_*`` / ``detach_*`` 由 ``FaceType`` / ``PanelRole`` 驱动。
"""

from __future__ import annotations

from typing import Any

from ..constants.enums import AnchorType, PanelRole, PlacementMode
from ..debug_flags import DEBUG_VIEW3D
from ..space.constraint_engine import ConstraintEngine
from ..space.space_face_occupancy import FaceType, get_face_occupancy_manager
from ..space.space_models import Space

from .panel_calculator import calculate_side_panel
from .panel_models import Panel, PanelGroup
from .panel_placement import side_stack_offset_mm
from .side_panel_solver import solve_side_panel
from .side_panel_spec import (
    PanelRoleSpec,
    SidePanelSpec,
    face_from_payload,
    spec_for_command,
    spec_for_face,
    spec_for_panel,
)

_fit_engine = ConstraintEngine()


def _target_space(ctx: dict[str, Any]) -> Space | None:
    root = ctx.get("root_space")
    if isinstance(root, Space):
        return root
    project = ctx.get("project")
    if project is not None:
        rs = getattr(project, "root_space", None)
        if isinstance(rs, Space):
            return rs
    return None


def _resolve_spec(
    *,
    face: FaceType | None = None,
    command_name: str | None = None,
    panel: Panel | None = None,
) -> SidePanelSpec:
    if panel is not None:
        sp = spec_for_panel(panel)
        if sp is not None:
            return sp
    if face is not None:
        sp = spec_for_face(face)
        if sp is not None:
            return sp
    if command_name:
        sp = spec_for_command(command_name)
        if sp is not None:
            return sp
    raise ValueError("unknown side panel spec (face / command / panel)")


def build_side_panel(
    space: Space,
    spec: SidePanelSpec,
    thickness: float = 18.0,
) -> Panel:
    """构造侧板实例（算尺、落位、校验），尚未写入 ``panel_groups`` / 面占用。"""
    t = max(6.0, min(float(thickness), 80.0))
    panel = Panel(
        name=spec.label,
        role=spec.role,
        placement_mode=PlacementMode.ANCHOR_FIXED,
        anchor_type=spec.anchor,
    )
    calculate_side_panel(panel, space, thickness=t)
    fm = get_face_occupancy_manager()
    if not fm.can_place(space.id, spec.face, panel):
        raise RuntimeError(f"该空间{spec.label}面已占用板件，无法重复添加。")
    panel.space_id = space.id
    solve_side_panel(panel, space)
    if not _fit_engine.validate(space, panel):
        raise RuntimeError(f"板件超出当前空间盒子尺寸，无法添加{spec.label}。")
    return panel


def mount_side_panel(space: Space, panel: Panel, spec: SidePanelSpec | None = None) -> None:
    """将 ``build_side_panel`` 产出的 **同一** ``Panel`` 挂入 ``space.panel_groups`` 并登记面占用。"""
    sp = spec or _resolve_spec(panel=panel)
    fm = get_face_occupancy_manager()
    if not hasattr(space, "panel_groups") or space.panel_groups is None:
        space.panel_groups = []
    for g in space.panel_groups:
        pls = getattr(g, "panels", None) or []
        if panel in pls:
            return
    group = PanelGroup(space_id=space.id)
    group.add(panel)
    space.panel_groups.append(group)
    if not fm.occupy(space.id, sp.face, panel):
        group.panels.remove(panel)
        space.panel_groups.remove(group)
        raise RuntimeError(f"{sp.label}面占用登记失败（内部状态不一致）。")
    from core.dirty.dirty_tracker import mark_panel_dirty, mark_space_dirty

    mark_space_dirty(space)
    mark_panel_dirty(panel, host_space=space)


def detach_side_panel(
    panel: Panel,
    space: Space,
    spec: SidePanelSpec | None = None,
) -> None:
    """卸下 ``mount_side_panel`` 挂载的同一块 ``Panel``（禁止 ``deepcopy`` 后删除）。"""
    sp = spec or _resolve_spec(panel=panel)
    fm = get_face_occupancy_manager()
    fm.release_for_panel(panel)
    if not hasattr(space, "panel_groups") or space.panel_groups is None:
        if sp is not None:
            fm.update_face_occupancy_cache(space, sp.face)
        return
    groups = space.panel_groups
    for g in list(groups):
        pls = getattr(g, "panels", None) or []
        if panel in pls:
            pls.remove(panel)
            if len(pls) == 0 and g in groups:
                groups.remove(g)
            break
    if sp is not None:
        fm.update_face_occupancy_cache(space, sp.face)
    from core.dirty.dirty_tracker import mark_panel_dirty, mark_space_dirty

    mark_space_dirty(space)
    mark_panel_dirty(panel, host_space=space)


def add_side_panel(
    space: Space,
    spec: SidePanelSpec,
    thickness: float = 18.0,
) -> Panel:
    """构建 + 挂载一步完成。"""
    if DEBUG_VIEW3D:
        print(f"[Core] add_side_panel {spec.label} ENTER")
    panel = build_side_panel(space, spec, thickness=thickness)
    mount_side_panel(space, panel, spec)
    if DEBUG_VIEW3D:
        print(f"[Core] add_side_panel {spec.label} DONE")
    return panel


# ── 兼容别名（LEFT）────────────────────────────────────────────────────

def left_side_stack_offset_mm(space: Space) -> float:
    return side_stack_offset_mm(space, PanelRole.LEFT_SIDE)


def build_left_side_panel(space: Space, thickness: float = 18.0) -> Panel:
    sp = spec_for_face(FaceType.LEFT)
    assert sp is not None
    return build_side_panel(space, sp, thickness=thickness)


def mount_left_side_panel(space: Space, panel: Panel) -> None:
    mount_side_panel(space, panel)


def detach_left_side_panel(panel: Panel, space: Space) -> None:
    detach_side_panel(panel, space)


def add_left_side_panel(space: Space, thickness: float = 18.0) -> Panel:
    sp = spec_for_face(FaceType.LEFT)
    assert sp is not None
    return add_side_panel(space, sp, thickness=thickness)


# ── RIGHT ───────────────────────────────────────────────────────────────

def right_side_stack_offset_mm(space: Space) -> float:
    return side_stack_offset_mm(space, PanelRole.RIGHT_SIDE)


def build_right_side_panel(space: Space, thickness: float = 18.0) -> Panel:
    sp = spec_for_face(FaceType.RIGHT)
    assert sp is not None
    return build_side_panel(space, sp, thickness=thickness)


def mount_right_side_panel(space: Space, panel: Panel) -> None:
    mount_side_panel(space, panel)


def detach_right_side_panel(panel: Panel, space: Space) -> None:
    detach_side_panel(panel, space)


def add_right_side_panel(space: Space, thickness: float = 18.0) -> Panel:
    sp = spec_for_face(FaceType.RIGHT)
    assert sp is not None
    return add_side_panel(space, sp, thickness=thickness)


def _add_panel_via_ctx(
    ctx: dict[str, Any],
    *,
    default_face: FaceType,
    payload: Any = None,
) -> None:
    space = _target_space(ctx)
    if space is None:
        raise RuntimeError(
            "add_panel: no target Space (selection / root_space / project.root_space)"
        )
    t = 18.0
    face = face_from_payload(payload) or default_face
    if isinstance(payload, dict):
        raw = payload.get("thickness")
        if raw is not None:
            try:
                t = float(raw)
            except (TypeError, ValueError):
                t = 18.0
    t = max(6.0, min(t, 80.0))
    sp = spec_for_face(face)
    if sp is None:
        raise RuntimeError(f"unsupported side panel face: {face!r}")
    add_side_panel(space, sp, thickness=t)
    if DEBUG_VIEW3D:
        print(f"[Panel] add {sp.command_name} -> {space.name}")


def add_left_panel(ctx: dict[str, Any], payload: Any = None) -> None:
    _add_panel_via_ctx(ctx, default_face=FaceType.LEFT, payload=payload)


def add_right_panel(ctx: dict[str, Any], payload: Any = None) -> None:
    _add_panel_via_ctx(ctx, default_face=FaceType.RIGHT, payload=payload)


__all__ = [
    "add_left_panel",
    "add_left_side_panel",
    "add_right_panel",
    "add_right_side_panel",
    "add_side_panel",
    "build_left_side_panel",
    "build_right_side_panel",
    "build_side_panel",
    "detach_left_side_panel",
    "detach_right_side_panel",
    "detach_side_panel",
    "left_side_stack_offset_mm",
    "mount_left_side_panel",
    "mount_right_side_panel",
    "mount_side_panel",
    "right_side_stack_offset_mm",
]
