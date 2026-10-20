# 02 · TRD: Rescue Grid

## Stack

| | |
|---|---|
| **Frontend** | Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui. Maps: MapLibre GL JS with OpenStreetMap vector tiles. Field app is the same Next.js app as an installable PWA. |
| **Backend** | Python 3.12 + FastAPI (REST + WebSocket). Background workers consume Redis Streams. |
| **AI / Agents** | LangGraph pipeline for SOS understanding (extract → geocode → ask follow-ups). LLM via the Anthropic Claude API (model set in env). Embeddings stored in ChromaDB for de-duplication and landmark lookup. |
| **ML** | TensorFlow / Keras urgency model (gradient-boosted baseline first, with scikit-learn as a fallback). |
| **Optimisation** | Google OR-Tools (vehicle routing with time windows and capacities); hot paths in C++ via pybind11 if needed. |
| **Routing engine** | Self-hosted OSRM (or Valhalla) on OSM data, with dynamic road blocking for flooded segments. |
| **Database** | PostgreSQL 16 + PostGIS (spatial queries), with Alembic migrations. |
| **Event bus / cache** | Redis 7: Streams for the intake pipeline, Pub/Sub for live map updates, plus caching. |
| **Auth** | FastAPI JWT auth (fastapi-users) with roles; field teams can use magic-link or OTP login. Next.js stores the session in an httpOnly cookie. |
| **Hosting** | Docker Compose for local and demo; a single VM (AWS Lightsail / DigitalOcean / Azure) for the pilot. Vercel optional for the frontend. |

## Third-party APIs

| Service | Purpose | Tier |
|---|---|---|
| Anthropic Claude API | SOS extraction, translation, follow-up questions | Paid (pay per token) |
| Meta WhatsApp Cloud API | Inbound SOS and outbound status updates | Free tier for testing, then per-conversation pricing |
| Nominatim (self-hosted or public) | Geocoding | Free (respect rate limits) |
| Google Geocoding / Places | Fallback geocoding for landmarks | Paid, free monthly credit |
| OpenStreetMap / Geofabrik extracts | Road network, landmarks | Free |
| Bhuvan / NRSC / Copernicus EMS flood maps | Flood extent polygons | Free |
| Sentry | Error tracking | Free tier |

## Key libraries

- **Backend:** fastapi, pydantic v2, sqlalchemy 2 + geoalchemy2, alembic, redis-py, langgraph, langchain-anthropic, chromadb, ortools, shapely, rapidfuzz, httpx, structlog
- **ML:** tensorflow, scikit-learn, pandas
- **Frontend:** maplibre-gl, react-map-gl, @tanstack/react-query, zod, zustand, lucide-react, date-fns, socket client (native WebSocket)

## Folder structure

```
rescue-grid/
├─ apps/
│  ├─ web/                  # Next.js (command centre + field PWA)
│  │  ├─ app/(auth)/ app/(command)/ app/(field)/ app/sos/
│  │  ├─ components/ lib/ hooks/
│  ├─ api/                  # FastAPI
│  │  ├─ app/
│  │  │  ├─ routers/        # cases, teams, assignments, intake, auth, replay
│  │  │  ├─ models/         # SQLAlchemy models
│  │  │  ├─ schemas/        # Pydantic
│  │  │  ├─ services/       # triage, dedup, geocode, dispatch
│  │  │  ├─ agents/         # LangGraph graphs
│  │  │  ├─ workers/        # Redis Stream consumers
│  │  │  └─ core/           # config, security, db
│  │  ├─ alembic/
│  │  └─ tests/
│  └─ optimizer/            # OR-Tools dispatch service (+ optional C++ ext)
├─ data/                    # replay datasets, OSM extracts (gitignored)
├─ ml/                      # notebooks, training scripts, saved models
├─ infra/                   # docker-compose.yml, OSRM config, nginx
└─ docs/                    # these 6 documents
```

## Naming conventions

- Python: snake_case; TypeScript: camelCase vars, PascalCase components.
- DB tables are snake_case plural (`sos_messages`, `cases`).
- API routes are `/api/v1/<resource>` in kebab-case.
- Redis streams are `stream:<domain>:<event>` (e.g. `stream:intake:raw`).

## Environment variables

```
DATABASE_URL
REDIS_URL
CHROMA_HOST
ANTHROPIC_API_KEY
LLM_MODEL
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_ACCESS_TOKEN
WHATSAPP_VERIFY_TOKEN
WHATSAPP_APP_SECRET
GOOGLE_MAPS_API_KEY
NOMINATIM_URL
OSRM_URL
JWT_SECRET
JWT_EXPIRES_MIN
NEXT_PUBLIC_API_URL
NEXT_PUBLIC_WS_URL
NEXT_PUBLIC_MAP_STYLE_URL
SENTRY_DSN
```

## Constraints

- **Works on bad networks:** the field PWA must load on 3G, cache its last assignment offline, and queue status updates.
- **Mobile-first** for field teams, desktop-first for the command centre.
- **Human in the loop:** the system never dispatches without coordinator approval in v1, and every AI decision shows its reasons.
- **Latency:** an SOS should be visible on the map within 10 s of arrival, and dispatch re-planning should finish within 5 s for 500 cases and 50 teams.
- **Privacy:** phone numbers and medical info are personal data under the DPDP Act 2023. Encrypt at rest, restrict by role, and purge 90 days after the disaster.
- **Cost:** the demo must run on one 8 GB VM plus pay-per-use LLM.
- **Auditability:** every assignment and status change is logged with actor and timestamp.
