# Ticket List: Simplify Admin Workflow (Batch 1/2/3)

Use this as the implementation queue for the simplification work. Complete Batch 1 before Batch 2, and Batch 2 before Batch 3.

## Burndown Integration

1. Master ticket status lives in this file.
2. Execution checklists live in:
  - `.github/burndown/batch-1.md`
  - `.github/burndown/batch-2.md`
  - `.github/burndown/batch-3.md`
3. For every completed ticket, check off both:
  - the item in the relevant batch burndown file
  - the matching item in the Master Status Board below
4. A batch is complete only when all ticket checkboxes and all exit-gate checkboxes are checked.

## Master Status Board

### Batch 1 Status

- [x] B1-01 Rename setup/auth and primary-scan keys to semantic names
- [x] B1-02 Rename save/reload-scan keys to semantic names
- [x] B1-03 Complete positional-name sweep and lock naming baseline
- [x] B1-04 Admin-first copy update and matcher explanation tightening

### Batch 2 Status

- [x] B2-01 Remove secondary-scan feature path
- [x] B2-02 Remove exact/narrowing feature path
- [x] B2-03 Rewire step order and dependency messaging
- [x] B2-04 Remove orphaned controls and dead export/save branches

### Batch 3 Status

- [x] B3-01 Add pre-edit snapshot capture for apply operations
- [x] B3-02 Add targeted rollback input mode (manual and file-based IDs)
- [x] B3-03 Add rollback preview, confirmation, and execution controls
- [x] B3-04 Add rollback audit exports and run dual end-to-end validation

Batch 3 Finalized: Pass A and Pass B are both marked PASS.

## Batch 1: Semantic Rename and Admin Copy Baseline

### Ticket B1-01: Rename setup/auth and primary-scan keys to semantic names
- Scope: Replace positional widget/context names in setup/auth and primary-scan paths.
- Includes: notebook variable names, context keys, helper key lookups, callback bindings.
- Done when:
  1. Setup/auth executes without missing-key errors.
  2. Primary scan executes and renders output in the intended widget.
  3. No stale positional names remain in these sections.
- Smoke test: setup -> auth -> primary scan using known test terms.
- Suggested commit message: `refactor: semantic names for setup and primary scan`

### Ticket B1-02: Rename save/reload-scan keys to semantic names
- Scope: Apply semantic names for save/reload controls and helper lookup keys.
- Includes: save scan output paths, reload path inputs, button/status/output bindings.
- Done when:
  1. Save scan writes expected artifacts.
  2. Reload scan restores expected dataframes/state.
  3. No missing context lookups in save/reload callbacks.
- Smoke test: run scan -> save artifacts -> reload artifacts.
- Suggested commit message: `refactor: semantic names for save and reload scan`

### Ticket B1-03: Complete positional-name sweep and lock naming baseline
- Scope: Remove remaining `inputN`, `outputN`, `btnN`, `statusN` references from active paths.
- Includes: notebook + helpers + any docs that reference active control names.
- Done when:
  1. Grep finds no active positional naming patterns.
  2. All callbacks still bind to expected controls.
- Smoke test: notebook run-through of setup/scan/save/reload.
- Suggested commit message: `chore: remove remaining positional widget names`

### Ticket B1-04: Admin-first copy update and matcher explanation tightening
- Scope: Update notebook guidance/TL;DR for admin operators and clarify scan vs structural matching roles.
- Includes: concise wording updates only; no behavior changes.
- Done when:
  1. Admin-first wording appears in all operator guidance sections.
  2. Candidate search and structural matcher responsibilities are clearly separated.
- Smoke test: quick docs review in rendered notebook.
- Suggested commit message: `docs: align notebook copy to admin-first workflow`

## Batch 2: Workflow Simplification and Wiring Cleanup

### Ticket B2-01: Remove secondary-scan feature path
- Scope: Delete secondary-scan UI elements, callback wiring, and unreachable helper logic.
- Includes: widget creation, event bindings, dependency/status text, unused context keys.
- Done when:
  1. No secondary-scan controls appear.
  2. No callback references to removed controls remain.
