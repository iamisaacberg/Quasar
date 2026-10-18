# Source and contribution record

This implementation preserves Git history and the existing feature branch; it does not claim all repository code or UI assets as original. Team/event eligibility and originality dispositions were excluded from this task and remain outside this record.

- PR #26 (`507de03`) supplied the audit, 20-task plan and workboard.
- Existing model/preparation, geometry, forecast, browser and proxy code are reused. Their original commits and training/activation reports remain in history.
- `preview` through `d920a8d` was merged into this feature branch, preserving PR #27's active exact-hour directory, PR #25's manual compiled-scorer fallback and PRs #28–#30's app fixes. No branch rename, history reset or service replacement was performed.
- Local checkpoint `6e494e7` adds an optional hash-pinned catalog/batch workflow, transfer/model-evidence/parity tools, a separate county official-alert importer/API, regression tests and the demonstration package. Merge `f40e1b0` reconciles this with the later `preview` behavior. Subsequent commits refine the live NWS canonical endpoint and record actual verification. Work was performed with Codex under Isaac's direction.
- Authorized verification transferred existing inputs/models/assessments and executed unchanged model arithmetic in an isolated LinuxONE directory. It did not train new weights, change an existing service, query new WeatherNext dates or deploy.
- Shadcnblocks supplies licensed application/dashboard/chart structures; React, Radix, Lucide, Mapbox, H3 and other dependencies retain their own provenance/terms. The [attribution record](sources-and-attribution.md) and [locked package inventory](dependency-inventory.json) identify them. No template permission or third-party authorship is inferred from an API key or Git author field.

Final code access must point to the reviewed feature/`preview` commit, with intended reviewer access checked separately. A local commit is not a pushed branch, public-access check, event submission or permission to redistribute raw data. Do not update `main` merely to change a default-branch link.
