# instanseg_tasks.py
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Tuple

import numpy as np
import openslide
from PIL import Image, ImageDraw
from skimage.color import rgb2gray
from skimage.filters import threshold_otsu
from skimage.measure import regionprops
from instanseg import InstanSeg

from app.models import JobInternal, JobType
from app.utils.progress import update_job_progress
from app.utils.tiles import compute_tile_grid
from app.utils.storage import get_job_output_dir, save_segmentation_result


# ============================================================
#  GLOBAL INSTANSEG MODEL (shared across jobs)
# ============================================================

_instanseg_model: InstanSeg | None = None
_model_lock = asyncio.Lock()


async def get_instanseg_model() -> InstanSeg:
    """
    Lazily load the InstanSeg model once and reuse it.
    """
    global _instanseg_model
    if _instanseg_model is not None:
        return _instanseg_model

    async with _model_lock:
        if _instanseg_model is None:
            def _init() -> InstanSeg:
                # Matches the tutorial: brightfield nuclei model
                return InstanSeg("brightfield_nuclei", verbosity=0)

            _instanseg_model = await asyncio.to_thread(_init)

    return _instanseg_model


# ============================================================
#  LOW-RES PYRAMID LOADER (perfect alignment)
# ============================================================

def load_lowres_wsi(slide: openslide.OpenSlide):
    """
    Read the lowest-resolution level of the WSI pyramid.

    Returns:
        lowres (PIL.Image RGB)  : lowest-resolution image
        lw, lh (int)            : low-res width / height
        sx, sy (float)          : scale factors (full → lowres)
    """
    level = slide.level_count - 1                  # coarsest level
    lw, lh = slide.level_dimensions[level]

    lowres = slide.read_region((0, 0), level, (lw, lh)).convert("RGB")

    full_w, full_h = slide.dimensions
    sx = lw / full_w
    sy = lh / full_h

    return lowres, lw, lh, sx, sy


# ============================================================
#  TILE-LEVEL INSTANSEG INFERENCE
# ============================================================

async def _segment_tile(
    model: InstanSeg,
    slide: openslide.OpenSlide,
    tile_box: Tuple[int, int, int, int],
    pixel_size_um: float,
    tile_index: int,
) -> List[Dict[str, Any]]:
    """
    Extract one tile from the WSI, run InstanSeg, and return a
    list of cell detections with full-resolution bounding boxes.
    """
    x, y, w, h = tile_box

    def _work() -> List[Dict[str, Any]]:
        # Read tile from the full-res WSI
        region = slide.read_region((x, y), 0, (w, h)).convert("RGB")
        tile_np = np.asarray(region, dtype=np.uint8)

        # Run InstanSeg on the tile
        labeled_output, _ = model.eval_small_image(tile_np, pixel_size_um)

        # Torch tensor → numpy
        if hasattr(labeled_output, "detach"):
            mask = labeled_output.detach().cpu().numpy()
        else:
            mask = np.asarray(labeled_output)

        # Squeeze leading singleton dimensions, e.g. (1,1,H,W) → (H,W)
        while mask.ndim > 2 and mask.shape[0] == 1:
            mask = np.squeeze(mask, axis=0)

        # If we have probability channels (H,W,C) → argmax over C
        if mask.ndim == 3:
            mask = np.argmax(mask, axis=-1)

        # Ensure integer labels for regionprops
        mask = mask.astype("int32")

        cells: List[Dict[str, Any]] = []
        for prop in regionprops(mask):
            minr, minc, maxr, maxc = prop.bbox  # tile-local coords

            cells.append(
                {
                    "bbox": {
                        # convert back to global (full-res) coordinates
                        "x_min": int(x + minc),
                        "y_min": int(y + minr),
                        "x_max": int(x + maxc),
                        "y_max": int(y + maxr),
                    },
                    "area_pixels": float(prop.area),
                    "tile_index": tile_index,
                    "tile_origin": (x, y),
                }
            )

        return cells

    return await asyncio.to_thread(_work)


# ============================================================
#  CELL VISUALIZATION (LOW-RES MASK + OVERLAY)
# ============================================================

def render_cell_visuals(
    slide: openslide.OpenSlide,
    all_cells: List[Dict[str, Any]],
    mask_fs_path: str,
    overlay_fs_path: str,
) -> None:
    """
    Create:
      - mask.png     : low-res binary mask (255 = inside any cell bbox)
      - overlay.png  : low-res WSI with red-tinted cell regions
    Both images have the dimensions of the lowest pyramid level.
    """
    lowres, lw, lh, sx, sy = load_lowres_wsi(slide)

    # --- 1) Low-resolution binary mask ---
    mask_img = Image.new("L", (lw, lh), 0)
    draw_mask = ImageDraw.Draw(mask_img)

    for cell in all_cells:
        bx = cell["bbox"]
        # Map full-res bbox → low-res bbox
        x1 = int(bx["x_min"] * sx)
        y1 = int(bx["y_min"] * sy)
        x2 = int(bx["x_max"] * sx)
        y2 = int(bx["y_max"] * sy)

        draw_mask.rectangle([(x1, y1), (x2, y2)], fill=255)

    mask_img.save(mask_fs_path)

    # --- 2) Low-resolution overlay ---
    overlay = lowres.copy()
    red = Image.new("RGB", (lw, lh), (255, 0, 0))
    # Alpha is scaled from the binary mask (0 or 255 → about 0 or 90)
    alpha = mask_img.point(lambda v: int(v * 0.35))
    overlay.paste(red, mask=alpha)
    overlay.save(overlay_fs_path)


