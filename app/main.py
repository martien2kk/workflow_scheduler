# app/main.py
from __future__ import annotations

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routers import workflow_routes, job_routes, user_routes
from app.scheduler_core import scheduler_loop

app = FastAPI(
    title="WSI Workflow Scheduler",
    version="0.1.0",
)

# ------------------------------------------------------------
# 1) Serve FRONTEND (index.html)
# ------------------------------------------------------------

# Mount entire frontend directory (your HTML/CSS/JS)
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Route "/" → serve index.html directly
@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")


# ------------------------------------------------------------
# 2) Serve OUTPUT IMAGE FILES (mask.png, overlay.png, etc.)
# ------------------------------------------------------------
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

# ------------------------------------------------------------
# 3) Enable CORS (frontend loads images + JSON)
# ------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# 4) Include backend routes
# ------------------------------------------------------------
app.include_router(workflow_routes.router)
app.include_router(job_routes.router)
app.include_router(user_routes.router)

# ------------------------------------------------------------
# 5) Start Scheduler
# ------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scheduler_loop())
