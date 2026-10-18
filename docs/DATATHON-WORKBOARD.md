# Quasar teammate workboard

Use this with the [complete execution plan](DATATHON-GAP-CLOSURE-PLAN.md) and [evidence audit](DATATHON-DEV-HANDOFF.md). This is a planning tracker: **none of the rows below is marked complete by creation of this document**. Existing implementation and historical run evidence are described in the audit.

## Takeover details

| Field | Fill in before starting |
| --- | --- |
| Incoming development owner | Unassigned |
| Team lead / actual team name | Unconfirmed |
| Runtime/access owner | Unassigned |
| Model/data owner | Unassigned |
| Presenter | Unassigned |
| Visual reviewer | Isaac |
| Selected theme / track | Confirm against submitted abstract |
| Source baseline | `665b3e2`; verify current checkout |
| Final cutoff / time zone / organizer source | Unconfirmed; do not infer from ambiguous guidebook schedule |
| Last proven demo window | Recorded local assessment: Oct 9, 2026, 05:00–11:00 UTC; host/app proof pending |
| Artifact transfer location / receipt | Unconfirmed; private channel |
| Evidence ledger location | To be created; proposed layout in plan section 8 |

Statuses: **Open → In progress → Ready for review → Verified**. Use **Blocked** with an owner/next action when an external dependency prevents progress. Use **Deferred** only for an explicitly retained post-deadline item. “Documented limitation” is not “Verified capability.”

## Task queue

P0 means needed for the immediate submission/demo. P1 means evidence or usability work to prioritize after the core path works. P2 means broader research/operation; it remains open if deferred. Formal event requirements take priority over these project labels.

| ID | Task | Priority / owner role | Depends on | Deliverable required for verification | Status |
| --- | --- | --- | --- | --- | --- |
| T01 | Eligibility, labs, team/title and deadline | P0 / lead | Organizer/member evidence | Private receipts and resolved prerequisite/cutoff questions | Open |
| T02 | Artifact transfer and audit | P0 / developer + supplier | Existing artifact owner | File/hash manifest, matched lineage and authoritative county-validation evidence | Open |
| T03 | Local/research baseline | P0 / developer | Source; T02 for actual data | Logs, versions, required checks and relevant optional-test results | Open |
| T04 | Actual LinuxONE inference | P0 / runtime + developer | T02, T03, authorized host access | Real `s390x` run, complete output, parity comparison, benchmark and redacted captures | Open |
| T05 | Activate and verify app path | P0 / integrator | T04, authorized changes | Same model/run/window in host, proxy, API and app; rollback evidence | Open |
| T06A | Honest single-window demo | P0 / developer | T05 | Supported hour works; unsupported hour clears scores and remains unknown | Open |
| T06B | Complete replay coverage | P2 / developer | T06A, agreed contract | Catalog/orchestrator, exact per-window provenance, bounded memory, tests and coverage report | Open |
| T07 | Reproducible model summary | P0 / model owner | T02; T04 for host claims | Verified metric lineage, baselines, exclusions, weak groups and limitations | Open |
| T08 | Functional and human acceptance | P0 / developer + Isaac | T05, chosen T06 path | Test matrix, actual visual/accessibility checklist and fixes | Open |
| T09 | Runtime performance/security evidence | P0 for claimed capabilities; P1 for broader testing / runtime owner | T04, T05, approved test scope | Measured production/API limits and proof for platform/control claims | Open |
| T10 | Attribution, originality and code link | P0 / developer + lead | Source inventory, T01 | Reviewed resource/terms list, contribution record and accessible final source | Open |
| T11 | Community value and novelty | P0 brief; P1 external measurement / presenter + lead | Theme, sources, usable demo for study | Sourced problem/comparison; separately labeled actual user evidence | Open |
| T12 | Docs and pitch package | P0 / presenter + developer | T07–T11 | Current architecture, claim ledger, timed rehearsal and final evidence package | Open |
| T13 | Submission | P0 / lead | T01, T10, T12 | <=180-second video, accessible links, correct fields and successful receipt | Open |
| T14 | Proxy weakness investigation | P2 / model owner | T07, appropriate holdout/data review | Reproduced failure analysis and evaluated improvement or documented use restriction | Open |
| T15 | Observed-outcome experiment | P2 / research/data owner | Suitable independently reviewed labels and forecasts | Coverage-backed labels, leakage checks and held-out outcome evaluation | Open |
| T16 | Missing physical/context inputs | P2 / GIS + domain reviewer | Defined research target and source access | Validated features, provenance and evaluation of incremental value | Open |
| T17 | Current forecast and lead time | P2 / data/integration | Storage plan, budgets, explicit acquisition/operation scope | Repeated fresh coherent runs, expiry behavior and measured availability latency | Open |
| T18 | Official NWS alert integration | P2 / backend/data | Coverage contract and current API review | Verified coverage, lifecycle handling and distinct empty/stale/error states | Open |
| T19 | Reliable operation and adoption | P2 / product/runtime | T08/T09; relevant live/data work and approved scope | Owners, monitored objectives, recovery test and actual pilot feedback | Open |
| T20 | Innovation Excellence evidence | P1 evidence review; P2 experiments / research + presenter | T07/T11 and selected research results | Supported original contribution and technical/impact evidence | Open |

Assign a named owner and due/check-in time to each active item. Estimates and deadline buffers are in plan section 4; do not turn them into promises before checking actual access, artifacts and available hours.

## Per-task update template

Copy this under the task when work begins. Keep private URLs/receipts outside the public repo and reference their private evidence ID here.

```text
Task ID / named owner:
Status / next check-in:
Current source revision and environment:
Required authorization or external dependency:
What changed or was verified:
Evidence ID / path / checksum / observation time:
Checks run and results, including skips:
Reviewer / review date:
Remaining limitation or blocker:
Next concrete action and responsible person:
Rollback or last proven state:
```

## Demonstration gate

- [ ] Required participation/lab questions have actual receipts or organizer disposition.
- [ ] Correct data/model release is transferred and audited.
- [ ] Actual LinuxONE model inference and aggregation are recorded.
- [ ] Source, proxy, API and app agree on run/model/inventory/window.
- [ ] One scored and one unknown example are verified; examples are not presented as a representative validation study.
- [ ] Unsupported hour, stale data and source failure cannot appear as a fresh low score.
- [ ] Core and relevant optional checks pass; Isaac accepts the rendered walkthrough.
- [ ] Each platform/model/performance claim has evidence and a stated boundary.
- [ ] Final architecture and attribution match the actual demo revision.

## Submission gate

- [ ] Team name appears in the actual title; track/theme are correct.
- [ ] Video is accessible, understandable and <=180 seconds including all extras.
- [ ] Video includes problem, supporting data, solution/demo, stack, LinuxONE instance and model.
- [ ] Judge-accessible source URL points to the reviewed code, with open-source/resource links.
- [ ] Optional prototype/architecture links work and do not imply unverified capabilities.
- [ ] Exact cutoff is confirmed; upload/access buffer remains.
- [ ] Submission is completed in the team account, reopened and checked.
- [ ] Receipt, final content, URLs, revision and submission time/time zone are retained privately.

## After submission

Record which outcome was reached: submission complete, demonstration complete, or deeper research/operation complete. Move unfinished work to a dated follow-up with an owner. Keep T06B and T14–T20 open/deferred unless their actual acceptance evidence exists. Share the plan, audit, updated workboard, source revision, transfer manifest, access owner and last working demo state with the next developer; a Git link alone does not transfer ignored artifacts.
