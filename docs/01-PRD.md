# 01 · PRD: Rescue Grid

| | |
|---|---|
| **App Name** | Rescue Grid |
| **Tagline** | Turns thousands of chaotic flood SOS messages into a live, prioritised rescue plan. |
| **Version** | v1 (MVP) |

## Problem

During urban floods and cyclones (Chennai 2015 and 2023, Kerala 2018, Wayanad 2024), SOS requests pour in through WhatsApp forwards, X posts, helpline calls and volunteer Google Sheets. They are:

- **Duplicated:** the same family reported by five relatives.
- **Vague:** "behind the Murugan temple near the bus depot", with no pin.
- **Stale:** already rescued, but still circulating.
- **Unprioritised:** a dialysis patient on a rooftop sits in the same list as a request for food parcels.

Rescue teams (NDRF, SDRF, fire services, fishermen with boats, volunteer groups) have no shared picture of who needs help most and who is going where. Teams chase duplicates while critical cases wait.

**Who feels it:** stranded residents and their relatives, and the control-room coordinators and field teams trying to help them.

## Core value proposition

Rescue Grid is the **single live source of truth** during a disaster. It pulls in SOS from every channel, turns each into a clean, located, de-duplicated and risk-scored case, and **assigns and routes rescue teams automatically**, re-planning as water levels and roads change. Existing tools are spreadsheets, WhatsApp groups, or generic incident dashboards that need manual entry.

## Target users

- **Control-room coordinator (primary):** works at a district/state emergency operations centre or a large NGO. Overwhelmed by thousands of messages, needs to decide in seconds who goes where, and is accountable for the outcome.
- **Field team lead:** leads a boat crew or rescue squad and has a phone with patchy connectivity. Needs one clear next assignment, the route, and who to call.
- **Requester / relative:** stranded or worried about family. Wants to report once, in their language, and know someone is coming.

## Core features (Must Have)

1. **Multi-channel intake:** WhatsApp bot, a web SOS form, CSV/Google Sheet import, and manual entry for helpline operators.
2. **AI understanding:** extract location, headcount, vulnerable people (elderly, children, pregnant, disabled, medical needs), water level and phone number from free text in English, Tamil, Hindi, Malayalam and Telugu.
3. **Geocoding with confidence:** map vague landmarks to coordinates and flag low-confidence cases for a human to confirm.
4. **De-duplication:** cluster reports of the same household or location into one case and keep every source linked.
5. **Risk triage:** an explainable 0–100 urgency score (vulnerability, water depth trend, time since report, medical need).
6. **Team registry and live location:** teams register their asset type (boat, truck, medical team), capacity and live location.
7. **Auto-dispatch:** suggest the best assignment and route for each team (the coordinator approves or overrides), avoiding flooded roads.
8. **Live command map:** cases, teams, routes and flood zones on one map with filters.
9. **Field app:** the team sees its next assignment, navigation, and buttons for "reached", "rescued" and "unable to reach".
10. **Close the loop:** automatic WhatsApp updates to the requester ("Team assigned", "Rescued").
11. **Disaster replay mode:** replay a historical SOS dataset on a timeline for demos, training and benchmarking.

## Nice to have (v2)

- Ingest public X/Twitter posts by keyword.
- Voice-note SOS with speech-to-text.
- Flood-depth nowcast layer from rainfall and elevation.
- Relief supply logistics (food, medicine drops).
- Offline-first field app with SMS fallback.
- Volunteer self-registration with verification.
- Multi-agency views (police, NDRF, NGOs) with permissions.

## Out of scope (v1)

- Predicting floods (we consume flood maps; we don't forecast them).
- Payment or donations.
- Shelter management.
- Native iOS/Android apps (the v1 field app is a mobile web PWA).
- Live production integration with government systems (v1 is a pilot or demo).

## User stories

- As a **coordinator**, I want every incoming SOS automatically located, de-duplicated and scored, so that I see the 20 most critical cases first instead of 2,000 raw messages.
- As a **coordinator**, I want the system to propose which team goes where, so that I only approve or adjust instead of planning manually.
- As a **coordinator**, I want to correct a wrong location on the map, so that the team is not sent to the wrong place.
- As a **field team lead**, I want my next assignment and a route that avoids flooded roads, so that I reach people faster.
- As a **field team lead**, I want to mark a case rescued or unreachable in one tap, so that the control room stays current.
- As a **relative**, I want to send an SOS on WhatsApp in Tamil and get updates, so that I know help is coming.
- As a **demo viewer or judge**, I want to replay the Chennai 2015 flood and see Rescue Grid against first-come-first-served, so that the impact is obvious.

## Success metrics

- **Median time from SOS to team assignment:** under 2 minutes, against a manual baseline that takes hours (replay benchmark).
- **Critical cases rescued within 3 hours:** ≥ 30% more than first-come-first-served (replay simulation).
- **Duplicate reduction:** ≥ 60% of raw messages merged correctly (precision ≥ 95%).
- **Geocoding:** ≥ 85% of cases within 300 m of the true location; 100% of low-confidence cases flagged.
- **Extraction accuracy:** ≥ 90% F1 on headcount and vulnerability fields on a labelled test set.
- **Pilot:** at least one NGO or district control room uses it in a drill.
