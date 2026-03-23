## Plan: AGO Utility Master Plan

Deliver an admin-first, publicly discoverable ArcGIS Online notebook utility (login required for operations) with explicit search/replace guidance, stable UX, deferred semantic renaming, and gated rollout. This consolidates the current strategy with both attached planning documents into one execution path.

## Strategy Update (Decision Locked)

1. This repository is now focused on an administrative workflow and no longer targets individual-user-first requirements.
2. Core workflow direction for this repo: candidate search -> dry run + structural matcher preview -> review report -> apply edits -> export results.
3. Secondary scan and optional exact-match narrowing are planned for removal in this repo as part of workflow simplification.
4. Advanced matcher settings exploration will move to a separate repository: ArcGIS-Online-Item-Details-matcher-lab.
5. Keep candidate-term search and structural replacement matching as separate concerns (candidate discovery in scan, block eligibility in dry run).

**Steps**
1. Phase 0 - Guardrails and sequencing
2. Freeze major workflow reshuffling until one complete local end-to-end runthrough succeeds on current naming. *blocks Phase 2 and Phase 3*
3. Keep inline report rendering as the primary review UX and preserve large-report safeguards/fallback behavior during all upcoming changes. *global constraint*
4. Phase 1 - Immediate clarity and non-technical guidance (current priority)
5. Update TL;DR and Step 6 wording to explicitly state:
6. What is searched (primary/secondary target terms and exact filter role).
7. What is replaced (replacement HTML file path/template source).
8. How default vs strict matching behaves, including concrete bounded-distance semantics.
9. Add concise “for technical users” guidance that identifies safe modification points (search term parsing, template file, matcher constants/patterns) without requiring code edits for normal usage.
10. Add a short “configuration map” in user-facing text linking key UI inputs to behavior/output artifacts. *depends on 5*
11. Standardize terminology across notebook steps so search/replace/matching terms are consistent. *parallel with 10*
12. Phase 1.5 - Admin-first UX hardening before rename
13. Add explicit preflight messaging at setup/scan/update boundaries to clarify expected admin capability and non-admin limitations early. *depends on Phase 1*
14. Keep visual workflow clean and non-technical: review-first sequence, clear status messages, explicit next-step guidance, and card/report preview continuity. *parallel with 13*
15. Validate no regression in scan -> dry run -> report -> apply -> export outputs while making copy/UX changes. *depends on 13 and 14*
16. Phase 2 - Deferred semantic variable/context-key renaming (start only after Phase 1.5 verification)
17. Execute rename as six controlled batches (producer and consumer updates together) per approved mapping:
18. Batch 1: setup/auth + primary scan.
19. Batch 2: save/reload scan.
20. Batch 3: secondary scan + secondary save.
21. Batch 4: exact filter + dry run.
22. Batch 5: dry-run export + report.
23. Batch 6: apply edits + final export.
24. After each batch: run diagnostics plus focused step-level smoke tests before continuing. *strict dependency between batches*
25. Run global stale-name sweep for positional identifiers and resolve or explicitly defer any leftovers. *depends on all rename batches*
26. Phase 3 - Post-rename rollout gates (from rollout plan)
27. Entry criteria check: full runthrough success, context-contract validation, known-issues triage, and baseline artifact set captured. *depends on Phase 2 completion*
28. Phase 3A local stabilization: two consecutive full local runs without kernel restart; confirm output placement, bindings, parity counts.
29. Phase 3B controlled pilot: constrained real dataset, reviewed selection file, limited apply, operator feedback capture.
30. Phase 3C expanded rollout: production procedure with mandatory dry-run/report review, explicit confirmation phrase, per-run artifact archive and change log.
31. Phase 3D optional undo hardening: pre-edit snapshots, applied-edits log, undo preview/execute flow, pilot-first validation.
32. Phase 4 - Public discoverability packaging and architecture decision gates
33. Publish discoverability and usage docs: public entry, login-required operation model, audience expectations (admin-first).
34. Maintain a decision gate after stable rollout to choose: continue notebook-first vs hybrid service extraction vs full web utility migration, using real operational friction and adoption signals.

