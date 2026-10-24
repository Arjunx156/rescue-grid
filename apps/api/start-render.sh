#!/bin/sh
# Render's free tier: no pre-deploy step and no shell around dockerCommand, so the
# whole boot lives here. Migrating and seeding are both idempotent.
set -e
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