# ============================================================
#  CELL SEGMENTATION JOB
# ============================================================

async def run_cell_segmentation(job: JobInternal) -> None:
    """
    Run InstanSeg over WSI tiles, collect cell bounding boxes,
    and generate low-res mask/overlay PNGs.
    """
    wsi_path = job.params.get("wsi_path")
    if not wsi_path or not os.path.exists(wsi_path):
        raise FileNotFoundError(f"WSI not found: {wsi_path}")

    tile_size = int(job.params.get("tile_size", 512))
    overlap = int(job.params.get("overlap", 32))
    # Tutorial uses 0.5 µm per pixel for brightfield nuclei
    pixel_size_um = float(job.params.get("pixel_size_um", 0.5))

    max_tiles = job.params.get("max_tiles")
    max_tiles = int(max_tiles) if max_tiles else None

    # Open WSI
    slide = openslide.OpenSlide(wsi_path)
    width, height = slide.dimensions

    # Build tile grid
    tiles = compute_tile_grid(width, height, tile_size, overlap)
    if max_tiles:
        tiles = tiles[:max_tiles]

    job.tiles_total = len(tiles)

    # Shared InstanSeg model
    model = await get_instanseg_model()
    all_cells: List[Dict[str, Any]] = []

    # Process each tile
    for idx, tbox in enumerate(tiles):
        cells = await _segment_tile(model, slide, tbox, pixel_size_um, idx)
        all_cells.extend(cells)

        job.tiles_done = idx + 1
        update_job_progress(job)

    slide.close()

    # -----------------------------------------
    # Filesystem paths (where we actually save)
    # -----------------------------------------
    out_dir = get_job_output_dir(job.id)          # outputs/<job_id>/
    mask_fs = out_dir / "mask.png"
    overlay_fs = out_dir / "overlay.png"

    # Public URLs for frontend (served via StaticFiles in main.py)
    mask_url = f"/outputs/{job.id}/mask.png"
    overlay_url = f"/outputs/{job.id}/overlay.png"

    # Render low-res visualizations
    slide2 = openslide.OpenSlide(wsi_path)
    render_cell_visuals(slide2, all_cells, str(mask_fs), str(overlay_fs))
    slide2.close()

    # Save JSON result (only URL paths, not raw binaries)
    save_segmentation_result(
        job,
        {
            "type": "cell_segmentation",
            "wsi_path": wsi_path,
            "pixel_size_um": pixel_size_um,
            "tiles_processed": job.tiles_total,
            "num_cells": len(all_cells),
            "cells": all_cells,
            "mask_png": mask_url,        # ← frontend reads this
            "overlay_png": overlay_url,  # ← frontend reads this
        },
    )


# ============================================================
#  TISSUE MASK JOB (LOW-RES OTSU)
# ============================================================

async def run_tissue_mask(job: JobInternal) -> None:
    """
    Simple tissue mask using a low-res Otsu threshold on grayscale.
    Produces:
      - tissue_mask.png      (low-res binary)
      - tissue_overlay.png   (low-res overlay)
    """
    wsi_path = job.params.get("wsi_path")
    if not wsi_path or not os.path.exists(wsi_path):
        raise FileNotFoundError(f"WSI not found: {wsi_path}")

    slide = openslide.OpenSlide(wsi_path)

    # Use coarsest WSI level for speed + robustness
    lowres, lw, lh, sx, sy = load_lowres_wsi(slide)
    low_np = np.asarray(lowres, dtype=np.uint8)
    gray = rgb2gray(low_np)

    # Global Otsu threshold for tissue vs background
    try:
        th = threshold_otsu(gray)
        tissue = gray < th
    except Exception:
        # Fallback heuristic if Otsu fails
        tissue = gray < 0.85

    # Binary mask 0/255
    binary = (tissue * 255).astype(np.uint8)

    # Filesystem paths
    out_dir = get_job_output_dir(job.id)
    mask_fs = out_dir / "tissue_mask.png"
    overlay_fs = out_dir / "tissue_overlay.png"

    # Public URLs for frontend
    mask_url = f"/outputs/{job.id}/tissue_mask.png"
    overlay_url = f"/outputs/{job.id}/tissue_overlay.png"

    # Save mask
    Image.fromarray(binary).save(str(mask_fs))

    # Save overlay (tissue tinted red)
    overlay = lowres.copy()
    red = Image.new("RGB", (lw, lh), (255, 0, 0))
    alpha = Image.fromarray((tissue * 90).astype(np.uint8))  # ~35% opacity
    overlay.paste(red, mask=alpha)
    overlay.save(str(overlay_fs))

    slide.close()

    # Save JSON metadata
    save_segmentation_result(
        job,
        {
            "type": "tissue_mask",
            "wsi_path": wsi_path,
            "tissue_mask_png": mask_url,        # frontend uses these
            "tissue_overlay_png": overlay_url,
        },
    )


# ============================================================
#  DISPATCHER
# ============================================================

async def run_job_body(job: JobInternal) -> None:
    if job.job_type == JobType.CELL_SEGMENTATION:
        await run_cell_segmentation(job)
    elif job.job_type == JobType.TISSUE_MASK:
        await run_tissue_mask(job)
    else:
        raise ValueError(f"Unknown job type: {job.job_type}")
