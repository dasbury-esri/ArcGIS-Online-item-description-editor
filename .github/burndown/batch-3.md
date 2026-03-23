# Batch 3 Burndown

## Goal

Add optional rollback with targeted undo and validate both baseline and remediation paths.

## Ticket Checklist

- [x] B3-01 Add pre-edit snapshot capture for apply operations
- [x] B3-02 Add targeted rollback input mode (manual and file-based IDs)
- [x] B3-03 Add rollback preview, confirmation, and execution controls
- [x] B3-04 Add rollback audit exports and run dual end-to-end validation

## Exit Gate

- [x] Targeted rollback affects only selected item IDs
- [x] Undo preview and confirmation prevent accidental rollback
- [x] Apply and rollback both generate auditable success/error exports
- [x] Pass A succeeds: scan -> dry run -> report -> apply -> export
- [ ] Pass B succeeds: scan -> dry run -> report -> apply -> undo -> export

## Session Log

- Date: 2026-03-23
- Completed tickets: B3-01, B3-02, B3-03, B3-04
- Blockers: Pass B end-to-end validation is still pending.
- Next action: Run Pass B in notebook runtime against org content and capture output artifacts.

## Post-Batch Feature Additions

- [x] F3-01 Report JSON download button turns green when one or more report row checkboxes are selected and returns to gray when none are selected.
- [x] F3-02 Timestamp all CSV outputs using filename_YYYYMMDD_HHMM.csv format.
