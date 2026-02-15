"""FastAPI webhook trigger service for monorepo-scheduler jobs."""

from contextlib import asynccontextmanager
import logging
import secrets
import subprocess

import bcrypt
import yaml
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
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


def _load_users() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    with open(USERS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("users", [])


def _authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    users = _load_users()
    for user in users:
        if secrets.compare_digest(credentials.username, user["username"]):
            if bcrypt.checkpw(
                credentials.password.encode(), user["password_hash"].encode()
            ):
                return credentials.username
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/jobs")
def list_jobs(username: str = Depends(_authenticate)):
    return [
        {
            "job_id": j["job_id"],
            "target_name": j["target_name"],
            "cron": j["cron"],
            "command": j["command"],
        }
        for j in _job_catalog
    ]


@app.post("/jobs/{job_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
def trigger_job(job_id: str, username: str = Depends(_authenticate)):
    job = next((j for j in _job_catalog if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    doppler = _config.get("doppler", {})
    cmd = build_wrapper_command(job, doppler)

    subprocess.Popen(cmd, shell=True, start_new_session=True)

    return {"status": "triggered", "job_id": job_id, "triggered_by": username}


@app.post("/catalog/reload")
def reload_catalog(username: str = Depends(_authenticate)):
    global _job_catalog, _config
    _job_catalog, _config = load_catalog(TARGETS_FILE)
    return {"status": "reloaded", "job_count": len(_job_catalog)}
