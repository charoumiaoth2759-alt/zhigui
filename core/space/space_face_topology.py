# -*- coding: utf-8 -*-
"""已并入 ``space_face_occupancy.SpaceFaceOccupancyManager``；本模块仅 re-export。"""

from __future__ import annotations

from .space_face_occupancy import (
    DEFAULT_DOOR_FACE,
    DEFAULT_DRAWER_FACE,
    FaceOwnerKind,
    FaceOwnershipRecord,
    FaceOwnershipRegistry,
    FaceState,
    FaceType,
    SpaceFace,
    SpaceFaceMountError,
    SpaceFaceOccupancyManager,
    SpaceFaceSystem,
    SpaceFaceTopology,
    get_space_face_occupancy_manager,
    get_space_face_system,
    get_space_face_topology,
)

__all__ = [
    "DEFAULT_DOOR_FACE",
    "DEFAULT_DRAWER_FACE",
    "FaceOwnerKind",
    "FaceOwnershipRecord",
    "FaceOwnershipRegistry",
    "FaceState",
    "FaceType",
    "SpaceFace",
    "SpaceFaceMountError",
    "SpaceFaceOccupancyManager",
    "SpaceFaceSystem",
    "SpaceFaceTopology",
    "get_space_face_occupancy_manager",
    "get_space_face_system",
    "get_space_face_topology",
]
