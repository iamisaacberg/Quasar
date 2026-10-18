# Analyst task and community value

Primary user: a county analyst reviewing one dated forecast window and deciding which parcel inputs need closer investigation. The task is to identify the forecast's date/source, inspect parcel reference data, explain an experimental index or why it is unknown, and understand cell coverage. It is not to issue an evacuation or declare a property safe.

Okaloosa's [Local Mitigation Strategy](https://myokaloosa.gov/LMS) covers floodplain management alongside other hazards. The county also publishes [flood protection information](https://myokaloosa.gov/sites/default/files/Users/gmuser/CRS%20Flood%20Facts%20Flyer%20with%20web%20links%202025.pdf). These support a county flood-information use case, not an estimate of demand, affected parcels or lives saved. No incident totals or population statistics are used without verifying their original records.

## Comparison checked against primary references

| Reference workflow | Established role | Quasar's proposed addition / remaining limit |
| --- | --- | --- |
| [NWS weather and alert services](https://www.weather.gov/documentation/services-web-api) | Official forecasts, observations and alerts, with source-specific timing/geography | A separate dated forecast/parcel investigation view; Quasar does not replace official instructions. Its archive cannot show today's alerts. |
| [FEMA Map Service Center](https://msc.fema.gov/portal/home) | Official regulatory flood-map information | Parcel context next to a selected rainfall window; a model trained to reproduce mapping must be compared with simply showing that mapping. It does not independently validate the maps or predict an event. |
| [Okaloosa GIS viewer](https://webgis.myokaloosa.com/) | County GIS reference layers | An experimental linked forecast/model/unknown workflow. No claim that the county viewer lacks a particular feature or that Quasar is an agency-endorsed replacement. |

The distinct contribution to test is a single view connecting forecast provenance, prepared county parcel context, portable model inference and explicit unknowns. Fresh LinuxONE execution and API checks now have [actual evidence](verified-run.md); rendered review and measured analyst benefit remain open. The architecture alone does not establish technical novelty.

## Evaluation ready to run

Use two comparable information-finding tasks, each requiring a dated forecast, a parcel reference input and an explanation of unknown coverage. Compare the separate official-source workflow with Quasar. Alternate task order across willing reviewers. Record role, task/order, completion, time, incorrect interpretations and whether unknown was mistaken for low exposure. Do not collect unnecessary personal details or contact anyone automatically.

Success criteria before observing results: fewer source switches and completed tasks without more wrong source/time/unknown interpretations. Report every participant and failure, not just a favorable example. A small convenience sample is usability evidence; it does not measure emergency outcomes or representative adoption. No participants or measured benefit exist in this checkout. Isaac's visual review is separate from a user study or domain review.
