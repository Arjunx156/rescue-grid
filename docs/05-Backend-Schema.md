# 05 · Backend Schema: Rescue Grid

PostgreSQL 16 + PostGIS. All `id`s are `uuid` (default `gen_random_uuid()`). All tables have `created_at timestamptz default now()` and `updated_at timestamptz`. Geometry uses SRID 4326.

## Tables

### users
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| email | text unique null | coordinators/admins |
| phone | text unique null | field teams (E.164) |
| name | text | |
| password_hash | text null | null for OTP-only users |
| role | text | `admin` \| `coordinator` \| `field_lead` \| `viewer` |
| organization_id | uuid FK → organizations.id | |
| preferred_language | text | `en`, `ta`, `hi`, `ml`, `te` |
| is_active | bool | |

### organizations
| id uuid PK | name text | type text (`govt`, `ngo`, `volunteer`) |

### disasters
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text | e.g. "Chennai Floods Dec 2023" |
| status | text | `active` \| `closed` \| `replay` |
| area | geometry(MultiPolygon) | operational boundary |
| started_at / ended_at | timestamptz | |

### flood_zones
| id uuid PK | disaster_id FK | geom geometry(MultiPolygon) | depth_estimate_m numeric null | source text | valid_from timestamptz |

### sos_messages (raw intake, immutable)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| disaster_id | uuid FK | |
| channel | text | `whatsapp` \| `web_form` \| `csv_import` \| `helpline` \| `twitter` \| `replay` |
| external_id | text null | WhatsApp message id etc. (unique per channel) |
| sender_phone | text null | **encrypted** |
| raw_text | text | **encrypted** |
| raw_location | geometry(Point) null | if a pin was shared |
| received_at | timestamptz | |
| processing_status | text | `pending` \| `processed` \| `failed` |
| case_id | uuid FK → cases.id null | set after dedup |

### extractions (LLM output per message)
| id uuid PK | sos_message_id FK unique | people_count int | vulnerable jsonb (`{elderly:1, child:0, pregnant:0, disabled:0, medical:["dialysis"]}`) | location_text text | water_level text | needs text[] | language text | model text | confidence numeric | raw_json jsonb |

### cases (one real-world household/location)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| disaster_id | uuid FK | |
| tracking_code | text unique | short public code, e.g. `RG-7K3P` |
| location | geometry(Point) | best estimate |
| location_confidence | numeric | 0–1 |
| location_source | text | `pin` \| `geocoded` \| `manual` |
| address_text | text | |
| people_count | int | |
| vulnerability | jsonb | merged |
| urgency_score | int | 0–100 |
| urgency_level | text | `critical` \| `high` \| `medium` \| `low` |
| score_breakdown | jsonb | explainability |
| status | text | `new` \| `needs_review` \| `queued` \| `assigned` \| `en_route` \| `on_scene` \| `rescued` \| `unreachable` \| `duplicate` \| `false_alarm` \| `closed` |
| merged_into_id | uuid FK → cases.id null | |
| contact_phone | text null | **encrypted** |
| first_reported_at / last_reported_at | timestamptz | |
| source_count | int | |

### teams
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| disaster_id | uuid FK | |
| organization_id | uuid FK | |
| call_sign | text | e.g. `B-07` |
| asset_type | text | `boat` \| `truck` \| `medical` \| `foot` \| `helicopter` |
| capacity | int | people per trip |
| lead_user_id | uuid FK → users.id | |
| status | text | `off_duty` \| `available` \| `assigned` \| `en_route` \| `on_scene` \| `returning` |
| current_location | geometry(Point) | |
| location_updated_at | timestamptz | |
| base_location | geometry(Point) null | drop-off / relief camp |

### team_locations (time series)
| id bigserial PK | team_id FK | location geometry(Point) | recorded_at timestamptz | speed numeric null |

### dispatch_plans
| id uuid PK | disaster_id FK | created_by text (`optimizer`/user id) | status text (`proposed`/`approved`/`superseded`) | objective_value numeric | solver_ms int | created_at |

### assignments
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| case_id | uuid FK | |
| team_id | uuid FK | |
| plan_id | uuid FK null | null for manual assignments |
| sequence | int | order in the team's route |
| route | geometry(LineString) null | |
| eta | timestamptz null | |
| status | text | `proposed` \| `approved` \| `started` \| `reached` \| `completed` \| `failed` \| `cancelled` |
| approved_by | uuid FK → users.id null | |
| outcome_people_rescued | int null | |
| outcome_note | text null | |

### case_events (audit log, append-only)
| id bigserial PK | case_id FK | actor_type text (`system`/`user`/`team`) | actor_id uuid null | event_type text | payload jsonb | created_at |

### outbound_messages
| id uuid PK | case_id FK | channel text | to_phone text (**encrypted**) | template text | body text | status text (`queued`/`sent`/`delivered`/`failed`) | provider_message_id text |

### replay_datasets
| id uuid PK | name text | description text | source_url text | message_count int | file_path text |

## Relationships

