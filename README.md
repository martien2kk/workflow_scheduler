# Workflow Scheduler

A minimal branch-aware, multi-tenant workflow scheduler for large image inference.

## Quick Start
```bash
python -m venv scheduler
source scheduler/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
