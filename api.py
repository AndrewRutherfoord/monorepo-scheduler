"""FastAPI webhook trigger service for monorepo-scheduler jobs."""

from contextlib import asynccontextmanager
import logging
import secrets
import subprocess
from typing import Optional

import bcrypt
import yaml
import uuid
import threading
from datetime import datetime
from fastapi import APIRouter, APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlmodel import Field, Session, SQLModel, create_engine, select

from catalog import build_wrapper_command, load_catalog

logger = logging.getLogger(__name__)

USERS_FILE = Path(__file__).resolve().parent / "users.yaml"
TARGETS_FILE = Path(__file__).resolve().parent / "targets.yaml"
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

LOGS_DIR = Path("/var/lib/monorepo-scheduler/logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = "sqlite:///./runs.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# SQLModel models
class JobRun(SQLModel, table=True):
    run_id: str = Field(primary_key=True)
    job_id: str
    target_name: str
    status: str  # running, success, failed
    triggered_by: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None

def get_session():
    with Session(engine) as session:
        yield session

# Loaded at startup, refreshable via /catalog/reload
_job_catalog: list[dict] = []
_config: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _job_catalog, _config
    # Create database tables
    SQLModel.metadata.create_all(engine)
    
    logger.info("Loading job catalog from %s", TARGETS_FILE)
    _job_catalog, _config = load_catalog(TARGETS_FILE)
    logger.info("Catalog loaded: %d job(s) found", len(_job_catalog))
    for job in _job_catalog:
        logger.info("  Job: %s (target=%s)", job["job_id"], job["target_name"])
    yield


app = FastAPI(title="monorepo-scheduler API", lifespan=lifespan)
security = HTTPBasic()

router = APIRouter(prefix="/api")   

jobs_router = APIRouter(prefix="/jobs")
runs_router = APIRouter(prefix="/runs")

def _load_users() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    with open(USERS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("users", [])

def _authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> dict:
    users = _load_users()
    for user in users:
        if secrets.compare_digest(credentials.username, user["username"]):
            if bcrypt.checkpw(
                credentials.password.encode(), user["password_hash"].encode()
            ):
                return {"username": credentials.username, "groups": user.get("groups", [])}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def _jobs_for_user(user_groups: list[str]) -> list[dict]:
    """Return jobs the user has access to based on group membership."""
    group_set = set(user_groups)
    return [j for j in _job_catalog if group_set & set(j.get("groups", []))]


@router.get("/health")
def health():
    return {"status": "ok"}


@jobs_router.get("")
def list_jobs(user: dict = Depends(_authenticate)):
    return [
        {
            "job_id": j["job_id"],
            "target_name": j["target_name"],
            "cron": j["cron"],
        }
        for j in _jobs_for_user(user["groups"])
    ]

@jobs_router.get("/{job_id}")
def get_job(job_id: str, user: dict = Depends(_authenticate)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return {
        "job_id": job["job_id"],
        "target_name": job["target_name"],
        "cron": job["cron"],
        "groups": job.get("groups", []),
    }

def _execute_job(run_id: str, job: dict, cmd: str, triggered_by: str):
    log_file = LOGS_DIR / f"{run_id}.log"
    
    started_at = datetime.utcnow()
    
    # Create initial run record
    with Session(engine) as session:
        job_run = JobRun(
            run_id=run_id,
            job_id=job["job_id"],
            target_name=job["target_name"],
            status="running",
            triggered_by=triggered_by,
            started_at=started_at
        )
        session.add(job_run)
        session.commit()

    try:
        with open(log_file, "w") as log:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            for line in process.stdout:
                log.write(line)
                log.flush()

            process.wait()

        finished_at = datetime.utcnow()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        status = "success" if process.returncode == 0 else "failed"
        
        # Update run record
        with Session(engine) as session:
            job_run = session.get(JobRun, run_id)
            if job_run:
                job_run.status = status
                job_run.finished_at = finished_at
                job_run.exit_code = process.returncode
                job_run.duration_ms = duration_ms
                if process.returncode != 0:
                    # Read error from log file
                    if log_file.exists():
                        error_content = log_file.read_text()
                        # Take last few lines as error message
                        error_lines = error_content.strip().split('\n')[-5:]
                        job_run.error_message = '\n'.join(error_lines)
                session.add(job_run)
                session.commit()
                
    except Exception as e:
        # Mark run as failed due to execution error
        finished_at = datetime.utcnow()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        
        with Session(engine) as session:
            job_run = session.get(JobRun, run_id)
            if job_run:
                job_run.status = "failed"
                job_run.finished_at = finished_at
                job_run.exit_code = -1
                job_run.duration_ms = duration_ms
                job_run.error_message = str(e)
                session.add(job_run)
                session.commit()

@jobs_router.post("/{job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_job(job_id: str, user: dict = Depends(_authenticate)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    doppler = _config.get("doppler", {})
    cmd = build_wrapper_command(job, doppler)

    run_id = str(uuid.uuid4())

    thread = threading.Thread(
        target=_execute_job,
        args=(run_id, job, cmd, user["username"]),
        daemon=True,
    )
    thread.start()

    return {
        "status": "triggered",
        "job_id": job_id,
        "run_id": run_id,
    }

@jobs_router.get("/{job_id}/runs")
def list_job_runs(job_id: str, user: dict = Depends(_authenticate), session: Session = Depends(get_session)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    statement = select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.started_at.desc())
    runs = session.exec(statement).all()
    
    return [
        {
            "run_id": run.run_id,
            "job_id": run.job_id,
            "target_name": run.target_name,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "created_at": run.started_at.isoformat(),
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "exit_code": run.exit_code,
            "duration": run.duration_ms,
            "error": run.error_message
        }
        for run in runs
    ]

@jobs_router.get("/{job_id}/runs/{run_id}")
def get_job_run(job_id: str, run_id: str, user: dict = Depends(_authenticate), session: Session = Depends(get_session)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    run = session.get(JobRun, run_id)
    if not run or run.job_id != job_id:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return {
        "run_id": run.run_id,
        "job_id": run.job_id,
        "target_name": run.target_name,
        "status": run.status,
        "triggered_by": run.triggered_by,
        "created_at": run.started_at.isoformat(),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "exit_code": run.exit_code,
        "duration": run.duration_ms,
        "error": run.error_message
    }

@jobs_router.get("/{job_id}/runs/{run_id}/logs")
def get_job_run_logs(job_id: str, run_id: str, user: dict = Depends(_authenticate), session: Session = Depends(get_session)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    run = session.get(JobRun, run_id)
    if not run or run.job_id != job_id:
        raise HTTPException(status_code=404, detail="Run not found")
    
    log_file = LOGS_DIR / f"{run_id}.log"
    if not log_file.exists():
        return "No logs available"
    
    return log_file.read_text()

@runs_router.get("/")
def list_runs(user: dict = Depends(_authenticate), session: Session = Depends(get_session)):
    statement = select(JobRun).order_by(JobRun.started_at.desc())
    runs = session.exec(statement).all()
    
    # Filter runs based on user access
    accessible_job_ids = {j["job_id"] for j in _jobs_for_user(user["groups"])}
    filtered_runs = [run for run in runs if run.job_id in accessible_job_ids]
    
    return [
        {
            "run_id": run.run_id,
            "job_id": run.job_id,
            "target_name": run.target_name,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "created_at": run.started_at.isoformat(),
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "exit_code": run.exit_code,
            "duration": run.duration_ms,
            "error": run.error_message
        }
        for run in filtered_runs
    ]

@runs_router.get("/{run_id}")
def get_run(run_id: str, user: dict = Depends(_authenticate), session: Session = Depends(get_session)):
    run = session.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Check user access to this job
    accessible_job_ids = {j["job_id"] for j in _jobs_for_user(user["groups"])}
    if run.job_id not in accessible_job_ids:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return {
        "run_id": run.run_id,
        "job_id": run.job_id,
        "target_name": run.target_name,
        "status": run.status,
        "triggered_by": run.triggered_by,
        "created_at": run.started_at.isoformat(),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "exit_code": run.exit_code,
        "duration": run.duration_ms,
        "error": run.error_message
    }

@runs_router.get("/{run_id}/logs")
def get_logs(run_id: str, user: dict = Depends(_authenticate), session: Session = Depends(get_session)):
    run = session.get(JobRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Check user access to this job
    accessible_job_ids = {j["job_id"] for j in _jobs_for_user(user["groups"])}
    if run.job_id not in accessible_job_ids:
        raise HTTPException(status_code=404, detail="Logs not found")
    
    log_file = LOGS_DIR / f"{run_id}.log"
    if not log_file.exists():
        return "No logs available"
    
    return log_file.read_text()


@router.post("/catalog/reload")
def reload_catalog(user: dict = Depends(_authenticate)):
    global _job_catalog, _config
    _job_catalog, _config = load_catalog(TARGETS_FILE)
    return {"status": "reloaded", "job_count": len(_job_catalog)}

router.include_router(jobs_router)
router.include_router(runs_router)

app.include_router(router)

# # Serve Vue SPA from frontend/dist (production build)
# if FRONTEND_DIST.is_dir():
#     app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

#     @app.get("/{full_path:path}")
#     def serve_spa(full_path: str):
#         # Serve the file if it exists in dist, otherwise serve index.html (SPA fallback)
#         file_path = FRONTEND_DIST / full_path
#         if full_path and file_path.is_file():
#             return FileResponse(file_path)
#         return FileResponse(FRONTEND_DIST / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
