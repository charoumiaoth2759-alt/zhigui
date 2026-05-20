from .models import Space
from .enums import SplitDirection


# ==========================================================
# 垂直分割（左右）
# ==========================================================

def split_vertical(
    space: Space,
    widths: list[float]
) -> list[Space]:

    children = []

    current_x = space.x

    for i, width in enumerate(widths):

        child = Space(
            name=f"Vertical_{i + 1}",

            x=current_x,
            y=space.y,
            z=space.z,

            width=width,
            height=space.height,
            depth=space.depth,
        )

        current_x += width

        space.add_child(child)

        children.append(child)

    space.split_direction = SplitDirection.VERTICAL

    return children


# ==========================================================
# 水平分割（上下）
# ==========================================================

def split_horizontal(
    space: Space,
    heights: list[float]
) -> list[Space]:

    children = []

    current_z = space.z

    for i, height in enumerate(heights):

        child = Space(
            name=f"Horizontal_{i + 1}",

            x=space.x,
            y=space.y,
            z=current_z,

            width=space.width,
            height=height,
            depth=space.depth,
        )

        current_z += height

        space.add_child(child)

        children.append(child)

    space.split_direction = SplitDirection.HORIZONTAL

    return children


# ==========================================================
# 比例分割
# ==========================================================

def split_by_ratio(
    space: Space,
    ratios: list[float]
) -> list[Space]:

    total = sum(ratios)

    widths = [
        space.width * r / total
        for r in ratios
    ]

    return split_vertical(space, widths)