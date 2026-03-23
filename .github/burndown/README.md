# Burndown Tracking Guide

This folder provides execution checklists for each batch in the simplify-admin workflow.

## Files

1. batch-1.md
2. batch-2.md
3. batch-3.md

## Conventions

1. Use the ticket IDs (B1-01, B2-03, B3-04) as the shared key between burndown checklists and the master ticket list.
2. Update status in two places for every completed ticket:
   - the matching checkbox in the batch burndown file
   - the matching checkbox in the master board in .github/prompts/tickets-simplify-admin-workflow.prompt.md
3. Do not begin a later batch until the prior batch gate is fully checked.
4. Keep one commit per ticket when possible.
5. Before committing or pushing any batch work, update the current batch Session Log with date, completed tickets, blockers, and next action.
6. Treat Session Log updates as part of done criteria for each ticket and for each end-of-session checkpoint.

## Suggested Cadence

1. Start session: open ticket list + current batch file.
2. During work: keep ticket checkbox unchecked until smoke test passes.
3. After smoke test: check both the batch file and master board.
4. Before each commit/push: update Session Log in the current batch file.
5. End session: add a short note under Session Log in the current batch file.
