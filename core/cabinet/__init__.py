# -*- coding: utf-8 -*-
"""柜体设计相关动作（与 ``core.space`` 空间数据/分割算法配合）。"""

from .cabinet_model import (
    Cabinet,
    collect_boards_from_space_tree,
    register_board,
    unregister_board,
    sync_cabinet_boards,
    sync_cabinet_boards_from_ctx,
)

__all__ = [
    "Cabinet",
    "collect_boards_from_space_tree",
    "register_board",
    "unregister_board",
    "sync_cabinet_boards",
    "sync_cabinet_boards_from_ctx",
]
