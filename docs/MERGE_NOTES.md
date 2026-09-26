# Merge notes

## PR #7: `shellhacks-demo` into `main` (merged `origin/main` into `shellhacks-demo`)

`shellhacks-demo` rewrote the frontend onto the current backend API. `main` had 238b63d ("update to map and new
frontend color scheme"), which restyled the old pages. The merge keeps the new API-integrated app and ports
238b63d's design into it. Nothing that calls the old API came back. Backup of the pre-merge branch:
`backup/shellhacks-demo-pre-merge`.

| File | Conflict | Resolution |
|---|---|---|
| `frontend/app/globals.css` | content | 238b63d's tokens and base styles are the source of truth: the dark navy console palette, Inter, the radial background glow, map, marker, route, sequence and match-card styles. Kept every class the new pages use (topbar, demobar, seg, code-big, states). Added contrast tokens where a palette value fails 4.5:1: `--accent-strong` #2563eb for filled buttons (white on #3b82f6 is 3.7:1), `--on-good` for text on mint (white on #34d399 is 1.9:1), and `--bad-text` #f87171 for red text on red washes (#ef4444 there is 4.1:1). Dark is the default. A light variant with the same hues is available from the theme toggle. All 40 checked text/background pairs pass 4.5:1 in both themes. |
| `frontend/app/layout.tsx` | content | 238b63d's fonts (Inter display and body, JetBrains Mono data) and `themeColor` #07111f, plus shellhacks-demo's AuthProvider and the saved-theme script. |
| `frontend/components/MapView.tsx`, `FlowMap.tsx` | modify/delete | Not restored (old API types). Ported into `components/RescueMapView.tsx`: the same react-leaflet setup, the Esri dark gray canvas (or Mapbox dark with a token), emoji badge markers with pulse, the glowing route with moving particles, numbered stops, gliding carrier markers and the legend. `components/RescueMap.tsx` loads it with `ssr: false` and builds points from `Rescue` data. It is used on the coordinator, restaurant and volunteer pages. In light theme it switches to Esri's light gray canvas. |
| `frontend/components/MatchCard.tsx` | modify/delete | Ported into `components/RescueCard.tsx`: the match-card entrance, the restaurant → carrier → organization flow with icons, and the ETA / deadline / safety-margin tiles with the same 20/10 minute thresholds, computed from the rescue's recorded times. |
| `frontend/components/WhyThisMatch.tsx` | modify/delete | Ported into the new `components/WhyThisAssignment.tsx`, which uses the same CHOSEN/OPTION card layout and cyan accents. It renders only the backend's recorded decision (`GET /rescues/{id}/matching-explanation`). The old score bars are gone because the current backend does not record per-term scores. |
| `frontend/components/AppShell.tsx` | modify/delete | Ported into `components/Shell.tsx`: the Brand logo mark in his colors, the sticky translucent header with a bottom border, and a filled accent sign-out. Shell's role-based workspaces stay. |
| `frontend/app/admin/dashboard/page.tsx`, `app/restaurant/dashboard/page.tsx` | modify/delete | Kept deleted. His changes (carrier state colors, RescueSequence while posting) are ported into `/coordinator` and `/restaurant`. `next.config.ts` redirects `/admin/dashboard` to `/coordinator` and `/restaurant/dashboard` to `/restaurant`, plus `/driver/dashboard` to `/volunteer` and `/organization/dashboard` to `/org`. |
| `frontend/components/RescueSequence.tsx` | added on main | Kept the dispatch animation and styling, adapted to real data. The original showed random counts ("drivers available" = 14 + random) and fixed candidate names. It now shows the organizations checked, how many were eligible, the eligible names (the chosen one highlighted) and the assigned carrier, all from the post response and the recorded explanation. Its steps map onto the lifecycle: created = posted, searching = matching, found = matched or still posted. Posting is no longer delayed 2.9 s for the animation. |

What could not be kept from 238b63d:
- **Carrier markers on live maps.** The current backend does not expose carrier positions, so no carrier is drawn
  from a guess. `GlidingCarrier` is ported and ready for when positions exist.
- **Score bars in "Why this match?"** The current matching records eligibility reasons and a plain-English
  carrier reason, not per-term scores.
- **Road route geometry.** No route endpoint exists yet. Stops are joined with straight lines, and the legend says so.

## `origin/frontend` (Saito, a357483): not merged

It branches from 5aec836 (before the passwordless API) and edits the old pages, so merging it would bring back the
old API (`/auth/login`, password, driver/organization dashboards, signup, qr). Here is what it adds and how to
re-apply it on the new `main`:

| Piece | What it is | Ports cleanly? |
|---|---|---|
| `components/Motion.tsx` | `Reveal` (adds `.in` when scrolled into view) and `CountUp` (eased number) | Yes, as a standalone helper. It imports only `number` from `lib/format`, which still exists. One fix is needed: `Reveal` relies on IntersectionObserver alone, so above-the-fold content can stay hidden if IO never fires. Check `getBoundingClientRect` on mount first. |
| `components/HeroMap.tsx` | Pure SVG illustrated city map with a self-drawing route, flowing dashes and a looping driver | Mostly. It needs no API. Replace its hard-coded names ("ABC Restaurant", "Community Food Bank", "Hope Shelter", "50 meals", "32 min, 5.0 mi") with the current fictional seed names, or label them "illustration". It also hard-codes light colors (#eef2f7, #1456d9); switch them to the CSS variables so it follows the dark palette. |
| Animation keyframes in `globals.css` (`ff-rise`, `ff-fade`, `ff-sheet`, `ff-pop`, `ff-ping`, `ff-draw`, `ff-flow`, `ff-drive`, `.reveal`, `.stagger`, `.live-dot`) | Motion utilities | Yes, as additions. Keep the existing `prefers-reduced-motion` rule covering them. |
| New tokens (`--shadow-1..3`, `--radius` 20px, `--ease-*`, light palette #0b1220 / #f5f8fc, Plus Jakarta Sans) | A light, soft-shadow visual direction | Conflicts. The team chose 238b63d's dark palette and Inter. Take the easing and shadow tokens only if they fit the dark theme. |
| Landing page (`app/page.tsx`) | Hero with HeroMap, floating header, example trip card, "who it's for" list | Partly. The new landing must keep the required one-liner ("Move surplus food to local organizations with less coordination. ...") and the "Try the donation demo" button to `/demo`. The example trip card uses old demo names. |
| Old pages (`admin/dashboard`, `driver/dashboard`, `organization/dashboard`, `restaurant/dashboard`, `impact`, `login`, `signup`, `qr`), `AppShell`, `MapView`, `MatchCard`, `WhyThisMatch` | Visual tweaks to the old-API screens | No. These files no longer exist. Re-apply visual ideas to `/restaurant`, `/volunteer`, `/org`, `/coordinator`, `components/Shell.tsx`, `RescueCard.tsx`, `RescueMapView.tsx` and `WhyThisAssignment.tsx`. Don't change `/login` behavior: sign-in stays the emailed code. |

Suggested way to re-apply: branch from the new `main`, copy `Motion.tsx` and `HeroMap.tsx` over, add the keyframes,
then restyle the landing hero. Run `npm run lint && npm run build` and `cd e2e && npm run test:3x` before opening
the PR.
