"""Shared job catalog logic for monorepo-scheduler."""

import logging
import shlex
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
WRAPPER_PATH = Path("/usr/local/bin/monorepo-scheduler-wrapper.sh")
RUN_LOG = SCRIPT_DIR / "run_log.csv"


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def shell_quote(s):
    return shlex.quote(str(s))


def load_catalog(config_path: str | Path = "targets.yaml"):
    """Parse targets.yaml and each target's schedule.yml, returning a list of job dicts."""
    logger.info("Loading catalog from %s", config_path)
    config = load_yaml(config_path)
    doppler = config.get("doppler", {})
    targets = config.get("targets", [])
    logger.info("Found %d target(s) in config", len(targets))
    jobs = []

    for target in targets:
        name = target["name"]
        if not target.get("enabled", True):
            logger.info("Target '%s' is disabled, skipping", name)
            continue

        repo_path = Path(target["repo_path"])
        schedule_path = repo_path / target["schedule_file"]

        if not schedule_path.exists():
            logger.warning("Schedule file not found: %s (target '%s')", schedule_path, name)
            continue

        logger.info("Loading schedule for target '%s' from %s", name, schedule_path)
        schedule_config = load_yaml(schedule_path)
        defaults = schedule_config.get("defaults", {})
        schedules = schedule_config.get("schedules", [])
        logger.info("Target '%s' has %d schedule(s)", name, len(schedules))

        for job in schedule_config.get("schedules", []):
            env_vars = defaults.get("env", {})
            env_prefix = " ".join(f'{k}={shell_quote(v)}' for k, v in env_vars.items())
            command = job["command"]
            final_command = f"{env_prefix} {command}" if env_prefix else command

            log_file = job.get("log_file", f"{defaults.get('log_dir', 'logs')}/{job['name']}.log")
            abs_log_path = repo_path / log_file

            jobs.append({
                "job_id": f"{name}-{job['name']}",
                "target_name": name,
                "repo_path": str(repo_path),
                "command": final_command,
                "log_file": str(abs_log_path),
                "hc_slug": job.get("hc_slug", ""),
                "cron": job["cron"],
                "groups": target.get("groups", []),
            })

    return jobs, config


def build_wrapper_command(job, doppler_config, log_file_override=None):
    """Build the full doppler run ... wrapper.sh ... command string for a job."""
    doppler_project = doppler_config.get("project", "")
    doppler_conf = doppler_config.get("config", "")
    log_file = log_file_override or job["log_file"]

    return (
        f"doppler run --project {shell_quote(doppler_project)} --config {shell_quote(doppler_conf)} -- "
        f"{WRAPPER_PATH} "
        f"{shell_quote(log_file)} "
        f"{shell_quote(job['repo_path'])} "
        f"{shell_quote(job['command'])} "
        f"{shell_quote(job['job_id'])} "
        f"{shell_quote(str(RUN_LOG))} "
        f"{shell_quote(job['hc_slug'])}"
    )
