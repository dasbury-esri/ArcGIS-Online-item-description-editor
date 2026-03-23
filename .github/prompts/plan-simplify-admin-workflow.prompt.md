# Plan: Simplify Administrative Workflow (Current Repo)

## Goal

Refocus the notebook workflow on administrative operators and remove optional paths that increase complexity without improving the core admin task.

## Target Workflow

1. Setup and authenticate.
2. Search candidate items using operator-provided terms.
3. Dry run with structural matcher preview and replacement plan.
4. Generate and review report.
5. Apply edits after explicit confirmation.
6. Monitor results and identify broken/unintended edits (immediate or discovered later).
7. Optionally run rollback flow (full batch or targeted item IDs) when remediation is needed.
8. Export final result artifacts (post-apply or post-rollback).

## Scope Changes

1. Keep: candidate search, dry run, preview card/report, apply, export, undo.
2. Remove: secondary scan step.
3. Remove: optional narrowing/exact-match filter step.
4. Keep default replacement HTML file behavior (`Esri_ToU.html`) while allowing user-provided path in dry run.
5. Implement semantic variable/context-key naming refactor early to streamline maintenance and troubleshooting.
6. Add targeted rollback input mode so operators can load specific item IDs for undo when issues are discovered after large batch edits.

## Design Principles

1. Admin-first UX and wording.
2. Clear separation between candidate discovery and structural replacement matching.
3. Preserve review-first and explicit confirmation safeguards.
4. Keep status outputs concise and operationally useful.
5. Prefer stable semantic names over positional widget/context names to reduce coupling and debugging friction.

## Strict Execution Checklist (Batch 1/2/3)

Use this sequence for the upcoming code implementation. Do not start a later batch until the current batch passes its exit gate.

### Global Rules (All Batches)

1. Keep each commit scoped to one checklist item or tightly related pair of items.
2. After each checklist item, run a focused smoke test before continuing.
3. If a regression appears, stop and fix in the same batch before adding new work.
4. Preserve explicit confirmation requirements for destructive actions.
5. Keep file/output names stable unless this checklist explicitly changes them.

### Batch 1: Semantic Rename and Admin Copy Baseline

Objective: establish maintainable names and admin-first language before logic removal.

Tasks

1. Apply semantic variable/context-key renames for setup/auth and primary scan sections.
2. Apply semantic variable/context-key renames for save/reload scan sections.
3. Complete stale positional-name sweep and remove remaining `inputN`, `outputN`, `btnN`, `statusN` references.
4. Update notebook markdown/TL;DR copy to admin-first wording.
5. Tighten matcher explanation text so candidate search and structural matching are clearly separated.

Batch 1 Exit Gate (must all pass)

1. Setup/auth and primary scan execute end-to-end without missing context-key errors.
2. Save/reload scan still writes and reloads expected files.
3. No stale positional-name references remain in active notebook/helper paths.
4. Admin copy appears in notebook guidance without ambiguity.

### Batch 2: Workflow Simplification and Wiring Cleanup

Objective: remove non-core optional paths and keep the core admin flow stable.

Tasks

1. Remove secondary scan UI, callbacks, and any unreachable helper wiring.
2. Remove exact-match narrowing UI, callbacks, and related dependency text.
3. Rewire step numbering and dependency/status messaging to the simplified flow.
4. Remove orphaned save/export controls introduced only for deleted paths.
5. Keep dry run preview/report, apply confirmation, and final export flow intact.

Batch 2 Exit Gate (must all pass)

1. Candidate search, dry run preview/report, apply, and final export run in order without dead controls.
2. No broken widget bindings or missing context lookups from deleted paths.
3. Simplified workflow text matches actual executable order.
4. No references remain to removed secondary scan or exact narrowing features.

### Batch 3: Undo Workflow and Final Validation

Objective: add safe optional rollback and confirm parity of the simplified admin workflow.

Tasks

1. Add pre-edit snapshot capture for rows targeted by apply.
2. Add targeted rollback input mode (manual IDs and/or file-based IDs) for delayed issue discovery.
3. Add undo preview showing rollback candidates before execution (full or targeted).
4. Add undo confirmation and execution with conflict/error reporting.
5. Add undo success/error export artifacts for audit trail.
6. Run two full local end-to-end passes:
	- pass A: scan -> dry run -> report -> apply -> export.
	- pass B: scan -> dry run -> report -> apply -> undo -> export.
7. Verify final status/output placement and ensure no orphan controls remain.

Batch 3 Exit Gate (must all pass)

1. Undo reliably restores prior values in pilot rollback tests.
2. Targeted rollback accepts specific item IDs and only affects selected rows.
3. Undo preview and confirmation gates prevent accidental rollback.
4. Success/error export artifacts are generated for both apply and undo paths.
5. Baseline flow (without rollback) and rollback flow both pass with consistent outputs.
6. Operator-facing text, behavior, and exported artifacts are aligned.

## Verification Checklist

1. Candidate scan still identifies expected rows for admin term sets.
2. Dry run still builds plan_df and preview/report correctly.
3. Apply step only runs after explicit confirmation text.
4. Undo step restores expected prior values for selected rows in pilot tests.
5. Targeted rollback works for manually entered item IDs and file-loaded item IDs discovered after initial runs.
6. Final export produces expected success and error CSV outputs after apply, and after rollback when rollback is used.
7. Notebook text and README remain aligned with simplified workflow.

## Out of Scope

1. Advanced matcher settings UI and profile management.
2. New architecture migration work.
3. Broad feature expansion unrelated to admin workflow simplification.