- organizations 1—* users, 1—* teams
- disasters 1—* sos_messages, cases, teams, flood_zones, dispatch_plans
- sos_messages *—1 cases (many messages merge into one case)
- sos_messages 1—1 extractions
- cases 1—* assignments, case_events, outbound_messages
- teams 1—* assignments, team_locations
- dispatch_plans 1—* assignments
- cases.merged_into_id → cases.id (self-reference for merged duplicates)

## Indexes

- GIST: `cases.location`, `teams.current_location`, `flood_zones.geom`, `disasters.area`, `team_locations.location`
- `cases (disaster_id, status, urgency_score DESC)`: the triage queue
- `sos_messages (channel, external_id)` unique: idempotent intake
- `sos_messages (processing_status)` partial where `pending`
- `team_locations (team_id, recorded_at DESC)`
- `case_events (case_id, created_at)`
- `cases (tracking_code)` unique

## Vector store (ChromaDB)

- Collection `sos_embeddings`: id is sos_message_id; metadata `{disaster_id, case_id, lat, lng, received_at}`. Used for semantic de-duplication (combined with distance under 300 m and a time window).
- Collection `landmarks`: OSM POIs and local landmark aliases ("Ganesh temple Velachery") → coordinates. Used for geocoding vague text.

## Redis

- Stream `stream:intake:raw` → worker `extract` → `stream:intake:extracted` → worker `resolve` (geocode + dedup + score) → `stream:cases:updated`
- Stream `stream:dispatch:trigger`: debounced re-plan requests
- Pub/Sub `ws:disaster:{id}`: fan-out to command-centre WebSockets
- Keys: `team:{id}:loc` (latest location, TTL 5 min), rate limits `rl:{phone}`

## Auth provider

FastAPI JWT (fastapi-users). Access token 30 min plus a refresh token in an httpOnly cookie. Field teams use phone OTP (sent over WhatsApp) giving a long-lived device session (7 days, revocable).

## User roles and permissions

| Role | Access |
|---|---|
| admin | Everything; manage disasters, organizations and users |
| coordinator | Read and write cases, teams and assignments for disasters their organization is attached to; approve plans |
| field_lead | Read only their own team's assignments and those cases' details; update assignment status and team location |
| viewer | Read-only command map and analytics, with **masked phone and medical fields** |
| public | Create an SOS; read the status of their own tracking code only (no personal fields) |

Enforcement is in the FastAPI dependency layer (role + organization + disaster scope). Optionally add Postgres Row Level Security on `cases` and `assignments` keyed by `organization_id` as defence in depth.

## Sensitive fields

- `sender_phone`, `raw_text`, `contact_phone`, `to_phone`: encrypted at the application level (Fernet/AES-GCM, key in env or KMS); deterministic hash columns (`*_hash`) for lookup.
- Medical info inside `vulnerability`: visible only to coordinator and field_lead.
- Retention: a purge job deletes personal fields 90 days after `disasters.ended_at`.

## File storage

- `data/replay/{dataset_id}.jsonl`: replay datasets (local disk or S3-compatible bucket).
- `uploads/{disaster_id}/imports/{file}.csv`: imported sheets.
- WhatsApp media (photos or voice) at `media/{disaster_id}/{sos_message_id}.*` (v2).

## Webhooks and event triggers

- `POST /api/v1/webhooks/whatsapp`: Meta webhook (signature verified with `WHATSAPP_APP_SECRET`) → push to `stream:intake:raw`.
- `GET /api/v1/webhooks/whatsapp`: verification challenge.
- Any case or team change → publish to `ws:disaster:{id}`.
- Case reaches `critical`, or a team goes `available` → enqueue `stream:dispatch:trigger` (debounced 5 s).
- Assignment `approved` → push notification to the field lead plus a WhatsApp update to the requester.

## API endpoints (v1)

```
POST   /api/v1/auth/login | /auth/otp/request | /auth/otp/verify | /auth/refresh | /auth/logout
GET    /api/v1/disasters                     POST /api/v1/disasters
GET    /api/v1/disasters/{id}/cases?status=&min_score=&bbox=
GET    /api/v1/cases/{id}                    PATCH /api/v1/cases/{id}
POST   /api/v1/cases/{id}/merge              POST /api/v1/cases/{id}/assign
GET    /api/v1/review?disaster_id=
POST   /api/v1/sos                           (public web form)
GET    /api/v1/sos/{tracking_code}           (public status)
POST   /api/v1/intake/import                 (CSV upload)
GET    /api/v1/teams?disaster_id=            POST /api/v1/teams   PATCH /api/v1/teams/{id}
POST   /api/v1/teams/{id}/location
GET    /api/v1/dispatch/plan?disaster_id=    POST /api/v1/dispatch/plan/{id}/approve
POST   /api/v1/dispatch/replan
GET    /api/v1/field/assignments/current     PATCH /api/v1/field/assignments/{id}
GET    /api/v1/analytics/summary?disaster_id=
POST   /api/v1/replay/start | /replay/pause | /replay/speed
WS     /ws/disasters/{id}
```
