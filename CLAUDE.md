# Offshore Fishing Recommendation Engine

Full build spec: `docs/HANDOFF.md`. Read it before any work and treat it as source of truth.

## Non-negotiable constraints
- $0 cost. Never add a paid API, service, or host. If something seems to need payment, STOP and ask.
- MVP first = Phases 0–3. Don't start /frontend-design or ML until the MVP loop works.
- Commit freely, in small verifiable increments.
- Update REFERENCES.md in the SAME commit whenever you add a tool, dependency, data feed, or reference.

## Working agreement
- Propose a plan and get approval before writing code for a new phase.
- Species/domain logic lives in species_profiles config, never hardcoded.
- Keep the scorer contract stable: score(features, profile) -> (score, reasons).
- No DECLARE in SQL; inline values or use a CTE.
- catch_logs is the crown jewel: never drop a label; snapshot conditions on every log.