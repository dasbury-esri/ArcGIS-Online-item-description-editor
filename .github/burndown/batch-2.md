# Batch 2 Burndown

## Goal

Remove optional feature branches and simplify to the admin core flow.

## Ticket Checklist

- [x] B2-01 Remove secondary-scan feature path
- [x] B2-02 Remove exact/narrowing feature path
- [x] B2-03 Rewire step order and dependency messaging
- [x] B2-04 Remove orphaned controls and dead export/save branches

## Exit Gate

- [x] Baseline flow runs scan -> dry run -> report -> apply -> export
- [x] No dead controls or missing bindings remain
- [x] Workflow text matches executable order
- [x] No references remain to removed feature paths

## Session Log

- Date: 2026-03-23
- Completed tickets: B2-01 Remove secondary-scan feature path; B2-02 Remove exact/narrowing feature path; B2-03 Rewire step order and dependency messaging; B2-04 Remove orphaned controls and dead export/save branches
- Blockers: None
- Next action: Batch 2 complete. Commit and push, then begin Batch 3 rollback implementation.

- Validation: Full end-to-end notebook check passed (scan -> dry run -> report -> apply -> export).
