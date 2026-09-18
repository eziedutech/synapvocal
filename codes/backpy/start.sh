#!/bin/sh
# Migrate first when contributions have a database; the Bridge alone needs none.
set -e
if [ -n "$DATABASE_URL" ]; then
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
