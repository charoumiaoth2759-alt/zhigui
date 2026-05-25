# -*- coding: utf-8 -*-
"""空间盒 hover 高亮判定策略（纯逻辑，无 UI 依赖）。"""

from __future__ import annotations


def should_highlight_space_node(
    current_space_id: str | None,
    hover_hit_space_id: str | None,
    preview_active: bool,
) -> bool:
    """仅当当前节点就是命中节点时高亮。

    ``preview_active`` 保留在签名中，便于调用方统一传参与后续扩展；
    当前策略下它**不会**放大全局高亮范围。
    """
    _ = preview_active
    cur = str(current_space_id or "").strip()
    hit = str(hover_hit_space_id or "").strip()
    if not cur or not hit:
        return False
    return cur == hit


__all__ = ["should_highlight_space_node"]
