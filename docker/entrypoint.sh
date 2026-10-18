#!/bin/bash
set -e

mkdir -p /app/data /app/user_credentials
touch /app/data/cron.log

# Export environment variables for cron
printenv | grep -Ev '^(HOME|PWD|OLDPWD|SHLVL|_)=' > /etc/environment

# Start cron daemon
if [ "$1" = "gunicorn" ]; then cron; fi

# Run migrations if applicable
python run.py migrate --check 2>/dev/null || true

# Execute container command
exec "$@"
