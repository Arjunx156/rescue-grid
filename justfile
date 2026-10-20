set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set dotenv-load := false

# the root .env also fills the ${VARS} in the compose file
compose := "docker compose --env-file .env -f infra/docker-compose.yml"

default: check

# First run: secrets, dependencies, database, demo data
setup:
    cd apps/api; uv run python scripts/gen_env.py
    cd apps/api; uv sync
    cd apps/web; bun install
    just up
    just migrate
    just seed

# Postgres+PostGIS and Redis in Docker
up:
    {{compose}} up -d --build db redis

down:
    {{compose}} down

# API (with workers inline) and web app together
dev:
    bun x concurrently@9.2.1 -k -n api,web -c blue,green "just api" "just web"

api:
    cd apps/api; uv run uvicorn app.main:app --reload --port 8000 --reload-dir app --timeout-graceful-shutdown 3

worker:
    cd apps/api; uv run python -m app.workers

web:
    cd apps/web; bun run dev

migrate:
    cd apps/api; uv run alembic upgrade head
    cd apps/api; uv run alembic -x url=postgresql+asyncpg://rescuegrid:rescuegrid@localhost:5432/rescuegrid_test upgrade head

seed:
    cd apps/api; uv run python -m app.seed

# Dev only: empty the database and Redis, then seed again
reset:
    cd apps/api; uv run python -m app.seed --reset

# Rescue Grid vs first-come-first-served on the replay; writes data/replay/chennai-2015/benchmark.json
bench:
    cd apps/api; uv run python -m app.sim.benchmark
    cd apps/api; uv run python scripts/export_landing.py

# Extraction, geocoding and de-duplication quality on the labelled replay
eval:
    cd apps/api; uv run python -m evals.run

# Regenerate the synthetic replay and its flood zones
replay-data:
    cd apps/api; uv run python scripts/build_flood_zones.py
    cd apps/api; uv run python scripts/make_replay.py

# TypeScript types for the web app from the API's OpenAPI schema
types:
    cd apps/api; uv run python -c "import json, app.main as m; open('../web/lib/openapi.json','w').write(json.dumps(m.app.openapi()))"
    cd apps/web; bun x openapi-typescript@7.9.1 lib/openapi.json -o lib/api-types.ts

# Format check, lint, types and tests for both apps (must pass before any commit)
check: check-api check-web

check-api:
    cd apps/api; uv run ruff format --check .
    cd apps/api; uv run ruff check .
    cd apps/api; uv run basedpyright
    cd apps/api; uv run pytest -q

check-web:
    cd apps/web; bun x biome check .
    cd apps/web; bun x tsc --noEmit
    cd apps/web; bun test

fmt:
    cd apps/api; uv run ruff format .
    cd apps/api; uv run ruff check --fix .
    cd apps/web; bun x biome check --write .

test:
    cd apps/api; uv run pytest -q
    cd apps/web; bun test

# Browser journeys against a running stack (just dev in another terminal)
e2e:
    cd apps/web; bun x playwright test

# Everything in containers behind Caddy, as on the demo VM
stack:
    {{compose}} --profile stack up -d --build
