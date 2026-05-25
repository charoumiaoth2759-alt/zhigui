# -*- coding: utf-8 -*-
"""
空间六面注册表：``rebuild_face_registry`` 仅在可交互空间绑定 ``left_face`` / ``right_face``。

可交互（``is_space_interactable``）::

    not topology_occupied（实时 ``panel_groups`` 推导）
    not space.children
    not space.locked / ``is_locked``

绑定（禁止裸 ``register FaceType.LEFT``）::

    FaceType.LEFT  → ``space.left_face``（仅 ``is_face_registerable`` 为真时创建）
    FaceType.RIGHT → ``space.right_face``

占用面在 **registry 阶段不创建**（非 hover 拦截）。
"""

from __future__ import annotations

from typing import Any, Iterator

from core.space.space_face_occupancy import (
    FaceType,
    SpaceFace,
    get_face_occupancy_manager,
    iter_interactable_spaces,
)
from core.space.space_models import Space
from core.space.splitter import METADATA_ZONE_ROLE, _OCCUPIED_ZONE_ROLES
from core.space.tree import walk_dfs
from core.space.usable_space_resolver import find_active_remain_leaf


def _log_registry(message: str) -> None:
    from core.cabinet_pipeline_log import log_face_registry

    log_face_registry(message)


def _space_log_id(space: Space) -> str:
    return str(getattr(space, "id", None) or "?")


def is_space_interactable(space: Any) -> bool:
    """
    FACE_REGISTRY 可注册空间（不单判 ``is_leaf``）::

        occupied / 有子节点 / locked → 不可交互。
    """
    if not isinstance(space, Space):
        return False
    from .space_occupancy import leaf_topology_occupied

    if leaf_topology_occupied(space):
        return False
    if space.children:
        return False
    if bool(getattr(space, "locked", False)) or bool(
        getattr(space, "is_locked", False)
    ):
        return False
    return True


def is_interactable_leaf(space: Any) -> bool:
    """兼容别名 → ``is_space_interactable``。"""
    return is_space_interactable(space)


def is_attachable_leaf(space: Any) -> bool:
    """兼容别名 → ``is_interactable_leaf``。"""
    return is_interactable_leaf(space)


def is_face_registerable(space: Any, face_type: FaceType) -> bool:
    """
    该面是否允许写入 FaceRegistry（``rebuild`` 时创建 ``SpaceFace`` / 绑定槽位）::

        空间可交互 且 ``_face_occupied[(space_id, face)]`` 为 False。
    """
    if not isinstance(space, Space):
        return False
    if not is_space_interactable(space):
        return False
    mgr = get_face_occupancy_manager()
    return not mgr.is_face_occupied(str(space.id), face_type)


def iter_attachable_leaves(root: Space) -> Iterator[Space]:
    """兼容别名 → ``iter_interactable_spaces``（仅 active remain 叶）。"""
    return iter_interactable_spaces(root)


def _is_occupied_leaf(space: Space) -> bool:
    """叶节点是否为 occupied 窄条（``topology_occupancy`` 或 zone_role）。"""
    if not space.is_leaf:
        return False
    from .space_occupancy import leaf_topology_occupied

    if leaf_topology_occupied(space):
        return True
    md = getattr(space, "metadata", None)
    if isinstance(md, dict) and md.get(METADATA_ZONE_ROLE) in _OCCUPIED_ZONE_ROLES:
        return True
    return False


def _clear_face_registration(space: Space) -> None:
    from .space_occupancy import clear_face_occupancy_on_space

    space.clear_side_face_slots()
    mgr = get_face_occupancy_manager()
    clear_face_occupancy_on_space(space)
    mgr._occupancy_cache.clear_space(str(space.id))
    mgr.clear_face_occupied_for_space(str(space.id))


def clear_face_registry_before_rebuild(
    root: Space,
    *,
    ctx: dict[str, Any] | None = None,
) -> None:
    """
    拓扑 rebuild 注册 **之前**：卸全树旧面绑定/占用缓存与 UI 悬停瞬态。

    本仓库无 ``face_visual_map`` / ``pickables``；等价物为::

        ``Space.left_face`` / ``right_face`` + ``face_occupancy`` 缓存
        + ``PreviewManager.hit`` / ``current_hover_result``
        + ParamSpace ``SceneManager._visuals`` 悬停高亮
    """
    _log_registry("clear old face visuals")
    for node in walk_dfs(root):
        _clear_face_registration(node)
    _clear_face_hover_visuals(ctx)
    _invalidate_transient_hover_after_registry_rebuild(ctx)


def clear_face_visuals(
    root: Any | None,
    *,
    ctx: dict[str, Any] | None = None,
) -> None:
    """模块级别名 → ``clear_face_registry_before_rebuild``（拓扑 rebuild 前调用）。"""
    if root is None or not isinstance(root, Space):
        return
    clear_face_registry_before_rebuild(root, ctx=ctx)


def _clear_face_hover_visuals(ctx: dict[str, Any] | None) -> None:
    """卸 GL 空间盒悬停高亮（等价 ``hover_face = None`` 的可视部分）。"""
    if not ctx:
        return
    canvas = ctx.get("canvas")
    if canvas is None:
        return
    try:
        from ui.cabinet_design_host import resolve_cabinet_interaction_manager

        mgr = resolve_cabinet_interaction_manager(canvas)
        if mgr is not None:
            mgr.current_hover_result = None
    except Exception:
        pass
    try:
        mw = getattr(canvas, "window", lambda: None)()
        if mw is None:
            return
        from ui.cabinet_space.param_space_gl_view import ParamSpaceGLView

        for pv in mw.findChildren(ParamSpaceGLView):
            scene = getattr(pv, "_scene", None)
            if scene is not None and hasattr(scene, "clear_face_hover_visuals"):
                scene.clear_face_hover_visuals()
    except Exception:
        pass


