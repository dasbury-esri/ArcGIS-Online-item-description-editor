# Batch 3 Burndown

## Goal

Add optional rollback with targeted undo and validate both baseline and remediation paths.

## Ticket Checklist

- [ ] B3-01 Add pre-edit snapshot capture for apply operations
- [ ] B3-02 Add targeted rollback input mode (manual and file-based IDs)
- [ ] B3-03 Add rollback preview, confirmation, and execution controls
- [ ] B3-04 Add rollback audit exports and run dual end-to-end validation

## Exit Gate

- [ ] Targeted rollback affects only selected item IDs
- [ ] Undo preview and confirmation prevent accidental rollback
- [ ] Apply and rollback both generate auditable success/error exports
- [ ] Pass A succeeds: scan -> dry run -> report -> apply -> export
- [ ] Pass B succeeds: scan -> dry run -> report -> apply -> undo -> export

## Session Log

- Date:
- Completed tickets:
- Blockers:
- Next action:
