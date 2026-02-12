#!/usr/bin/env python3
import argparse
import yaml
import subprocess
from pathlib import Path
import shlex

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_TARGETS = Path("targets.yaml")
CRON_DIR = Path("/etc/cron.d")
MAKEFILE_PATH = Path("Makefile")
WRAPPER_SRC = SCRIPT_DIR / "wrapper.sh"
WRAPPER_PATH = Path("/usr/local/bin/monorepo-scheduler-wrapper.sh")
RUN_LOG = SCRIPT_DIR / "run_log.csv"

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

def shell_quote(s):
    return shlex.quote(str(s))

def doppler_get(secret, project, config):
    """Fetch a single secret from Doppler. Returns empty string on failure."""
    result = subprocess.run(
        ["doppler", "secrets", "get", secret, "--project", project, "--config", config, "--plain"],
        capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else ""

def install_wrapper():
    wrapper_content = WRAPPER_SRC.read_text()
    existing = WRAPPER_PATH.read_text() if WRAPPER_PATH.exists() else ""
    if existing == wrapper_content:
        return
    WRAPPER_PATH.write_text(wrapper_content)
    WRAPPER_PATH.chmod(0o755)
    print(f"Installed wrapper script to {WRAPPER_PATH}")

def apply_target(target, pull=False, doppler=None, pushgateway_url="", loki_url=""):
    if not target.get("enabled", True):
        return False

    name = target["name"]
    repo_path = Path(target["repo_path"])
    schedule_path = repo_path / target["schedule_file"]
    print(f"Applying scheduler for {name}")

    if pull and target.get("branch"):
        subprocess.run(["git", "-C", str(repo_path), "fetch"], check=False)
        subprocess.run(["git", "-C", str(repo_path), "checkout", target["branch"]], check=False)
        subprocess.run(["git", "-C", str(repo_path), "pull", "--rebase"], check=False)

    if not schedule_path.exists():
        print(f"⚠️  Schedule file not found for {name}: {schedule_path}")
        return False

    config = load_yaml(schedule_path)
    defaults = config.get("defaults", {})
    schedules = config.get("schedules", [])

    cron_file = CRON_DIR / f"{name}"
    lines = [f"# Auto-generated cron jobs for {name}\n"]

    log_dir = repo_path / defaults.get("log_dir", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    for job in schedules:
        cron = job["cron"]
        command = job["command"]
        log_file = job.get("log_file", f"{defaults.get('log_dir', 'logs')}/{job['name']}.log")
        abs_log_path = repo_path / log_file

        # If environment variables exist in defaults, prefix them in command
        env_vars = defaults.get("env", {})
        env_prefix = " ".join(f'{k}={shell_quote(v)}' for k, v in env_vars.items())

        final_command = f"{env_prefix} {command}" if env_prefix else command

        job_name = f"{name}-{job['name']}"
        doppler_project = doppler.get("project", "") if doppler else ""
        doppler_config = doppler.get("config", "") if doppler else ""

        line = (
            f"{cron} root doppler run --project {shell_quote(doppler_project)} --config {shell_quote(doppler_config)} -- {WRAPPER_PATH} "
            f"{shell_quote(str(abs_log_path))} "
            f"{shell_quote(str(repo_path))} "
            f"{shell_quote(final_command)} "
            f"{shell_quote(job_name)} "
            f"{shell_quote(str(RUN_LOG))} "
            f"{shell_quote(pushgateway_url)} "
            f"{shell_quote(loki_url)}\n"
        )

        lines.append(line)

    new_content = "".join(lines)
    existing_content = cron_file.read_text() if cron_file.exists() else ""

    if new_content == existing_content:
        print(f"⏩ No changes for {name}")
        return False

    cron_file.write_text(new_content)
    print(f"Applied {len(schedules)} schedules for {name}")
    return True

def generate_makefile(config, pushgateway_url="", loki_url=""):
    targets = []
    rules = []
    doppler = config.get("doppler")

    for target in config.get("targets", []):
        if not target.get("enabled", True):
            continue

        name = target["name"]
        repo_path = Path(target["repo_path"])
        schedule_path = repo_path / target["schedule_file"]

        if not schedule_path.exists():
            continue

        schedule_config = load_yaml(schedule_path)
        defaults = schedule_config.get("defaults", {})

        for job in schedule_config.get("schedules", []):
            target_name = f"{name}-{job['name']}"
            targets.append(target_name)

            env_vars = defaults.get("env", {})
            env_prefix = " ".join(f'{k}={shell_quote(v)}' for k, v in env_vars.items())
            command = job["command"]
            final_command = f"{env_prefix} {command}" if env_prefix else command

            doppler_project = doppler.get("project", "") if doppler else ""
            doppler_config = doppler.get("config", "") if doppler else ""

            wrapper_call = (
                f"doppler run --project {shell_quote(doppler_project)} --config {shell_quote(doppler_config)} -- {WRAPPER_PATH} "
                f"/dev/stdout "
                f"{shell_quote(str(repo_path))} "
                f"{shell_quote(final_command)} "
                f"{shell_quote(target_name)} "
                f"{shell_quote(str(RUN_LOG))} "
                f"{shell_quote(pushgateway_url)} "
                f"{shell_quote(loki_url)}"
            )

            rules.append(f"{target_name}:\n\t{wrapper_call}")

    content = f"# Auto-generated by monorepo-scheduler\n"
    content += f".PHONY: {' '.join(targets)}\n\n"
    content += "\n\n".join(rules) + "\n"

    existing = MAKEFILE_PATH.read_text() if MAKEFILE_PATH.exists() else ""
    if content != existing:
        MAKEFILE_PATH.write_text(content)
        print(f"Generated Makefile with {len(targets)} targets")

def main():
    parser = argparse.ArgumentParser(description="Apply cron schedules from monorepo targets")
    parser.add_argument("--pull", action="store_true", help="Git pull target repos before applying")
    args = parser.parse_args()

    install_wrapper()
    config = load_yaml(BASE_TARGETS)
    doppler = config.get("doppler")

    pushgateway_url = ""
    loki_url = ""
    if doppler:
        pushgateway_url = doppler_get("PUSHGATEWAY_URL", doppler["project"], doppler["config"])
        loki_url = doppler_get("LOKI_URL", doppler["project"], doppler["config"])

    generate_makefile(config, pushgateway_url=pushgateway_url, loki_url=loki_url)
    results = [apply_target(t, pull=args.pull, doppler=doppler, pushgateway_url=pushgateway_url, loki_url=loki_url) for t in config.get("targets", [])]
    changed = any(results)

    if changed:
        subprocess.run(["systemctl", "reload-or-restart", "cron"], check=False)
    else:
        print("⏩ No changes detected, skipping cron restart")

if __name__ == "__main__":
    main()
