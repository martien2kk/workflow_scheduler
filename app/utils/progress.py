# app/utils/progress.py
from __future__ import annotations

from app.utils.storage import save_job_progress
from app.models import JobInternal


def update_job_progress(job: JobInternal) -> None:
    """
    Update any derived job metrics and persist if needed.
    Currently just ensures progress is in [0, 1] and calls a simple saver.
    """
    if job.tiles_total > 0:
        job.progress = job.tiles_done / job.tiles_total
    else:
        job.progress = 0.0
    save_job_progress(job)
