# 03 · App Flow: Rescue Grid

## Pages

| Route | Who | Description |
|---|---|---|
| `/` | Public | Landing page: what Rescue Grid is, a "Report SOS" button, and the replay demo |
| `/sos` | Public | Mobile SOS form (location pin, people, needs, phone), multilingual |
| `/sos/[trackingId]` | Public | Request status tracker ("Received → Team assigned → Rescued") |
| `/login` | Staff | Email + password (coordinators) or phone OTP (field teams) |
| `/command` | Coordinator | **Live command map**: the main screen |
| `/command/queue` | Coordinator | Triage queue: cases sorted by urgency, bulk actions |
| `/command/cases/[id]` | Coordinator | Case detail drawer: merged sources, extracted fields, score breakdown, history |
| `/command/review` | Coordinator | Human review inbox: low-confidence locations, possible duplicates |
| `/command/teams` | Coordinator | Team roster: status, capacity, live location |
| `/command/dispatch` | Coordinator | Proposed assignment plan: approve all, approve one, or override |
| `/command/intake` | Coordinator | Import CSV/Sheet, manual entry form for helpline operators |
| `/command/analytics` | Coordinator | Response-time metrics, cases by status, heatmap |
| `/command/replay` | Coordinator / demo | Pick a dataset, play/pause/speed, compare with a first-come-first-served baseline |
| `/field` | Field team | Current assignment card with route, and the next queued task |
| `/field/assignment/[id]` | Field team | Navigation, case details, call requester, status buttons |
| `/field/history` | Field team | Completed rescues |
| `/admin/disasters` | Admin | Create or close a disaster event, set the area boundary and flood layers |
| `/admin/users` | Admin | Invite users and set roles |
| `/settings` | All staff | Profile, language, notifications |

## Navigation

- **Command centre (desktop):** a left sidebar (Map, Queue, Review, Teams, Dispatch, Intake, Analytics, Replay) and a top bar with a disaster selector, live counters (Open / Critical / Teams active) and the user menu. Case details open in a **right-side drawer** over the map.
- **Field app (mobile PWA):** bottom tabs for Assignment, Map and History. Big buttons, high contrast.
- **Public:** a single-column page with no navigation, just the SOS form and tracker.

## First screen

- **New visitor:** the landing page with two buttons: "Report an emergency" and "Watch the Chennai 2015 replay".
- **Logged-in coordinator:** `/command` (live map) for the most recent active disaster.
- **Logged-in field team:** `/field`.

## Auth flow

- **Coordinator:** invited by an admin by email → sets password → `/command`. No public signup.
- **Field team:** a coordinator adds the team lead's phone → the lead gets a WhatsApp/SMS OTP link → `/field` → grants location permission → goes on duty.
- **Requester:** no account. Gets a tracking ID by WhatsApp.

## Core user journey 1: an SOS becomes a rescue

1. A relative sends on WhatsApp: "Amma and appa stuck on first floor, water rising, near Velachery bus depot behind Ganesh temple, appa on dialysis".
2. The bot replies in Tamil with a tracking link and asks for a live location pin (optional).
3. Pipeline: extract (2 people, elderly, medical: dialysis) → geocode (landmark match, confidence 0.72) → de-duplicate (merged with 2 earlier reports) → score 91 (Critical).
4. The case appears on the command map as a red pin with a pulsing ring, at the top of the queue.
5. The dispatch optimiser proposes Boat team B-07 (1.4 km away, capacity 6, route avoiding the flooded road).
6. The coordinator clicks **Approve**.
7. Team B-07's phone buzzes, and `/field` shows the case card and route. They tap **Start**.
8. On arrival they tap **Reached**, then **Rescued (2)**.
9. The case closes, the relative gets "Rescued at 14:32 by team B-07", and analytics update.

## Core user journey 2: coordinator triage and review

1. The coordinator opens `/command/review`: 14 cases need attention.
2. A low-confidence location: they drag the pin to the right street and save. The score and plan recompute.
3. A possible duplicate pair: side-by-side comparison, then **Merge** or **Keep separate**.
4. They return to `/command/dispatch` and approve the updated plan.

## Core user journey 3: replay demo

1. On `/command/replay`, choose "Chennai Dec 2015 (public SOS sheets)".
2. Set speed to 60× and press Play. Messages stream in on the timeline.
3. A split view shows Rescue Grid on the left and first-come-first-served on the right, with a live counter of critical cases reached within 3 h.

## Empty states

- **No active disaster:** "No active event. Create one or start a replay." (with a button)
- **Queue empty:** "All clear. No open cases." (illustration)
- **No teams on duty:** a warning banner, "No teams available. Dispatch is paused."
- **Field app with no assignment:** "Stand by. You'll be notified when assigned." plus an on-duty toggle.

## Error states

- **WebSocket disconnected:** a yellow banner, "Live updates paused, reconnecting…"; auto-retry with backoff and a last-updated timestamp.
- **Geocoding failed:** the case goes to the Review inbox with "Location unknown".
- **LLM or API failure:** the raw message is still stored and shown, and the case is marked "Needs manual reading".
- **Field app offline:** actions are queued locally with an "Offline: 3 updates pending" chip, then synced when back online.
- **Optimiser timeout:** the previous plan stays and a "Plan may be stale" chip appears; the coordinator can assign manually.
- **403/401:** redirect to `/login`, keeping the return URL.

## Modals and drawers

- **Case drawer** (right): fields, sources, score breakdown, timeline, actions (assign, merge, mark false alarm).
- **Assign modal:** choose a team manually, with ETA shown for each candidate.
- **Merge modal:** compare two cases side by side.
- **Confirm modals** for closing a case or ending a disaster.

## Redirects

- After login → `/command` (coordinator) or `/field` (team).
- After logout → `/login`.
- After SOS form submit → `/sos/[trackingId]`.
- An unauthenticated visit to `/command/*` or `/field/*` → `/login?next=…`.
- A field user visiting `/command` → `/field` (role guard).
