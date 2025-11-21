# Workflow Scheduler

A lightweight workflow engine for whole-slide image (WSI) processing with:
- Multi-tenant scheduling
- Branch-aware workflows
- Limit of 3 concurrent active users
- Real-time progress tracking (via polling API)
- Cell segmentation (InstanSeg)
- Tissue mask generation
- Simple frontend viewer (HTML + JS)

## Setup Instructions (using venv)
These steps assume you are running locally on macOS/Linux/Windows (WSL).

#### 1. Clone the repository
```bash
git clone github.com/martien2kk/workflow_scheduler
cd workflow_scheduler
```

#### 2. cd workflow_scheduler

```
python3 -m venv .scheduler
source .scheduler/bin/activate     # macOS / Linux

# WINDOWS (PowerShell)
.sheduler\Scripts\activate

```

#### 3. Install dependencies
```
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Start the backend server
```
uvicorn app.main:app --reload
```
Open the frontend UI:
http://127.0.0.1:8000/

#### 5. API Documentation (Swagger / OpenAPI)
This project exposes fully interactive API documentation using FastAPI’s built-in Swagger (OpenAPI) UI. Once the server is running locally, the interactive documentation is automatically available at:
```
http://127.0.0.1:8000/docs
```
This interface lets you explore all endpoints—such as workflow creation, job status queries, tissue mask generation, and InstanSeg cell segmentation—without needing any external tools. You can execute API calls directly from the browser, view request/response schemas, inspect validation rules, and test the workflow orchestration end-to-end. A second documentation view is also available at /redoc, offering a more structured, read-only OpenAPI reference. Because the OpenAPI schema is generated dynamically, any changes to routes or request models are automatically reflected in the documentation, ensuring that API consumers always have an up-to-date specification with no manual maintenance required.

## Project Structure
```
workflow-scheduler/
│
├── scheduler/                      # the Python virtual environment (ignore in Git)
│
├── app/
│   ├── main.py                     # FastAPI entry point
│   ├── models.py                   # Pydantic models (Job, Workflow, etc.)
│   ├── scheduler_core.py           # Branch-aware scheduler logic
│   ├── workers.py                  # Worker process (Redis RQ)
│   ├── instanseg_tasks.py          # Actual image segmentation code
│   ├── workflow_manager.py         # Create workflows, manage branches
│   │
│   ├── utils/
│   │     ├── tiles.py              # tile splitting + merging
│   │     ├── progress.py           # track job/workflow progress
│   │     ├── storage.py            # store output files/results
│   │
│   └── routers/
│         ├── workflow_routes.py    # endpoints: create workflow, get workflow
│         ├── job_routes.py         # endpoints: submit job, cancel, status
│         └── user_routes.py        # maybe: user info, active limits
│
│
├── frontend/                       
│   ├── index.html
│   ├── app.js
│   └── styles.css                  # TODO
│
├── tests/                          # TODO
│   └── test_scheduler.py
│
├── docker-compose.yml              # TODOworker containers
├── Dockerfile                      # TODO
├── requirements.txt                
├── README.md                       
└── .gitignore                      # ignore env + pycache + outputs
```

## Example Run-Through (Using CMU-2.svs Workflow)
This example demonstrates a complete end-to-end workflow using the publicly available whole-slide image CMU-2.svs, provided by Carnegie Mellon University as part of the OpenSlide test dataset:

🔗 CMU-2.svs download link:
https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-2.svs

In this example, we submit a workflow consisting of two jobs on a single branch:

1.Cell Segmentation (cell_segmentation)

- Runs tile-based nucleus segmentation using the InstanSeg model

- Outputs:

    - overlay.png 
    - mask.png 
    - result.json → metadata (cell coordinates, counts, tiles processed, etc.)

2. Tissue Mask Generation (tissue_mask)

- Computes a whole-slide tissue mask using Otsu thresholding on the lowest-resolution pyramid level

- Outputs:

    - tissue_mask.png 

    - tissue_overlay.png 

    - result.json → metadata with accessible PNG paths

Both jobs operate on the same whole-slide image, allowing you to confirm that the scheduler processes dependent tasks correctly and that result files are created inside: `outputs/<job_id>/`

**First start the Server**
<img width="515" height="142" alt="image" src="https://github.com/user-attachments/assets/eb84f7f6-5150-46ea-b24a-5e711be78195" />

Expected output:
```
Uvicorn running on http://127.0.0.1:8000

```
To submit a workflow, navigate to: `http://localhost:8000/docs`
<img width="1892" height="967" alt="image" src="https://github.com/user-attachments/assets/8020c475-e1ac-4573-bb1f-07a5fc14c457" />

