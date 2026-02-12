#!/bin/bash
LOG_FILE="$1"
WORK_DIR="$2"
COMMAND="$3"
JOB_NAME="$4"
RUN_LOG="$5"

cd "$WORK_DIR" || exit 1

PUSHGATEWAY_URL="$PUSHGATEWAY_URL"
PUSHGATEWAY_USERNAME="$PUSHGATEWAY_USERNAME"
PUSHGATEWAY_PASSWORD="$PUSHGATEWAY_PASSWORD"

LOKI_URL="$LOKI_URL"
LOKI_USERNAME="$LOKI_USERNAME"
LOKI_PASSWORD="$LOKI_PASSWORD"

START_TS=$(date '+%Y-%m-%d %H:%M:%S')
START_EPOCH=$(date +%s)

# Capture output to temp file so we can write to log AND push to Loki
TMPLOG=$(mktemp)

{
    echo "=== START $START_TS ==="
    bash -c "$COMMAND"
    EXIT_CODE=$?
    echo "=== END $(date '+%Y-%m-%d %H:%M:%S') exit_code=$EXIT_CODE ==="
} > "$TMPLOG" 2>&1

END_EPOCH=$(date +%s)
DURATION=$((END_EPOCH - START_EPOCH))

# Append to per-job log file
cat "$TMPLOG" >> "$LOG_FILE"

# Append to run log CSV
if [ -n "$RUN_LOG" ]; then
    if [ ! -f "$RUN_LOG" ]; then
        echo "timestamp,job_name,exit_code,duration_seconds" > "$RUN_LOG"
    fi
    echo "$START_TS,$JOB_NAME,$EXIT_CODE,$DURATION" >> "$RUN_LOG"
fi

# Push metrics to Prometheus Pushgateway
if [ -n "$PUSHGATEWAY_URL" ] && \
   [ -n "$PUSHGATEWAY_USERNAME" ] && \
   [ -n "$PUSHGATEWAY_PASSWORD" ]; then
    cat <<PROM_EOF | curl -s -u "${PUSHGATEWAY_USERNAME}:${PUSHGATEWAY_PASSWORD}" --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/cron_jobs/instance/${JOB_NAME}" > /dev/null 2>&1
# TYPE cron_job_duration_seconds gauge
cron_job_duration_seconds $DURATION
# TYPE cron_job_exit_code gauge
cron_job_exit_code $EXIT_CODE
# TYPE cron_job_last_run_timestamp gauge
cron_job_last_run_timestamp $END_EPOCH
PROM_EOF

    # Track last success separately so it persists across failed runs

    if [ "$EXIT_CODE" -eq 0 ]; then
    cat <<PROM_EOF | curl -s -u "${PUSHGATEWAY_USERNAME}:${PUSHGATEWAY_PASSWORD}" --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/cron_jobs_success/instance/${JOB_NAME}" > /dev/null 2>&1
# TYPE cron_job_last_success_timestamp gauge
cron_job_last_success_timestamp $END_EPOCH
PROM_EOF
    fi
fi

# Push logs to Loki
if [ -n "$LOKI_URL" ] && [ -n "$LOKI_USERNAME" ] && [ -n "$LOKI_PASSWORD" ] && [ -s "$TMPLOG" ] && command -v jq >/dev/null 2>&1; then
    HOSTNAME=$(hostname)
    NANO_TS="${START_EPOCH}000000000"

    jq -Rs \
        --arg job_name "$JOB_NAME" \
        --arg host "$HOSTNAME" \
        --arg exit_code "$EXIT_CODE" \
        --arg ts "$NANO_TS" \
        '{streams: [{stream: {job: "cron_jobs", job_name: $job_name, host: $host, exit_code: $exit_code}, values: [[$ts, .]]}]}' \
        "$TMPLOG" | \
    curl -s -X POST "${LOKI_URL}/loki/api/v1/push" \
        -H "Content-Type: application/json" \
        -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
        -d @- > /dev/null 2>&1
fi

rm -f "$TMPLOG"

# Discord notification on failure
if [ "$EXIT_CODE" -ne 0 ] && [ -n "$DISCORD_WEBHOOK_URL" ]; then
    WEBHOOK_URL=$DISCORD_WEBHOOK_URL
    if [ -n "$WEBHOOK_URL" ]; then
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        HOSTNAME=$(hostname)
        curl -s -H "Content-Type: application/json" -d "{
            \"embeds\": [{
                \"title\": \"Cron Job Failed\",
                \"color\": 15548997,
                \"fields\": [
                    {\"name\": \"Job\", \"value\": \"$JOB_NAME\", \"inline\": true},
                    {\"name\": \"Exit Code\", \"value\": \"$EXIT_CODE\", \"inline\": true},
                    {\"name\": \"Time\", \"value\": \"$TIMESTAMP\", \"inline\": true},
                    {\"name\": \"Host\", \"value\": \"$HOSTNAME\", \"inline\": true}
                ]
            }]
        }" "$WEBHOOK_URL" > /dev/null 2>&1
    fi
fi
