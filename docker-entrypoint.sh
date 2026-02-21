#!/bin/bash
set -e

# Apply cron schedules from targets.yaml
echo "Applying cron schedules..."
cd /app
uv run python main.py

# Start supervisord (manages cron + FastAPI)
echo "Starting services..."
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
