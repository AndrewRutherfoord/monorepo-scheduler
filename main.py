#!/usr/bin/env python3
import yaml
import subprocess
from pathlib import Path
import shlex

BASE_TARGETS = Path("targets.yaml")
CRON_DIR = Path("/etc/cron.d")

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

def shell_quote(s):
    return shlex.quote(str(s))

def apply_target(target):
    if not target.get("enabled", True):
        return False

    name = target["name"]
    repo_path = Path(target["repo_path"])
    schedule_path = repo_path / target["schedule_file"]
    print(f"Applying scheduler for {name}")

    if not schedule_path.exists():
        print(f"⚠️  Schedule file not found for {name}: {schedule_path}")
        return False

    # Optional git pull for branch
    if target.get("branch"):
        subprocess.run(["git", "-C", str(repo_path), "fetch"], check=False)
        subprocess.run(["git", "-C", str(repo_path), "checkout", target["branch"]], check=False)
        subprocess.run(["git", "-C", str(repo_path), "pull", "--rebase"], check=False)

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
            f"{cron} root cd {repo_path} && "
            f"{final_command} >> {abs_log_path} 2>&1\n"
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
    config = load_yaml(BASE_TARGETS)
    results = [apply_target(t) for t in config.get("targets", [])]
    changed = any(results)

    if changed:
        subprocess.run(["systemctl", "reload-or-restart", "cron"], check=False)
    else:
        print("⏩ No changes detected, skipping cron restart")

if __name__ == "__main__":
    main()
