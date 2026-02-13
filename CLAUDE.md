# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A cron job orchestration tool that manages scheduled tasks across multiple Git repositories. It reads a central `targets.yaml` to discover repos, loads each repo's `schedule.yml`, and writes cron entries to `/etc/cron.d/`. A wrapper script handles execution logging and Discord failure notifications via Doppler secrets.

## Commands

```bash
# Run the scheduler (apply cron files from current repo state)
uv run python main.py

# Run with git pull of target repos first
uv run python main.py --pull

# Install dependencies
uv sync
```

The scheduler also generates a `Makefile` with targets for each job (e.g., `make project1-backup`). These run through the wrapper but output to stdout instead of log files, for manual testing.

## Architecture

**Flow:** `targets.yaml` → `main.py` → reads each target's `schedule.yml` → writes `/etc/cron.d/{name}` + `Makefile`

**Key files:**
- `main.py` — Orchestrator: loads config, installs wrapper, generates cron files and Makefile, restarts cron only if files changed
- `wrapper.sh` — Template deployed to `/usr/local/bin/monorepo-scheduler-wrapper.sh`. Wraps job execution with START/END timestamps, exit codes, Healthchecks pinging, CSV run log, and Discord notifications on failure
- `targets.yaml` — Central config defining Doppler project/config and target repositories
- `targets.example.yaml` — Example config for reference

**Schedule file format** (lives in each target repo):
```yaml
defaults:
  log_dir: logs
  env:
    KEY: value
schedules:
  - name: job-name
    cron: "0 2 * * *"
    command: "python script.py"
    hc_slug: your-healthcheck-slug  # optional, for Healthchecks pinging
```

**Doppler secrets** (all optional):
- `DISCORD_WEBHOOK_URL` — Discord webhook for failure notifications
- `HC_PING_URL` — Healthchecks base URL (e.g. `https://hc.local.example.com/ping`)
- `HC_PING_KEY` — Healthchecks project ping key. Combined with per-job `hc_slug` from schedule.yml to ping `{HC_PING_URL}/{HC_PING_KEY}/{hc_slug}/{exit_code}`

**System requirements:** Python 3.12+, uv, bash, git, systemctl/cron, Doppler CLI (optional, for Discord/Healthchecks)

## Key Patterns

- Cron files and the wrapper script use content-diffing before writing to avoid unnecessary restarts/reinstalls
- `shell_quote()` (wrapping `shlex.quote`) is used for all values passed through shell — always use it for paths and commands in cron/Makefile lines
- The `--pull` flag is the only way git operations run; by default the scheduler works with whatever is on disk
- Doppler config is global (top-level in `targets.yaml`), not per-target
