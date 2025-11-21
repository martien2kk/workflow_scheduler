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

## How to Scale to 10× More Jobs / Users
To scale the system to support ten times more simultaneous jobs and users, the architecture would need to move beyond the current single-process, in-memory scheduler design. The first major improvement is shifting all heavy computation—such as InstanSeg cell segmentation and tissue mask generation—into distributed task workers using frameworks like Celery, Ray, or Redis Queue. This allows jobs to run in parallel across multiple CPU/GPU machines instead of inside the FastAPI server. In addition, job and workflow state should be persisted in a real database such as PostgreSQL or Redis rather than Python dictionaries so that multiple scheduler instances can coordinate reliably. For storage, output files (masks, overlays, JSON) should be moved to a scalable blob storage service like AWS S3 or Google Cloud Storage, and served via a CDN for faster delivery. On the frontend and backend, load balancers and autoscaling (e.g., Kubernetes Horizontal Pod Autoscaler) can ensure the system grows with demand. Finally, batching tile inference, caching models on GPUs, and parallelizing tile processing further reduce execution time per job. Together, these upgrades allow the system to handle dramatically higher workload while remaining responsive, fault-tolerant, and performant.

## **Testing** and **monitoring** in production  
In production, the system should be validated through automated testing, integration testing, and continuous monitoring. Unit tests should cover job scheduling logic, workflow branching behavior, concurrency limits, and file-serving endpoints. Integration tests can simulate multiple users submitting concurrent WSI jobs, verifying that the scheduler respects active-user limits and that results are written correctly to storage. Load testing tools such as Locust or k6 help measure system performance under heavy workloads before deployment. Once deployed, monitoring tools like Prometheus + Grafana or CloudWatch should track key metrics including job throughput, queue length, latency, worker utilization, and error rates. Structured logging (e.g., via ELK stack) is essential for debugging failed jobs and tracing user workflows end-to-end. Alerts should be configured for job failures, sustained high latency, or stalled workflows. Together, automated testing and real-time monitoring ensure that the system remains reliable, scalable, and observable during production use.

