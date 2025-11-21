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

Image.MAX_IMAGE_PIXELS = None
# ============================================================
#   GLOBAL INSTANSEG MODEL
# ============================================================

_instanseg_model: InstanSeg | None = None
_model_lock = asyncio.Lock()

async def get_instanseg_model() -> InstanSeg:
    global _instanseg_model
    if _instanseg_model is not None:
        return _instanseg_model

    async with _model_lock:
        if _instanseg_model is None:
            def _init():
                # Recommended MPP (0.5) from tutorial
                return InstanSeg(
                    "brightfield_nuclei",
                    verbosity=0
                )
            _instanseg_model = await asyncio.to_thread(_init)

    return _instanseg_model


# ============================================================
#   LOW-RES WSI PYRAMID LOADER (perfect alignment)
# ============================================================

def load_lowres_wsi(slide: openslide.OpenSlide):
    level = slide.level_count - 1
    lw, lh = slide.level_dimensions[level]

    lowres = slide.read_region((0, 0), level, (lw, lh)).convert("RGB")

    full_w, full_h = slide.dimensions
    sx = lw / full_w
    sy = lh / full_h

    return lowres, lw, lh, sx, sy


# ============================================================
#   TILE-LEVEL INSTANSEG INFERENCE
# ============================================================

async def _segment_tile(
    model: InstanSeg,
    slide: openslide.OpenSlide,
    tile_box: Tuple[int, int, int, int],
    pixel_size_um: float,
    tile_index: int,
) -> List[Dict[str, Any]]:
    
    x, y, w, h = tile_box

    def _work():
        region = slide.read_region((x, y), 0, (w, h)).convert("RGB")
        tile_np = np.asarray(region, dtype=np.uint8)

        # Run InstanSeg
        labeled_output, _ = model.eval_small_image(tile_np, pixel_size_um)

        # tensor → numpy
        mask = labeled_output.detach().cpu().numpy() if hasattr(labeled_output, "detach") \
            else np.asarray(labeled_output)

        # Squeeze shape
        while mask.ndim > 2 and mask.shape[0] == 1:
            mask = np.squeeze(mask, axis=0)

        if mask.ndim == 3:
            mask = np.argmax(mask, axis=-1)

        mask = mask.astype("int32")

        cells = []
        for prop in regionprops(mask):
            minr, minc, maxr, maxc = prop.bbox

            # real coordinates
            cells.append({
                "bbox": {
                    "x_min": int(x + minc),
                    "y_min": int(y + minr),
                    "x_max": int(x + maxc),
                    "y_max": int(y + maxr),
                },
                "area_pixels": float(prop.area),
                "tile_index": tile_index,
                "tile_origin": (x, y),
            })

        return cells

    return await asyncio.to_thread(_work)


# ============================================================
#   CELL OVERLAY (aligned)
# ============================================================

# def render_cell_overlay(slide, all_cells, out_mask_path, out_overlay_path):
#     full_w, full_h = slide.dimensions

#     # ---- full resolution mask ----
#     mask_full = Image.new("L", (full_w, full_h), 0)
#     draw_full = ImageDraw.Draw(mask_full)

#     for c in all_cells:
#         bx = c["bbox"]
#         draw_full.rectangle(
#             (bx["x_min"], bx["y_min"], bx["x_max"], bx["y_max"]),
#             fill=255
#         )

#     mask_full.save(out_mask_path)

#     # ---- lowres overlay ----
#     lowres, lw, lh, sx, sy = load_lowres_wsi(slide)
#     base = lowres.convert("RGBA")

#     red_layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
#     red_draw = ImageDraw.Draw(red_layer)

#     for c in all_cells:
#         bx = c["bbox"]
#         x1 = int(bx["x_min"] * sx)
#         y1 = int(bx["y_min"] * sy)
#         x2 = int(bx["x_max"] * sx)
#         y2 = int(bx["y_max"] * sy)

#         red_draw.rectangle(
#             [(x1, y1), (x2, y2)],
#             outline=(255, 0, 0, 255),
#             fill=(255, 0, 0, 80),
#             width=1,
#         )

#     combined = Image.alpha_composite(base, red_layer).convert("RGB")
#     combined.save(out_overlay_path)
def render_cell_overlay(slide, all_cells, out_mask_path, out_overlay_path):
    lowres, lw, lh, sx, sy = load_lowres_wsi(slide)

    # -------- LOW-RES MASK --------
    mask = Image.new("L", (lw, lh), 0)
    draw = ImageDraw.Draw(mask)

    for c in all_cells:
        bx = c["bbox"]
        x1 = int(bx["x_min"] * sx)
        y1 = int(bx["y_min"] * sy)
        x2 = int(bx["x_max"] * sx)
        y2 = int(bx["y_max"] * sy)

        draw.rectangle([(x1, y1), (x2, y2)], fill=255)

    mask.save(out_mask_path)



# ============================================================
#   CELL SEGMENTATION JOB
# ============================================================

