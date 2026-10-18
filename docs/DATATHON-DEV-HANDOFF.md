# Datathon rubric audit and developer handoff

> Taking over development? Follow the [complete gap-closure plan](DATATHON-GAP-CLOSURE-PLAN.md) and track ownership/evidence in the [workboard](DATATHON-WORKBOARD.md). This audit preserves the evidence baseline and guidebook references behind that plan.

Audit date: **October 17, 2026, America/Chicago**. Reviewed source commit: **`665b3e2`**, on `iamisaacberg/datathon-rubric-handoff`, initially identical to the local `origin/preview` reference. County: **Okaloosa, Florida, FIPS `12091` only**.

## Start here

**The highest-priority development task is to run the existing trained model on LinuxONE, produce a real assessment there, and demonstrate that same result through the app.** The model, portable inference, assessment producer, API and display already exist. Do not start by training a replacement model or rebuilding the frontend.

The largest remaining submission gaps are evidence of both mandatory IBM labs, evidence of actual LinuxONE AI/ML execution, a rehearsed video of at most three minutes, and a completed submission package. Team registration, attendance, abstract submission and final submission are **unverified**, not proven absent.

Use this as the current takeover plan. [The earlier exposure handoff](TEAMMATE-HANDOFF.md) contains historical implementation tasks; its claim that no producer exists has been superseded by [the modeling pipeline](modeling.md) and [the first training report](modeling-run-v1.md).

Recommended order:

1. Team lead confirms eligibility, prerequisites, exact deadline and team name; retrieves missing receipts.
2. Isaac/model owner transfers the existing ignored artifacts and manifests to the incoming developer through an approved private channel.
3. Incoming developer verifies the artifacts, then performs authorized LinuxONE inference and benchmarking.
4. Integrator connects the resulting assessment to the existing API; Isaac checks the rendered demo.
5. Presenter records a timed walkthrough; team lead verifies links and submits with a receipt.

These are suggested roles, not assignments to unidentified teammates. Write names beside the task IDs before work starts.

## Evidence and scope of this audit

The controlling source is the supplied **Participant Guidebook, IBM Z Datathon 2026**, 22 PDF pages, attached at `.context/attachments/aUwKHf/Participant Guidebook_IBM Z Datathon 2026.pdf`. Page references below are PDF page numbers. The attachment is ignored and will not follow a Git handoff; share it separately with the teammate.

I read the guidebook, tracked repository docs, relevant model/API/frontend code, Git history and local artifact inventory, and ran the checks recorded below. This workspace has **no `data/` directory**, model environment, model artifacts, lab evidence, video or submission receipts. No other workspace, private event account, IBM host or deployed application was accessed. Prior deployment/training claims below are attributed to committed reports, not fresh host verification.

Status vocabulary:

- **Verified here:** source code, local files, history or checks inspected in this audit.
- **Recorded:** an existing project report describes an earlier run; its artifacts/host were not rechecked here.
- **Missing here:** no matching deliverable in this checkout; another teammate may have it.
- **Unverified:** requires a person, account, host or receipt outside this audit.

