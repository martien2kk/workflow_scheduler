# app/workflow_manager.py
from __future__ import annotations

import asyncio
from typing import Dict, List, Tuple, Set
from uuid import uuid4

from app.models import (
    JobInternal,
    WorkflowInternal,
    WorkflowCreate,
    JobRead,
    WorkflowRead,
    JobStatus,
)


# ---------- In-memory "DB" + scheduler shared state ----------

WORKFLOWS: Dict[str, WorkflowInternal] = {}
JOBS: Dict[str, JobInternal] = {}
# (workflow_id, branch_id) -> ordered list of job_ids
BRANCH_JOBS: Dict[Tuple[str, str], List[str]] = {}

running_jobs: Set[str] = set()
active_users: Set[str] = set()

# Global lock for scheduler updates
scheduler_lock = asyncio.Lock()

print("workflow_manager module loaded, id(JOBS) =", id(JOBS))

# ---------- Conversion helpers ----------

def job_to_read(job: JobInternal) -> JobRead:
    return JobRead(
        id=job.id,
        workflow_id=job.workflow_id,
        branch_id=job.branch_id,
        user_id=job.user_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        tiles_done=job.tiles_done,
        tiles_total=job.tiles_total,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def compute_workflow_progress(wf: WorkflowInternal) -> float:
    if not wf.job_ids:
        return 0.0
    progresses = [JOBS[jid].progress for jid in wf.job_ids]
    return sum(progresses) / len(progresses)


def workflow_to_read(wf: WorkflowInternal) -> WorkflowRead:
    return WorkflowRead(
        id=wf.id,
        name=wf.name,
        user_id=wf.user_id,
        created_at=wf.created_at,
        job_ids=wf.job_ids,
        overall_progress=compute_workflow_progress(wf),
    )


# ---------- CRUD-style helpers ----------

def create_workflow(user_id: str, payload: WorkflowCreate) -> WorkflowInternal:
    wf_id = str(uuid4())
    wf = WorkflowInternal(id=wf_id, name=payload.name, user_id=user_id)
    WORKFLOWS[wf_id] = wf

    for branch in payload.branches:
        key = (wf_id, branch.branch_id)
        BRANCH_JOBS.setdefault(key, [])
        for job_create in branch.jobs:
            jid = str(uuid4())
            job = JobInternal(
                id=jid,
                workflow_id=wf_id,
                branch_id=branch.branch_id,
                user_id=user_id,
                job_type=job_create.job_type,
                params=job_create.params,
            )
            JOBS[jid] = job
            wf.job_ids.append(jid)
            BRANCH_JOBS[key].append(jid)

    return wf


def get_workflow_for_user(user_id: str, workflow_id: str) -> WorkflowInternal:
    wf = WORKFLOWS.get(workflow_id)
    if wf is None or wf.user_id != user_id:
        raise KeyError("Workflow not found or not owned by user")
    return wf


def list_workflows_for_user(user_id: str) -> List[WorkflowInternal]:
    return [wf for wf in WORKFLOWS.values() if wf.user_id == user_id]


def list_jobs_for_workflow(user_id: str, workflow_id: str) -> List[JobInternal]:
    wf = get_workflow_for_user(user_id, workflow_id)
    return [JOBS[jid] for jid in wf.job_ids]


def get_job_for_user(user_id: str, job_id: str) -> JobInternal:
    job = JOBS.get(job_id)
    if job is None or job.user_id != user_id:
        raise KeyError("Job not found or not owned by user")
    return job


def cancel_pending_job(user_id: str, job_id: str) -> JobInternal:
    job = get_job_for_user(user_id, job_id)
    if job.status != JobStatus.PENDING:
        raise ValueError("Only PENDING jobs can be cancelled")
    job.status = JobStatus.CANCELLED
    job.progress = 0.0
    job.tiles_done = 0
    job.tiles_total = 0
    return job