**Phase 1 Immediate Execution Checklist (Exact Copy Edits)**
1. Edit Cell 4 (TL;DR code cell in AGO_Item_Details_Editor.ipynb): replace only the text inside the tldr_md bullet list with the exact lines below.
2. Use this exact TL;DR text:

**What this notebook does**  
- Authenticates to ArcGIS Online.
- Searches Item Details Terms of Use content (licenseInfo JSON field) for candidate items using the target terms entered in Step 2.
- Supports an optional secondary search in Step 4 to look for additional terms while excluding already matched item IDs, speeding up search.
- Uses a regex-based matcher during a dry-runto identify a Terms of Use HTML block based on:
- Uses a regex-based matcher during a dry-run to identify a Terms of Use HTML block based on:
  - an Esri logo image, 
  - followed by license text, 
  - and optionally summary/terms links
- Replaces matched Terms of Use blocks with HTML loaded from the Step 6 Input HTML file path (default file: Esri_ToU.html).
- Shows a dry-run preview before any edits are applied.
- Generates a review report with checkboxes so you can choose which item IDs to edit.
- Applies edits only after explicit confirmation.
- Exports CSV outputs for primary/secondary scans, dry run, and final edit results.
- Works in ArcGIS Online notebooks and local VS Code notebooks.

3. Edit Step 2 markdown cell in AGO_Item_Details_Editor.ipynb: replace the full markdown source with the exact lines below.
4. Use this exact Step 2 markdown:

## 2. Scan your content
Search Item Details Terms of Use content (licenseInfo JSON field) for candidate items using the target terms entered below.
We use the search terms to find candidate items. Detailed matching happens in Step 6.
There is an optional cap: leave it blank to scan the entire org, or enter a number to stop after that many matches for faster test runs.
After the scan finishes, files will be saved for review and archival purposes. You can modify the output filenames for regular use.

5. Edit Step 4 markdown cell in AGO_Item_Details_Editor.ipynb: replace the full markdown source with the exact lines below.
6. Use this exact Step 4 markdown:

## 4. Secondary scan
Use this step to run an additional search with new target terms while skipping item IDs already matched in Step 2.
What is searched in this step: the secondary target terms entered below.
This step helps broaden coverage without reprocessing previously matched items.
After the secondary scan finishes, optional save fields appear below when there is secondary scan output worth exporting.

7. Edit Step 6 markdown cell in AGO_Item_Details_Editor.ipynb: replace the full markdown source with the exact lines below.
8. Use this exact Step 6 markdown:

## 6. Dry run
Do a dry-run before making any changes.
What is replaced in this step: matched Terms of Use blocks are replaced with HTML loaded from the Input HTML file path below.

Default matching mode (checkbox off):
- Looks for a recognized Esri logo, then scans forward within bounded distance for license text and related links.
- Distance bounds: logo to license text <= 5000 chars, license text to summary link <= 4000 chars, summary link to terms link <= 2000 chars.
- Summary/terms links are optional as a pair in this mode.

Strict matching mode (checkbox on):
- Requires recognized logo + license text + summary link + terms link in order.
- Tighter distance bounds: logo to license text <= 2000 chars, license text to summary link <= 1500 chars, summary link to terms link <= 1200 chars.

For technical users:
- You can change target-term behavior in helper_functions.py (parse_target_terms and related normalization helpers).
- You can change replacement HTML by editing the Input HTML file path or editing Esri_ToU.html.
- You can adjust matcher behavior in helper_functions.py constants and regex patterns (for example TOU_BLOCK_RE and STRICT_TOU_BLOCK_RE).

After the dry run finishes, an optional CSV export appears when there is output worth saving.

