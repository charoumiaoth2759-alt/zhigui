from enum import Enum


class SpaceType(Enum):

    ROOT = "root"

    NORMAL = "normal"

    DRAWER = "drawer"

    HANGING = "hanging"

    SHELF = "shelf"

    DOOR = "door"


class SplitDirection(Enum):

    NONE = "none"

    VERTICAL = "vertical"

    HORIZONTAL = "horizontal"