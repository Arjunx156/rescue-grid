# 06 · Implementation Plan: Rescue Grid

Build order: foundation → data → the core pipeline (intake → understanding → resolution → triage) → dispatch → field loop → replay benchmark → polish → deploy. Each phase ends with explicit "done" criteria.

## Phase 1: Setup
- Create the monorepo (`apps/web`, `apps/api`, `apps/optimizer`, `ml`, `infra`, `docs`) and put these 6 docs in `docs/`.
- Docker Compose: Postgres+PostGIS, Redis, ChromaDB, OSRM (Chennai OSM extract), api, web.
- FastAPI skeleton with config (pydantic-settings), structlog, health check. Next.js 14 + Tailwind + shadcn/ui + MapLibre base map.
- `.env.example` with every variable from the TRD; pre-commit (ruff, black, eslint, prettier); GitHub Actions running lint and tests.
- **Done:** `docker compose up` brings everything up; `/health` returns OK; the web app shows a map of Chennai.

## Phase 2: Database
- SQLAlchemy models + Alembic migrations for every table in the schema, including PostGIS indexes.
- Encryption helper for sensitive columns, plus hash columns.
- Seed script: 1 organization, 1 admin, 1 coordinator, 10 teams with locations, 1 disaster with an area polygon and sample flood zones.
- **Done:** migrations run clean from zero; seed data is visible via `psql`; a unit test proves encrypt/decrypt round-trips.

## Phase 3: Auth
- fastapi-users: email/password for staff, WhatsApp OTP for field leads (stub OTP in dev).
- JWT access + refresh cookie; role and organization dependencies; Next.js middleware route guards for `/command/*` and `/field/*`.
- Admin user invite flow.
- **Done:** a coordinator logs in and reaches `/command`; a field lead logs in by OTP and reaches `/field`; cross-role access returns 403 (tests).

## Phase 4: Core feature 1, intake pipeline
- `POST /sos` web form, CSV import, and WhatsApp webhook (signature check) → `stream:intake:raw`, idempotent on `(channel, external_id)`.
- Replay loader: reads a `.jsonl` dataset and emits messages at scaled timestamps.
- **Build the replay dataset:** collect public Chennai 2015/2023 SOS sheets and posts, clean and anonymise them, and hand-label about 300 messages (location, people, vulnerability, duplicate groups) as the test set.
- **Done:** messages from all 4 channels land in `sos_messages`; replay streams 1,000 messages at 60× speed.

## Phase 5: Core feature 2, understanding (LangGraph)
- Graph: `detect_language → extract_fields (structured output) → validate → maybe_ask_followup (WhatsApp) → emit`.
- Pydantic schema for extraction; retries and fallback to `needs_manual_reading`.
- Evaluate on the labelled set: ≥ 90% F1 on people and vulnerability fields.
- **Done:** every message gets an `extractions` row; the eval script prints accuracy; the follow-up question works in the WhatsApp sandbox.

## Phase 6: Core feature 3, resolution (geocode + de-duplication) and triage
- Geocoder chain: shared pin → landmark vector search (ChromaDB `landmarks`) → Nominatim → Google fallback, with a confidence score; under 0.6 goes to `needs_review`.
- De-duplication: candidates within 300 m and 12 h → embedding similarity + phone hash + name fuzzy match → merge into a case.
- Urgency score v1: a transparent weighted rule model (vulnerability, medical, water level, time waiting, inside a flood zone), with a `score_breakdown`. v2: train a TensorFlow/GBM model on labelled priorities.
- **Done:** ≥ 85% of test cases are within 300 m; dedup precision ≥ 95%; the queue API returns cases sorted by score with breakdowns.

## Phase 7: Core feature 4, command centre UI
- Live map (cases, teams, flood zones, clustering), queue table, case drawer, review inbox (location fix, merge UI), teams page.
- WebSocket `/ws/disasters/{id}` fed by Redis Pub/Sub; React Query cache patched by events.
- **Done:** during a replay, new cases appear on the map within 10 s, and a coordinator can fix a location and merge duplicates.

## Phase 8: Core feature 5, dispatch optimiser
- OR-Tools VRP: teams as vehicles (capacity, start location), cases as nodes (priority = penalty for dropping, service time), travel times from OSRM with flooded segments excluded.
- Objective: maximise the urgency-weighted number of people reached, minus travel time. Rolling re-plan on triggers (debounced 5 s), warm-started from the current plan.
- Dispatch page: proposed plan, approve all or one, manual override.
- **Done:** a plan for 500 cases and 50 teams in under 5 s; approved assignments show routes on the map.

## Phase 9: Core feature 6, field app and closing the loop
- PWA: current assignment, route (MapLibre + OSRM geometry), Start / Reached / Rescued / Can't reach, location pings every 15 s on duty, offline queue (IndexedDB + background sync).
- WhatsApp updates to requesters on assignment and rescue; public `/sos/[code]` tracker.
- **Done:** a full journey works end to end on a phone: SOS → assignment → rescued → requester notified.

## Phase 10: Core feature 7, replay benchmark and analytics
- Simulation mode: virtual teams move along routes at asset speeds and complete cases automatically.
- Baseline policy (first-come-first-served, nearest free team) run side by side with Rescue Grid on the same replay.
- Analytics page: median time to assignment, critical cases reached within 3 h, duplicates removed, chart over time.
- **Done:** one command produces a comparison report; the result clearly shows the improvement (target ≥ 30% more critical cases reached within 3 h).

## Phase 11: UI polish
- Loading skeletons, empty and error states from the App Flow, keyboard shortcuts, i18n (en/ta/hi/ml/te), reduced motion, AA contrast check, responsive tablet layout.
- **Done:** every page in the App Flow has its empty, loading and error states; a Lighthouse accessibility score ≥ 90.

## Phase 12: Testing and hardening
- pytest (services, API, auth), Playwright end-to-end for journeys 1–3, load test (Locust: 50 messages/s intake), chaos tests (kill the worker, drop the WebSocket, LLM timeout).
- Security: webhook signature, rate limits, personal-data masking for viewers, dependency scanning.
- **Done:** CI green; the load test sustains 50 messages/s with p95 time-to-map under 10 s; no critical security findings.

## Phase 13: Deploy
- Single VM with Docker Compose + Caddy/nginx (HTTPS), daily Postgres backups, Sentry, uptime monitor.
- A public demo URL with replay mode and seeded demo accounts; a 3-minute demo video.
- **Done:** a public URL is live; the replay demo runs reliably; the README has setup steps.

## Done criteria (v1)

- The full journey works end to end with real WhatsApp messages and in replay mode.
- The replay benchmark shows Rescue Grid beating first-come-first-served on critical cases reached within 3 h.
- All PRD success metrics are measured and reported in the README.
- Ready to show an NGO or district disaster management authority for a pilot drill.
