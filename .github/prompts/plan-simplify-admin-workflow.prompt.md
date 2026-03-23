# Plan: Simplify Administrative Workflow (Current Repo)

## Goal

Refocus the notebook workflow on administrative operators and remove optional paths that increase complexity without improving the core admin task.

## Target Workflow

1. Setup and authenticate.
2. Search candidate items using operator-provided terms.
3. Dry run with structural matcher preview and replacement plan.
4. Generate and review report.
5. Apply edits after explicit confirmation.
6. Export final result artifacts.

## Scope Changes

1. Keep: candidate search, dry run, preview card/report, apply, export.
2. Remove: secondary scan step.
3. Remove: optional narrowing/exact-match filter step.
4. Keep default replacement HTML file behavior (`Esri_ToU.html`) while allowing user-provided path in dry run.

## Design Principles

1. Admin-first UX and wording.
2. Clear separation between candidate discovery and structural replacement matching.
3. Preserve review-first and explicit confirmation safeguards.
4. Keep status outputs concise and operationally useful.

## Implementation Phases

### Phase 1: UX and Copy Alignment

1. Update notebook markdown and TL;DR for admin-first framing.
2. Remove user-facing references to individual-user-first paths.
3. Keep matcher explanations accurate but concise.

### Phase 2: Workflow Simplification

1. Remove secondary scan UI and callbacks.
2. Remove exact-match narrowing UI and callbacks.
3. Rewire step numbering and dependency messaging accordingly.
4. Ensure no broken context keys remain after removal.

### Phase 3: Validation

1. Run full local end-to-end flow at least twice.
2. Verify dry run, report generation, apply, and exports parity.
3. Confirm outputs and status widgets render in expected locations.
4. Confirm no orphaned save/export controls remain from removed steps.

## Verification Checklist

1. Candidate scan still identifies expected rows for admin term sets.
2. Dry run still builds plan_df and preview/report correctly.
3. Apply step only runs after explicit confirmation text.
4. Final export produces expected success and error CSV outputs.
5. Notebook text and README remain aligned with simplified workflow.

## Out of Scope

1. Advanced matcher settings UI and profile management.
2. New architecture migration work.
3. Broad feature expansion unrelated to admin workflow simplification.
