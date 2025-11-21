# app/routers/workflow_routes.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.models import WorkflowCreate, WorkflowRead
from app.workflow_manager import (
    create_workflow,
    workflow_to_read,
    list_workflows_for_user,
    get_workflow_for_user,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def get_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    return x_user_id


@router.post("/", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
async def create_workflow_route(
    payload: WorkflowCreate,
    user_id: str = Depends(get_user_id),
):
    wf = create_workflow(user_id=user_id, payload=payload)
    return workflow_to_read(wf)


@router.get("/", response_model=list[WorkflowRead])
async def list_workflows_route(
    user_id: str = Depends(get_user_id),
):
    wfs = list_workflows_for_user(user_id)
    return [workflow_to_read(wf) for wf in wfs]


@router.get("/{workflow_id}", response_model=WorkflowRead)
async def get_workflow_route(
    workflow_id: str,
    user_id: str = Depends(get_user_id),
):
    try:
        wf = get_workflow_for_user(user_id, workflow_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow_to_read(wf)
