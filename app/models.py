# app/models.py
from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------- Enums ----------

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    CELL_SEGMENTATION = "cell_segmentation"
    TISSUE_MASK = "tissue_mask"


# ---------- Pydantic Schemas (API) ----------

class JobCreate(BaseModel):
    job_type: JobType
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary job parameters (e.g., image_path, tiles_total)",
    )


class BranchCreate(BaseModel):
    branch_id: str
    jobs: List[JobCreate]


class WorkflowCreate(BaseModel):
    name: str
    branches: List[BranchCreate]


class JobRead(BaseModel):
    id: str
    workflow_id: str
    branch_id: str
    user_id: str
    job_type: JobType
    status: JobStatus
    progress: float
    tiles_done: int
    tiles_total: int
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class WorkflowRead(BaseModel):
    id: str
    name: str
    user_id: str
    created_at: datetime
    job_ids: List[str]
    overall_progress: float


# ---------- Internal Models (used by scheduler) ----------

class JobInternal:
    def __init__(
        self,
        id: str,
        workflow_id: str,
        branch_id: str,
        user_id: str,
        job_type: JobType,
        params: Dict[str, Any],
    ) -> None:
        self.id = id
        self.workflow_id = workflow_id
        self.branch_id = branch_id
        self.user_id = user_id
        self.job_type = job_type
        self.params = params

        self.status: JobStatus = JobStatus.PENDING
        self.progress: float = 0.0
        self.tiles_done: int = 0
        self.tiles_total: int = 0
        self.error: Optional[str] = None

        self.created_at: datetime = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None


class WorkflowInternal:
    def __init__(self, id: str, name: str, user_id: str) -> None:
        self.id = id
        self.name = name
        self.user_id = user_id
        self.created_at: datetime = datetime.utcnow()
        self.job_ids: List[str] = []


class ActiveUsersRead(BaseModel):
    active_users: List[str]
    running_jobs: List[str]
    count_active_users: int
    count_running_jobs: int


class JobResult(BaseModel):
    job_id: str
    data: Dict[str, Any]
