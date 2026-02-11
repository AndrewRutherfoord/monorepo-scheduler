#!/bin/bash
LOG_FILE="$1"
WORK_DIR="$2"
COMMAND="$3"
JOB_NAME="$4"
DOPPLER_PROJECT="$5"
DOPPLER_CONFIG="$6"

DB_PATH="/var/lib/monorepo-scheduler/runs.db"

escape_sql() {
    echo "${1//\'/\'\'}"
}

cd "$WORK_DIR" || exit 1

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
OUTPUT_FILE=$(mktemp)

# Run command, capturing output to temp file
bash -c "$COMMAND" > "$OUTPUT_FILE" 2>&1
EXIT_CODE=$?
END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

# Write to log file
{
    echo "=== START $START_TIME ==="
    cat "$OUTPUT_FILE"
    echo "=== END $END_TIME exit_code=$EXIT_CODE ==="
} >> "$LOG_FILE" 2>&1

# Record run in SQLite (with output)
if [ -f "$DB_PATH" ]; then
    HOSTNAME=$(hostname)
    OUTPUT=$(cat "$OUTPUT_FILE")
    sqlite3 "$DB_PATH" <<EOSQL
INSERT INTO runs (job_name, command, work_dir, log_file, start_time, end_time, exit_code, hostname, output)
VALUES ('$(escape_sql "$JOB_NAME")', '$(escape_sql "$COMMAND")', '$(escape_sql "$WORK_DIR")', '$(escape_sql "$LOG_FILE")', '$START_TIME', '$END_TIME', $EXIT_CODE, '$(escape_sql "$HOSTNAME")', '$(escape_sql "$OUTPUT")');
EOSQL
fi

rm -f "$OUTPUT_FILE"

# Discord notification on failure
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
