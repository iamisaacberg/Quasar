# App premise and product boundaries

## The idea

Quasar explores how a county-focused application can combine rainfall forecasts with local site characteristics and explain which locations deserve closer investigation as conditions change. Its scope is **Okaloosa County, Florida, FIPS `12091`**. The project is an IBM Z Datathon research application, with a working demonstration that teammates can inspect and extend.

The central question is: **How can we show changing exposure, the inputs behind it, and the limits of the available evidence in one place?**

The current implementation answers that question with six fictional exercise sites, three synthetic weather windows, an optional imported WeatherNext rainfall snapshot, a configurable historical reconstruction, and a transparent five-factor score. It provides a mechanism for exploring an idea; it has not established predictive skill for real homes or roads.

## The problem being explored

Forecast rainfall, terrain, mapped flood zones, waterways, gauges, and official alerts describe different parts of a weather event. They also have different geographic coverage, update schedules, units, and uncertainty. Combining them without those distinctions can produce precise-looking results that the inputs cannot support.

Quasar brings the pieces into a shared view while retaining their identities. A reader can inspect an input, see its contribution to a relative score, compare time windows, and see when the application lacks enough information to score a site. Historical reconstruction adds a time dimension; routing demonstrates the effect of explicit exercise restrictions.

This is the project's premise, rather than a measured claim about user demand or emergency response effectiveness. No user study, adoption result, or reduction in flood losses is established by the repository.

## Intended audiences

| Audience | Useful activity today | Evidence still needed for broader use |
| --- | --- | --- |
| Datathon judges and presenters | Trace an input through the API, score explanation, map, and report | Reproducible source-backed results and a demonstrated IBM Z run |
| Data and GIS teammates | Inspect contracts, acquire public research inputs, and design county-validated adapters | Real site inventory, spatial joins, source terms, and quality assessment |
| Modeling teammates | Study the baseline, run controlled experiments, and define evaluation | Independent observed outcomes and documented training/evaluation procedures |
| Frontend and integration teammates | Build on one shared pipeline and explicit source statuses | Usability review, accessibility evidence, reliability, and scale measurements |
| Future analysts or emergency-planning partners | Potentially inspect local exposure and source conditions | Domain review, operational agreements, validated outputs, and an appropriate service stack |

Residents appear in the routing and message-preview exercises. The current app has no real subscriber system, verified shelter service, or operational resident guidance.

## What the application currently does

### Explore synthetic conditions

The default dashboard offers `baseline`, `heavy-rain`, and `peak` windows. Rainfall and gauge margin change; the fictional sites retain their static inputs. Scores, factor contributions, site ordering, and occupied H3 summaries update from the selected window.

One site deliberately lacks terrain elevation. It stays unknown in every window. This demonstrates that missing information does not become a favorable input.

### Inspect imported rainfall

The WeatherNext scenario reads an explicitly imported local file. It combines native-grid forecast rainfall with the same fictional non-rainfall inputs and labels the result as a mixed demonstration. The application checks snapshot structure, six-hour completeness, and freshness. Loading the dashboard never starts a cloud query.

Existing integration notes record a successful October 17 import. That record establishes a past integration checkpoint; it does not establish that the local file is currently configured, fresh, or available on another teammate's machine.

### Reconstruct a historical forecast sequence

The `isaias-2026` scenario is configured for October 7–11, 2026, with 97 hourly selections including both endpoints. Each selected hour looks forward over the next six forecast hours. This is the app's configured reconstruction interval, not a claim of Okaloosa landfall or observed local flooding.

Archive mode uses eligible historical forecast runs when a separate archive is present. What-if mode allows explicit synthetic rainfall additions and road/destination overrides. Missing historical rainfall stays unknown in both modes. NHC advisory text supplies storm context when prepared; it is not a local flood-outcome dataset.

### Demonstrate routing assumptions

The routing exercise uses a locally prepared subset of county street-centerline geometry, fictional destinations, simulated access connectors, and an assumed speed. It can show a route changing after a restriction, destination loss, or manual override.

Historical road conditions are unavailable in archive mode. In what-if mode, closures are controlled exercise inputs. The output is not navigation, an evacuation order, a verified shelter opening, or evidence that a road is passable.

### Explain and share results

Reports provide a scenario overview, comparison of the three synthetic windows, and individual site explanations. CSV, GeoJSON, and a BI ZIP bundle reuse the application analysis. Browser printing supports saving the selected report as a PDF. No server-side PDF renderer, native BI workbook, or automatic BI refresh is included.

Notification previews show how an elevated-score message could be worded. The normal UI exposes them only for synthetic scenarios. They collect no real contact details and always report zero messages sent. The [roadmap](improvement-roadmap.md#p0--make-status-and-validation-consistent) identifies a backend scenario-validation gap to address before expanding this surface.

## What the demonstration establishes

It shows that the application can express a coherent workflow: load inputs, preserve missing values, compute an explainable baseline, expose GeoJSON, display sites and summaries, and reuse the same results in research and exports. Source inspection and synthetic tests can support claims about those software behaviors.

It does not establish that the score predicts floods, that one score corresponds to a given water depth or event probability, that an exercise route is safe, or that a message was delivered. The existence of a container also does not establish execution on IBM Z.

## Design principles

1. **Keep the county boundary explicit.** County identity is fixed. Future external site imports need authoritative geometry checks, beyond a county tag or bounding rectangle.
2. **Show the reasoning.** The baseline returns each input's contribution and the model version. A later trained model must carry its own documentation and evaluation.
3. **Expose uncertainty through state.** Missing, invalid, stale, disconnected, and unavailable inputs retain their meanings.
4. **Keep source scales honest.** Forecast assignment to a site and aggregation into H3 cells do not sharpen native weather resolution.
5. **Separate forecast from observation.** A reconstructed forecast is not a recorded flood outcome. Source issue time, validity, publication availability, and retrieval time answer different questions.
6. **Keep cloud work deliberate.** Importers are explicit commands, dry-run by default, with byte caps. The application reads local results.
7. **Use shared analytical code.** The app, CLI, reports, and notebooks call reusable Python functions. Jupyter remains optional.

## How to judge progress

For the datathon, useful progress means a clear explanation, reproducible inputs, honest source status, traceable calculations, preserved unknowns, and a run on the target environment. These are demonstration and engineering goals.

For modeling research, progress means defining the prediction target, acquiring independent outcomes, preventing time leakage, and measuring performance against a baseline on held-out events. For potential operational use, additional requirements include domain review, service reliability, individual access control, and any explicitly authorized consent/delivery system.

These are proposed success criteria. No model performance target, operational readiness level, or product-market conclusion has been achieved merely by creating the demo.

## Next reading

Read the [data guide](data-guide.md) for source boundaries, [mechanisms](mechanisms.md) for the implementation, and [improvement roadmap](improvement-roadmap.md) for a staged path forward. The [documentation index](README.md) links setup and contract references.
