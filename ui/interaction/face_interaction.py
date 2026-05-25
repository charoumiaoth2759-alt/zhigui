# -*- coding: utf-8 -*-
"""
侧板面悬停 / 点击统一入口（LEFT / RIGHT 共用，禁止 ``if face == LEFT`` 分叉）。

``process_face_hover`` — 过滤不可预览的命中；
``process_face_click`` — 占用校验 → ``submit_add_panel``（仅 ``FaceSelectionSnapshot``）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.panel.panel_face_mapper import SIDE_PANEL_FACE_ROLES, get_panel_role_by_face
from core.panel.panel_role_spec import iter_panel_role_specs, spec_for_face
from core.space.space_face_occupancy import FaceType, SpaceFaceOccupancy
from core.space.space_occupancy import leaf_topology_occupied
from core.space.face_click_resolve import find_space
from core.space.face_selection_snapshot import FaceSelectionSnapshot
from view.interaction.hover_hit_result import HoverHitResult
from .interaction_log import (
    log_hover_click_confirm,
    log_hover_direction_mismatch,
    log_hover_face_direction,
)

from .cabinet_interaction_sources import CabinetInteractionSource

if TYPE_CHECKING:
    from .cabinet_interaction_manager import CabinetInteractionManager

_HOVER_CLICK_SOURCES: frozenset[CabinetInteractionSource] = frozenset(
    {
        CabinetInteractionSource.MAIN_3D_HOVER_CLICK,
        CabinetInteractionSource.PARAM_SPACE_TOOL,
    }
)

_SIDE_PANEL_FACES: frozenset[FaceType] = frozenset(SIDE_PANEL_FACE_ROLES.keys())

# ``SidePanelSpec.command_name`` ↔ ``ToolMode``（注册表驱动，无左右分支）
_FACE_BY_TOOL_MODE: dict[Any, FaceType] = {}
_TOOL_MODE_BY_FACE: dict[FaceType, Any] = {}


def _register_tool_face_maps() -> None:
    if _FACE_BY_TOOL_MODE:
        return
    from ui.cabinet_space.tool_modes import ToolMode

    _cmd_tool = {
        "add_left_panel": ToolMode.ADD_LEFT_PANEL,
        "add_right_panel": ToolMode.ADD_RIGHT_PANEL,
    }
    for sp in iter_panel_role_specs():
        tm = _cmd_tool.get(sp.command_name)
        if tm is None:
            continue
        _FACE_BY_TOOL_MODE[tm] = sp.face
        _TOOL_MODE_BY_FACE[sp.face] = tm


def is_side_panel_face(face: FaceType) -> bool:
    return face in _SIDE_PANEL_FACES


def face_for_tool_mode(tool_mode: Any) -> FaceType | None:
    _register_tool_face_maps()
    return _FACE_BY_TOOL_MODE.get(tool_mode)


def tool_mode_for_face(face: FaceType) -> Any | None:
    _register_tool_face_maps()
    return _TOOL_MODE_BY_FACE.get(face)


def side_panel_face_blocks_interaction(space: Any, face: FaceType) -> bool:
    """该面是否禁止继续加侧板（``SpaceFaceOccupancy`` 实时查询）。"""
    if not is_side_panel_face(face):
        return False
    from core.space.space_models import Space

    if not isinstance(space, Space):
        return False
    return not SpaceFaceOccupancy.is_face_available(space, face)


def validate_click_hover_direction(
    clicked: FaceSelectionSnapshot,
    manager: CabinetInteractionManager,
    *,
    frozen_hover: Any | None = None,
) -> bool:
    """
    点击前方向验证：``clicked`` 须与本次冻结的 hover 一致。

    ``confirm_viewport_hover_click`` 读取后已 ``current_hover_result = None``，
    须传入 ``frozen_hover``。打印 ``[HOVER]`` + ``space_id`` + ``face_type``。
    """
    hover = frozen_hover
    if hover is None:
        hover = getattr(manager, "current_hover_result", None)
    if hover is None:
        return False
    log_hover_face_direction(hover.face_type, _log_space(hover.space_id))
    if clicked.face_type != hover.face_type:
        log_hover_direction_mismatch(
            clicked_face=clicked.face_type,
            hovered_face=hover.face_type,
            space_id=hover.space_id,
        )
        return False
    if clicked.space_id != hover.space_id:
        log_hover_direction_mismatch(
            clicked_face=clicked.face_type,
            hovered_face=hover.face_type,
            space_id=hover.space_id,
        )
        return False
    return True


def _log_space(space_id: str) -> Any:
    return type("_LogSpace", (), {"id": space_id})()


def space_blocks_hover(space: Any) -> bool:
    """悬停/预览拦截：``metadata.topology_occupancy`` 为权威。"""
    from core.space.space_models import Space

    if not isinstance(space, Space):
        return False
    return leaf_topology_occupied(space)


def block_occupied_space_target(space: Any | None) -> bool:
    """
    点击/加板执行前最终拦截（悬停漏检时兜底）。

    ``topology_occupancy`` 为权威；拦截时打印 ``[BLOCK] occupied space``。
    """
    if space is None:
        return False
    from core.space.space_models import Space

    if isinstance(space, Space) and leaf_topology_occupied(space):
        print("[BLOCK] occupied space")
        return True
    return False


def process_face_hover(
    face: FaceType,
    hit: HoverHitResult | None,
    **_: Any,
) -> HoverHitResult | None:
    """统一悬停：过滤不可预览的命中。"""
    if hit is None:
        return None
    if hit.face != face:
        return None
    log_hover_face_direction(face, hit.space)
    return hit


def process_face_click(
    clicked: FaceSelectionSnapshot,
    *,
    manager: CabinetInteractionManager,
    source: CabinetInteractionSource,
    payload: Any | None = None,
    frozen_hover: Any | None = None,
) -> bool:
    """
    统一点击确认 → 加板命令链。

    只接受 ``FaceSelectionSnapshot``；禁止传入悬停 ``HoverHitResult`` 或
    ``PreviewManager.hit`` 等可变引用。
    """
    face = clicked.face_type
    if source in _HOVER_CLICK_SOURCES:
        if not validate_click_hover_direction(
            clicked, manager, frozen_hover=frozen_hover
        ):
            return False
    host = getattr(manager, "_host", None)
    dispatcher = getattr(host, "_cmd_dispatcher", None)
    ctx = getattr(dispatcher, "context", None) if dispatcher is not None else None
    if not isinstance(ctx, dict):
        return False
    clicked_space_id = clicked.space_id
    space = find_space(ctx, clicked_space_id)
    if space is None:
        return False
    if block_occupied_space_target(space):
        manager.clear_preview()
        return False
    log_hover_click_confirm(face)
    cmd_payload: dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
    _ = cmd_payload
    res = manager.submit_add_panel(
        None,
        source=source,
        face_snapshot=clicked,
    )
    if res.success:
        manager.clear_preview()
    return bool(res.success)


__all__ = [
    "face_for_tool_mode",
    "is_side_panel_face",
    "process_face_click",
    "process_face_hover",
    "block_occupied_space_target",
    "space_blocks_hover",
    "side_panel_face_blocks_interaction",
    "tool_mode_for_face",
    "validate_click_hover_direction",
]
