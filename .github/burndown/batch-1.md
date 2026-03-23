# Batch 1 Burndown

## Goal

Semantic rename baseline and admin-first copy alignment.

## Ticket Checklist

- [x] B1-01 Rename setup/auth and primary-scan keys to semantic names
- [x] B1-02 Rename save/reload-scan keys to semantic names
- [x] B1-03 Complete positional-name sweep and lock naming baseline
- [x] B1-04 Admin-first copy update and matcher explanation tightening

## Exit Gate

- [x] Setup/auth and primary scan run cleanly
- [x] Save/reload scan writes and restores expected artifacts
- [x] No active positional naming patterns remain
- [x] Admin guidance text is unambiguous

## Session Log

- Date: 2026-03-23
- Completed tickets: B1-01, B1-02, B1-03, B1-04
- Blockers: None. Smoke checks passed; only a non-blocking SciPy/NumPy environment warning was observed during local test execution.
- Next action: Start Batch 2 (B2-01) and keep master/batch trackers synchronized after each ticket.
