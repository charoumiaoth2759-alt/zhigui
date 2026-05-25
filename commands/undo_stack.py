# -*- coding: utf-8 -*-
"""通用撤销 / 重做栈：``UndoStack.push`` / ``undo_last`` / ``redo_last``。"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Deque, Optional

_UNDO_LOG = os.environ.get("ZHIGUI_UNDO_LOG", "1").strip() not in (
    "0",
    "false",
    "False",
    "no",
    "NO",
)


def _undo_log(tag: str) -> None:
    if _UNDO_LOG:
        print(tag, flush=True)


class UndoableCommand(ABC):
    """可入撤销栈的命令：由 ``UndoStack.push`` 调用 ``execute``，由 ``undo_last`` 调用 ``undo``。"""

    @abstractmethod
    def execute(self) -> bool:
        """执行本命令对应的模型修改；成功且应可撤销时返回 True。"""

    @abstractmethod
    def undo(self) -> None:
        """撤销 ``execute`` 已提交的变更。"""


class UndoStack:
    """后进先出撤销栈 + 重做栈；``maxlen`` 限制撤销深度（重做栈同限）。"""

    def __init__(self, maxlen: Optional[int] = None) -> None:
        self._undo: Deque[UndoableCommand] = (
            deque(maxlen=maxlen) if maxlen is not None else deque()
        )
        self._redo: Deque[UndoableCommand] = (
            deque(maxlen=maxlen) if maxlen is not None else deque()
        )

    def push(self, command: UndoableCommand) -> bool:
        """先 ``execute()``；成功则入撤销栈并清空重做栈。"""
        _undo_log("[UNDO] push")
        _undo_log("[UNDO] execute")
        if not command.execute():
            return False
        self._undo.append(command)
        self._redo.clear()
        return True

    def undo_last(self) -> bool:
        """撤销最近一次 ``push``；命令移入重做栈。"""
        if not self._undo:
            return False
        command = self._undo.pop()
        _undo_log("[UNDO] undo")
        command.undo()
        self._redo.append(command)
        return True

    def redo_last(self) -> bool:
        """重做最近一次撤销；再次 ``execute`` 成功后回到撤销栈。"""
        if not self._redo:
            return False
        command = self._redo.pop()
        _undo_log("[REDO] execute")
        if not command.execute():
            self._redo.append(command)
            return False
        self._undo.append(command)
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def __len__(self) -> int:
        return len(self._undo)

    def redo_depth(self) -> int:
        return len(self._redo)


__all__ = ["UndoableCommand", "UndoStack"]
