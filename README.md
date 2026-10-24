# Rescue Grid

When a city floods, help arrives as a flood of its own: WhatsApp forwards, form posts, spreadsheet rows and phone calls, half of them duplicates, many with no usable address, all of them getting older by the minute. Rescue Grid reads every one in English, Tamil, Hindi, Malayalam or Telugu, pins it to a street, merges the reports that describe the same family, ranks who is in most danger and proposes which boat goes where. A coordinator approves, the crew's phone buzzes, and the family gets a text when they're safe.

On a replay of 1,062 messages shaped like the public Chennai 2015 SOS sheets, with the same 28 teams on both sides:

| | Rescue Grid | First come, first served |
|---|---|---|
| Critical families reached within 3 hours | **54 of 103** | 8 of 103 |
| Median wait for a team, critical cases | **63 min** | 22.7 h |
| People rescued | **1,763** | 660 |
| Wasted trips (already rescued, wrong place, gone) | **101** | 184 |

The replay is synthetic, with ground truth for every household, so these are numbers we can check rather than anecdotes. `just bench` regenerates them.

## Quick start

You need Docker, [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh) and [just](https://just.systems).

```sh
just setup   # secrets, dependencies, Postgres and Redis, migrations, a seeded drill
just dev     # API on :8000, web app on :3100
```

Open http://localhost:3100 and press **Open the live demo**. The login page signs you in as a coordinator, admin, viewer or field lead in one click. To watch the whole thing move, go to **Replay**, pick Chennai 2015 and press play at 60x.

## How it works

**Intake.** Messages land from the WhatsApp Cloud API (signature-checked), the public SOS form, CSV uploads and a helpline form, and queue on a Redis stream. Every sender gets a tracking code in their own language.

**Understanding.** A rule-based multilingual reader pulls out headcount, children, elders, pregnancy, medical needs, water level and whether it's rising. It needs no model and sends nothing off the machine. Gemini or a local Ollama model can sit on top: phone numbers are stripped first, output is schema-checked, and anything either reader notices is kept, so a model can add detail but never erase a warning.

**Location.** A gazetteer built from OpenStreetMap matches landmarks and localities across scripts ("Velachery", "வேளச்சேரி" and "velacheri" are the same place), with phonetic keys for the spellings people actually type. Every pin carries a calibrated confidence. Below 0.6 it goes to a human with the candidates on a map.

**De-duplication.** The same family gets reported five times by five relatives. Matching weighs phone numbers in the text, distance, door numbers, names, headcount, water level and timing, and subtracts for conflicts. Confident pairs merge, close calls go to review, and a report near a family that was just rescued is flagged before a boat goes back.

**Triage.** A 0 to 100 score with every point explained: who is there, how deep the water is, how long they've waited, whether it's rising. Coordinators see the reasons, not just the number.

**Dispatch.** OR-Tools solves a prize-collecting vehicle routing problem over the open cases and the teams on duty. It respects boat versus truck reach at the reported depth, capacity, and soft deadlines for critical cases. It replans on every change, shows why each team got each stop, and never sends anyone until a coordinator approves.

**The field.** Crews get an installable app with one big button per step (Start, Reached, Rescued) that queues taps offline and syncs when signal returns. Families follow their tracking code on a page that needs no login.

## Measured quality

`just eval` runs a property-based eval set and the full replay, writes the numbers the landing page shows, and fails the build if any metric drops below its floor. Current results with the local reader, no model:

| | Result | PRD target |
|---|---|---|
| Headcount correct | 95.9% | 90% |
| Vulnerability F1 | 97.9% | 90% |
| Language detected | 99.8% | |
| Located within 300 m (auto-accepted pins) | 88.7% | 85% |
| Merges that were right | 99.6% | 95% |
| True duplicates merged automatically | 50.0% | 60% |
| True duplicates merged or sent to review | 66.3% | |
| Time per message | 7.2 ms | |

Automatic merging is the one number below target. It's tuned for precision on purpose: merging two different families hides one of them, while a missed merge costs a coordinator one click in review.

## Running it for real

Everything runs behind Caddy on one origin with `just stack`. Put a domain in `SITE_ADDRESS` and Caddy fetches the HTTPS certificate itself. Then in `.env`:

- set `ENV=prod`, `COOKIE_SECURE=true`, `DEMO_MODE=false` and `OTP_DEV_ECHO=false`, and point `PUBLIC_BASE_URL` and `CORS_ORIGINS` at the domain (the API refuses to boot in prod with development secrets)
- fill the four `WHATSAPP_*` values to receive and answer messages on WhatsApp
- set `CONTACT_EMAIL` so the privacy page tells people where to ask for deletion
- leave `LLM_PROVIDER=local` unless your agency has decided that sending message text to a hosted model is acceptable

For flood-aware road routing, start Valhalla with `docker compose --env-file .env -f infra/docker-compose.yml --profile routing up -d` (the first boot builds South India's road tiles, about 20 minutes), then set `ROUTER=valhalla` and `ROUTER_URL=http://valhalla:8002` (or `http://localhost:8002` for `just dev`).

### On free tiers

The public demo runs without a VM. The API and a Key Value store come up on Render from `render.yaml` (New, then Blueprint, then this repo), with migrations, seeding and the workers inside the one free instance. Postgres with PostGIS lives on Neon: paste its connection string as `DATABASE_URL` and the API adapts it for asyncpg. The web app deploys to Vercel with `apps/web` as its root, `API_INTERNAL_URL` set to the Render URL and `NEXT_PUBLIC_WS_URL` set to the same host over `wss://`. Vercel proxies HTTP but not WebSockets, so the browser fetches a 60-second ticket through the proxy and opens its socket straight to the API. A free Render instance sleeps after 15 idle minutes, so the first visit after a quiet spell takes about a minute.

## Privacy and security

Phone numbers, names and message text are encrypted at rest. Viewers never see phones or diagnoses, and the masking happens on the server, including over the WebSocket. Ninety days after a disaster closes, a worker deletes every personal field and keeps the anonymous operational record. Sessions are short-lived JWTs with rotating refresh tokens. Writes need a CSRF header, WebSockets check their origin, and production pages ship a strict Content-Security-Policy.

## Commands

| | |
|---|---|
| `just check` | ruff, basedpyright, pytest, Biome, tsc and bun test; CI runs the same |
| `just e2e` | Playwright journeys and axe accessibility checks against a running stack |
| `just eval` | extraction, location and de-duplication quality on the replay |
| `just bench` | Rescue Grid against first come, first served |
| `just reset` | empty the dev database and seed the drill again |
| `just types` | regenerate the web app's API types from the OpenAPI schema |

## Layout

```text
apps/api     FastAPI, SQLAlchemy, Alembic, Redis workers, OR-Tools; tests and evals
apps/web     Next.js 16 command centre, field PWA, public SOS and tracker; Playwright e2e
data         OSM gazetteer, water bodies and the Chennai 2015 replay
docs         PRD, technical design, flows, UI brief, schema and plan
infra        Docker Compose, Caddy, Postgres with PostGIS and pgvector
```

## Credits

Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, under the ODbL. Map tiles from [OpenFreeMap](https://openfreemap.org). Dispatch optimisation by [Google OR-Tools](https://developers.google.com/optimization).

Engineered by Arjun Krishnan.