9. Edit README.md: replace the opening two paragraphs with the exact lines below.
10. Use this exact README opening text:

# ArcGIS Online Item Details Editor

This repository contains an ArcGIS Online notebook workflow for searching and updating Terms of Use content in ArcGIS Online Item Details pages at scale.

What is searched: Item Details licenseInfo content using target terms entered by the operator (primary and optional secondary terms).
What is replaced: matched Terms of Use blocks are replaced with HTML loaded from the configured template file path (default template: Esri_ToU.html).

The workflow is designed to keep edits safe and reviewable: scan first, dry-run second, report review third, then apply edits only after explicit confirmation.

11. README consistency pass: update any remaining sentence that says only “identify outdated text” so it also states the replacement source is template HTML from Step 6 input path.
12. Verification after copy edits:
13. Re-run Cell 4 and confirm TL;DR now explicitly states what is searched and what is replaced.
14. Confirm Step 2, Step 4, and Step 6 markdown render with the new wording.
15. Confirm README opening section matches notebook terminology (search targets, replacement HTML template, review-first flow).

**Relevant files**
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/AGO_Item_Details_Editor.ipynb — TL;DR, step descriptions, user-facing workflow guidance, and widget wiring touched by rename batches.
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/helper_functions.py — context contract consumer, matching/replacement behavior, report rendering, preflight/status logic.
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/README.md — public discoverability and login-required usage model documentation.
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/scripts/generate_bootstrap_notebook.py — portable notebook intro consistency and helper/template bundling behavior.
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/.github/prompts/plan-agoItemDescriptionEditor.prompt.md — authoritative deferred semantic rename mapping and batch order.
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/.github/prompts/plan-post-runthrough-rollout.prompt.md — rollout gates, validation matrix, rollback/ownership model.
- /Users/davi6569/Documents/GitHub/AGO-item-description-editor/.github/prompts/runbook-operator-quick-checklist.prompt.md — operator procedure alignment during phased rollout.

**Verification**
1. Content clarity verification: TL;DR and Step 6 explicitly describe search targets, replacement source, strict/default matching semantics, and technical-user modification points.
2. UX verification: workflow remains understandable for non-technical operators with clear step transitions and status outcomes.
3. Contract verification: every renamed widget/context key resolves correctly in helper callbacks after each rename batch.
4. Functional parity verification: scan, dry run, report creation, apply edits, and final exports remain behaviorally consistent (counts, IDs, outputs).
5. Rollout-gate verification: entry criteria and phase exit criteria are met before advancing.
6. Auditability verification: required artifacts and run notes are archived per run, rollback path remains executable.

**Decisions**
- Included now: notebook-first improvements, explicit user-facing clarity, admin-first preflight UX, deferred-but-planned semantic renaming, gated rollout.
- Deferred until prerequisites: semantic renaming start, expanded production rollout, undo capability implementation.
- Out of current implementation scope: full web app rebuild and broad non-rollout feature expansion.
- Public access model: discoverable utility with sign-in required for operational actions.

**Further Considerations**
1. Recommendation: complete Phase 1 and Phase 1.5 copy/UX hardening first, then lock behavior before beginning rename batches.
2. Recommendation: enforce a no-mixed-change rule per patch set (either rename/mechanical or behavior/UX) to reduce regression ambiguity.
3. Recommendation: use the post-rename local stabilization evidence as the architecture decision checkpoint for next-stage investment.

## Immediate Execution Order (Post-Decision)

1. Commit and push current tracked implementation and planning changes in this repository.
2. Add repo split decision and simplified-admin-workflow planning docs to this repository.
3. Create simplify-admin-tool branch from updated main.
4. Create ArcGIS-Online-Item-Details-matcher-lab as a clean repository.
5. Seed the new matcher-lab repository with planning docs and README before porting code.
6. In this repository, finalize and execute the simplified admin workflow plan before code-level simplification.
7. In matcher-lab, draft advanced matcher settings design prior to implementation.
