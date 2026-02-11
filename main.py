#!/usr/bin/env python3
import argparse
import yaml
import subprocess
from pathlib import Path
import shlex

BASE_TARGETS = Path("targets.yaml")
CRON_DIR = Path("/etc/cron.d")
WRAPPER_PATH = Path("/usr/local/bin/monorepo-scheduler-wrapper.sh")

WRAPPER_SCRIPT = """\
#!/bin/bash
LOG_FILE="$1"
WORK_DIR="$2"
COMMAND="$3"

cd "$WORK_DIR" || exit 1

{
    echo "=== START $(date '+%Y-%m-%d %H:%M:%S') ==="
    bash -c "$COMMAND"
    EXIT_CODE=$?
    echo "=== END $(date '+%Y-%m-%d %H:%M:%S') exit_code=$EXIT_CODE ==="
} >> "$LOG_FILE" 2>&1
"""

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

def shell_quote(s):
    return shlex.quote(str(s))

def install_wrapper():
    existing = WRAPPER_PATH.read_text() if WRAPPER_PATH.exists() else ""
    if existing == WRAPPER_SCRIPT:
        return
    WRAPPER_PATH.write_text(WRAPPER_SCRIPT)
    WRAPPER_PATH.chmod(0o755)
    print(f"Installed wrapper script to {WRAPPER_PATH}")

def apply_target(target, pull=False):
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

        line = (
            f"{cron} root {WRAPPER_PATH} "
            f"{shell_quote(str(abs_log_path))} "
            f"{shell_quote(str(repo_path))} "
            f"{shell_quote(final_command)}\n"
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

def main():
    parser = argparse.ArgumentParser(description="Apply cron schedules from monorepo targets")
    parser.add_argument("--pull", action="store_true", help="Git pull target repos before applying")
    args = parser.parse_args()

    install_wrapper()
    config = load_yaml(BASE_TARGETS)
    results = [apply_target(t, pull=args.pull) for t in config.get("targets", [])]
    changed = any(results)

    if changed:
        subprocess.run(["systemctl", "reload-or-restart", "cron"], check=False)
    else:
        print("⏩ No changes detected, skipping cron restart")

if __name__ == "__main__":
    main()