async def run_cell_segmentation(job: JobInternal) -> None:
    await asyncio.sleep(15)
    wsi_path = job.params["wsi_path"]
    if not os.path.exists(wsi_path):
        raise FileNotFoundError(wsi_path)

    tile_size = int(job.params.get("tile_size", 512))
    overlap = int(job.params.get("overlap", 32))
    pixel_size_um = float(job.params.get("pixel_size_um", 0.5))  # tutorial default
    max_tiles = job.params.get("max_tiles")
    max_tiles = int(max_tiles) if max_tiles else None

    # Open WSI
    slide = openslide.OpenSlide(wsi_path)
    width, height = slide.dimensions

    # Build tiles
    tiles = compute_tile_grid(width, height, tile_size, overlap)
    if max_tiles:
        tiles = tiles[:max_tiles]

    job.tiles_total = len(tiles)

    # Load shared InstanSeg model
    model = await get_instanseg_model()
    all_cells = []

    # Process tiles
    for idx, tbox in enumerate(tiles):
        cells = await _segment_tile(model, slide, tbox, pixel_size_um, idx)
        all_cells.extend(cells)

        job.tiles_done = idx + 1
        update_job_progress(job)

    slide.close()

    # ----------------------------------------------------
    # Correct paths (filesystem vs. public URLs)
    # ----------------------------------------------------
    out_dir = get_job_output_dir(job.id)  # outputs/<job_id>  (FS PATH)
    mask_fs = out_dir / "mask.png"        # FS path
    overlay_fs = out_dir / "overlay.png"  # FS path

    # Public URLs the browser can access
    mask_url = f"/outputs/{job.id}/mask.png"
    overlay_url = f"/outputs/{job.id}/overlay.png"

    # ----------------------------------------------------
    # Render overlays
    # ----------------------------------------------------
    slide2 = openslide.OpenSlide(wsi_path)
    render_cell_overlay(slide2, all_cells, str(mask_fs), str(overlay_fs))
    slide2.close()

    # ----------------------------------------------------
    # Save result JSON with URL paths (public paths only)
    # ----------------------------------------------------
    save_segmentation_result(job, {
    "mask_png": mask_url,
    "overlay_png": overlay_url,
    "type": "cell_segmentation",
    "wsi_path": wsi_path,
    "pixel_size_um": pixel_size_um,
    "tiles_processed": job.tiles_total,
    "num_cells": len(all_cells),
    "cells": all_cells,
    })




# ============================================================
#   TISSUE MASK JOB
# ============================================================

async def run_tissue_mask(job: JobInternal) -> None:
    await asyncio.sleep(15)
    wsi_path = job.params["wsi_path"]
    if not os.path.exists(wsi_path):
        raise FileNotFoundError(wsi_path)

    # Open whole-slide image
    slide = openslide.OpenSlide(wsi_path)

    # ---------------------------------------------------------
    # Low-resolution WSI for tissue mask (fast + high quality)
    # ---------------------------------------------------------
    lowres, lw, lh, sx, sy = load_lowres_wsi(slide)

    low_np = np.asarray(lowres, dtype=np.uint8)
    gray = rgb2gray(low_np)

    # Global Otsu threshold
    try:
        th = threshold_otsu(gray)
        tissue = gray < th
    except Exception:
        tissue = gray < 0.85     # fallback threshold

    binary = (tissue * 255).astype(np.uint8)

    # ---------------------------------------------------------
    # Output paths
    # ---------------------------------------------------------
    out_dir = get_job_output_dir(job.id)
    
    # filesystem paths (real paths)
    mask_fs = out_dir / "tissue_mask.png"
    overlay_fs = out_dir / "tissue_overlay.png"

    # public URLs (frontend will use these)
    mask_url = f"/outputs/{job.id}/tissue_mask.png"
    overlay_url = f"/outputs/{job.id}/tissue_overlay.png"

    # ---------------------------------------------------------
    # Save binary mask
    # ---------------------------------------------------------
    Image.fromarray(binary).save(str(mask_fs))

    # ---------------------------------------------------------
    # Save overlay (tissue tinted red)
    # ---------------------------------------------------------
    overlay = lowres.copy()
    red = Image.new("RGB", (lw, lh), (255, 0, 0))
    alpha = Image.fromarray((tissue * 90).astype(np.uint8))  # opacity 90/255

    overlay.paste(red, mask=alpha)
    overlay.save(str(overlay_fs))

    slide.close()

    # ---------------------------------------------------------
    # Save result JSON
    # ---------------------------------------------------------
    save_segmentation_result(job, {
        "type": "tissue_mask",
        "tissue_mask_png": mask_url,        # <- URL for frontend
        "tissue_overlay_png": overlay_url,  # <- URL for frontend
    })

# ============================================================
#   DISPATCHER
# ============================================================

async def run_job_body(job: JobInternal) -> None:
    if job.job_type == JobType.CELL_SEGMENTATION:
        await run_cell_segmentation(job)
    elif job.job_type == JobType.TISSUE_MASK:
        await run_tissue_mask(job)
    else:
        raise ValueError(f"Unknown job type: {job.job_type}")
