#!/usr/bin/env bash
set -e

echo "Starting Telegram bot + admin panel..."

python main.py &
BOT_PID=$!

python run_admin.py &
ADMIN_PID=$!

trap "kill $BOT_PID $ADMIN_PID" SIGTERM SIGINT

wait $BOT_PID $ADMIN_PID
