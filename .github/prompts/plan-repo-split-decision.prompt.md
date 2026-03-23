# Plan: Repo Split Decision (Administrative Tool + Matcher Lab)

## Decision

1. Keep this repository as the operational ArcGIS Online administrative tool.
2. Create a separate repository named `ArcGIS-Online-Item-Details-matcher-lab` for advanced matcher experimentation.
3. Stop expanding this repo toward mixed admin/individual-user requirements.

## Rationale

1. Operational stability: this repo already contains a usable workflow with review and confirmation safeguards.
2. Scope control: advanced matcher settings are exploratory and should not destabilize the admin tool.
3. UX clarity: separating operational workflow from experimentation reduces cognitive load for operators.
4. Release discipline: production changes and research changes can now follow independent cadence and risk tolerance.

## Repository Roles

### Current Repo (Operational)

1. Candidate search (admin-focused usage).
2. Structural dry-run matching and replacement planning.
3. Review report generation and selective edit execution.
4. Final export and audit artifacts.
5. Simplification work: remove secondary scan and exact-match narrowing steps.

### Matcher Lab Repo (Experimental)

1. Advanced matcher profile design.
2. Configurable structural anchors and strictness options.
3. Alternative replacement strategies and edge-case testing.
4. Potential future UX/architecture options beyond the notebook baseline.

## Guardrails

1. Do not couple candidate search terms directly to structural matcher anchors by default.
2. Keep safe defaults in the operational repo.
3. Introduce advanced matcher knobs only in matcher-lab first.
4. Promote proven patterns from matcher-lab into this repo only after validation.

## Next Actions

1. Commit and push current changes in this repo.
2. Branch `simplify-admin-tool` from updated `main`.
3. Initialize matcher-lab repo with planning docs and README.
4. Draft simplified admin workflow plan in this repo.
5. Draft advanced matcher settings plan in matcher-lab prior to code import.
