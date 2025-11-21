# app/routers/job_routes.py
from __future__ import annotations

import os
import json
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.models import JobRead, JobResult, JobStatus
from app.workflow_manager import (
    get_job_for_user,
    job_to_read,
    list_jobs_for_workflow,
    cancel_pending_job,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# Extract user ID
async def get_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    return x_user_id


# ---------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------
@router.get("/{job_id}", response_model=JobRead)
async def get_job_route(job_id: str, user_id: str = Depends(get_user_id)):
    try:
        job = get_job_for_user(user_id, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_read(job)


# ---------------------------------------------------------
# GET /jobs/workflow/{workflow_id}
# ---------------------------------------------------------
@router.get("/workflow/{workflow_id}", response_model=list[JobRead])
async def list_jobs_for_workflow_route(workflow_id: str, user_id: str = Depends(get_user_id)):
    try:
        jobs = list_jobs_for_workflow(user_id, workflow_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return [job_to_read(j) for j in jobs]


# ---------------------------------------------------------
# POST /jobs/{job_id}/cancel
# ---------------------------------------------------------
@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job_route(job_id: str, user_id: str = Depends(get_user_id)):
    try:
        job = cancel_pending_job(user_id, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return job_to_read(job)


# ---------------------------------------------------------
# GET /jobs/{job_id}/result  
# ---------------------------------------------------------
@router.get("/{job_id}/result")
async def get_job_result(job_id: str, user_id: str = Depends(get_user_id)):
    # Validate user
    try:
        job = get_job_for_user(user_id, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

    # Ensure job finished
    if job.status not in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        raise HTTPException(status_code=400, detail="Result is only available after job finishes.")

    
    result_path = os.path.join("outputs", job_id, "result.json")

    if not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Result file not found")

    # Load raw JSON
    with open(result_path, "r") as f:
        data = json.load(f)

    # Return directly so frontend sees mask_png & overlay_png at TOP
    return {"job_id": job_id, "data": data}


# ---------------------------------------------------------
# Direct image access (optional)
# ---------------------------------------------------------
@router.get("/{job_id}/result/mask")
async def get_mask(job_id: str, user_id: str = Depends(get_user_id)):
    path = os.path.join("outputs", job_id, "mask.png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="mask.png not found")
    return FileResponse(path)


@router.get("/{job_id}/result/overlay")
async def get_overlay(job_id: str, user_id: str = Depends(get_user_id)):
    path = os.path.join("outputs", job_id, "overlay.png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="overlay.png not found")
    return FileResponse(path)