The guidebook links to [official rules](https://www.starhacks.org/ibmzdatathon-official-rule) and [Hack2skill submission](https://hack2skill.com/event/datathon-2026). Public text retrieval during this audit exposed no substantive rule text or submission fields. It did not resolve deadlines or establish account/submission status. Check the signed-in platform and hub announcements manually.

## What is already built

| Area | Evidence at this checkpoint | Boundary |
| --- | --- | --- |
| County data application | [README](../README.md), [runtime contract](data-contract.md), `quasar/server.py`, frontend and static source | Archive rainfall, parcel browsing, prepared input inspection, Data, Reports and downloads exist. Visual acceptance was not performed here. |
| Real county inventory and inputs | [Source catalog](data-sources.md), [parcel inputs](parcel-inputs.md), [activation record](real-data-rollout.md) | Recorded 113,818 county-contained parcels, terrain/FEMA/mapped-stream inputs and 45 native archive cells. Actual data are absent here. |
| LinuxONE data service | [Activation record](real-data-rollout.md) | Records an authenticated Okaloosa runtime on `s390x` and public HTTPS checks. This supersedes old notes about an inactive Miami-Dade bridge. It does **not** establish model execution or current availability. |
| Trained ML | [Training report](modeling-run-v1.md), `quasar/modeling/training.py`, `portable.py` | Recorded five-member XGBoost ensemble trained on a Mac, with a standard-library portable export. Model target is FEMA mapped-area fraction, not observed flooding. |
| Evaluation | [Training report](modeling-run-v1.md) | Spatial split, buffer, two baselines, held-out metrics, abstentions and native/portable parity are recorded. Do not describe model evaluation as missing altogether. |
| County assessment production | `quasar/modeling/production.py`, [modeling guide](modeling.md) | Existing `assess` and `benchmark` commands. One six-hour local assessment is recorded; no LinuxONE model activation is recorded. |
| Exposure API and UI | `quasar/exposure.py`, `quasar/static/app.js`, [display contract](exposure-display.md) | Matching artifact validation, full-inventory H3 P90/coverage, parcel lookup and model explanations exist. Results remain unknown without a matching artifact. |
| Safe failure and source handling | Tests, adapters, bridge and model validators | Unknown/stale states, server-only credentials and county/inventory checks exist. These are software controls, not flood validation or proof of a secure production service. |

Current app behavior matters for the pitch: it defaults to **October 9 archived forecasts**, has 25 hourly positions, and displays county-clipped H3 rainfall. The rainfall hex is the maximum of overlapping native cells; the exposure hex is a separate P90 parcel index. Switching to the **exposure layer** is necessary to demonstrate model results. The two layers do not represent the same quantity.

## Required participation and submission checks

Treat the open items below as submission blockers until the team supplies evidence. They are requirements from the guidebook, not additional product features invented by this audit.

| ID | Requirement and guidebook pages | Current evidence / missing deliverable | Owner and completion evidence |
| --- | --- | --- | --- |
| R1 | Currently enrolled college/university students; 4–6 members; individual registration plus team creation (pp. 1, 4, 15–16, 18, 20) | Team roster and registrations unverified. Registration/team deadline listed as Oct 10. | Team lead: verify all members, track/hub and H2S team record privately. Do not put personal registration details in the public repo. |
| R2 | Abstract: problem and proposed approach (pp. 12, 17–18, 22) | No submission receipt here. Main schedule says Oct 15; vocabulary table says before Oct 5. | Team lead: retrieve actual submitted abstract/receipt and organizer resolution of conflicting dates. A proposal PDF is not a submission receipt. |
| R3 | Mandatory LinuxONE setup session and participant learning/engagement sessions; join official Discord (pp. 12, 17–18) | Attendance and membership unverified. | Team lead: confirm attendance and prerequisites with members/organizers; record any accepted remedy for a missed prerequisite. |
| R4 | Both provided AI/ML labs completed before building: Predictive AI Hybrid AI scenarios (multi-model), and Predictive AI + Generative AI (p. 7) | No completion evidence here. Quasar's starter notebook is not evidence of either IBM lab. | Each required participant/team owner, as clarified by organizer: collect lab identifiers, completion records and redacted outputs. Ask organizer about missing/late completion; do not backdate. |
| R5 | Original solution and event-window code; no continuation hack (pp. 4, 7, 19–20) | Earliest reachable commit is `2f25c7a`, Oct 17 at 10:24:34 Central; all reachable commits fall on Oct 17 Central. Commit timestamps alone cannot prove authorship or when code was written. | Team lead: preserve history, contributor account of work, and disclose pre-event research versus event implementation. Do not rewrite history as eligibility evidence. |
| R6 | Legal/permitted use and links for open-source libraries, frameworks, tools and datasets (pp. 4, 17, 20) | Package manifests and data source links exist; no consolidated submission attribution list. Shadcnblocks-derived UI needs its provenance/terms checked rather than assumed to be open source. | Developer + lead: package/source/version/license links, copied asset notices, UI template permission/organizer clarification if needed. Keep county attribution/disclaimer. |
| R7 | Use IBM Z/LinuxONE; AI/ML runs there; platform screenshots support capability claims (pp. 1, 7–8, 16, 20) | Data-service activation recorded; model run, benchmark and judge-ready screenshots missing here. | Developer + Isaac: actual target-host inference, matching output IDs, benchmark, redacted screenshots of instance/model/results. See D2–D3. |
| R8 | Compulsory video, maximum 3 minutes: problem, supporting data, solution, tech stack, LinuxONE instance and model, solution demo (pp. 3–4, 8–9, 20) | No video or rehearsal evidence here. | Presenter: accessible final video, measured duration <=180 seconds and every required segment visible. Script below targets 175 seconds. |
| R9 | Code submission and repository link (pp. 3–4, 20) | Remote is `https://github.com/iamisaacberg/Quasar`; access for judges and final source revision unverified. Page 4 permits code zip, but pp. 4/20 still request repo link. | Lead: accessible GitHub/GitLab link to final `preview` revision, optional source ZIP, reproducibility notes and no secrets/raw property bundle. Do not send a stale `main` link as the reviewed code. |
| R10 | Project title contains team name (pp. 4, 20) | Actual team name unknown. | Lead: replace placeholder in `<TEAM NAME>_Quasar_IBM Z Datathon 2026`; verify exact submitted title. |
| R11 | Complete on-time Hack2skill submission (pp. 3, 12, 17–20) | Final cutoff, submitted fields and receipt unverified. | Lead: confirm exact local date/time/zone with UTD POC and H2S, submit, then retain timestamp/receipt and final URLs. |
| R12 | Original, respectful, non-hateful work and participant conduct (pp. 4–5, 20) | No issue established by this audit; acceptance/eligibility is not inferable from code. | Lead: participant acknowledgment and organizer questions resolved; no fabricated originality or participation claims. |

**Deadline ambiguity:** the Americas schedule uses “EST,” lists continuation through Oct 18 at 10:00 AM, and lists a 10:30 AM closing ceremony; the FAQ says local schedules come from the hub POC. It does not unambiguously label an exact final upload cutoff. Do not silently convert those labels into a Dallas deadline. The October 23 feedback/video entry is a post-event item, not evidence that the compulsory project video can wait until then. Optional IBM badges and November IBM Z Day participation are not development blockers.

The guidebook does not explicitly require Quasar itself to use generative AI, train on LinuxONE, or use all of containers/security/scalability. It **does** require the two labs and describes AI/ML running on LinuxONE. Portable inference from locally trained XGBoost is the proposed way to demonstrate that; explain and show it, including the open-source training lineage. WeatherNext being AI elsewhere, or LinuxONE serving JSON computed on a Mac, does not by itself prove the required on-platform AI execution. Confirm any interpretation dispute with the IBM SME.

## Gap analysis against every scoring category

Standard judging is **four categories × 10 points = 40** (pp. 6–9, 19–20). This is an evidence assessment, not a predicted judge score.

| Category | Existing strength | Missing or weak evidence | Concrete next deliverable |
| --- | --- | --- | --- |
| **Community value and theme alignment — 10** | County-specific forecast/input inspection; explainable unknowns; [premise](app-premise.md) names audiences and the problem. | No verified user workflow study, quantified benefit or polished source-backed problem statement. Current archive-only demo does not demonstrate live streaming decisions. Theme choice is not recorded as a submission decision. | Lead/presenter selects Theme 1, “Real-Time AI for Critical Decisions,” if consistent with the submitted abstract, and explicitly calls the demo a historical reconstruction. Identify one primary user, the decision supported and why existing separate maps are insufficient. Include sourced local problem evidence with date/geography and one measured task benefit if actually tested. No lives-saved or loss-reduction claim without evidence. |
| **Novelty and originality — 10** | Native forecast provenance + county-validated parcels + portable model + missingness-aware inspection is a coherent integration. | No concise comparison with ordinary weather viewers/FEMA maps; no demonstrated uniquely new AI method; originality/third-party evidence is incomplete. | A small comparison table covering what each reference does and the specific Quasar workflow difference. Cite real references after checking them. Preserve event history and attribution. Do not call this a new flood prediction algorithm solely because it combines XGBoost, H3 and weather. |
| **Technical design, LinuxONE and AI/ML — 10** | Substantial data pipeline, trained model report, held-out mapping-proxy results, portable inference, authenticated bridge and documented contracts. | Mandatory lab receipts; actual model execution on `s390x`; current host/artifact/API proof; target-host speed/memory; platform screenshots; clear up-to-date architecture; optional ML/GIS checks absent in this checkout. Local model has known subgroup weaknesses and no observed-flood validation. | Complete D1–D4. Show why LinuxONE does the essential computation and aggregation, prove the inference path, and quantify only measured capacity. Provide model/evaluation limitations, capability evidence and source/version identities. |
| **Execution, delivery and pitch — 10** | Working source, passing core tests, source-aware reports, model-detail UI and an existing demo path. | No final <=3-minute video, recorded end-to-end model/app demo, final link/access check, visual acceptance, accessible flowchart or submitted receipt. Historical docs can confuse a new presenter. | Complete D4–D7 and the submission checklist. Rehearse a single coherent story with visible instance/model/output and a known unknown-data example. Keep a recorded fallback and identify any failures honestly. |

For community evidence, the older handoff records **19 county-coded flash-flood reports across 12 episodes** in NOAA 2018–2025 files. Those files are absent here, and county-coded reports are not parcel-validated outcomes. Obtain the underlying records and verify the claim before placing it in the pitch. Do not convert “no report” into a negative flood label or imply those older events occurred during the October 2026 replay.

### Additional AI Innovation Excellence rubric

The additional award has **two categories × 10 = 20** (pp. 9–10). It is separate consideration for eligible high-scoring/innovative teams, not a routine 20-point addition to every standard score.

| Category | Remaining gap | Evidence that would strengthen it |
| --- | --- | --- |
| AI innovation and originality | A conventional tree ensemble plus an uncalibrated rainfall interaction is not demonstrated breakthrough AI. Differentiation is currently an integration hypothesis. | Specific original technical contribution, comparison/ablation evidence and explanation of why it solves a problem conventional approaches miss. Add only if time remains after the required package. |
| Transformational impact and technical excellence | No measured end-user benefit, adoption evidence, target-host scale demonstration or observed-flood validation; no substantiated transformation claim. | Real task measurement or domain feedback, measured county workload on LinuxONE, a credible adoption path and clear limitations. Do not invent users, partners or outcomes. |

## Development work queue

### D1 — Recover and verify the existing artifacts (P0, incoming developer + Isaac/model owner)

Git alone is insufficient. Request the existing release bundle rather than reacquiring weather, retraining or accessing another workspace. Model source location is recorded in the training report; the owner must supply it. Keep secrets separate from the data handoff.

| Required item | Expected relative location / identity |
| --- | --- |
| Parcel SQLite and its `.sqlite3.manifest.json` | `data/processed/okaloosa/linuxone/quasar-parcels.sqlite3`; inventory identity below |
| Reconciled inputs plus manifest | `data/processed/okaloosa/parcel-inputs/reconciled/parcel-inputs.sqlite3` and `manifest.json` |
| Authoritative boundary | `data/raw/census_okaloosa_county.geojson` |
| Inspection SQLite and manifest | `data/processed/okaloosa/parcel-inspection/20261018-marseille/`; contains verified overlaps for the exact saved forecast |
| Saved county archive | `data/processed/isaias-2026.json`, with source/import provenance; exact file hash must occur in inspection manifest |
| Portable model, evaluation, model card | `data/processed/okaloosa/modeling/portable-model-v1.json`; `experiment-v1/evaluation.json`, `MODEL_CARD.md` and saved native members |
| Research reproducibility records | `dataset-v1/manifest.json`, dataset and test ledger; experiment residuals, split records and native/portable parity evidence |
| Existing assessment and benchmark | `exposure-replay-20261009T050000Z.json` and its `.benchmark.json`, plus `benchmark-local-v1.json`; local reference only |
| Transfer and source records | Checksums, retrieval times, source IDs/URLs, terms, CRS/units, processing notes and transfer receipt |

Recorded SHA-256 identities from [the training report](modeling-run-v1.md):

```text
Inventory:  0d8bf9c244cbae678108bbc8149d80c60db30f60824e24cd49435f2b93b4fd5a
Boundary:   03d0eb4232382046cf1bc85c77c3fd7b7178bb0ac9af8dafdc8c1de09c3b00f4
Dataset:    447374887feed64c7d11918aca14fff9715fedaf4eebdda48ed5cde98ba93f87
Model:      c3896f84e4593bbe20af909aade20edf7d46e43459b79e7aa79d5dc13188457f
Assessment: 4c2283d716eaedd53c3f0f6d2c16224452f4b9f4ce317c08ee07921853f8b2c7
```

The inventory identity is the parcel source output hash, **not automatically the SQLite file hash**. Use each manifest's actual file checksum for transfer verification. Expected inventory is 113,818; recorded first assessment is 112,120 scored + 1,698 unknown. Preserve reasons, not just the totals.

**Done when:** incoming machine has an inventory of files and hashes, validated manifests and county/inventory/boundary/model/weather compatibility, and an identified private owner for host access. No credentials or raw data committed. If identities differ, reconcile versions before proceeding; do not change the expected hashes merely to pass.

### D2 — Execute trained inference on LinuxONE (P0, incoming developer / IBM integrator)

Requires explicit host-access authorization; this audit did not grant or exercise it. Reuse the current service and existing reviewed artifacts. No new BigQuery queries are needed for the chosen archived demo. The runtime uses Python's standard library; optional native training dependencies remain local. The modeling guide records missing `s390x` wheels for the checked training stack, so do not assume `pip install` of that stack will work on IBM Z.

After D1, these are explicit offline commands for the authorized host, from the repository/release root with the transferred relative layout. Choose unused output paths; the producer refuses to overwrite an existing artifact. These commands neither start services nor activate the app:

```sh
uname -m
python3 --version

python3 -m quasar.modeling audit \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/parcel-inspection/20261018-marseille

python3 -m quasar.modeling assess \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --inputs data/processed/okaloosa/parcel-inputs/reconciled \
  --boundary data/raw/census_okaloosa_county.geojson \
  --inspection data/processed/okaloosa/parcel-inspection/20261018-marseille \
  --model data/processed/okaloosa/modeling/portable-model-v1.json \
  --evaluation data/processed/okaloosa/modeling/experiment-v1/evaluation.json \
  --weather data/processed/isaias-2026.json \
  --from 2026-10-09T05:00:00Z --mode replay \
  --output data/processed/okaloosa/modeling/exposure-linuxone-demo-v1.json

python3 -m quasar.modeling benchmark \
  --database data/processed/okaloosa/linuxone/quasar-parcels.sqlite3 \
  --artifact data/processed/okaloosa/modeling/exposure-linuxone-demo-v1.json \
  --output data/processed/okaloosa/modeling/benchmark-linuxone-demo-v1.json
```

Save the complete redacted logs, actual architecture/Python/revision, file hashes, run ID, window, counts, elapsed time, peak RSS and free disk. Audit verifies lineage/hashes; it is not a substitute for the authoritative polygon-containment evidence already produced during GIS preparation. Preserve that evidence too.

The project's internal target is production plus R4–R7 aggregation under 300 seconds and 2 GiB peak RSS, with at least 1 GiB disk free. Those are **team targets, not rubric thresholds**. Recorded Mac results are 45.23 seconds and about 393.2 MiB, not an IBM benchmark. A new host run has a different run ID/computation timestamp and therefore normally a different assessment hash; compare matched inputs and outputs, not byte equality to the earlier Mac artifact.

**Done when:** real county model inference and aggregation finish on `s390x`, saved evidence identifies the evaluated portable model and complete inventory, and measured limits/failures are documented. Merely uploading precomputed Mac results is insufficient for this task.

### D3 — Connect the assessment to the app and preserve window identity (P0, integrator)

After authorized configuration review, point LinuxONE `QUASAR_EXPOSURE_FILE` at the verified new artifact. Retain the existing parcel database and private authentication. Follow [activation/rollback instructions](real-data-rollout.md) for any service/proxy change; do not replace the running deployment based on old bridge notes. Vercel reads exposure through its server-only `QUASAR_LINUXONE_API_URL` and token. Any restart, shared infrastructure change or deployment requires separate authorization under `AGENTS.md`.

Verify source-host authentication and the app proxy. Inspect responses for:

```text
GET /api/exposure?from=2026-10-09T05:00:00Z&to=2026-10-09T11:00:00Z&mode=replay&resolution=7
GET /api/exposure?from=2026-10-09T05:00:00Z&to=2026-10-09T11:00:00Z&mode=replay&parcel_ids=<verified-id>&run_id=<summary-run-id>
```

Select actual scored and unknown IDs from the produced artifact; do not assume the parcel in an old example is scored. Require matching run/inventory/model/window, `aggregation_architecture: s390x`, real coverage counts, and the same result in parcel details. Confirm unauthenticated direct source reads fail. Never put tokens in screenshots or URLs.

**Window limitation:** the existing producer and benchmark operate on one window; the recorded assessment covers Oct 9 **00:00–06:00 Central (05:00–11:00 UTC)**. The app has 25 hourly starts. A single assessment cannot color every frame. For the minimum demo, show this supported window and explicitly show unknown on an unsupported hour. If multiple scored hours are essential, implement and test a window-aware artifact selection/storage contract first. Simply concatenating 25 copies of the approximately 73 MB assessment exceeds the 128 MiB artifact cap, and modeling provenance is currently top-level for one forecast window. Coordinate changes to `quasar/exposure.py`, model contracts, producer, tests and docs; never reuse one hour's scores for another.

**Done when:** the hosted/local authorized app displays an actual matching LinuxONE model result, changing hour clears mismatched results, and an unknown example stays unknown. LinuxONE data serving alone does not close this item.

### D4 — Rehearse, verify and capture proof (P0, developer + Isaac)

- Run required checks below. Use the optional local modeling/GIS environment when modifying those components so their skipped tests actually execute; do not reset the held-out test ledger or retrain against published test results.
- Isaac checks: rainfall versus exposure layer/units, one scored parcel and its factors, one unknown parcel, H3 coverage, hour change, map/Data/Reports agreement for rainfall, mobile/readable labels, and source failure. Reports currently export source rainfall; do not promise a model-result report that is not implemented.
- Verify the submitted app link without account access and verify source/video links from the judge's perspective. Vercel protection can still block an otherwise public app.
- Capture redacted instance identification, `s390x`, the real inference command/output, benchmark and matching API/model/run IDs. A Dockerfile or generic IBM logo is not execution evidence. Only claim container execution if it was actually run; the recorded service is systemd-based.
- Record security controls actually exercised: private source endpoints, TLS path, no browser credentials, read-only artifacts and unknown-preserving failures. Do not claim confidential computing, hardware acceleration, high availability or enterprise security without evidence.

**Done when:** code checks plus recorded data/API checks plus Isaac's visual acceptance are all available, with failures and limitations stated separately. Unit tests are not a substitute for the latter two.

### D5 — Assemble the judge evidence package (P0, presenter + developer)

Create a shareable folder with final video, source revision/link, one-page architecture, concise model card/evaluation excerpt, data/software attribution, lab receipts and redacted platform evidence. Keep private receipts/data separate from public materials. Suggested filenames: `demo.mp4`, `architecture.pdf`, `model-summary.md`, `sources-and-attribution.md`, `linuxone-run.json`, `submission-receipt`.

The architecture should show:

```text
Explicit WeatherNext import + county/GIS preparation
             -> verified snapshots and manifests
Local XGBoost training -> evaluated portable model
             -> LinuxONE model inference + exposure production + H3 aggregation
             -> authenticated HTTPS API -> Vercel server proxy -> browser
```

Label the model/inference path “planned” until D2/D3 are proven. Distinguish preparation, training, inference, serving and browser rendering. Explain why LinuxONE performs the workload and how the protected data path works. The guidebook makes a flowchart and prototype optional, but they support technical/pitch scoring; a public deployment is not itself a mandatory submission item.

Model summary must include: target/units; training data and source dates; six terrain/area/stream predictors; spatial split/buffer; baselines; held-out metrics/support; model/version/hash; abstentions; and interpretation limits. The recorded supported-test RMSE is **0.115756 mapped-area fraction**, versus **0.233466** mean and **0.215976** ridge, on **7,792 supported test parcels**. Include the 118 unsupported test parcels and weak subgroups: fully mapped test MAE **0.262964**, validation fully mapped MAE **0.779924** on 60 parcels. Do not turn RMSE into “accuracy” or flood probability. These figures are from the committed report; retrieve evaluation artifacts before presenting them as independently checked.

The final exposure is `100 × learned susceptibility × rain_mm / (rain_mm + 50)`. The 50 mm interaction is uncalibrated. Forecast AI (WeatherNext), trained FEMA proxy (XGBoost), deterministic rainfall interaction and H3 aggregation are four distinct things. H3 does not improve native weather resolution. Tree-path contributions are not physical causation; ensemble spread is not a confidence interval.

**Done when:** every pitch claim has a source/artifact, all required evidence is accessible and redacted, and the final folder is usable by someone without access to the developer's machine.

### D6 — Record the video and submit (P0, presenter + team lead)

Suggested **175-second** storyboard (leaves five seconds below the maximum):

| Time | Show and explain |
| --- | --- |
| 0:00–0:20 | Actual team name, Quasar, Okaloosa user/problem, selected theme, one verified supporting fact. |
| 0:20–0:40 | Architecture and stack; why the LinuxONE computation is essential; distinguish WeatherNext and the local-trained proxy. |
| 0:40–1:25 | Actual LinuxONE instance/architecture, model identity and inference evidence; measured benchmark and linked result. |
| 1:25–2:15 | App archive window, rainfall/exposure distinction, scored parcel explanation, cell coverage, unknown example. |
| 2:15–2:40 | Held-out proxy result versus baselines, key weakness, no observed-flood/probability claim. |
| 2:40–2:55 | Community benefit, demonstrated scope, source/code access and concrete next step. |

Use these sentences only after D2/D3 succeed: “We trained a model against FEMA mapping, then ran its portable inference on IBM LinuxONE. Quasar combines that output with archived WeatherNext rainfall to show an experimental relative exposure index and its missing inputs.” Until then, explicitly call LinuxONE model inference an unfinished step.

Submission packet checklist: actual team-name title; final <=180-second video; accessible final code link/revision; software/source links; required platform/lab evidence; optional architecture/prototype; correct track; all H2S fields; successful submission receipt. A recording, upload page or generated ZIP is not a completed submission. Allow time to fix private links or upload failures before the organizer-confirmed cutoff.

### D7 — Resolve stale documentation (P1, incoming developer)

Use README, data contract, modeling report and this audit as the current entry points. The older premise/architecture/mechanisms docs carry offline-context banners but retain descriptions of fictional sites and routing. The old roadmap includes tasks already superseded by the public source-only runtime and real-data work. The older handoff's producer-missing paragraphs and hatching descriptions do not define the current transparent-interior UI. Some rollout steps still refer to an old team access gate.

After the final demo scope is frozen, update the relevant architecture/pitch/onboarding descriptions to match that scope and mark historical sections clearly. Keep retired HTTP endpoints retired. This audit adds entry links rather than rewriting unrelated documents or changing product behavior.

## Important gaps beyond the minimum submission

These affect scientific claims, community value and exceptional technical scores. They are **not all mandatory datathon features**. Do not spend the deadline rebuilding them before the P0 evidence package is complete.

| Gap | Why it matters / next acceptance evidence |
| --- | --- |
| Observed-flood validation | No verified parcel flood labels or coverage-backed negatives; the conditional outcome pipeline exists but has not trained a real outcome model. Obtain independently reviewed time/location-linked outcomes before claiming flood prediction skill. Code's minimum 10 episodes and 200 positives/200 negatives is a readiness gate, not proof of statistical sufficiency. |
| FEMA proxy limitations and subgroup weakness | Model learns regulatory mapping, not event dynamics. Reconcile effective dates/reference revisions and coastal/open-water issues; retain poorly performing groups and unknown terrain in reports. Do not tune on the published test set. |
| Missing physical inputs | Floor heights, hydraulic connectivity, drainage, surge/tidal processes and complete coastal/lake/canal coverage are not established. Mapped stream distance and low terrain are insufficient to infer flood depth or safe property. |
| Real-time operation | Current forecast is expired in project records and absent from app controls. No operational refresh/streaming path is demonstrated. A live claim would require authorized capped imports, verified freshness/availability, latency evidence and failure handling. Keep the current demo labeled archive/reconstruction. |
| Proven as-issued lead time | Initialization is not proof of publication availability. Preserve available publication times and disclose use of retrospective reference layers. No validated warning lead-time claim. |
| Official alerts | NWS remains explicitly disconnected. Implement freshness/coverage/error semantics if later authorized; disconnected is never “no active alerts.” |
| Usability and accessibility | No human acceptance record here for keyboard/focus, screen readers, contrast, reduced motion, mobile and exported report readability. Isaac performs visual review. Provide useful non-map information when maps fail. |
| Scale and service reliability | Need LinuxONE model and API latency, memory/disk, cold/warm behavior and error/rollback checks. A single county run is not multi-user load testing or nationwide scalability. The 853 KB JS bundle warning is a measured build fact, not proof of poor user performance. |
| Operational adoption | No confirmed agency partner, user study, measured emergency response improvement, production monitoring/refresh owner or reviewed public safety workflow. Keep benefits as hypotheses until evaluated. |
| Notifications/routing | Removed from the app; offline modules remain. The rubric does not require them. Do not reintroduce simulated routes as navigation, collect contacts or send messages to make the demo appear complete. |

## Code map and verified checks

| Change area | Start here |
| --- | --- |
| Artifact identity, feature schema and preparation | `quasar/modeling/dataset.py`, `__init__.py`, `contracts.py`; `quasar/inspection_prepare.py`; `tests/test_modeling.py`, `test_parcel_context.py` |
| Training/export and test-ledger protection | `quasar/modeling/training.py`, `portable.py`, `outcomes.py`; [modeling guide](modeling.md) |
| Target-host inference/benchmark | `quasar/modeling/__main__.py`, `production.py` |
| Assessment reads and H3/parcel API | `quasar/exposure.py`, `server.py`; `tests/test_exposure.py`, `test_api.py` |
| Source bridge, parcel contexts and rollout | `quasar/bridge.py`, `parcel_context.py`, `ops/linuxone/`; [bridge](data-bridge.md), [activation](real-data-rollout.md) |
| App layer/selection/model display | `quasar/static/app.js`, `spatial.js`, `inspection.js`, `frontend/dashboard.tsx`; JS tests |
| Forecast archive and exports | `quasar/forecast_timeline.py`, `adapters/county_weather.py`, `replay.py`, `source_exports.py`; [data contract](data-contract.md) |

Required local checks were run against `665b3e2` during this audit:

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | **192 run, OK, 8 skipped**: optional ML/GIS dependencies absent. Skips include native export/training/outcomes and spatial preparation/containment tests. |
| `npm ci --ignore-scripts` | Passed; 207 packages installed, audit reported zero vulnerabilities. This is not a comprehensive security audit. |
| `npm run check` | Passed TypeScript and JavaScript syntax checks. |
| `npm test` | **75 passed**, none skipped. |
| `npm run build` | Passed; generated assets unchanged. Vite warned about JS chunk size above 500 KB (853.18 KB output, 259.20 KB gzip). |

Local logs are `.context/datathon-python-tests.log`, `datathon-npm-ci.log`, `datathon-check.log`, `datathon-js-tests.log` and `datathon-build.log`; they are ignored and must be shared separately if wanted. No notebook was changed/executed, Docker/s390x build performed, model retrained, cloud query run, service activated, browser review performed or external submission made in this audit.

Repeat the required checks after implementation changes, add targeted tests for scoring/data/API changes, build frontend assets when source changes, and run `git diff --check`. Keep work on a feature branch and target `preview` for an explicitly authorized PR handoff. Do not rename the existing branch, push `main`, access another workspace, deploy or restart shared services without the applicable authorization. Optional notebooks stay outside runtime and use shared functions.

## Takeover completion record

Fill this in when the next developer accepts ownership; blank fields are unresolved, not implicitly complete.

```text
Incoming developer / owner:
Team name / lead / selected track and theme:
Confirmed cutoff (date, time, time zone, organizer source):
Registration / abstract / attendance / lab receipts:
Final source commit and judge-accessible repository URL:
Artifact transfer receipt and verified identities:
LinuxONE authorization owner / runtime revision:
Model hash / inference log / target-host benchmark:
Exposure run ID / inventory ID / demonstrated window:
API verification / Isaac visual acceptance:
Video URL / exact duration:
Attribution and architecture links:
Submission timestamp / receipt:
Remaining limitations and owner:
```
