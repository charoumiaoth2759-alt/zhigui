# -*- coding: utf-8 -*-
"""
柜体领域模型：``Cabinet.boards`` 为全树真实 ``Panel`` 的扁平权威列表。

板件挂载在 ``Space.panel_groups`` 上；``boards`` 由 ``sync_cabinet_boards`` 从空间树
收集写入，禁止与树内板件长期不一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..panel.panel_models import Panel
    from ..space.space_models import Space


@dataclass
class Cabinet:
    """
    柜体设计根对象（可与 ``project`` / 命令 ``ctx`` 宿主共用）。

    ``boards`` 变更须经 ``register_board`` / ``unregister_board``，或全树重建
    ``sync_cabinet_boards``；禁止外部 ``boards.append`` / ``boards.remove``。
    """

    name: str = ""
    cabinet_width: float = 2400.0
    cabinet_height: float = 2200.0
    cabinet_depth: float = 600.0
    root_space: "Space | None" = None
    boards: list["Panel"] = field(default_factory=list)

    def register_board(self, panel: "Panel") -> None:
        if panel in self.boards:
            return
        self.boards.append(panel)

    def unregister_board(self, panel: "Panel") -> None:
        if panel not in self.boards:
            return
        self.boards.remove(panel)

    def _replace_boards_from_tree(self, panels: list["Panel"]) -> None:
        """全量替换（仅 ``sync_cabinet_boards`` 内部使用）。"""
        self.boards = list(panels)


def collect_boards_from_space_tree(root: "Space | None") -> list["Panel"]:
    """从 ``root_space`` 子树收集全部真实 ``Panel``（``id`` 去重，DFS 顺序）。"""
    if root is None:
        return []
    from ..space.space_consistency_manager import collect_panels_from_space_tree

    return list(collect_panels_from_space_tree(root))


def sync_cabinet_boards(
    cabinet: Any,
    *,
    root: "Space | None" = None,
) -> list["Panel"]:
    """
    将 ``cabinet.boards`` 设为 ``root`` 子树上的全部板件（替换列表，非增量 patch）。

    ``cabinet`` 可为 ``Cabinet``、``project``（``CommandDispatcher`` 上下文）等；
    无 ``boards`` 属性时会创建空列表再写入。
    """
    if cabinet is None:
        return []
    if root is None:
        root = getattr(cabinet, "root_space", None)
    boards = collect_boards_from_space_tree(root)
    if isinstance(cabinet, Cabinet):
        cabinet._replace_boards_from_tree(boards)
    else:
        setattr(cabinet, "boards", boards)
    return boards


def register_board(cabinet: Any, panel: "Panel") -> None:
    """登记板件；``Cabinet`` 走实例方法，其它宿主须为 ``Cabinet`` 子类或自行对齐。"""
    if cabinet is None:
        return
    if isinstance(cabinet, Cabinet):
        cabinet.register_board(panel)
        return
    reg = getattr(cabinet, "register_board", None)
    if callable(reg):
        reg(panel)
        return
    raise TypeError(
        "register_board requires core.cabinet.Cabinet (or register_board method); "
        "do not use boards.append"
    )


def unregister_board(cabinet: Any, panel: "Panel") -> None:
    """移除板件登记；禁止对 ``boards`` 直接 ``remove``。"""
    if cabinet is None:
        return
    if isinstance(cabinet, Cabinet):
        cabinet.unregister_board(panel)
        return
    unreg = getattr(cabinet, "unregister_board", None)
    if callable(unreg):
        unreg(panel)
        return
    raise TypeError(
        "unregister_board requires core.cabinet.Cabinet (or unregister_board method); "
        "do not use boards.remove"
    )


def sync_cabinet_boards_from_ctx(ctx: dict[str, Any] | None) -> list["Panel"]:
    """从命令上下文 ``project`` / ``root_space`` 同步 ``boards``。"""
    if not ctx:
        return []
    proj = ctx.get("project")
    root = ctx.get("root_space")
    if root is None and proj is not None:
        root = getattr(proj, "root_space", None)
    if proj is not None:
        return sync_cabinet_boards(proj, root=root)
    if root is not None:
        return sync_cabinet_boards(ctx, root=root)
    return []


__all__ = [
    "Cabinet",
    "collect_boards_from_space_tree",
    "register_board",
    "unregister_board",
    "sync_cabinet_boards",
    "sync_cabinet_boards_from_ctx",
]