def _bind_side_face_slot(space: Space, face: SpaceFace) -> None:
    if face.face_type is FaceType.LEFT:
        space.left_face = face
    elif face.face_type is FaceType.RIGHT:
        space.right_face = face


def register_attachable_faces(space: Any) -> bool:
    """
    在可交互叶上按面绑定侧板槽位；**occupied 面不创建**（LEFT/RIGHT 独立判断）。
    """
    if not is_space_interactable(space):
        return False
    if _is_occupied_leaf(space):
        return False

    mgr = get_face_occupancy_manager()
    space.clear_side_face_slots()
    bound = False
    for ft in (FaceType.LEFT, FaceType.RIGHT):
        if not is_face_registerable(space, ft):
            _log_registry(
                f"skip register {ft.name} (occupied) id={_space_log_id(space)}"
            )
            continue
        mgr.update_face_occupancy_cache(space, ft)
        sf = mgr.get_face(space, ft, create=False)
        if sf is None:
            _log_registry(
                f"skip register {ft.name} (no SpaceFace) id={_space_log_id(space)}"
            )
            continue
        _bind_side_face_slot(space, sf)
        _log_registry(
            f"bind {ft.name.lower()}_face id={_space_log_id(space)} face={ft}"
        )
        bound = True
    return bound


def register_attachable_face(space: Any, face_type: FaceType) -> bool:
    """单面增量绑定（``left_face`` 或 ``right_face``）；occupied 面不创建。"""
    if face_type not in (FaceType.LEFT, FaceType.RIGHT):
        return False
    if not is_face_registerable(space, face_type):
        return False

    mgr = get_face_occupancy_manager()
    mgr.update_face_occupancy_cache(space, face_type)
    sf = mgr.get_face(space, face_type, create=False)
    if sf is None:
        return False
    _bind_side_face_slot(space, sf)
    return True


def _invalidate_transient_hover_after_registry_rebuild(
    ctx: dict[str, Any] | None,
) -> None:
    """
    rebuild 会重建 ``SpaceFace`` 实例；清除 UI 悬停瞬态，避免旧引用失效后 fallback 到默认 LEFT。

    **不**触及 ``FaceSelectionSnapshot`` / 已入栈命令（命令只认 ``face_type_name``）。
    """
    if not ctx:
        return
    try:
        from commands.cabinet_event_bridge import clear_cabinet_hover_preview

        clear_cabinet_hover_preview(ctx)
    except Exception:
        pass


def _rebuild_face_registry_core(
    root: Space,
    *,
    ctx: dict[str, Any] | None = None,
) -> None:
    """
    注册可交互面（调用方须已 ``clear_face_visuals`` / ``clear_face_registry_before_rebuild``）。
    """
    _log_registry("rebuild")
    active = find_active_remain_leaf(root)

    registered = 0
    for node in walk_dfs(root):
        if not is_space_interactable(node):
            if node.children:
                _log_registry(f"skip non-interactable (children) id={_space_log_id(node)}")
            elif _is_occupied_leaf(node):
                _log_registry(f"skip non-interactable (occupied) id={_space_log_id(node)}")
            elif bool(getattr(node, "locked", False)) or bool(
                getattr(node, "is_locked", False)
            ):
                _log_registry(f"skip non-interactable (locked) id={_space_log_id(node)}")
            else:
                _log_registry(f"skip non-interactable id={_space_log_id(node)}")
            continue
        if _is_occupied_leaf(node):
            _log_registry(f"skip occupied zone id={_space_log_id(node)}")
            continue
        _log_registry(f"register interactable id={_space_log_id(node)}")
        if register_attachable_faces(node):
            registered += 1

    if registered == 0:
        _log_registry("interactable registered=0")
    elif active is not None and is_space_interactable(active):
        _log_registry(
            f"interactable registered={registered} id={_space_log_id(active)} "
            f"left_face={active.left_face is not None} "
            f"right_face={active.right_face is not None}"
        )
    else:
        _log_registry(f"interactable registered={registered}")

    _invalidate_transient_hover_after_registry_rebuild(ctx)


def rebuild_face_registry(
    root: Any | None,
    *,
    ctx: dict[str, Any] | None = None,
) -> None:
    """
    FaceRegistry.rebuild（模块级）：先 ``clear_face_visuals`` 再注册。

    拓扑主路径请用 ``SpaceConsistencyManager.rebuild_face_registry``（``self.clear_face_visuals()``）。
    """
    if root is None or not isinstance(root, Space):
        return
    clear_face_registry_before_rebuild(root, ctx=ctx)
    _rebuild_face_registry_core(root, ctx=ctx)


def register_side_faces_for_space(space: Any) -> None:
    """兼容别名 → ``register_attachable_faces``。"""
    register_attachable_faces(space)


__all__ = [
    "clear_face_registry_before_rebuild",
    "clear_face_visuals",
    "is_attachable_leaf",
    "is_face_registerable",
    "is_interactable_leaf",
    "is_space_interactable",
    "iter_attachable_leaves",
    "iter_interactable_spaces",
    "rebuild_face_registry",
    "register_attachable_face",
    "register_attachable_faces",
    "register_side_faces_for_space",
]
