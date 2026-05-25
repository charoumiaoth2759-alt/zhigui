# arch_check.py
# 架构解耦自动验收工具（UI / commands / core / solver）

import os
import re
from pathlib import Path

ROOT = Path(".")

RULES = [
    # ❌ UI 不允许直接写 core / solver
    (r"ui/.*\.py", r"import\s+.*core", "UI 层禁止直接 import core"),
    (r"ui/.*\.py", r"import\s+.*solver", "UI 层禁止直接 import solver"),

    # ❌ solver 不允许碰 UI
    (r"solver/.*\.py", r"import\s+.*view", "Solver 禁止 import view"),
    (r"solver/.*\.py", r"Qt", "Solver 禁止依赖 Qt"),

    # ❌ core 纯净
    (r"core/.*\.py", r"Qt", "Core 层禁止 Qt"),
    (r"core/.*\.py", r"signal|emit", "Core 层禁止 Qt signal"),

    # ❌ commands 不能直接操作 UI
    (r"commands/.*\.py", r"import\s+.*view", "Commands 禁止 import view"),

    # ❌ UI 不能直接创建 Space（强规则）
    (r"ui/.*\.py", r"Space\(", "UI 层禁止直接创建 Space"),
    # ❌ UI 不能直接写 project.root_space（须经 CommandDispatcher）
    (r"ui/.*\.py", r'setattr\s*\(\s*[^,]+,\s*["\']root_space["\']', "UI 禁止 setattr(project, \"root_space\", ...)"),
    (r"ui/.*\.py", r"\.root_space\s*=", "UI 禁止对 .root_space 直接赋值"),

    # ❌ 禁止用 children 下标 / child0|child1 推断左右与 active leaf
    (
        r"(?!arch_check\.py$).+\.py",
        r"children\s*\[\s*0\s*\]|children\s*\[\s*1\s*\]",
        "禁止 children 下标推断方向，须用 left_space/right_space",
    ),
    (
        r"(?!arch_check\.py$).+\.py",
        r"\bchild0\b|\bchild1\b",
        "禁止 child0/child1，须用 left_space/right_space",
    ),
    # ❌ 点击/execute 禁止用 selection 可变态或「最新叶」替代 hover 冻结 id
    (
        r"commands/cabinet/.*\.py",
        r"get_latest_leaf|last_interactable|find_active_remain_leaf|resolve_panel_operating_space",
        "AddBoard 命令禁止 get_latest_leaf / last_interactable / active remain 重定向",
    ),
    (
        r"commands/cabinet/.*\.py",
        r"\.current_space\b|\.active_space\b|getattr\s*\(\s*[^,]+,\s*[\"']current_space[\"']|getattr\s*\(\s*[^,]+,\s*[\"']active_space[\"']",
        "AddBoard 命令禁止读取 selection.current_space / active_space",
    ),
    (
        r"ui/interaction/.*\.py",
        r"get_latest_leaf|last_interactable|find_active_remain_leaf|resolve_panel_operating_space",
        "交互确认禁止重定向到最新 remain 叶",
    ),
    (
        r"ui/interaction/.*\.py",
        r"getattr\s*\(\s*[^,]+,\s*[\"']current_space[\"']|getattr\s*\(\s*[^,]+,\s*[\"']active_space[\"']",
        "交互确认禁止读取 selection current_space / active_space",
    ),
]

VIOLATIONS = []


def scan_file(path, pattern, msg):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except:
        return

    if re.search(pattern, text):
        VIOLATIONS.append(f"[FAIL] {path} → {msg}")


def main():
    print("[arch_check] Architecture Check Start...\n")

    for file in ROOT.rglob("*.py"):
        rel = str(file.as_posix())

        for file_rule, pattern, msg in RULES:
            if re.match(file_rule, rel):
                scan_file(file, pattern, msg)

    if not VIOLATIONS:
        print("[arch_check] PASS: no violations")
        return

    print("[arch_check] FAIL: violations found\n")
    for v in VIOLATIONS:
        print(v)

    print("[arch_check] fix violations before continuing.\n")


if __name__ == "__main__":
    main()