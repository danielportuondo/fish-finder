# Claude Code Handoff — Offshore Fishing Recommendation Engine

## 0. Mission

Build the **synthesis and recommendation layer** for offshore fishing that no existing
product offers: given a user's **launch point**, **how far they'll run**, **target
species**, and **today's conditions**, return a **ranked list of zones** to fish and
**what's likely biting there**, each with a **human-readable "why."**

We are **not** building an SST/chlorophyll imagery product. That market is mature and
monetized (FishTrack, SatFish, Hilton's RealTime Navigator). We **consume** free
environmental data; we do not render our own satellite charts.

The single hardest problem — and the reason this product doesn't already exist — is the
**cold-start problem**: on day one we have zero labeled "caught species X at zone Y under
conditions Z" data, so we cannot train a supervised model. The entire design is organized
around **shipping useful recommendations with no data while minting labeled training
examples from the very first screen.**

---

## 1. Hard constraints (read first — non-negotiable)

- **$0 cost.** This project must never cost the owner money. Free tiers and free/open data
  only. **Do not introduce any paid API, paid service, or paid hosting.** If a task seems to
  need something paid, stop and ask — there is almost always a free alternative.
- **MVP first, then optimize.** Build the smallest useful end-to-end loop first (see §3).
  Polish, `/frontend-design`, and the ML model come *after* the basic MVP works.
- **Commit freely.** Claude Code is authorized to commit to this repo without asking. Commit
  in small, verifiable increments with clear messages.
- **Maintain a living references/tools log.** See §12. Part of the definition of done, not an
  afterthought.

---

## 2. Cold-start strategy (the core idea)

The product must be valuable on day one and get smarter with every trip. Five mechanisms:

1. **Rule-based scorer as v1.** Encode well-understood species-habitat signatures as
   *versioned config* (not hardcoded). This produces defensible rankings with zero catch
   data — a rule engine that a model later replaces through the same interface.
2. **Log catches from screen one, and snapshot conditions at catch time.** Every logged catch
   stores the full environmental feature vector for that zone/time, so each log is immediately
   a *labeled training example*. This is the core data flywheel.
3. **Capture negatives, not just positives.** After a trip, prompt "fished here, caught
   nothing?" A zone fished with no catch is a valuable negative label — the thing crowdsourced
   apps systematically under-collect. (Negative capture is post-MVP, but the schema must
   support it from the start.)
4. **Backfill labels from public reports (post-MVP).** A one-off tool ingests historical South
   Florida dockside/charter reports (species + rough location + date), reconstructs conditions
   from historical env feeds, and seeds the label table.
5. **Defined graduation criterion.** Once ~200 labeled catches exist for a species in a
   corridor, train a per-species model, evaluate its ranking against the rule scorer on
   held-out recent trips, and promote it only if it beats the rules. The rule scorer stays as
   the fallback and the cold-start default for new corridors/species.

**Design invariant:** the scorer is a pure function `score(features, species_profile) ->
(score, reasons)`. The rule engine and any future ML model implement the same signature so
they are hot-swappable per species without touching the recommendation pipeline.

---

## 3. MVP boundary & roadmap

**Basic MVP = Phases 0–3 + a bare-bones local web UI, running locally.** No styling effort,
no deployment, no ML, no LLM. The goal is a working end-to-end loop: pull conditions → score
zones → show ranked recommendations with reasons → log a catch with its conditions snapshot.

**Then, optimization passes (post-MVP), roughly in order:**
- **Negatives + report backfill** (Phase 4) — grow the label set.
- **ML model + eval harness** (Phase 5) — graduate from rules to a per-species model.
- **UI/UX polish via `/frontend-design`** and **deploy to Cloudflare Pages** (Phase 6).
- **Deferred:** LLM features, mobile client, additional corridors (§11).

We will iterate through these passes until we're happy with the project. Do not start an
optimization pass until the MVP loop works and its phase DoDs are met.

---

## 4. Scope for v1 (do not exceed without asking)

- **One corridor:** South Florida offshore. Launch points: Haulover Inlet, Government Cut, and
  one Keys point (Islamorada). Corridors are **config, not code** — adding one later must not
  require a code change to the pipeline.
- **Four species:** mahi (dolphinfish), sailfish, kingfish, wahoo.
- **Scheduled/triggered environmental ingestion** for the corridor (run manually or via local
  cron for the MVP).
- **Rule-based zone scorer** + recommendation logic.
- **Catch logging with conditions snapshot** from the first usable screen.

**Explicitly out of scope for the MVP:** satellite imagery rendering, global coverage, social
feed, auth, mobile, ML, LLM. Consume a chart *value* at a lat/lng; do not build a charting
pipeline.

---

## 5. Stack (local-first, $0)

- **Data store: local SQLite** (single file, zero setup, $0). Holds `zone_conditions`,
  `catch_logs`, `trips`, `species`, `species_profiles`. Local Postgres is an acceptable
  alternative if preferred, but SQLite is the default for the MVP.
- **Zones: a flat file** (`data/zones.geojson`) — the zone catalog for the corridor lives in
  version control, not the DB. Range filtering is done in Python with a haversine distance
  check over this file (no PostGIS needed for one corridor).
- **Language: Python** for ingestion, scoring, and a tiny local web server (FastAPI or Flask)
  that serves recommendations and accepts catch logs.
- **Client: a bare-bones local web UI** (plain HTML/JS or a minimal React page) that calls the
  local server. No design effort until the `/frontend-design` pass.
- **Auth: none for the MVP.** Tie catch logs to an anonymous device/local id. Real auth isn't
  needed until there are multiple remote users.

**Deployment target (post-MVP, still $0):** Cloudflare Pages for the static client. To stay
free when deployed: run ingestion as a **GitHub Actions cron** that commits a static
conditions JSON artifact the site serves, do scoring client-side or in a Pages Function, and
move catch logging to **Cloudflare D1** (edge SQLite, free tier) via a Pages Function. Keep
MVP choices compatible with this: keep conditions serializable to static JSON and keep the
scorer portable and simple.

---

## 6. Data model (core tables)

SQLite tables (mirror in Postgres if that path is chosen). Zones are a flat GeoJSON file,
**not** a table.

- **`ports`** — launch points. `id, name, lat, lng, corridor` (a small table or flat file;
  either is fine).
- **`species`** — `id, code (mahi|sailfish|kingfish|wahoo), display_name`
- **`species_profiles`** — versioned habitat rules. `species_id, version, active (bool), params
  (JSON)`. `params` encodes the domain signature, e.g. mahi:
  `{ "sst_optimal_f": [78, 82], "prefers_structure": ["current_edge","open"], "depth_ft":
  [120, 1000], "chlorophyll_pref": "break", "current_edge_affinity": 0.9, "pressure_response":
  "neutral", "weedline_bonus": true }`. **Never hardcode these in the scorer.** Exactly one
  `active` profile per species.
- **`zone_conditions`** — append-only time series; the feature vector per zone per pull.
  `zone_id, observed_at, sst_f, sst_break_gradient, chlorophyll, current_speed_kt,
  current_dir_deg, dist_to_stream_edge_nm, wave_height_ft, wind_speed_kt, wind_dir_deg,
  pressure_mb, pressure_trend_3h, moon_illumination, solunar_score, tide_state`.
- **`catch_logs`** — the label table. `id, device_id, species_id, zone_id, caught_at, count,
  notes, outcome (caught|skunked), conditions_snapshot (JSON)`. `conditions_snapshot` is the
  full feature vector at catch time — a denormalized JSON copy so labels survive any retention
  rollup. If conditions can't be resolved, still save the log but flag `snapshot_incomplete` —
  **never drop a label.**
- **`trips`** — groups logs; powers the post-MVP negative prompt. `id, device_id, port_id,
  range_nm, target_species (JSON), trip_date, zones_fished (JSON)`.

Every logged catch **must** produce a complete labeled feature row (or a flagged incomplete
one). `catch_logs` is the crown jewel of the project.

---

## 7. Environmental data sources (free only)

Pull on a schedule, resolve each feed to each zone's lat/lng. **All sources must be free.**

- **SST + chlorophyll + true color:** NOAA CoastWatch / NASA Ocean Color. Derive
  `sst_break_gradient` locally from the SST field.
- **Tides & currents:** NOAA CO-OPS web services — `https://api.tidesandcurrents.noaa.gov/api/prod/`
  (JSON/CSV, station-based, free).
- **Real-time observed conditions:** NDBC buoys (wind, wave height, water temp; free).
- **Marine forecast (waves/swell/wind/SST):** Open-Meteo Marine (free, no key).
- **Bathymetry / structure:** NOAA + GEBCO (used once to build the zone catalog, not per-pull).
- **Barometric pressure + 3h trend:** from the marine feed above — compute and store the trend,
  not just the level; it materially drives bite windows.
- **Gulf Stream / Florida Current edge position:** derive from SST/altimetry; store
  `dist_to_stream_edge_nm` per zone per pull. Off Miami this is the dominant offshore driver.

**Known tradeoff:** free SST/chlorophyll is coarser than the paid "cloud-free" offshore
products, so on cloudy days some zones will have gaps. Acceptable for the MVP — handle missing
values gracefully (score with what's available, note reduced confidence). A gap-fill step can
come later. Verify current endpoints/params at build time; some NOAA services have migrated to
cloud URLs — log each one you settle on in the references doc (§12).

---

## 8. Recommendation pipeline

Local endpoint: `GET /recommendations?port_id=&range_nm=&species=&date=`

1. **Range filter:** load `data/zones.geojson`, keep zones whose haversine distance from the
   port is `<= range_nm` → reachable candidates.
2. **Load latest conditions** per candidate zone from `zone_conditions` for `date`.
3. **Score** each (zone, species) with the active scorer: `score(features, species_profile) ->
   (score, reasons)`.
4. **Rank** zones per requested species; return top N with score and `reasons`.

**Every recommendation must return human-readable reasons**, e.g. *"78.9°F, 1.4° temp break 3
nm inside the current edge, weedline present."* Reasons are (a) the user trust surface, (b) the
debugging surface for the rules, and (c) later map onto model feature importance.
Non-negotiable.

---

## 9. Scale path (later, not MVP)

When one corridor + SQLite + flat file is outgrown: move zones into Postgres + PostGIS and use
`ST_DWithin` for range queries; partition `zone_conditions` by month with a retention/rollup
policy (but never drop data referenced by a `catch_logs.conditions_snapshot`); make scoring
stateless and cacheable by `(corridor, date, conditions_hash, species, profile_version)`; add
corridors as config rows, not code. In the deployed Cloudflare setup, `zone_conditions` becomes
committed static JSON and `catch_logs` moves to D1.

---

## 10. Build phases (each with a definition of done)

**Phase 0 — Foundation (MVP).** Repo scaffold, SQLite schema (§6), `data/zones.geojson` seeded
with a South Florida zone catalog, ports, species rows, one active `species_profile` per
species, and an initial `REFERENCES.md` (§12). *DoD:* schema creates clean; seed data
queryable; references doc exists.

**Phase 1 — Ingestion (MVP).** Python job pulls §7 free feeds, resolves to zones, writes
`zone_conditions`. Handles missing/cloudy data gracefully. *DoD:* one command populates today's
conditions for every zone; re-runs are idempotent; missing values don't crash it.

**Phase 2 — Rule scorer + recommendations (MVP).** Implement `score(features, profile)` reading
`species_profiles.params`; build the §8 endpoint on a small local server. *DoD:* on a
known-good day, rankings are sane and every result carries `reasons`.

**Phase 3 — Catch logging + snapshot (MVP).** Bare-bones web UI for port/range/species input,
ranked results with reasons, and a catch-logging flow that writes `catch_logs` with a complete
`conditions_snapshot`. *DoD:* the full loop runs locally; logging a catch produces a full
labeled feature row; incomplete snapshots are flagged, never dropped. **← Basic MVP complete
here.**

**Phase 4 — Negatives + backfill (optimization).** Post-trip "skunked?" capture writing negative
labels; one-off script to ingest historical public reports and reconstruct their conditions.
*DoD:* negatives land in `catch_logs`; backfill produces labeled rows per species.

**Phase 5 — ML pipeline + eval harness (optimization).** Offline trainer reads labels joined to
snapshots, trains per-species; eval harness compares model vs rule ranking on held-out recent
trips; model promoted only if it beats rules; scorer swaps by config. *DoD:* reproducible
training run + a model-vs-rules report on held-out data.

**Phase 6 — Polish + deploy (optimization).** Apply `/frontend-design` to the web client; deploy
to Cloudflare Pages using the $0 pattern in §5 (Actions cron → static JSON, D1 for logging).
*DoD:* deployed site works end-to-end at $0; last results readable if a feed is stale.

---

## 11. Deferred (explicitly future scope)

- **LLM features.** No LLM in the MVP. When introduced, the natural fits are (a) parsing messy
  dockside/charter report text in the Phase 4 backfill, and (b) a possible future
  natural-language "where should I fish today?" query layer. **All LLM calls must go to the
  owner's free Gemini tier (Google AI Studio free API key) — never a paid model.** Respect its
  rate limits (batch the backfill).
- **Mobile client** (offline-capable, for on-the-water use).
- **Additional corridors.**

---

## 12. References & tools log (required, living)

Maintain **`REFERENCES.md`** at the repo root (create it in Phase 0). Update it in the **same
commit** whenever you introduce a new dependency, data feed, external API, dataset, library, or
notable reference/doc. Format as a simple table:

```
| Date added | Name | Type (tool/lib/data feed/API/doc/dataset) | Used for | Link |
|------------|------|-------------------------------------------|----------|------|
| 2026-07-22 | Open-Meteo Marine | data feed | free marine forecast (waves/wind/SST) | https://open-meteo.com/en/docs/marine-weather-api |
```

Keep it current — an out-of-date log is worse than none. This log is part of every phase's
definition of done.

---

## 13. Operating instructions for Claude Code

- **Commit freely** in small, verifiable increments with clear messages.
- **$0 guardrail:** never introduce a paid API, service, or host. If something seems to require
  payment, stop and ask — there's almost always a free path.
- **MVP first:** land Phases 0–3 and their DoDs before any optimization pass. Do not start
  `/frontend-design` or ML work early.
- **Update `REFERENCES.md`** in the same commit as any new tool/dependency/feed/reference.
- Propose a plan and confirm Phase 0 scope **before** writing code.
- Keep all species/domain logic in `species_profiles` config, never in the scorer body.
- Keep the `score(features, profile) -> (score, reasons)` contract stable across the rule engine
  and any future model — this seam is what the whole design depends on.
- No `DECLARE` in any SQL — inline values or use a CTE.
- Do not build satellite imagery rendering. Consume values, not tiles.
- Treat `catch_logs` as the crown jewel: never drop or silently corrupt a label; snapshot
  conditions on every log; support negatives in the schema from day one.
- Handle missing/cloudy environmental data gracefully — score with what's available.
- Prefer boring, verifiable increments; land each phase's DoD before moving on.