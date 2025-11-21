# app/routers/user_routes.py
from __future__ import annotations
from app.models import ActiveUsersRead
from fastapi import APIRouter, Header, Depends

from app.workflow_manager import active_users, running_jobs

router = APIRouter(prefix="/users", tags=["users"])


async def get_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    return x_user_id


@router.get("/me")
async def get_me(user_id: str = Depends(get_user_id)):
    return {"user_id": user_id}


@router.get("/active", response_model=ActiveUsersRead)
async def get_active_users():
    """
    Simple view of which users are currently 'active'
    (i.e., have RUNNING jobs) and how many jobs are running.
    """
    return ActiveUsersRead(
        active_users=list(active_users),
        running_jobs=list(running_jobs),
        count_active_users=len(active_users),
        count_running_jobs=len(running_jobs),
    )