Use this example JSON for **POST /workflows/**:
```
{
  "name": "test-wsi",
  "branches": [
    {
      "branch_id": "A",
      "jobs": [
        {
          "job_type": "cell_segmentation",
          "params": {
            "wsi_path": "<WSI-PATH>/workflow_scheduler/data/CMU-2.svs",
            "tile_size": 512,
            "overlap": 32,
            "max_tiles": 4
          }
        },
        {
          "job_type": "tissue_mask",
          "params": {
            "wsi_path": "<WSI-PATH>/workflow_scheduler/data/CMU-2.svs",
            "tile_size": 1024,
            "overlap": 64,
            "max_tiles": 2
          }
        }
      ]
    }
  ]
}

```
Required header:
```
X-User-ID: user-1
```
<img width="1638" height="980" alt="image" src="https://github.com/user-attachments/assets/ac9ddc3a-cc2d-44af-8b9d-ba5145c517e9" />

Your terminal will show logs like:
```
>>> Scheduler loop started
running_jobs: {...}
active_users: {...}
Candidates: [...]
```
<img width="1276" height="230" alt="image" src="https://github.com/user-attachments/assets/4f548d6f-3a5a-46b5-95e4-581f3974535d" />

Retreive job ID and workflow ID
```
{
  "id": "2cad6352-085f-4d40-af00-dd4f2dee6026",
  "name": "test-wsi",
  "user_id": "user-1",
  "created_at": "2025-11-21T18:35:00.147118",
  "job_ids": [
    "23eabec6-7fa4-4ab0-9ca7-b87bb7e39b31",
    "d47d4959-8884-4a76-80fb-285b6d42abad"
  ],
  "overall_progress": 0
}
```
You can view workflow jobs:

`GET /workflows/<workflow_id>`


or list all jobs for a workflow:

```GET /jobs/workflow/<workflow_id>```


**To check job progress, use the endpoint:**

`GET /jobs/<job_id>`


You’ll see status evolve:

- PENDING

- RUNNING

- SUCCEEDED

You will also see:

- tiles_done

- tiles_total

- progress = tiles_done / tiles_total

This satisfies the real-time progress tracking requirement.

**Fetch Results for Each Job**

Once a job has status = SUCCEEDED, do:

`GET /jobs/<job_id>/result`


This returns something like:
```
{
  "job_id": "36b8ecaf-3fc2-479b-a1d0-7f4a3b4441aa",
  "data": {
    "mask_png": "/outputs/36b8ecaf-3fc2-479b-a1d0-7f4a3b4441aa/mask.png",
    "overlay_png": "/outputs/36b8ecaf-3fc2-479b-a1d0-7f4a3b4441aa/overlay.png",
    "pixel_size_um": 0.5,
    "tiles_processed": 4,
    "num_cells": 4,
    "cells": [
      {
        "bbox": { ... }
      }
    ]
  }
}
```

To view the images directly:
```
http://localhost:8000/outputs/<job_id>/overlay.png
http://localhost:8000/outputs/<job_id>/mask.png
http://localhost:8000/outputs/<job_id>/tissue_overlay.png
http://localhost:8000/outputs/<job_id>/tissue_mask.png
```

**To View Results in the Frontend**
Open the UI: `http://localhost:8000/`


Enter both job IDs:

- Cell segmentation job ID

- Tissue mask job ID

- Click Load Results.
<img width="1836" height="921" alt="image" src="https://github.com/user-attachments/assets/3785f4dc-4172-4e1c-becc-fb8cf7141a4a" />

The UI shows:

- cell segmentation JSON

- segmentation overlay PNG

- segmentation mask PNG

- tissue mask overlay

- tissue mask binary PNG
<img width="1842" height="895" alt="image" src="https://github.com/user-attachments/assets/03a68c27-4a82-43c2-b695-bf4e0b0121f5" />


## How to Scale to 10× More Jobs / Users
To scale the system to support ten times more simultaneous jobs and users, the architecture would need to move beyond the current single-process, in-memory scheduler design. The first major improvement is shifting all heavy computation—such as InstanSeg cell segmentation and tissue mask generation—into distributed task workers using frameworks like Celery, Ray, or Redis Queue. This allows jobs to run in parallel across multiple CPU/GPU machines instead of inside the FastAPI server. In addition, job and workflow state should be persisted in a real database such as PostgreSQL or Redis rather than Python dictionaries so that multiple scheduler instances can coordinate reliably. For storage, output files (masks, overlays, JSON) should be moved to a scalable blob storage service like AWS S3 or Google Cloud Storage, and served via a CDN for faster delivery. On the frontend and backend, load balancers and autoscaling (e.g., Kubernetes Horizontal Pod Autoscaler) can ensure the system grows with demand. Finally, batching tile inference, caching models on GPUs, and parallelizing tile processing further reduce execution time per job. Together, these upgrades allow the system to handle dramatically higher workload while remaining responsive, fault-tolerant, and performant.

## **Testing** and **monitoring** in production  
In production, the system should be validated through automated testing, integration testing, and continuous monitoring. Unit tests should cover job scheduling logic, workflow branching behavior, concurrency limits, and file-serving endpoints. Integration tests can simulate multiple users submitting concurrent WSI jobs, verifying that the scheduler respects active-user limits and that results are written correctly to storage. Load testing tools such as Locust or k6 help measure system performance under heavy workloads before deployment. Once deployed, monitoring tools like Prometheus + Grafana or CloudWatch should track key metrics including job throughput, queue length, latency, worker utilization, and error rates. Structured logging (e.g., via ELK stack) is essential for debugging failed jobs and tracing user workflows end-to-end. Alerts should be configured for job failures, sustained high latency, or stalled workflows. Together, automated testing and real-time monitoring ensure that the system remains reliable, scalable, and observable during production use.