- Smoke test: execute primary path and ensure no missing-key errors.
- Suggested commit message: `feat: remove secondary scan workflow path`

### Ticket B2-02: Remove exact/narrowing feature path
- Scope: Delete optional exact-match narrowing UI and callback path.
- Includes: controls, bindings, helper references, step/dependency text.
- Done when:
  1. No exact/narrowing controls appear.
  2. Dry run still operates on the simplified candidate set.
- Smoke test: run scan -> dry run without exact step.
- Suggested commit message: `feat: remove exact narrowing workflow path`

### Ticket B2-03: Rewire step order and dependency messaging
- Scope: Reindex workflow to the simplified order, including optional rollback and final export sequence.
- Includes: step labels, status text, control ordering, dependency guard messages.
- Done when:
  1. Workflow displays as Steps 1-8 with optional Step 7 rollback.
  2. Baseline path runs scan -> dry run -> report -> apply -> export.
- Smoke test: baseline execution path without rollback.
- Suggested commit message: `chore: rewire simplified step flow and messaging`

### Ticket B2-04: Remove orphaned controls and dead export/save branches
- Scope: Clean up controls only needed by deleted paths.
- Includes: dead outputs, stale status widgets, old export/save branches from removed steps.
- Done when:
  1. No dead controls remain in active UI.
  2. Core flow controls are minimal and coherent.
- Smoke test: review rendered sections and run each remaining button once.
- Suggested commit message: `chore: remove orphan controls after workflow simplification`

## Batch 3: Optional Rollback, Targeted Undo, and Final Validation

### Ticket B3-01: Add pre-edit snapshot capture for apply operations
- Scope: Persist enough pre-edit state to support full and targeted rollback.
- Includes: snapshot schema, storage location, metadata for traceability.
- Done when:
  1. Apply action records rollback-ready snapshot data.
  2. Snapshot references map deterministically to edited rows.
- Smoke test: apply run confirms snapshot artifact generation.
- Suggested commit message: `feat: capture pre-edit snapshots for rollback`

### Ticket B3-02: Add targeted rollback input mode (manual and file-based IDs)
- Scope: Support rollback by specific item IDs discovered later.
- Includes: manual ID entry, file-loaded IDs, normalization/deduping/validation.
- Done when:
  1. Operators can provide IDs manually or via file.
  2. Invalid/unmatched IDs report clearly without stopping valid rollbacks.
- Smoke test: targeted undo with mixed valid/invalid IDs.
- Suggested commit message: `feat: add targeted rollback input by item IDs`

### Ticket B3-03: Add rollback preview, confirmation, and execution controls
- Scope: Implement full/targeted rollback preview and explicit confirm-to-execute flow.
- Includes: candidate preview table, confirmation gate, conflict/error handling.
- Done when:
  1. Preview reflects exact rollback scope before execution.
  2. Rollback runs only after confirmation.
  3. Conflict/error results are captured in status + outputs.
- Smoke test: full undo and targeted undo on pilot set.
- Suggested commit message: `feat: add rollback preview and confirmation workflow`

### Ticket B3-04: Add rollback audit exports and run dual end-to-end validation
- Scope: Produce rollback success/error exports and validate baseline and rollback paths.
- Includes: export file naming, output placement checks, pass A/pass B validation runs.
- Done when:
  1. Apply and rollback both produce auditable success/error exports.
  2. Pass A: scan -> dry run -> report -> apply -> export succeeds.
  3. Pass B: scan -> dry run -> report -> apply -> undo -> export succeeds.
- Smoke test: two full runs with consistent operator-facing outputs.
- Suggested commit message: `test: validate baseline and rollback flows with audit exports`

## Execution Rules

1. Do not start Batch 2 until all Batch 1 tickets are complete and smoke-tested.
2. Do not start Batch 3 until all Batch 2 tickets are complete and smoke-tested.
3. If a ticket introduces regression, fix within the same batch before proceeding.
4. Keep commits small and aligned to a single ticket whenever possible.
