# app/utils/storage.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.models import JobInternal

BASE_OUTPUT_DIR = Path("outputs")
BASE_OUTPUT_DIR.mkdir(exist_ok=True)


def get_job_output_dir(job_id: str) -> Path:
    d = BASE_OUTPUT_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_job_progress(job: JobInternal) -> None:
    """
    Save a tiny JSON sidecar with progress. Real version would go to DB/Redis.
    """
    data = {
        "status": job.status,
        "progress": job.progress,
        "tiles_done": job.tiles_done,
        "tiles_total": job.tiles_total,
        "error": job.error,
    }
    out_file = get_job_output_dir(job.id) / "progress.json"
    out_file.write_text(json.dumps(data, indent=2))


def save_segmentation_result(job: JobInternal, metadata: Dict[str, Any]) -> None:
    """
    Save the final segmentation output for a job.
    """
    out_file = get_job_output_dir(job.id) / "result.json"
    out_file.write_text(json.dumps(metadata, indent=2))
