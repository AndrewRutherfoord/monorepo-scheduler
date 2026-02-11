#!/bin/bash
LOG_FILE="$1"
WORK_DIR="$2"
COMMAND="$3"
JOB_NAME="$4"
DOPPLER_PROJECT="$5"
DOPPLER_CONFIG="$6"
RUN_LOG="$7"

cd "$WORK_DIR" || exit 1

START_TS=$(date '+%Y-%m-%d %H:%M:%S')
START_EPOCH=$(date +%s)

{
    echo "=== START $START_TS ==="
    bash -c "$COMMAND"
    EXIT_CODE=$?
    echo "=== END $(date '+%Y-%m-%d %H:%M:%S') exit_code=$EXIT_CODE ==="
} >> "$LOG_FILE" 2>&1

END_EPOCH=$(date +%s)
DURATION=$((END_EPOCH - START_EPOCH))

# Append to run log CSV
if [ -n "$RUN_LOG" ]; then
    if [ ! -f "$RUN_LOG" ]; then
        echo "timestamp,job_name,exit_code,duration_seconds" > "$RUN_LOG"
    fi
    echo "$START_TS,$JOB_NAME,$EXIT_CODE,$DURATION" >> "$RUN_LOG"
fi

if [ "$EXIT_CODE" -ne 0 ] && [ -n "$DOPPLER_PROJECT" ]; then
    WEBHOOK_URL=$(doppler secrets get DISCORD_WEBHOOK_URL --project "$DOPPLER_PROJECT" --config "$DOPPLER_CONFIG" --plain 2>/dev/null)
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
