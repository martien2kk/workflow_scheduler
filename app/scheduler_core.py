# app/scheduler_core.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List

from app.utils.storage import save_job_progress
from app.instanseg_tasks import run_job_body
from app.models import JobStatus
from app.workflow_manager import (
    JOBS,
    BRANCH_JOBS,
    running_jobs,
    active_users,
    scheduler_lock,
)


# Tuning params
MAX_WORKERS = 4          # Max concurrent RUNNING jobs globally
MAX_ACTIVE_USERS = 3     # Max distinct users with RUNNING jobs at once
SCHEDULER_INTERVAL = 0.5  # seconds


async def execute_job(job_id: str) -> None:
    job = JOBS[job_id]
    job.started_at = datetime.utcnow()

    try:
        await run_job_body(job)
        job.status = JobStatus.SUCCEEDED
        job.progress = 1.0

    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)

    finally:
        job.finished_at = datetime.utcnow()
        print("DEBUG FINAL WRITE:", job.status)
        save_job_progress(job)

        async with scheduler_lock:
            running_jobs.discard(job.id)
            still_running_for_user = any(
                j.user_id == job.user_id and j.status == JobStatus.RUNNING
                for j in JOBS.values()
            )
            if not still_running_for_user:
                active_users.discard(job.user_id)


def _first_runnable_job_ids_per_branch() -> List[str]:
    """
    Return job_ids that are the first PENDING job in their branch and
    whose predecessors in that branch are all finished (not PENDING/RUNNING).
    """
    runnable: List[str] = []

    for (wf_id, branch_id), job_ids in BRANCH_JOBS.items():
        for idx, jid in enumerate(job_ids):
            job = JOBS[jid]
            if job.status != JobStatus.PENDING:
                continue

            # Check all previous jobs in this branch
            blocking = False
            for prev_id in job_ids[:idx]:
                prev = JOBS[prev_id]
                if prev.status in (JobStatus.PENDING, JobStatus.RUNNING):
                    blocking = True
                    break

            if not blocking:
                runnable.append(jid)
            break  # only first PENDING per branch considered

    return runnable


async def schedule_once() -> None:
    """
    Single scheduling pass: picks eligible jobs and starts them
    while respecting:
      - branch serial execution
      - MAX_WORKERS
      - MAX_ACTIVE_USERS
    """
    print("schedule_once called")
    print("running_jobs:", running_jobs)
    print("active_users:", active_users)
    print("BRANCH_JOBS:", BRANCH_JOBS)
    print("All job statuses:", {jid: job.status for jid, job in JOBS.items()})

    if len(running_jobs) >= MAX_WORKERS:
        return

    candidates = _first_runnable_job_ids_per_branch()
    print("Candidates:", candidates)
    
    for jid in candidates:
        if len(running_jobs) >= MAX_WORKERS:
            break

        job = JOBS[jid]
        user_id = job.user_id

        # If user not already active, check user-limit
        if user_id not in active_users and len(active_users) >= MAX_ACTIVE_USERS:
            continue

        # Schedule job
        if job.status != JobStatus.PENDING:
            continue  # may have changed since we collected candidates

        job.status = JobStatus.RUNNING
        job.progress = 0.0

        running_jobs.add(job.id)
        active_users.add(user_id)

        asyncio.create_task(execute_job(job.id))



 
async def scheduler_loop() -> None:
    """
    Background loop that periodically tries to schedule new jobs.
    """
    print(">>> Scheduler loop started")
    while True:
        async with scheduler_lock:
            await schedule_once()
        await asyncio.sleep(SCHEDULER_INTERVAL)

