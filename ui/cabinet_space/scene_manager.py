# -*- coding: utf-8 -*-
"""管理所有 `SpaceVisual` 与 GL 视图项的挂载/卸载（逻辑空间盒 + 该 Space 下板件）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.debug_flags import DEBUG_VIEW3D
from core.space.space_models import Space
from core.space.tree import iter_subtree, walk_dfs

from .space_visual import SpaceVisual, is_pyqtgraph_gl_available

if TYPE_CHECKING:
    pass


def _collect_panel_groups_from_tree(root: Space) -> list:
    """遍历整棵树，收集各节点 ``panel_groups``（保持大致 DFS 顺序）。"""
    out: list = []
    for node in walk_dfs(root):
        for g in getattr(node, "panel_groups", None) or []:
            out.append(g)
    return out


def collect_panel_groups_from_tree(root: Space | None) -> list:
    """供 UI 增量刷新：与 ``_collect_panel_groups_from_tree`` 相同，``root`` 为 ``None`` 时返回空列表。"""
    if root is None:
        return []
    return _collect_panel_groups_from_tree(root)


def count_panels_in_groups(panel_groups) -> int:
    """统计 ``panel_groups`` 内板件数量（与 ``panel_visuals`` 键数应对齐）。"""
    n = 0
    for group in panel_groups or []:
        for panel in getattr(group, "panels", None) or []:
            if panel is not None:
                n += 1
    return n


def iter_panels_in_groups(panel_groups):
    """按 ``panel_groups`` 顺序产出 ``(panel_id, panel)``。"""
    for group in panel_groups or []:
        for panel in getattr(group, "panels", None) or []:
            if panel is None:
                continue
            pid = str(getattr(panel, "id", "") or "")
            if pid:
                yield pid, panel


class SceneManager:
    """管理 `SpaceVisual` 集合；不持有 `Space` 业务逻辑。"""

    def __init__(self, gl_view):
        self._gl_view = gl_view
        self._visuals: dict[str, SpaceVisual] = {}
        # panel_id → (mesh, edges)；与真实板件 1:1，禁止重复 append
        self._panel_visuals: dict[str, tuple[object, object | None]] = {}

    @property
    def panel_visuals(self) -> dict[str, tuple[object, object | None]]:
        return self._panel_visuals

    @property
    def panel_items(self) -> list[tuple[object, object | None]]:
        """兼容：按 ``panel_groups`` 遍历顺序的 mesh 列表。"""
        return list(self._panel_visuals.values())

    def panel_visual_count(self) -> int:
        return len(self._panel_visuals)

    def _sync_gl_mesh_item_list(self) -> None:
        """``panel_visual`` 通过 ``_rebuild_panel_mesh_items`` 跟踪 GL 项，与 dict 对齐。"""
        meshes = [t[0] for t in self._panel_visuals.values() if t[0] is not None]
        self._gl_view._rebuild_panel_mesh_items = meshes

    def _detach_panel_visual(self, pid: str, item: tuple[object, object | None]) -> None:
        mesh, edges = item
        if mesh is not None:
            try:
                self._gl_view.removeItem(mesh)
            except Exception:
                pass
        if edges is not None:
            try:
                self._gl_view.removeItem(edges)
            except Exception:
                pass
        self._panel_visuals.pop(pid, None)
        mesh_ids = dict(getattr(self._gl_view, "_panel_mesh_ids", None) or {})
        mesh_ids.pop(pid, None)
        self._gl_view._panel_mesh_ids = mesh_ids

    def _clear_solver_panel_items(self) -> None:
        for pid in list(self._panel_visuals.keys()):
            item = self._panel_visuals.get(pid)
            if item is not None:
                self._detach_panel_visual(pid, item)
        self._panel_visuals.clear()
        prev = getattr(self._gl_view, "_rebuild_panel_mesh_items", None) or []
        for item in list(prev):
            try:
                self._gl_view.removeItem(item)
            except Exception:
                pass
        self._gl_view._rebuild_panel_mesh_items = []
        self._gl_view._panel_mesh_ids = {}

    def _assert_panel_visual_invariant(self, panel_groups, *, context: str) -> None:
        real = count_panels_in_groups(panel_groups)
        visual = len(self._panel_visuals)
        if real != visual:
            raise RuntimeError(
                f"[SceneManager] panel visual leak ({context}): "
                f"visuals={visual} real_panels={real}"
            )
        ids_in_groups = {pid for pid, _ in iter_panels_in_groups(panel_groups)}
        if ids_in_groups != set(self._panel_visuals.keys()):
            raise RuntimeError(
                f"[SceneManager] panel id mismatch ({context}): "
                f"groups={sorted(ids_in_groups)} visuals={sorted(self._panel_visuals.keys())}"
            )

    def rebuild_panels(self, panel_groups) -> None:
        """
        将 ``panel_groups`` 中的板件画入当前 GL 视图。

        先清空全部 ``panel_visuals``，再按组顺序挂载；保证
        ``len(panel_visuals) == len(real_panels)``。
        """
        if not is_pyqtgraph_gl_available():
            return
        self._clear_solver_panel_items()
        groups = list(panel_groups or [])
        from .panel_visual import rebuild_panels as _rebuild_panels_gl

        built = _rebuild_panels_gl(self._gl_view, groups)
        # rebuild_panels 已写入 _rebuild_panel_mesh_items；按板件 id 建立 dict
        idx = 0
        for pid, panel in iter_panels_in_groups(groups):
            if idx >= len(built):
                break
            if pid in self._panel_visuals:
                continue
            self._panel_visuals[pid] = built[idx]
            idx += 1
        self._sync_gl_mesh_item_list()
        if DEBUG_VIEW3D:
            print(
                "[ParamSpaceGL] rebuild panels visuals=",
                len(self._panel_visuals),
                "real=",
                count_panels_in_groups(groups),
            )
        self._assert_panel_visual_invariant(groups, context="rebuild_panels")

    def append_panel(self, panel: object) -> bool:
        """增量挂载单块板件 GL；已存在同 ``id`` 时禁止重复 append。"""
        if not is_pyqtgraph_gl_available():
            return False
        pid = str(getattr(panel, "id", "") or "")
        if not pid or pid in self._panel_visuals:
            return False
        from .panel_visual import append_panel_mesh

        item = append_panel_mesh(self._gl_view, panel, panel_id=pid)
        if item is None:
            return False
        self._panel_visuals[pid] = item
        self._sync_gl_mesh_item_list()
        if DEBUG_VIEW3D:
            print("[ParamSpaceGL] append panel visual id=", pid)
        return True

    def remove_panel_by_id(self, panel_id: str) -> bool:
        """增量卸下一块板件 GL（``AddBoardCommand.undo`` 等）。"""
        pid = str(panel_id or "")
        if not pid:
            return False
        item = self._panel_visuals.pop(pid, None)
        if item is None:
            return False
        mesh, edges = item
        if mesh is not None:
            try:
                self._gl_view.removeItem(mesh)
            except Exception:
                pass
        if edges is not None:
            try:
                self._gl_view.removeItem(edges)
            except Exception:
                pass
        self._sync_gl_mesh_item_list()
        if DEBUG_VIEW3D:
            print("[ParamSpaceGL] remove panel visual id=", pid)
        return True

    def rebuild_spaces(self, spaces) -> None:
        """
        用当前 ``Space`` 列表重绑逻辑空间盒（仅 ``SpaceVisual``，不清理 ``rebuild_panels`` 挂载项）。

        ``spaces`` 可为 ``Space`` 可迭代序列（通常与 ``SolveResult.spaces`` 一致）。
        """
        if not is_pyqtgraph_gl_available():
            return
        for vis in list(self._visuals.values()):
            vis.detach(self._gl_view)
        self._visuals.clear()
        for s in spaces or []:
            if s is None:
                continue
            self.add_space(s)

    def add_space(self, space: Space) -> SpaceVisual | None:
        if not is_pyqtgraph_gl_available():
            return None
        self.clear()
        if space is None:
            return None
        first: SpaceVisual | None = None
        for node in walk_dfs(space):
            vis = SpaceVisual(node)
            vis.attach(self._gl_view)
            self._visuals[node.id] = vis
            if first is None:
                first = vis
        self.rebuild_panels(_collect_panel_groups_from_tree(space))
        return first

    def clear_face_hover_visuals(self) -> None:
        """
        rebuild 前卸悬停高亮（本视图无 ``face_visual_map`` / ``pickables``）。

        等价于清空 ``hover_face`` 的可视反馈；拾取会话由 ``clear_cabinet_hover_preview`` 清理。
        """
        if not is_pyqtgraph_gl_available():
            return
        for vis in self._visuals.values():
            vis.set_hover_highlight(False)

    def refresh_space_box_styles(self, *, hovered_space_ids: set[str] | None = None) -> None:
        """按 metadata / 悬停刷新所有已挂载空间盒颜色（不重画板件）。"""
        if not is_pyqtgraph_gl_available():
            return
        hs = hovered_space_ids or set()
        for sid, vis in self._visuals.items():
            vis.set_hover_highlight(sid in hs)
            vis.refresh_box_style(self._gl_view)

    def refresh_spaces_incremental(
        self,
        anchor: Space,
        *,
        hovered_space_ids: set[str] | None = None,
    ) -> None:
        """仅刷新 ``anchor`` 及其子空间盒（加板增量路径；不 ``rebuild_panels`` / 不 ``clear``）。"""
        if not is_pyqtgraph_gl_available():
            return
        hs = hovered_space_ids or set()
        for node in iter_subtree(anchor, include_self=True):
            vis = self._visuals.get(str(node.id))
            if vis is None:
                continue
            vis.set_hover_highlight(str(node.id) in hs)
            vis.refresh_box_style(self._gl_view)

    def sync_space_tree_visuals(
        self,
        root: Space,
        *,
        hovered_space_ids: set[str] | None = None,
    ) -> None:
        """
        与 ``Space`` 树对齐：补挂新子空间盒、移除已脱离树的 stale 项、刷新样式。

        侧板切分后 ``root.children`` 新增 occupied / usable 子空间时须走本路径。
        """
        if not is_pyqtgraph_gl_available() or root is None:
            return
        valid_ids = {str(n.id) for n in walk_dfs(root)}
        for sid in list(self._visuals.keys()):
            if sid in valid_ids:
                continue
            vis = self._visuals.pop(sid, None)
            if vis is not None:
                vis.detach(self._gl_view)
        for node in walk_dfs(root):
            sid = str(node.id)
            if sid not in self._visuals:
                vis = SpaceVisual(node)
                vis.attach(self._gl_view)
                self._visuals[sid] = vis
        self.refresh_spaces_incremental(root, hovered_space_ids=hovered_space_ids)

    def remove_space(self, space: Space) -> None:
        vis = self._visuals.pop(space.id, None)
        if vis is not None:
            vis.detach(self._gl_view)

    def clear(self) -> None:
        self._clear_solver_panel_items()
        for vis in list(self._visuals.values()):
            vis.detach(self._gl_view)
        self._visuals.clear()
