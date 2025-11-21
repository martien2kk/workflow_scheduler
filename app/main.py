# app/main.py
from __future__ import annotations

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from app.routers import workflow_routes, job_routes, user_routes
from app.scheduler_core import scheduler_loop


app = FastAPI(
    title="WSI Workflow Scheduler",
    version="0.1.0",
)

# ------------------------------------------------------------
# 1) BACKEND API ROUTES 
# ------------------------------------------------------------
app.include_router(workflow_routes.router)
app.include_router(job_routes.router)
app.include_router(user_routes.router)


# ------------------------------------------------------------
# 2) STATIC FRONTEND (served at /app)
# ------------------------------------------------------------
print("STATIC FRONTEND DIR:", os.path.abspath("frontend"))
# Serve the entire frontend folder 
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


# ------------------------------------------------------------
# 3) OUTPUT IMAGES (mask.png, overlay.png)
# ------------------------------------------------------------

app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")


# ------------------------------------------------------------
# 4) CORS (frontend → backend communication)
# ------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-User-ID"],   
)


# ------------------------------------------------------------
# 5) SCHEDULER (background job loop)
# ------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scheduler_loop())
