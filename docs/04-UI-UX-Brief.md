# 04 · UI/UX Design Brief: Rescue Grid

| | |
|---|---|
| **Aesthetic** | "Mission control": dark, dense, calm under pressure. Data-first, no decoration. Think Linear's polish plus an air-traffic-control screen. Colour is reserved for **meaning** (urgency and status), never for decoration. |
| **Primary Color** | `#3B82F6` (signal blue) for interactive elements and team markers |
| **Background Color** | Command centre: `#0B0F14` (near-black), panels `#121821`, borders `#1F2937`. Field app and public pages: light mode, `#FFFFFF` background, `#F3F4F6` panels. |
| **Text Color** | Dark: `#E5E7EB` primary, `#9CA3AF` secondary. Light: `#111827` primary, `#4B5563` secondary. |
| **Accent / CTA Color** | `#3B82F6` for primary actions; `#22C55E` for "Approve" and "Rescued" |
| **Urgency scale** | Critical `#EF4444` · High `#F97316` · Medium `#EAB308` · Low `#22C55E` · Closed `#6B7280`. Always paired with a text label or icon, never colour alone. |
| **Font** | Inter for UI; JetBrains Mono for IDs, timestamps and coordinates. Noto Sans Tamil / Devanagari / Malayalam / Telugu for regional text. |
| **Type scale** | 12 / 14 (body) / 16 / 20 / 24 / 32. The command centre uses 14 px body for density; the field app uses 16–18 px body for glanceability. |
| **Border Radius** | 6 px for inputs and cards, 9999 px for status pills |
| **Shadows** | None in dark mode (use 1 px borders and elevation by background shade); subtle `0 1px 2px rgba(0,0,0,.08)` in light mode |
| **Dark/Light Mode** | Command centre is dark by default (long shifts, wall screens). Field app and public SOS are **light by default** (outdoor sunlight readability), with a dark toggle. |
| **Reference Apps** | Linear (density, keyboard), Vercel dashboard (clean panels), Uber driver app (one clear next action), Flightradar24 (live map), Grafana (live counters) |
| **Mobile** | Field app and SOS are mobile-first with bottom tabs, minimum 48 px tap targets and one primary action per screen. The command centre is desktop-first (≥ 1280 px) and usable on tablet. |

## Key UI patterns

- **Map + queue split** on `/command`: the map takes about 70%, with a collapsible urgency-sorted queue on the right.
- **Case card:** urgency pill, headcount, vulnerability icons (elderly, child, pregnant, medical, disabled), age of report ("12m ago"), location confidence badge, and source count ("3 reports").
- **Score breakdown:** a horizontal bar of contributing factors, so every AI decision is explained.
- **Dense data tables** for the queue and teams, with sticky headers, keyboard navigation (j/k to move, a to approve, m to merge) and inline status pills.
- **Live counters** in the top bar with animated number transitions.
- **Right drawer** for details; modals only for destructive or confirm actions.
- **Toasts** (bottom-right) for real-time events: "New critical case", "Team B-07 rescued 4".
- **Timeline scrubber** for replay mode.
- **Map markers:** cases are circles coloured by urgency, with a pulsing ring for Critical. Teams are blue directional arrows with an ID label. Routes are blue lines. Flood zones are semi-transparent cyan polygons. Clustering applies when zoomed out.

## Interaction principles

1. **One glance, one decision.** The most urgent thing is always top-left of the queue and red on the map.
2. **Never hide uncertainty.** Low-confidence locations get a dashed outline and a "?" badge.
3. **Undo over confirm** for reversible actions (merge, reassign); confirm only for closing cases or ending a disaster.
4. **Live but stable.** New items animate in gently; the list never jumps while the user is hovering or selecting.
5. **Field app equals big buttons:** Start, Reached, Rescued and Can't reach, each full-width and colour-coded.

## Accessibility

- WCAG AA contrast minimum (AAA for field app text in sunlight).
- Urgency is never conveyed by colour alone: always a text label plus an icon.
- All actions are keyboard-accessible in the command centre, with visible focus rings.
- Respect `prefers-reduced-motion` (disable pulsing markers).
- Multilingual UI strings via i18n (English, Tamil, Hindi, Malayalam, Telugu); the SOS form auto-detects the browser language.
- Screen-reader labels on map markers ("Critical case, 4 people, 12 minutes ago").
