# app/utils/tiles.py
from __future__ import annotations

from typing import List, Tuple


def compute_tile_grid(width: int, height: int, tile_size: int, overlap: int = 0) -> List[Tuple[int, int, int, int]]:
    """
    Return a list of tiles defined as (x, y, w, h).
    This is a simple grid; in a real version we'd align with actual WSI dims.
    """
    tiles = []
    y = 0
    while y < height:
        x = 0
        h = min(tile_size, height - y)
        while x < width:
            w = min(tile_size, width - x)
            tiles.append((x, y, w, h))
            x += tile_size - overlap
        y += tile_size - overlap
    return tiles
