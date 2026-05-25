# -*- coding: utf-8 -*-
"""
Topological Space Kernel — ``SpaceConsistencyManager`` 为空间树**唯一**拓扑出口。

任何改变空间树或挂载关系的操作（split / add panel / remove panel / undo / redo /
根尺寸变更）在领域写入结束后**必须**调用::

    SpaceConsistencyManager().rebuild_topology(root_space)

或从任意节点上溯根::

    finalize_space_mutation(node=leaf, ctx=ctx)

``core.space.splitter`` 仅 split / 创建子空间，**禁止**写 neighbor / occupancy / faces。

``rebuild_topology`` 编排（全量，无锚点时）::

    _rebuild_tree_links → rebuild_adjacency(父链局部) → rebuild_occupancy → rebuild_faces → validate

局部变更优先 ``update_space_topology(space)``（当前 space + 相邻 space + 指定 face），
禁止 ``rebuild_adjacency`` 先清空全树 ``*_neighbor`` 再扫描。

``validate`` 默认检查：父子一致性、非法尺寸、子节点重叠、断裂拓扑（见 ``TOPOLOGY_CHECKS``）。

禁止：删除板件对象、清空 ``boards`` / ``panel_groups``、清空 ``Space.children``、
业务层直接写占用字段。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from ..dirty.dirty_flags import DirtyFlag
from ..dirty.dirty_tracker import mark_space_dirty
from ..constants.enums import PlacementMode
from ..panel.anchor_placement import apply_mixed_placements, placement_mode_effective
from ..panel.panel_models import Panel, PanelGroup
from .constraint_engine import ConstraintEngine
from .enums import SplitDirection, is_split_along_x, is_split_along_y, is_split_along_z
from .placement_state import (
    BLOCKED,
    INVALID,
    NEEDS_RELAYOUT,
    PLACED,
    UNPLACED,
    set_placement_state,
)
from .space_face_occupancy import (
    SpaceFaceOccupancyManager,
    get_space_face_occupancy_manager,
)
from .space_occupancy import rebuild_tree_occupancy, update_spaces_occupancy
from .space_resolver import SpaceResolver
from .tree import resolve_space_root, walk_dfs
from .validators import TOPOLOGY_CHECKS, ValidationResult, validate

if TYPE_CHECKING:
    from .space_models import Space

_NEIGHBOR_ATTRS = (
    "left_neighbor",
    "right_neighbor",
    "top_neighbor",
    "bottom_neighbor",
    "front_neighbor",
    "back_neighbor",
)

_INVERSE_NEIGHBOR: dict[str, str] = {
    "left_neighbor": "right_neighbor",
    "right_neighbor": "left_neighbor",
    "top_neighbor": "bottom_neighbor",
    "bottom_neighbor": "top_neighbor",
    "front_neighbor": "back_neighbor",
    "back_neighbor": "front_neighbor",
}

_POSITION_TOL_MM = 0.5

def _log_topology(message: str) -> None:
    from core.cabinet_pipeline_log import log_topology

    log_topology(message)


def _collect_panels_unique(root: "Space") -> list[Panel]:
    """树上全部 ``Panel``（``panel_groups`` + 各节点 ``panels``），按 ``id`` 去重。"""
    seen: set[str] = set()
    out: list[Panel] = []

    def add(p: Panel) -> None:
        k = str(getattr(p, "id", "") or id(p))
        if k in seen:
            return
        seen.add(k)
        out.append(p)

    for node in walk_dfs(root):
        for grp in getattr(node, "panel_groups", None) or []:
            for p in getattr(grp, "panels", None) or []:
                if isinstance(p, Panel):
                    add(p)
        for p in getattr(node, "panels", None) or []:
            if isinstance(p, Panel):
                add(p)
    return out


def _detach_panel_from_tree(root: "Space", panel: Panel) -> None:
    for node in walk_dfs(root):
        for grp in list(getattr(node, "panel_groups", None) or []):
            pls = getattr(grp, "panels", None)
            if pls and panel in pls:
                pls.remove(panel)
        flat = getattr(node, "panels", None)
        if flat and panel in flat:
            flat.remove(panel)
        groups = getattr(node, "panel_groups", None)
        if groups:
            node.panel_groups = [
                g for g in groups if len(getattr(g, "panels", []) or []) > 0
            ]


def _ensure_panel_group(space: "Space") -> PanelGroup:
    sid = space.id
    for g in getattr(space, "panel_groups", None) or []:
        if getattr(g, "space_id", None) == sid:
            return g
    if not hasattr(space, "panel_groups") or space.panel_groups is None:
        space.panel_groups = []
    g = PanelGroup(space_id=sid)
    space.panel_groups.append(g)
    return g


def _attach_panel_to_space(space: "Space", panel: Panel) -> None:
    grp = _ensure_panel_group(space)
    if panel not in grp.panels:
        grp.add(panel)


def _directional_pair(parent: "Space") -> tuple["Space", "Space"] | None:
    """二元切分的方向槽对（仅用 ``left_space``/``right_space`` 等方向槽）。"""
    ordered = parent.ordered_directional_children()
    if ordered is not None and len(ordered) >= 2:
        return ordered[0], ordered[1]
    return None


def _infer_split_direction(parent: "Space") -> SplitDirection:
    pair = _directional_pair(parent)
    if pair is None:
        return parent.split_direction
    if parent.split_direction != SplitDirection.NONE:
        return parent.split_direction

    a, b = pair
    if abs(b.x - a.x) > _POSITION_TOL_MM:
        return SplitDirection.SPLIT_X
    if abs(b.y - a.y) > _POSITION_TOL_MM:
        return SplitDirection.SPLIT_Y
    if abs(b.z - a.z) > _POSITION_TOL_MM:
        return SplitDirection.SPLIT_Z
    return SplitDirection.NONE


def _sort_siblings(parent: "Space") -> list["Space"]:
    ordered = parent.ordered_directional_children()
    if ordered is not None:
        return ordered
    return list(parent.children)


def _clear_neighbors(space: "Space") -> None:
    for attr in _NEIGHBOR_ATTRS:
        setattr(space, attr, None)


def _unlink_neighbor_on_space(space: "Space", attr: str) -> "Space | None":
    other = getattr(space, attr, None)
    if other is None:
        setattr(space, attr, None)
        return None
    inv = _INVERSE_NEIGHBOR[attr]
    if getattr(other, inv, None) is space:
        setattr(other, inv, None)
    setattr(space, attr, None)
    return other


def _unlink_all_neighbors(space: "Space") -> list["Space"]:
    """断开 ``space`` 全部邻接边（双向），返回触及节点列表（去重）。"""
    touched: list["Space"] = [space]
    seen: set[int] = {id(space)}
    for attr in _NEIGHBOR_ATTRS:
        other = _unlink_neighbor_on_space(space, attr)
        if other is not None and id(other) not in seen:
            seen.add(id(other))
            touched.append(other)
    return touched


def _link_sibling_pair(prev: "Space", nxt: "Space", direction: SplitDirection) -> None:
    if is_split_along_x(direction):
        prev.right_neighbor = nxt
        nxt.left_neighbor = prev
    elif is_split_along_y(direction):
        prev.top_neighbor = nxt
        nxt.bottom_neighbor = prev
    elif is_split_along_z(direction):
        prev.front_neighbor = nxt
        nxt.back_neighbor = prev


def _update_adjacency_for_space(space: "Space") -> list["Space"]:
    """
    仅刷新 ``space`` 及其沿父级切分轴的相邻兄弟链（禁止全树清空 + 扫描）。
    """
    touched = _unlink_all_neighbors(space)
    seen: set[int] = {id(s) for s in touched}
    parent = space.parent
    if parent is None or len(parent.children) < 2:
        return touched

    direction = parent.split_direction
    if not (
        is_split_along_x(direction)
        or is_split_along_y(direction)
        or is_split_along_z(direction)
    ):
        return touched

    ordered = _sort_siblings(parent)
    try:
        idx = ordered.index(space)
    except ValueError:
        return touched

    if idx > 0:
        prev = ordered[idx - 1]
        _link_sibling_pair(prev, space, direction)
        if id(prev) not in seen:
            seen.add(id(prev))
            touched.append(prev)
    if idx < len(ordered) - 1:
        nxt = ordered[idx + 1]
        _link_sibling_pair(space, nxt, direction)
        if id(nxt) not in seen:
            seen.add(id(nxt))
            touched.append(nxt)
    return touched


def _rebuild_tree_links_for_subtree(anchor: "Space") -> None:
    """自 ``anchor`` 向下 DFS，修正父子链与 ``split_direction``（局部）。"""
    mark_space_dirty(anchor)
    for node in walk_dfs(anchor):
        for child in list(node.children):
            if child.parent is not node:
                child.parent = node
        if node.children:
            inferred = _infer_split_direction(node)
            if (
                node.split_direction == SplitDirection.NONE
                and inferred != SplitDirection.NONE
            ):
                node.split_direction = inferred


@dataclass
class TopologyRebuildReport:
    """``rebuild_all`` / ``on_root_resized`` 汇总。"""

    panels_processed: int = 0
    topology_validation: ValidationResult = field(default_factory=ValidationResult)

    @property
    def topology_valid(self) -> bool:
        return self.topology_validation.is_valid


class SpaceConsistencyManager:
    """
    Topological Space Kernel：adjacency / occupancy / faces / validate 统一编排。

    所有空间变更路径须以 ``rebuild_topology(root)`` 收尾，禁止在业务层零散维护拓扑派生量。
    """

    def __init__(
        self,
        constraint_engine: ConstraintEngine | None = None,
        *,
        face_manager: Any | None = None,
    ) -> None:
        self.constraint_engine = constraint_engine or ConstraintEngine()
        self._face_system: SpaceFaceOccupancyManager = (
            face_manager or get_space_face_occupancy_manager()
        )
        self._faces = self._face_system
        self._resolver = SpaceResolver(self.constraint_engine, self._faces)
        self._last_validation: ValidationResult | None = None

    def rebuild_topology(
        self,
        root_space: "Space",
        *,
        anchor: "Space | None" = None,
    ) -> None:
        """
        统一拓扑重建入口。

        若提供 ``anchor``，仅 ``update_space_topology(anchor)``（增量）；
        否则全量：树链 → 各父节点局部邻接链 → 全树占用/面 → ``validate``。
        """
        if anchor is not None:
            self.update_space_topology(anchor, root_for_validate=root_space)
            return
        self._rebuild_tree_links(root_space)
        self.rebuild_adjacency(root_space)
        self.rebuild_occupancy(root_space)
        self.rebuild_faces(root_space)
        self.validate(root_space)

    def update_space_topology(
        self,
        space: "Space",
        *,
        face: Any | None = None,
        root_for_validate: "Space | None" = None,
    ) -> list["Space"]:
        """
        增量拓扑更新：仅当前 ``space``、其相邻 ``space``、以及 ``face``（若给定）。

        禁止全树 ``*_neighbor`` 清空扫描；邻接经 ``_update_adjacency_for_space``。
        """
        _rebuild_tree_links_for_subtree(space)
        touched = _update_adjacency_for_space(space)
        face_label = ""
        if face is not None:
            from .space_face_occupancy import FaceType as _FT

            ft = face if isinstance(face, _FT) else None
            if ft is None:
                from .space_face_occupancy import _resolve_face_type

                ft = _resolve_face_type(face)
            if ft is not None:
                face_label = f" face={ft.name}"
        _log_topology(
            f"[TOPOLOGY] update_space_topology id={space.id}{face_label} "
            f"touched={len(touched)}"
        )
        update_spaces_occupancy(list(touched))
        root = root_for_validate or resolve_space_root(space)
        if root is not None:
            self.sync_space_derived_state(root, ctx=None)
            self.validate(root)
        return touched

    def rebuild_adjacency(self, root_space: "Space") -> None:
        """
        按各父节点的兄弟链局部重建邻接（禁止先 walk 清空全树 ``*_neighbor``）。

        每个多子父节点仅对有序链首子调用 ``_update_adjacency_for_space``，
        由该子向两侧重连整条兄弟链。
        """
        _log_topology("[TOPOLOGY] rebuild adjacency (parent-local)")
        seen_parents: set[int] = set()
        for parent in walk_dfs(root_space):
            if len(parent.children) < 2:
                continue
            pid = id(parent)
            if pid in seen_parents:
                continue
            seen_parents.add(pid)
            direction = parent.split_direction
            if not (
                is_split_along_x(direction)
                or is_split_along_y(direction)
                or is_split_along_z(direction)
            ):
                continue
            ordered = _sort_siblings(parent)
            if ordered:
                _update_adjacency_for_space(ordered[0])

    def rebuild_occupancy(self, root_space: "Space") -> None:
        """
        统一计算 ``FREE`` / ``OCCUPIED`` / ``LOCKED`` 并写入 metadata（唯一写入点）。

        禁止业务层直接改占用；见 ``space_occupancy.rebuild_tree_occupancy``。
        """
        _log_topology("[TOPOLOGY] rebuild occupancy")
        rebuild_tree_occupancy(root_space)

    def rebuild_faces(
        self,
        root_space: "Space",
        *,
        ctx: dict[str, Any] | None = None,
    ) -> None:
        """占用缓存 + 面注册表 + 可交互绑定全量同步（拓扑重建后统一刷新）。"""
        self.sync_space_derived_state(
            root_space, ctx=ctx, skip_occupancy_rebuild=True
        )

    def clear_face_visuals(
        self,
        root_space: "Space",
        *,
        ctx: dict[str, Any] | None = None,
    ) -> None:
        """
        rebuild 注册前卸旧面可视/拾取态（全树 ``left_face``/``right_face`` + 悬停 ghost）。

        须在 ``rebuild_face_registry`` / ``register_attachable_faces`` 之前调用。
        """
        from .face_registry import clear_face_registry_before_rebuild

        clear_face_registry_before_rebuild(root_space, ctx=ctx)

    def rebuild_face_registry(
        self,
        root_space: "Space",
        *,
        ctx: dict[str, Any] | None = None,
    ) -> None:
        """``clear_face_visuals`` → 全树 ``register_attachable_faces``。"""
        self.clear_face_visuals(root_space, ctx=ctx)
        from .face_registry import _rebuild_face_registry_core

        _rebuild_face_registry_core(root_space, ctx=ctx)

    def sync_space_derived_state(
        self,
        root_space: "Space",
        *,
        ctx: dict[str, Any] | None = None,
        skip_occupancy_rebuild: bool = False,
    ) -> None:
        """
        拓扑重建后统一刷新::

            ``metadata.topology_occupancy`` / ``is_locked``
            → ``_face_occupied`` 全树 LEFT/RIGHT（有板即 occupied）
            → 可交互叶 ``SpaceFace`` 缓存
            → ``face_registry``（``left_face`` / ``right_face``）
            → 拾取 / 悬停可交互语义一致
        """
        from .space_face_occupancy import FaceType
        from .face_registry import is_space_interactable
        from .space_occupancy import (
            rebuild_tree_occupancy,
            repair_occupancy_field_drift,
        )

        if not skip_occupancy_rebuild:
            _log_topology("[TOPOLOGY] rebuild occupancy (sync)")
            rebuild_tree_occupancy(root_space)

        _log_topology("[TOPOLOGY] rebuild faces")
        repaired = repair_occupancy_field_drift(root_space)
        if repaired:
            _log_topology(
                f"[TOPOLOGY] repaired occupancy drift nodes={repaired}"
            )

        self._face_system.rebuild_face_occupied_from_tree(root_space)

        for node in walk_dfs(root_space):
            if not is_space_interactable(node):
                continue
            self._face_system.update_face_occupancy_cache(node, FaceType.LEFT)
            self._face_system.update_face_occupancy_cache(node, FaceType.RIGHT)

        self.rebuild_face_registry(root_space, ctx=ctx)

    @property
    def face_system(self) -> SpaceFaceOccupancyManager:
        return self._face_system

    @property
    def face_topology(self) -> SpaceFaceOccupancyManager:
        """兼容旧名。"""
        return self._face_system

    def validate(
        self,
        root_space: "Space",
        *,
        stop_on_error: bool = False,
    ) -> ValidationResult:
        """
        拓扑内核校验（``TOPOLOGY_CHECKS``）::

        - parent-child consistency（链接、切分方向、子盒在父盒内）
        - invalid size（``check_dimensions``）
        - overlapping children
        - broken topology（邻接对称、重复 id 等）

        结果缓存在 ``last_validation``；存在 ERROR 时写拓扑日志（可 ``ZHIGUI_TOPOLOGY_LOG=0`` 关闭）。
        """
        _log_topology("[TOPOLOGY] validate topology")
        result = validate(
            root_space, stop_on_error=stop_on_error, checks=TOPOLOGY_CHECKS
        )
        self._last_validation = result
        if not result.is_valid:
            _log_topology(
                f"[TOPOLOGY] validate FAILED errors={len(result.errors)} "
                f"warnings={len(result.warnings)}"
            )
            for issue in result.errors[:8]:
                _log_topology(f"  {issue}")
        return result

    @property
    def last_validation(self) -> ValidationResult | None:
        return self._last_validation

    def _rebuild_tree_links(self, root_space: "Space") -> None:
        """邻接重建前：父子双向链接与 ``split_direction`` 推断。"""
        mark_space_dirty(root_space)
        for node in walk_dfs(root_space):
            for child in list(node.children):
                if child.parent is not node:
                    child.parent = node
            if node.children:
                inferred = _infer_split_direction(node)
                if (
                    node.split_direction == SplitDirection.NONE
                    and inferred != SplitDirection.NONE
                ):
                    node.split_direction = inferred

    # ── 根尺寸 / 板件 reflow ─────────────────────────────────────────────

    def rebuild_all(
        self,
        root: "Space",
        boards: list[Any] | None = None,
        *,
        reflow_panels: bool = True,
    ) -> TopologyRebuildReport:
        """板件 reflow（可选）后调用 ``rebuild_topology``。"""
        panels = self._resolve_panels(root, boards)
        if reflow_panels and panels:
            self._reflow_boards(root, panels)
        self.rebuild_topology(root)
        validation = self._last_validation or ValidationResult()
        return TopologyRebuildReport(
            panels_processed=len(panels),
            topology_validation=validation,
        )

    def on_root_resized(self, root: "Space", boards: list[Any]) -> TopologyRebuildReport:
        """根 ``Space`` 尺寸已更新：reflow 板件 → ``rebuild_topology``。"""
        return self.rebuild_all(root, boards, reflow_panels=True)

    def _resolve_panels(
        self, root: "Space", boards: list[Any] | None
    ) -> list[Panel]:
        panels: list[Panel] = [p for p in (boards or []) if isinstance(p, Panel)]
        if not panels:
            panels = _collect_panels_unique(root)
        return panels

    def _reflow_boards(self, root: "Space", boards: list[Panel]) -> None:
        invalid = self._validate_boards(root, boards)
        self._handle_invalid_boards(invalid)

        for board in boards:
            space_map = {s.id: s for s in walk_dfs(root)}
            sid = getattr(board, "space_id", None)
            host = space_map.get(sid or "")
            is_anchor = placement_mode_effective(board) == PlacementMode.ANCHOR_FIXED

            if is_anchor:
                if host is not None:
                    ok = self.constraint_engine.validate(host, board)
                    set_placement_state(board, PLACED if ok else BLOCKED)
                    board.dirty_flag = DirtyFlag.DIRTY
                    mark_space_dirty(host)
                    continue
                best = self._resolver.pick_best_space(root, board)
                if best is not None:
                    _detach_panel_from_tree(root, board)
                    _attach_panel_to_space(best, board)
                    ok = self.constraint_engine.validate(best, board)
                else:
                    ok = False
                set_placement_state(board, PLACED if ok else BLOCKED)
                board.dirty_flag = DirtyFlag.DIRTY
                if best is not None:
                    mark_space_dirty(best)
                continue

            if host is not None and self.constraint_engine.validate(host, board):
                set_placement_state(board, PLACED)
                board.dirty_flag = DirtyFlag.DIRTY
                mark_space_dirty(host)
                continue

            set_placement_state(board, NEEDS_RELAYOUT)
            best = self._resolver.pick_best_space(root, board)
            if best is None:
                set_placement_state(board, UNPLACED)
                _detach_panel_from_tree(root, board)
                board.space_id = None
                continue

            _detach_panel_from_tree(root, board)
            _attach_panel_to_space(best, board)
            set_placement_state(board, PLACED)
            board.dirty_flag = DirtyFlag.DIRTY
            mark_space_dirty(best)

        space_map = {s.id: s for s in walk_dfs(root)}
        apply_mixed_placements(space_map, boards)

    def _validate_boards(self, root: "Space", boards: list[Panel]) -> list[Panel]:
        space_map = {s.id: s for s in walk_dfs(root)}
        invalid: list[Panel] = []
        for board in boards:
            if not self._is_board_still_valid(space_map, board):
                invalid.append(board)
        return invalid

    def _is_board_still_valid(
        self, space_map: dict[str, "Space"], board: Panel
    ) -> bool:
        sid = getattr(board, "space_id", None)
        space = space_map.get(sid or "")
        if space is None:
            return False
        if placement_mode_effective(board) == PlacementMode.ANCHOR_FIXED:
            return True
        if not self.constraint_engine.validate(space, board):
            return False
        return True

    def _handle_invalid_boards(self, invalid_boards: list[Panel]) -> None:
        for board in invalid_boards:
            if placement_mode_effective(board) == PlacementMode.ANCHOR_FIXED:
                set_placement_state(board, BLOCKED)
            else:
                set_placement_state(board, INVALID)


# 兼容旧名
SpaceTopologyRebuildCenter = SpaceConsistencyManager


def collect_panels_from_space_tree(root: "Space") -> list[Panel]:
    return _collect_panels_unique(root)


def rebuild_topology_after_split(
    root: "Space",
    *,
    anchor: "Space | None" = None,
) -> None:
    """``SpaceSplitter`` 切分完成后的便捷入口；``anchor`` 为切分产生子空间之一。"""
    mgr = SpaceConsistencyManager()
    if anchor is not None:
        mgr.update_space_topology(anchor, root_for_validate=root)
    else:
        mgr.rebuild_topology(root)


def rebuild_after_solver(
    *,
    root: "Space | None" = None,
    ctx: dict[str, Any] | None = None,
    manager: SpaceConsistencyManager | None = None,
) -> ValidationResult | None:
    """
    求解完成后强制全量同步：``topology`` + ``occupancy`` + ``face_registry``。

    禁止仅用 ``update_space_topology(node, face=…)`` 收尾（会导致 RIGHT 面占用缓存陈旧）。
    """
    resolved = root
    if resolved is None and ctx is not None:
        proj = ctx.get("project")
        resolved = getattr(proj, "root_space", None) if proj is not None else None
        if resolved is None:
            resolved = ctx.get("root_space")
    if resolved is None:
        return None
    mgr = manager or SpaceConsistencyManager()
    _log_topology("[TOPOLOGY] rebuild")
    mgr._rebuild_tree_links(resolved)
    mgr.rebuild_adjacency(resolved)
    mgr.rebuild_occupancy(resolved)
    mgr.rebuild_faces(resolved, ctx=ctx)
    if ctx is not None:
        from core.cabinet.cabinet_model import sync_cabinet_boards_from_ctx

        sync_cabinet_boards_from_ctx(ctx)
    return mgr.validate(resolved)


def finalize_space_mutation(
    *,
    root: "Space | None" = None,
    node: "Space | None" = None,
    face: Any | None = None,
    ctx: dict[str, Any] | None = None,
    manager: SpaceConsistencyManager | None = None,
    post_solve: bool = False,
) -> ValidationResult | None:
    """
    空间变更统一收尾（split / add panel / remove / undo / redo）。

    ``post_solve=True`` 或求解链调用须走 ``rebuild_after_solver``（全量面注册表）。
    局部几何变更（无求解）可用 ``node`` → ``update_space_topology``。
    """
    if post_solve:
        return rebuild_after_solver(root=root, ctx=ctx, manager=manager)
    resolved = root
    if resolved is None and ctx is not None:
        proj = ctx.get("project")
        resolved = getattr(proj, "root_space", None) if proj is not None else None
        if resolved is None:
            resolved = ctx.get("root_space")
    if resolved is None and node is not None:
        resolved = resolve_space_root(node)
    if resolved is None:
        return None
    mgr = manager or SpaceConsistencyManager()
    if node is not None:
        mgr.update_space_topology(
            node, face=face, root_for_validate=resolved
        )
    else:
        mgr.rebuild_topology(resolved)
    return mgr.last_validation


def split_space_and_rebuild(
    root: "Space",
    space: "Space",
    *,
    axis: str,
    position: float,
    manager: SpaceConsistencyManager | None = None,
) -> Any:
    """
    切分 + ``rebuild_topology`` 一体入口（避免 split 后遗漏拓扑重建）。

    ``axis``: ``"x"`` | ``"y"`` | ``"z"``（相对 ``space`` 局部坐标 mm）。
    """
    from .splitter import SpaceSplitter

    splitter = SpaceSplitter()
    ax = axis.strip().lower()
    if ax in ("x", "vertical"):
        result = splitter.split_vertical(space, position)
    elif ax in ("y", "horizontal"):
        result = splitter.split_horizontal(space, position)
    elif ax in ("z", "depth"):
        result = splitter.split_depth(space, position)
    else:
        raise ValueError(f"split axis must be x|y|z, got {axis!r}")
    mgr = manager or SpaceConsistencyManager()
    mgr.update_space_topology(result.first, root_for_validate=root)
    mgr.update_space_topology(result.second, root_for_validate=root)
    return result


def update_space_topology(
    space: "Space",
    *,
    face: Any | None = None,
    root_for_validate: "Space | None" = None,
    manager: SpaceConsistencyManager | None = None,
) -> list["Space"]:
    """模块级便捷入口 → ``SpaceConsistencyManager.update_space_topology``。"""
    mgr = manager or SpaceConsistencyManager()
    return mgr.update_space_topology(
        space, face=face, root_for_validate=root_for_validate
    )


__all__ = [
    "SpaceConsistencyManager",
    "SpaceTopologyRebuildCenter",
    "TopologyRebuildReport",
    "collect_panels_from_space_tree",
    "finalize_space_mutation",
    "rebuild_after_solver",
    "rebuild_topology_after_split",
    "clear_face_visuals",
    "rebuild_face_registry",
    "sync_space_derived_state",
    "split_space_and_rebuild",
    "update_space_topology",
]
