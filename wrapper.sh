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
echo "---- PUSHGATEWAY DEBUG START ----" >> "$LOG_FILE"

if [ -z "$PUSHGATEWAY_URL" ]; then
    echo "Pushgateway URL is NOT set" >> "$LOG_FILE"
fi

if [ -z "$PUSHGATEWAY_USERNAME" ]; then
    echo "Pushgateway USERNAME is NOT set" >> "$LOG_FILE"
fi

if [ -z "$PUSHGATEWAY_PASSWORD" ]; then
    echo "Pushgateway PASSWORD is NOT set" >> "$LOG_FILE"
fi

if [ -n "$PUSHGATEWAY_URL" ] && \
   [ -n "$PUSHGATEWAY_USERNAME" ] && \
   [ -n "$PUSHGATEWAY_PASSWORD" ]; then

    PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/cron_jobs/instance/${JOB_NAME}"
    echo "Push URL: $PUSH_URL" >> "$LOG_FILE"
    echo "Job: $JOB_NAME Duration: $DURATION Exit: $EXIT_CODE" >> "$LOG_FILE"

    METRICS_PAYLOAD=$(cat <<PROM_EOF
# TYPE cron_job_duration_seconds gauge
cron_job_duration_seconds $DURATION
# TYPE cron_job_exit_code gauge
cron_job_exit_code $EXIT_CODE
# TYPE cron_job_last_run_timestamp gauge
cron_job_last_run_timestamp $END_EPOCH
PROM_EOF
)

    echo "Payload being sent:" >> "$LOG_FILE"
    echo "$METRICS_PAYLOAD" >> "$LOG_FILE"

    HTTP_CODE=$(echo "$METRICS_PAYLOAD" | curl -s -w "%{http_code}" -o /tmp/pushgateway_response.txt \
        -u "${PUSHGATEWAY_USERNAME}:${PUSHGATEWAY_PASSWORD}" \
        --data-binary @- \
        "$PUSH_URL")

    echo "Pushgateway HTTP status: $HTTP_CODE" >> "$LOG_FILE"
    echo "Pushgateway response body:" >> "$LOG_FILE"
    cat /tmp/pushgateway_response.txt >> "$LOG_FILE"
    rm -f /tmp/pushgateway_response.txt

    # Success metric
    if [ "$EXIT_CODE" -eq 0 ]; then
        SUCCESS_URL="${PUSHGATEWAY_URL}/metrics/job/cron_jobs_success/instance/${JOB_NAME}"

        HTTP_CODE=$(cat <<PROM_EOF | curl -s -w "%{http_code}" -o /tmp/pushgateway_success_response.txt \
            -u "${PUSHGATEWAY_USERNAME}:${PUSHGATEWAY_PASSWORD}" \
            --data-binary @- \
            "$SUCCESS_URL"
# TYPE cron_job_last_success_timestamp gauge
cron_job_last_success_timestamp $END_EPOCH
PROM_EOF
)

        echo "Success metric HTTP status: $HTTP_CODE" >> "$LOG_FILE"
        cat /tmp/pushgateway_success_response.txt >> "$LOG_FILE"
        rm -f /tmp/pushgateway_success_response.txt
    fi
else
    echo "Skipping Pushgateway push due to missing credentials" >> "$LOG_FILE"
fi

echo "---- PUSHGATEWAY DEBUG END ----" >> "$LOG_FILE"

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
    curl -sf -X POST "${LOKI_URL}/loki/api/v1/push" \
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
        curl -sf -H "Content-Type: application/json" -d "{
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
