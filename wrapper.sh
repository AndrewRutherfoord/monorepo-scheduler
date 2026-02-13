#!/bin/bash
LOG_FILE="$1"
WORK_DIR="$2"
COMMAND="$3"
JOB_NAME="$4"
RUN_LOG="$5"
HC_PING_SLUG="$6"

cd "$WORK_DIR" || exit 1

HC_PING_URL="$HC_PING_URL"

START_TS=$(date '+%Y-%m-%d %H:%M:%S')
START_EPOCH=$(date +%s)

# Ping Healthchecks start
if [ -n "$HC_PING_URL" ] && [ -n "$HC_PING_SLUG" ]; then
    curl -sfm 10 "${HC_PING_URL}/${HC_PING_SLUG}/start" > /dev/null 2>&1
fi

# Capture output to temp file so we can send it to Healthchecks
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

# Ping Healthchecks with log output
if [ -n "$HC_PING_URL" ] && [ -n "$HC_PING_SLUG" ]; then
    if [ "$EXIT_CODE" -eq 0 ]; then
        curl -sfm 10 --data-binary @"$TMPLOG" "${HC_PING_URL}/${HC_PING_SLUG}" > /dev/null 2>&1
    else
        curl -sfm 10 --data-binary @"$TMPLOG" "${HC_PING_URL}/${HC_PING_SLUG}/fail" > /dev/null 2>&1
    fi
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
