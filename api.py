"""FastAPI webhook trigger service for monorepo-scheduler jobs."""

from contextlib import asynccontextmanager
import logging
import secrets
import subprocess

import bcrypt
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pathlib import Path

from catalog import build_wrapper_command, load_catalog

logger = logging.getLogger(__name__)

USERS_FILE = Path(__file__).resolve().parent / "users.yaml"
TARGETS_FILE = Path(__file__).resolve().parent / "targets.yaml"

# Loaded at startup, refreshable via /catalog/reload
_job_catalog: list[dict] = []
_config: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _job_catalog, _config
    logger.info("Loading job catalog from %s", TARGETS_FILE)
    _job_catalog, _config = load_catalog(TARGETS_FILE)
    logger.info("Catalog loaded: %d job(s) found", len(_job_catalog))
    for job in _job_catalog:
        logger.info("  Job: %s (target=%s)", job["job_id"], job["target_name"])
    yield


app = FastAPI(title="monorepo-scheduler API", lifespan=lifespan)
security = HTTPBasic()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


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


def _render_dashboard(request, user, flash=None):
    jobs = _jobs_for_user(user["groups"])
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": user["username"],
        "jobs": jobs,
        "flash": flash,
    })


@app.get("/ui", response_class=HTMLResponse)
def dashboard(request: Request, user: dict = Depends(_authenticate)):
    return _render_dashboard(request, user)


@app.post("/ui/trigger/{job_id}", response_class=HTMLResponse)
def ui_trigger_job(request: Request, job_id: str, user: dict = Depends(_authenticate)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        return _render_dashboard(request, user, flash={"kind": "err", "message": "Job not found."})

    doppler = _config.get("doppler", {})
    cmd = build_wrapper_command(job, doppler)
    subprocess.Popen(cmd, shell=True, start_new_session=True)

    return _render_dashboard(request, user, flash={"kind": "ok", "message": f"Triggered {job_id}."})


@app.get("/")
def root():
    return RedirectResponse(url="/ui")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/jobs")
def list_jobs(user: dict = Depends(_authenticate)):
    return [
        {
            "job_id": j["job_id"],
            "target_name": j["target_name"],
            "cron": j["cron"],
        }
        for j in _jobs_for_user(user["groups"])
    ]


@app.post("/jobs/{job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_job(job_id: str, user: dict = Depends(_authenticate)):
    accessible = _jobs_for_user(user["groups"])
    job = next((j for j in accessible if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    doppler = _config.get("doppler", {})
    cmd = build_wrapper_command(job, doppler)

    subprocess.Popen(cmd, shell=True, start_new_session=True)

    return {"status": "triggered", "job_id": job_id, "triggered_by": user["username"]}


@app.post("/catalog/reload")
def reload_catalog(user: dict = Depends(_authenticate)):
    global _job_catalog, _config
    _job_catalog, _config = load_catalog(TARGETS_FILE)
    return {"status": "reloaded", "job_count": len(_job_catalog)}
