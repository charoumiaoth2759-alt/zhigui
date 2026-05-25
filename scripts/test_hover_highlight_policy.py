# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.space.hover_highlight_policy import should_highlight_space_node


def main() -> None:
    hit_space_id = "space-hit"
    assert should_highlight_space_node(hit_space_id, hit_space_id, False)
    assert should_highlight_space_node(hit_space_id, hit_space_id, True)
    assert not should_highlight_space_node("space-other", hit_space_id, True)
    assert not should_highlight_space_node("space-any", None, True)
    print("PASS: hover color scoped to hit space only")


if __name__ == "__main__":
    main()
