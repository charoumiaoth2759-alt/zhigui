# -*- coding: utf-8 -*-
"""兼容 re-export → ``panel_role_spec``（新代码请用 ``PanelRoleSpec``）。"""

from __future__ import annotations

from .panel_role_spec import (
    PanelRoleSpec,
    face_from_payload,
    is_mount_panel_command,
    iter_mount_panel_command_names,
    iter_panel_role_specs,
    resolve_face,
    spec_for_command,
    spec_for_face,
    spec_for_panel,
    spec_for_role,
)

SidePanelSpec = PanelRoleSpec

iter_side_panel_specs = iter_panel_role_specs


__all__ = [
    "PanelRoleSpec",
    "SidePanelSpec",
    "face_from_payload",
    "is_mount_panel_command",
    "iter_mount_panel_command_names",
    "iter_panel_role_specs",
    "iter_side_panel_specs",
    "resolve_face",
    "spec_for_command",
    "spec_for_face",
    "spec_for_panel",
    "spec_for_role",
]
