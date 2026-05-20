from .models import Space


# ==========================================================
# 内部净尺寸
# ==========================================================

def get_inner_width(
    space: Space,
    left_thickness: float,
    right_thickness: float
) -> float:

    return (
        space.width
        - left_thickness
        - right_thickness
    )


def get_inner_height(
    space: Space,
    top_thickness: float,
    bottom_thickness: float
) -> float:

    return (
        space.height
        - top_thickness
        - bottom_thickness
    )


def get_inner_depth(
    space: Space,
    back_thickness: float
) -> float:

    return (
        space.depth
        - back_thickness
    )


# ==========================================================
# 剩余空间
# ==========================================================

def get_remaining_width(
    space: Space
) -> float:

    used = sum(
        child.width
        for child in space.children
    )

    return space.width - used


def get_remaining_height(
    space: Space
) -> float:

    used = sum(
        child.height
        for child in space.children
    )

    return space.height - used