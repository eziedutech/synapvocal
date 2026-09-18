#!/bin/sh
# Migrate first when contributions have a database. A failed migration is logged and
# the server starts anyway: the Bridge needs no database, and contribution routes
# then report their own errors instead of the whole service being down.
if [ -n "$DATABASE_URL" ]; then
  alembic upgrade head || echo "ERROR migration failed; contributions will not work until DATABASE_URL is fixed" >&2
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
