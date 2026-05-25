# -*- coding: utf-8 -*-
"""
Space Face System — 空间六面统一内核。

**数据结构**::

    ``FaceType`` — 面方位（LEFT / RIGHT / …）
    ``FaceState`` — FREE / OCCUPIED / BLOCKED
    ``SpaceFace`` — 单面记录（space + face_type + state + mounted_elements）

``mounted_elements`` 元素类型（``MountedElementKind``）::

    panel · door · drawer · basket · hardware · light · accessory

**职责**：face ownership、face occupancy、mounted elements、face state、face rebuild。

**挂载铁律**（禁止门/抽屉直接挂 ``Space``）::

    Door   → ``SpaceFace``（默认 ``FaceType.FRONT``）
    Drawer → ``SpaceFace``（默认 ``FaceType.FRONT``，``consume_inner_volume`` 写入元素 ``extra``）

对外 API：``SpaceFaceOccupancyManager``（``get_face`` / ``occupy_face`` / ``release_face`` /
``mount_element`` / ``unmount_element`` / ``rebuild_faces``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Iterator

from .face_occupancy_cache import (
    FaceOccupancyCache,
    FaceOccupancyCacheEntry,
    entry_from_face,
)
from .space_models import Space
from .tree import walk_dfs

_occupancy_manager_singleton: SpaceFaceOccupancyManager | None = None


class SpaceFaceMountError(RuntimeError):
    """门/抽屉必须经 ``SpaceFaceOccupancyManager`` 挂到 ``SpaceFace``，禁止直挂 ``Space``。"""


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class FaceType(Enum):
    """空间外表面方位（与交互层 ``view.interaction.face_type`` 同构）。"""

    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    FRONT = auto()
    BACK = auto()
    INNER = auto()


DEFAULT_DOOR_FACE = FaceType.FRONT
DEFAULT_DRAWER_FACE = FaceType.FRONT

_EXTERNAL_FACE_TYPES: tuple[FaceType, ...] = (
    FaceType.LEFT,
    FaceType.RIGHT,
    FaceType.TOP,
    FaceType.BOTTOM,
    FaceType.FRONT,
    FaceType.BACK,
)


class FaceState(Enum):
    """单面状态。"""

    FREE = auto()
    OCCUPIED = auto()
    BLOCKED = auto()


class FaceOwnerKind(Enum):
    UNASSIGNED = "unassigned"
    PANEL = "panel"
    DOOR = "door"
    DRAWER = "drawer"
    BASKET = "basket"
    HARDWARE = "hardware"
    LIGHT = "light"
    ACCESSORY = "accessory"


class MountedElementKind(Enum):
    """``SpaceFace.mounted_elements`` 支持的挂载类型。"""

    PANEL = "panel"
    DOOR = "door"
    DRAWER = "drawer"
    BASKET = "basket"
    HARDWARE = "hardware"
    LIGHT = "light"
    ACCESSORY = "accessory"


# 须经 SpaceFace 挂载，禁止直挂 Space（panel 走 panel_groups + occupy_face）
FACE_MOUNTED_ELEMENT_KINDS: frozenset[MountedElementKind] = frozenset(
    {
        MountedElementKind.DOOR,
        MountedElementKind.DRAWER,
        MountedElementKind.BASKET,
        MountedElementKind.HARDWARE,
        MountedElementKind.LIGHT,
        MountedElementKind.ACCESSORY,
    }
)

# 存在时通常阻止同面继续叠板
PANEL_BLOCKING_FACE_KINDS: frozenset[MountedElementKind] = frozenset(
    {
        MountedElementKind.DOOR,
        MountedElementKind.DRAWER,
        MountedElementKind.BASKET,
    }
)

# 同一面允许多件
MULTI_MOUNT_PER_FACE_KINDS: frozenset[MountedElementKind] = frozenset(
    {
        MountedElementKind.HARDWARE,
        MountedElementKind.LIGHT,
        MountedElementKind.ACCESSORY,
    }
)


def _owner_kind_for_element(kind: MountedElementKind) -> FaceOwnerKind:
    m = {
        MountedElementKind.PANEL: FaceOwnerKind.PANEL,
        MountedElementKind.DOOR: FaceOwnerKind.DOOR,
        MountedElementKind.DRAWER: FaceOwnerKind.DRAWER,
        MountedElementKind.BASKET: FaceOwnerKind.BASKET,
        MountedElementKind.HARDWARE: FaceOwnerKind.HARDWARE,
        MountedElementKind.LIGHT: FaceOwnerKind.LIGHT,
        MountedElementKind.ACCESSORY: FaceOwnerKind.ACCESSORY,
    }
    return m.get(kind, FaceOwnerKind.UNASSIGNED)


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass
class FaceOwnershipRecord:
    kind: FaceOwnerKind = FaceOwnerKind.UNASSIGNED
    owner_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MountedElement:
    kind: MountedElementKind
    element_id: str
    ref: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceFace:
    """
    空间中某一逻辑面的完整记录。

    ``mounted_elements`` 为 ``MountedElement`` 列表（panel / door / drawer /
    basket / hardware / light / accessory）；板件引用见 ``boards``。
    """

    space: Space
    face_type: FaceType
    state: FaceState = FaceState.FREE
    mounted_elements: list[MountedElement] = field(default_factory=list)
    ownership: FaceOwnershipRecord = field(default_factory=FaceOwnershipRecord)

    @property
    def boards(self) -> list[Any]:
        return [
            m.ref
            for m in self.mounted_elements
            if m.kind is MountedElementKind.PANEL and m.ref is not None
        ]

    def elements_of_kind(self, kind: MountedElementKind) -> list[MountedElement]:
        return [m for m in self.mounted_elements if m.kind is kind]

    def has_kind(self, kind: MountedElementKind) -> bool:
        return any(m.kind is kind for m in self.mounted_elements)

    def has_door(self) -> bool:
        return self.has_kind(MountedElementKind.DOOR)

    def has_drawer(self) -> bool:
        return self.has_kind(MountedElementKind.DRAWER)

    def has_basket(self) -> bool:
        return self.has_kind(MountedElementKind.BASKET)

    def has_face_fixture(self) -> bool:
        """是否存在非板件面挂载（door / drawer / basket / hardware / …）。"""
        return any(m.kind in FACE_MOUNTED_ELEMENT_KINDS for m in self.mounted_elements)

    def has_blocking_fixture(self) -> bool:
        """是否存在阻止继续叠板的面件（door / drawer / basket）。"""
        return any(m.kind in PANEL_BLOCKING_FACE_KINDS for m in self.mounted_elements)

    def is_free(self) -> bool:
        return self.state is FaceState.FREE and len(self.mounted_elements) == 0

    def sync_state(self) -> None:
        if not self.mounted_elements:
            self.state = FaceState.FREE
            if self.ownership.kind is not FaceOwnerKind.UNASSIGNED:
                self.ownership = FaceOwnershipRecord()
            return
        if self._accepts_more_placement():
            self.state = FaceState.OCCUPIED
        else:
            self.state = FaceState.BLOCKED

    def _accepts_more_placement(self) -> bool:
        if self.has_blocking_fixture():
            return False
        from ..panel.panel_face_mapper import SIDE_PANEL_FACE_ROLES, get_panel_role_by_face

        if self.face_type in SIDE_PANEL_FACE_ROLES:
            role = get_panel_role_by_face(self.face_type)
            if _side_face_only_matching_stack(self, role):
                return True
        if any(m.kind in MULTI_MOUNT_PER_FACE_KINDS for m in self.mounted_elements):
            return True
        return False

    def mount(self, element: MountedElement) -> None:
        self.mounted_elements.append(element)
        self.sync_state()

    def unmount_ref(self, ref: Any) -> None:
        self.mounted_elements = [
            m for m in self.mounted_elements if m.ref is not ref
        ]
        self.sync_state()

    def clear(self) -> None:
        self.mounted_elements.clear()
        self.ownership = FaceOwnershipRecord()
        self.state = FaceState.FREE


# 兼容旧名
SpaceFaceSlot = SpaceFace
FaceOccupancy = SpaceFace


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def is_interactable_space(space: Any) -> bool:
    """
    FACE_REGISTRY 可注册交互面的空间。

    核心条件（与 ``face_registry.is_space_interactable`` 一致）::

        not occupied、无 ``children``、未 locked。

    另排除 occupied 窄条 ``zone_role``。
    """
    from .face_registry import is_space_interactable

    if not is_space_interactable(space):
        return False
    from .splitter import METADATA_ZONE_ROLE, _OCCUPIED_ZONE_ROLES

    md = getattr(space, "metadata", None)
    if isinstance(md, dict) and md.get(METADATA_ZONE_ROLE) in _OCCUPIED_ZONE_ROLES:
        return False
    from .space_occupancy import leaf_topology_occupied

    if leaf_topology_occupied(space):
        return False
    return True


def iter_interactable_spaces(root: Space) -> Iterator[Space]:
    """
    FACE_REGISTRY 可注册空间：柜体上 **唯一** active remain 叶。

    禁止对多个历史 remain / occupied 窄条同时注册交互面。
    """
    from .usable_space_resolver import find_active_remain_leaf

    active = find_active_remain_leaf(root)
    if active is not None:
        yield active


def _infer_element_kind(ref: Any) -> MountedElementKind:
    from ..constants.enums import PanelRole

    role = getattr(ref, "role", None)
    if role in (
        PanelRole.DOOR_LEFT,
        PanelRole.DOOR_RIGHT,
        PanelRole.DOOR_DOUBLE,
    ):
        return MountedElementKind.DOOR
    if role in (PanelRole.DRAWER_FRONT, getattr(PanelRole, "DRAWER", None)):
        return MountedElementKind.DRAWER
    rv = getattr(role, "value", None) if role is not None else None
    if rv in ("door_left", "door_right", "door_double", "door"):
        return MountedElementKind.DOOR
    if rv in ("drawer_front", "drawer"):
        return MountedElementKind.DRAWER
    tag = str(getattr(ref, "element_kind", "") or getattr(ref, "kind", "") or "").lower()
    _TAG_MAP = {
        "door": MountedElementKind.DOOR,
        "drawer": MountedElementKind.DRAWER,
        "basket": MountedElementKind.BASKET,
        "hardware": MountedElementKind.HARDWARE,
        "light": MountedElementKind.LIGHT,
        "accessory": MountedElementKind.ACCESSORY,
        "panel": MountedElementKind.PANEL,
    }
    if tag in _TAG_MAP:
        return _TAG_MAP[tag]
    return MountedElementKind.PANEL


def _make_mounted_element(
    ref: Any,
    kind: MountedElementKind | None = None,
    *,
    extra: dict[str, Any] | None = None,
) -> MountedElement:
    k = kind or _infer_element_kind(ref)
    eid = str(getattr(ref, "id", "") or id(ref))
    return MountedElement(kind=k, element_id=eid, ref=ref, extra=dict(extra or {}))


def _assert_face_mount_not_space_direct(
    kind: MountedElementKind,
    *,
    space: Space | None = None,
    face: SpaceFace | None = None,
) -> None:
    """门/抽屉禁止直挂 ``Space``（无 ``SpaceFace``）。"""
    if kind not in FACE_MOUNTED_ELEMENT_KINDS:
        return
    if face is None:
        raise SpaceFaceMountError(
            f"{kind.value} 必须挂到 SpaceFace（例如 FRONT 面），禁止直接挂 Space。"
        )
    if space is not None and face.space is not space:
        raise SpaceFaceMountError("SpaceFace.space 与目标 Space 不一致。")


def _bind_element_face_metadata(
    ref: Any,
    space: Space,
    face_type: FaceType,
    element: MountedElement,
) -> None:
    setattr(ref, "bound_space_id", str(space.id))
    setattr(ref, "bound_space_face", face_type)
    md = getattr(ref, "metadata", None)
    if not isinstance(md, dict):
        md = {}
        setattr(ref, "metadata", md)
    md["space_face"] = face_type.name
    md["mounted_on_face"] = face_type.name
    md["mounted_element_kind"] = element.kind.value
    if element.kind is MountedElementKind.DRAWER and element.extra.get(
        "consume_inner_volume"
    ):
        md["consume_inner_volume"] = True


def _clear_element_face_metadata(ref: Any) -> None:
    _clear_panel_face_metadata(ref)
    for key in ("bound_space_id", "mounted_on_face", "mounted_element_kind", "consume_inner_volume"):
        md = getattr(ref, "metadata", None)
        if isinstance(md, dict):
            md.pop(key, None)
        if hasattr(ref, key):
            try:
                delattr(ref, key)
            except Exception:
                pass


def _is_side_panel(board: Any, role: Any) -> bool:
    r = getattr(board, "role", None)
    if r == role:
        return True
    val = getattr(r, "value", None)
    role_val = getattr(role, "value", role)
    return val == role_val


def _is_left_side_panel(board: Any) -> bool:
    from ..constants.enums import PanelRole

    return _is_side_panel(board, PanelRole.LEFT_SIDE)


def _is_right_side_panel(board: Any) -> bool:
    from ..constants.enums import PanelRole

    return _is_side_panel(board, PanelRole.RIGHT_SIDE)


def _side_face_only_matching_stack(face: SpaceFace, role: Any) -> bool:
    """该面仅堆叠同角色侧板时可继续叠板（LEFT / RIGHT 对称）。"""
    if face.is_free():
        return True
    for b in face.boards:
        if not _is_side_panel(b, role):
            return False
    return True


def _left_face_only_left_side_stack(face: SpaceFace) -> bool:
    from ..constants.enums import PanelRole

    return _side_face_only_matching_stack(face, PanelRole.LEFT_SIDE)


def face_type_for_anchor_panel(panel: Any) -> FaceType | None:
    from ..constants.enums import AnchorType
    from ..panel.anchor_placement import anchor_type_effective

    at = anchor_type_effective(panel)
    m = {
        AnchorType.LEFT: FaceType.LEFT,
        AnchorType.RIGHT: FaceType.RIGHT,
        AnchorType.TOP: FaceType.TOP,
        AnchorType.BOTTOM: FaceType.BOTTOM,
        AnchorType.FRONT: FaceType.FRONT,
        AnchorType.BACK: FaceType.BACK,
    }
    return m.get(at)


def space_face_for_anchor_panel(panel: Any) -> FaceType | None:
    """兼容别名 → ``face_type_for_anchor_panel``。"""
    return face_type_for_anchor_panel(panel)


def _panel_element(panel: Any) -> MountedElement:
    pid = str(getattr(panel, "id", "") or id(panel))
    return MountedElement(
        kind=MountedElementKind.PANEL,
        element_id=pid,
        ref=panel,
    )


def _resolve_face_type(raw: Any) -> FaceType | None:
    if isinstance(raw, FaceType):
        return raw
    if isinstance(raw, Enum) and hasattr(raw, "name"):
        try:
            return FaceType[raw.name]
        except KeyError:
            pass
    if isinstance(raw, str) and raw.strip():
        try:
            return FaceType[raw.strip().upper()]
        except KeyError:
            pass
    return None


class SpaceFaceOccupancy:
    """面占用 **实时查询**（读 ``panel_groups`` / ``panels``，不依赖缓存 metadata）。"""

    @staticmethod
    def _iter_space_panels(space: Space) -> Iterator[Any]:
        for panel in getattr(space, "panels", None) or []:
            yield panel
        for grp in getattr(space, "panel_groups", None) or []:
            for panel in getattr(grp, "panels", None) or []:
                yield panel

    @staticmethod
    def has_left_panel(space: Space) -> bool:
        from ..constants.enums import PanelRole
        from ..panel.panel_face_mapper import normalize_panel_role

        want = PanelRole.LEFT_SIDE
        for panel in SpaceFaceOccupancy._iter_space_panels(space):
            role = getattr(panel, "role", None)
            if role is None:
                continue
            if normalize_panel_role(role) == want:
                return True
        return False

    @staticmethod
    def has_right_panel(space: Space) -> bool:
        from ..constants.enums import PanelRole
        from ..panel.panel_face_mapper import normalize_panel_role

        want = PanelRole.RIGHT_SIDE
        for panel in SpaceFaceOccupancy._iter_space_panels(space):
            role = getattr(panel, "role", None)
            if role is None:
                continue
            if normalize_panel_role(role) == want:
                return True
        return False

    @staticmethod
    def is_face_available(space: Space, face_type: FaceType | Any) -> bool:
        """该面是否仍可挂板 / 交互（实时）。"""
        ft = _resolve_face_type(face_type)
        if ft is None:
            return False

        if getattr(space, "children", None):
            return False

        if float(getattr(space, "width", 0.0) or 0.0) <= 0.0:
            return False

        if bool(getattr(space, "is_locked", False)) or bool(
            getattr(space, "locked", False)
        ):
            return False

        from .splitter import METADATA_ZONE_ROLE, _OCCUPIED_ZONE_ROLES

        md = getattr(space, "metadata", None)
        if isinstance(md, dict) and md.get(METADATA_ZONE_ROLE) in _OCCUPIED_ZONE_ROLES:
            return False

        mgr = get_face_occupancy_manager()
        mgr.refresh_face_occupied(space, ft)
        return not mgr.is_face_occupied(str(space.id), ft)


def _bind_panel_face_metadata(panel: Any, face_type: FaceType) -> None:
    setattr(panel, "bound_space_face", face_type)
    md = getattr(panel, "metadata", None)
    if not isinstance(md, dict):
        md = {}
        setattr(panel, "metadata", md)
    md["space_face"] = face_type.name


def _clear_panel_face_metadata(panel: Any) -> None:
    md = getattr(panel, "metadata", None)
    if isinstance(md, dict):
        md.pop("space_face", None)
    if hasattr(panel, "bound_space_face"):
        try:
            delattr(panel, "bound_space_face")
        except Exception:
            pass


class FaceOwnershipRegistry:
    def __init__(self, manager: SpaceFaceOccupancyManager) -> None:
        self._manager = manager

    def clear(self) -> None:
        for face in self._manager._faces.values():
            face.ownership = FaceOwnershipRecord()

    def set_panel_owner(
        self, space_id: str, face_type: FaceType, panel_id: str | None
    ) -> None:
        self._manager.set_panel_owner(space_id, face_type, panel_id)

    def get(self, space_id: str, face_type: FaceType) -> FaceOwnershipRecord | None:
        rec = self._manager.get_ownership(space_id, face_type)
        if rec.kind is FaceOwnerKind.UNASSIGNED:
            return None
        return rec

    @property
    def records(self) -> dict[tuple[str, FaceType], FaceOwnershipRecord]:
        return self._manager.ownership_records


# ---------------------------------------------------------------------------
# Space Face Occupancy Manager
# ---------------------------------------------------------------------------


class SpaceFaceOccupancyManager:
    """
    空间六面占用管理器 — 门/抽屉/板件均挂 ``SpaceFace``，禁止直挂 ``Space``。
    """

    def __init__(self) -> None:
        self._faces: dict[tuple[str, FaceType], SpaceFace] = {}
        self._space_refs: dict[str, Space] = {}
        self.ownership = FaceOwnershipRegistry(self)
        self._occupancy_cache = FaceOccupancyCache()
        self._face_occupied: dict[tuple[str, FaceType], bool] = {}

    @staticmethod
    def _occupied_key(space_id: str, face_type: FaceType) -> tuple[str, FaceType]:
        return (str(space_id), face_type)

    @property
    def face_occupied(self) -> dict[tuple[str, FaceType], bool]:
        """``(space_id, face_type) → occupied`` 主索引（拾取/悬停查询）。"""
        return self._face_occupied

    def set_face_occupied(
        self,
        space_id: str,
        face_type: FaceType,
        occupied: bool,
    ) -> None:
        self._face_occupied[self._occupied_key(space_id, face_type)] = bool(occupied)

    def clear_face_occupied_for_space(self, space_id: str) -> None:
        sid = str(space_id)
        for key in list(self._face_occupied):
            if key[0] == sid:
                del self._face_occupied[key]

    def refresh_face_occupied(self, space: Space, face_type: FaceType) -> bool:
        """
        自 ``panel_groups`` / ``SpaceFace`` 实时推导并写入 ``_face_occupied``。
        """
        ft = face_type
        sid = str(space.id)
        if ft is FaceType.LEFT:
            occupied = SpaceFaceOccupancy.has_left_panel(space)
        elif ft is FaceType.RIGHT:
            occupied = SpaceFaceOccupancy.has_right_panel(space)
        else:
            face = self.get_face(space, ft, create=False)
            if face is None:
                occupied = False
            else:
                face.sync_state()
                occupied = not face.is_free()
        self.set_face_occupied(sid, ft, occupied)
        return occupied

    def rebuild_face_occupied_from_tree(self, root: Space) -> None:
        """
        拓扑 rebuild 后全树重算 ``_face_occupied``::

            LEFT 有板 → ``(space_id, LEFT)`` occupied
            RIGHT 有板 → ``(space_id, RIGHT)`` occupied
        """
        from .space_occupancy import write_face_occupancy_to_space

        for node in walk_dfs(root):
            self._register_space(node)
            for ft in (FaceType.LEFT, FaceType.RIGHT):
                occupied = self.refresh_face_occupied(node, ft)
                write_face_occupancy_to_space(
                    node,
                    ft,
                    FaceState.OCCUPIED if occupied else FaceState.FREE,
                )

    @property
    def occupancy_cache(self) -> dict[str, dict[FaceType, FaceOccupancyCacheEntry]]:
        """``occupancy_cache[space_id][face]`` 只读视图。"""
        return self._occupancy_cache.occupancy_cache

    @property
    def panel_occupancy(self) -> SpaceFaceOccupancyManager:
        return self

    # --- 公开 API ---

    def get_face(
        self,
        space: Space,
        face_type: FaceType,
        *,
        create: bool = True,
    ) -> SpaceFace | None:
        """获取（或创建）``space`` 上指定 ``face_type`` 的 ``SpaceFace``。"""
        return self.face_record(space, face_type, create=create)

    def mount_element(self, face: SpaceFace, element: MountedElement) -> None:
        """将元素挂到 ``SpaceFace``（低层 API）。"""
        _assert_face_mount_not_space_direct(element.kind, face=face)
        if not self._can_mount_element(face, element):
            raise SpaceFaceMountError(
                f"无法在 {face.face_type.name} 面挂载 {element.kind.value} "
                f"(state={face.state.name})"
            )
        face.mount(element)
        self._apply_ownership_after_mount(face, element)
        self._sync_face_occupancy_cache(face)

    def unmount_element(self, face: SpaceFace, ref: Any) -> None:
        """从 ``SpaceFace`` 卸下元素。"""
        kind = _infer_element_kind(ref)
        face.unmount_ref(ref)
        _clear_element_face_metadata(ref)
        if face.is_free():
            face.ownership = FaceOwnershipRecord()
        elif kind is MountedElementKind.PANEL:
            if face.boards:
                pid = str(getattr(face.boards[-1], "id", "") or "")
                self.set_panel_owner(str(face.space.id), face.face_type, pid)
            else:
                face.ownership = FaceOwnershipRecord()
        self._sync_face_occupancy_cache(face)

    def occupy_face(
        self,
        space: Space,
        face_type: FaceType,
        ref: Any,
        *,
        kind: MountedElementKind | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """
        在 ``space`` 的 ``face_type`` 面上占用/挂载 ``ref``。

        门/抽屉须走本方法（或 ``mount_door`` / ``mount_drawer``），禁止写入 ``Space.panels``。
        """
        face = self.get_face(space, face_type)
        assert face is not None
        element = _make_mounted_element(ref, kind, extra=extra)
        _assert_face_mount_not_space_direct(element.kind, space=space, face=face)
        if not self._can_mount_element(face, element):
            return False
        self.mount_element(face, element)
        if element.kind is MountedElementKind.PANEL:
            _bind_panel_face_metadata(ref, face_type)
        else:
            _bind_element_face_metadata(ref, space, face_type, element)
        self._sync_face_occupancy_cache(face)
        return True

    def release_face(self, space: Space, face_type: FaceType, ref: Any) -> None:
        """释放 ``space`` 某面上的 ``ref``。"""
        face = self.get_face(space, face_type, create=False)
        if face is None:
            return
        self.unmount_element(face, ref)

    def _sync_face_occupancy_cache(self, face: SpaceFace) -> FaceOccupancyCacheEntry:
        """将 ``SpaceFace`` 状态写入缓存、``_face_occupied`` 与 ``space.face_occupancy``。"""
        face.sync_state()
        entry = entry_from_face(face)
        sid = str(face.space.id)
        ft = face.face_type
        self._occupancy_cache.set(sid, ft, entry)
        self.set_face_occupied(sid, ft, bool(entry.occupied))
        from .space_occupancy import write_face_occupancy_to_space

        write_face_occupancy_to_space(face.space, face.face_type, face.state)
        return entry

    def read_face_occupancy_cache(
        self, space_id: str, face_type: FaceType
    ) -> FaceOccupancyCacheEntry | None:
        return self._occupancy_cache.get(str(space_id), face_type)

    def update_face_occupancy_cache(
        self, space: Space, face_type: FaceType
    ) -> FaceOccupancyCacheEntry:
        """
        增量面占用：仅 ``space`` + ``face_type``（不 ``reset``、不扫全树）。

        更新 ``SpaceFace`` 挂载并写入 ``occupancy_cache[space_id][face]``。
        """
        from ..constants.enums import PlacementMode
        from ..panel.anchor_placement import placement_mode_effective
        from ..panel.panel_models import Panel

        self._register_space(space)
        face = self.face_record(space, face_type)
        assert face is not None
        for el in list(face.mounted_elements):
            if el.kind is MountedElementKind.PANEL and el.ref is not None:
                self.unmount_element(face, el.ref)
        for grp in getattr(space, "panel_groups", None) or []:
            for p in getattr(grp, "panels", None) or []:
                if isinstance(p, Panel):
                    self._try_register_anchor_panel_on_face(space, p, face_type)
        for p in getattr(space, "panels", None) or []:
            if isinstance(p, Panel):
                self._try_register_anchor_panel_on_face(space, p, face_type)
        md = getattr(space, "metadata", None)
        if isinstance(md, dict):
            pending = md.get("pending_face_mount")
            if isinstance(pending, dict):
                ft = _resolve_face_type(pending.get("face_type")) or FaceType.FRONT
                if ft is face_type:
                    self._apply_pending_face_mount(space, pending)
        face = self.face_record(space, face_type)
        assert face is not None
        return self._sync_face_occupancy_cache(face)

    def update_space_face(self, space: Space, face_type: FaceType) -> None:
        """兼容别名 → ``update_face_occupancy_cache``。"""
        self.update_face_occupancy_cache(space, face_type)

    def warm_face_occupancy_cache(self, root: Space | Any | None) -> None:
        """
        冷启动 / 全量拓扑：自树注册板件与面件，再按节点刷新六外侧面缓存。

        不 ``reset`` 已有 ``SpaceFace``（避免增量会话中丢失引用）。
        """
        if root is None:
            return
        from .face_registry import is_space_interactable

        self._rebuild_panels_from_tree(root)
        self._rebuild_face_fixtures_from_tree(root)
        for node in walk_dfs(root):
            if not is_space_interactable(node):
                continue
            for ft in _EXTERNAL_FACE_TYPES:
                self.update_face_occupancy_cache(node, ft)

    def rebuild_faces(
        self, root: Space | Any | None, *, full_reset: bool = False
    ) -> None:
        """
        面系统重建。

        默认 ``full_reset=False``：``warm_face_occupancy_cache``（禁止 ``reset`` 全清）。
        ``full_reset=True``：清空 ``_faces`` / 缓存后全量暖机（仅项目加载等路径）。
        """
        if full_reset:
            self.reset()
        if root is None:
            return
        if full_reset:
            from .face_registry import is_space_interactable

            self._rebuild_panels_from_tree(root)
            self._rebuild_face_fixtures_from_tree(root)
            for node in walk_dfs(root):
                if not is_space_interactable(node):
                    continue
                for ft in _EXTERNAL_FACE_TYPES:
                    self.update_face_occupancy_cache(node, ft)
        else:
            self.warm_face_occupancy_cache(root)

    def mount_door(
        self,
        space: Space,
        door: Any,
        *,
        face_type: FaceType = DEFAULT_DOOR_FACE,
    ) -> bool:
        """门板 → ``FRONT``（可改 ``face_type``）面，禁止直挂 ``Space``。"""
        return self.occupy_face(
            space,
            face_type,
            door,
            kind=MountedElementKind.DOOR,
        )

    def mount_drawer(
        self,
        space: Space,
        drawer: Any,
        *,
        face_type: FaceType = DEFAULT_DRAWER_FACE,
        consume_inner_volume: bool = True,
    ) -> bool:
        """
        抽屉 → ``FRONT`` 面；``consume_inner_volume`` 记入元素 ``extra`` / metadata。
        """
        return self.occupy_face(
            space,
            face_type,
            drawer,
            kind=MountedElementKind.DRAWER,
            extra={"consume_inner_volume": consume_inner_volume},
        )

    # --- 内部 / 兼容 ---

    def _register_space(self, space: Space) -> None:
        self._space_refs[str(space.id)] = space

    def face_record(
        self,
        space: Space,
        face_type: FaceType,
        *,
        create: bool = True,
    ) -> SpaceFace | None:
        sid = str(space.id)
        self._register_space(space)
        key = (sid, face_type)
        if key in self._faces:
            self._faces[key].space = space
            return self._faces[key]
        if not create:
            return None
        rec = SpaceFace(
            space=space,
            face_type=face_type,
            state=FaceState.FREE,
            mounted_elements=[],
        )
        self._faces[key] = rec
        return rec

    def face_by_id(
        self, space_id: str, face_type: FaceType, *, create: bool = True
    ) -> SpaceFace | None:
        sid = str(space_id)
        space = self._space_refs.get(sid)
        if space is None:
            if not create:
                return None
            space = Space(id=sid)
            self._register_space(space)
        return self.face_record(space, face_type, create=create)

    def slot(self, space_id: str, face_type: FaceType) -> SpaceFace:
        rec = self.face_by_id(space_id, face_type, create=True)
        assert rec is not None
        return rec

    def _slot(self, space_id: str, face_type: FaceType) -> SpaceFace:
        return self.slot(space_id, face_type)

    def get_ownership(self, space_id: str, face_type: FaceType) -> FaceOwnershipRecord:
        return self.slot(space_id, face_type).ownership

    def set_ownership(
        self,
        space_id: str,
        face_type: FaceType,
        *,
        kind: FaceOwnerKind,
        owner_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.slot(space_id, face_type).ownership = FaceOwnershipRecord(
            kind=kind,
            owner_id=owner_id,
            extra=dict(extra or {}),
        )

    def set_panel_owner(
        self, space_id: str, face_type: FaceType, panel_id: str | None
    ) -> None:
        self.set_ownership(
            space_id,
            face_type,
            kind=FaceOwnerKind.PANEL,
            owner_id=panel_id,
        )

    @property
    def ownership_records(self) -> dict[tuple[str, FaceType], FaceOwnershipRecord]:
        return {(k[0], k[1]): f.ownership for k, f in self._faces.items()}

    def _can_mount_element(self, face: SpaceFace, element: MountedElement) -> bool:
        if element.kind is MountedElementKind.PANEL:
            from ..panel.panel_face_mapper import get_panel_role_by_face

            board = element.ref
            if face.state is FaceState.BLOCKED:
                return False
            _side_roles = (
                *(
                    (ft, get_panel_role_by_face(ft), fn)
                    for ft, fn in (
                        (FaceType.LEFT, _is_left_side_panel),
                        (FaceType.RIGHT, _is_right_side_panel),
                    )
                ),
            )
            for ft, role, is_role_panel in _side_roles:
                if face.face_type is ft and is_role_panel(board):
                    return face.is_free() or _side_face_only_matching_stack(
                        face, role
                    )
            if face.has_blocking_fixture():
                return False
            return face.is_free()
        if element.kind in PANEL_BLOCKING_FACE_KINDS:
            if face.face_type is not FaceType.FRONT:
                return False
            return not face.has_kind(element.kind)
        if element.kind in MULTI_MOUNT_PER_FACE_KINDS:
            return True
        return False

    def _apply_ownership_after_mount(
        self, face: SpaceFace, element: MountedElement
    ) -> None:
        sid = str(face.space.id)
        if element.kind is MountedElementKind.PANEL:
            self.set_panel_owner(sid, face.face_type, element.element_id)
        else:
            self.set_ownership(
                sid,
                face.face_type,
                kind=_owner_kind_for_element(element.kind),
                owner_id=element.element_id,
                extra=dict(element.extra),
            )

    def can_place(self, space_id: str, face_type: FaceType, board: Any) -> bool:
        space = self._space_refs.get(str(space_id))
        if space is None:
            space = Space(id=str(space_id))
            self._register_space(space)
        face = self.get_face(space, face_type)
        assert face is not None
        return self._can_mount_element(face, _make_mounted_element(board))

    def occupy(self, space_id: str, face_type: FaceType, board: Any) -> bool:
        space = self._space_refs.get(str(space_id))
        if space is None:
            space = Space(id=str(space_id))
            self._register_space(space)
        return self.occupy_face(space, face_type, board)

    def release(self, space_id: str, face_type: FaceType, board: Any) -> None:
        space = self._space_refs.get(str(space_id))
        if space is None:
            return
        self.release_face(space, face_type, board)

    def release_for_panel(self, board: Any) -> None:
        sid = getattr(board, "space_id", None) or getattr(board, "bound_space_id", None)
        if not sid:
            return
        space = self._space_refs.get(str(sid))
        if space is None:
            space = Space(id=str(sid))
        ft = _resolve_face_type(getattr(board, "bound_space_face", None))
        if ft is None:
            md = getattr(board, "metadata", None)
            if isinstance(md, dict) and md.get("space_face"):
                ft = _resolve_face_type(md["space_face"])
        if ft is None:
            ft = face_type_for_anchor_panel(board)
        if ft is not None:
            self.release_face(space, ft, board)

    def is_face_occupied(self, space_id: str, face_type: FaceType) -> bool:
        key = self._occupied_key(space_id, face_type)
        if key in self._face_occupied:
            return self._face_occupied[key]
        space = self._space_refs.get(str(space_id))
        if space is not None:
            return self.refresh_face_occupied(space, face_type)
        cached = self._occupancy_cache.get(str(space_id), face_type)
        if cached is not None:
            return bool(cached.occupied)
        return False

    def is_face_blocked(self, space_id: str, face_type: FaceType) -> bool:
        return self.slot(space_id, face_type).state is FaceState.BLOCKED

    def force_occupy(self, space_id: str, face_type: FaceType, board: Any) -> None:
        space = self._space_refs.get(str(space_id))
        if space is None:
            space = Space(id=str(space_id))
            self._register_space(space)
        face = self.get_face(space, face_type)
        assert face is not None
        face.clear()
        self.mount_element(face, _panel_element(board))
        _bind_panel_face_metadata(board, face_type)

    def mounted_on_face(
        self, space_id: str, face_type: FaceType
    ) -> list[MountedElement]:
        return list(self.slot(space_id, face_type).mounted_elements)

    def mounted_panels(self, space_id: str, face_type: FaceType) -> list[Any]:
        return list(self.slot(space_id, face_type).boards)

    def iter_faces(self) -> list[SpaceFace]:
        return list(self._faces.values())

    def reset(self) -> None:
        self._faces.clear()
        self._space_refs.clear()
        self._occupancy_cache.clear()
        self._face_occupied.clear()

    def rebuild_from_root(self, root: Space | Any | None) -> None:
        """兼容别名 → ``rebuild_faces``。"""
        self.rebuild_faces(root)

    def _rebuild_panels_from_tree(self, root: Any) -> None:
        from ..constants.enums import PlacementMode
        from ..panel.anchor_placement import placement_mode_effective
        from ..panel.panel_models import Panel

        for node in walk_dfs(root):
            self._register_space(node)
            for grp in getattr(node, "panel_groups", None) or []:
                for p in getattr(grp, "panels", None) or []:
                    if isinstance(p, Panel):
                        self._try_register_anchor_panel(node, p)
            for p in getattr(node, "panels", None) or []:
                if isinstance(p, Panel):
                    self._try_register_anchor_panel(node, p)

    def _try_register_anchor_panel(self, space: Space, panel: Any) -> None:
        ft = face_type_for_anchor_panel(panel)
        if ft is None:
            return
        self._try_register_anchor_panel_on_face(space, panel, ft)

    def _try_register_anchor_panel_on_face(
        self, space: Space, panel: Any, face_type: FaceType
    ) -> None:
        from ..constants.enums import PlacementMode
        from ..panel.anchor_placement import placement_mode_effective

        if placement_mode_effective(panel) != PlacementMode.ANCHOR_FIXED:
            return
        ft = face_type_for_anchor_panel(panel)
        if ft is None or ft is not face_type:
            return
        sf = self.face_record(space, face_type)
        assert sf is not None
        self.occupy_face(space, face_type, panel)

    def _apply_pending_face_mount(self, space: Space, pending: dict[str, Any]) -> None:
        kind_s = str(pending.get("kind", "")).lower()
        ref = pending.get("ref")
        if ref is None:
            return
        ft = _resolve_face_type(pending.get("face_type")) or FaceType.FRONT
        extra = pending.get("extra") if isinstance(pending.get("extra"), dict) else {}
        tag_map = {
            "door": MountedElementKind.DOOR,
            "drawer": MountedElementKind.DRAWER,
            "basket": MountedElementKind.BASKET,
            "hardware": MountedElementKind.HARDWARE,
            "light": MountedElementKind.LIGHT,
            "accessory": MountedElementKind.ACCESSORY,
        }
        mk = tag_map.get(kind_s)
        if mk is None:
            return
        if mk is MountedElementKind.DRAWER:
            extra = dict(extra)
            extra.setdefault("consume_inner_volume", True)
        self.occupy_face(space, ft, ref, kind=mk, extra=extra or None)

    def _rebuild_face_fixtures_from_tree(self, root: Any) -> None:
        """
        从 ``Space.metadata['pending_face_mount']`` 挂回非板件面元素。

        ``kind``: door | drawer | basket | hardware | light | accessory
        """
        for node in walk_dfs(root):
            md = getattr(node, "metadata", None)
            if not isinstance(md, dict):
                continue
            pending = md.get("pending_face_mount")
            if isinstance(pending, dict):
                self._apply_pending_face_mount(node, pending)


SpaceFaceSystem = SpaceFaceOccupancyManager
FaceOccupancyManager = SpaceFaceOccupancyManager
SpaceFaceTopology = SpaceFaceOccupancyManager


def get_space_face_occupancy_manager() -> SpaceFaceOccupancyManager:
    global _occupancy_manager_singleton
    if _occupancy_manager_singleton is None:
        _occupancy_manager_singleton = SpaceFaceOccupancyManager()
    return _occupancy_manager_singleton


def get_space_face_system() -> SpaceFaceOccupancyManager:
    return get_space_face_occupancy_manager()


def get_face_occupancy_manager() -> SpaceFaceOccupancyManager:
    return get_space_face_occupancy_manager()


def reset_face_occupancy_manager() -> None:
    global _occupancy_manager_singleton
    _occupancy_manager_singleton = None


def reset_space_face_system() -> None:
    reset_face_occupancy_manager()


def get_space_face_topology(
    panel_occupancy: SpaceFaceOccupancyManager | None = None,
) -> SpaceFaceOccupancyManager:
    if panel_occupancy is not None:
        return panel_occupancy
    return get_space_face_occupancy_manager()


__all__ = [
    "DEFAULT_DOOR_FACE",
    "DEFAULT_DRAWER_FACE",
    "FACE_MOUNTED_ELEMENT_KINDS",
    "MULTI_MOUNT_PER_FACE_KINDS",
    "PANEL_BLOCKING_FACE_KINDS",
    "FaceOccupancy",
    "FaceOccupancyManager",
    "FaceOwnerKind",
    "FaceOwnershipRecord",
    "FaceOwnershipRegistry",
    "FaceState",
    "FaceType",
    "MountedElement",
    "MountedElementKind",
    "SpaceFace",
    "SpaceFaceMountError",
    "SpaceFaceOccupancy",
    "SpaceFaceOccupancyManager",
    "SpaceFaceSlot",
    "SpaceFaceSystem",
    "SpaceFaceTopology",
    "face_type_for_anchor_panel",
    "get_face_occupancy_manager",
    "get_space_face_occupancy_manager",
    "get_space_face_system",
    "get_space_face_topology",
    "is_interactable_space",
    "iter_interactable_spaces",
    "read_face_occupancy_cache",
    "rebuild_face_occupied_from_tree",
    "reset_face_occupancy_manager",
    "reset_space_face_system",
    "space_face_for_anchor_panel",
    "update_face_occupancy_cache",
    "warm_face_occupancy_cache",
]
