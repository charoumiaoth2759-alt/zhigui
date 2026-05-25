# -*- coding: utf-8 -*-
"""``SpaceSplitter`` 入口别名（实现见 ``splitter``）。"""

from .splitter import *  # noqa: F403

__all__ = [name for name in globals() if not name.startswith("_")]
