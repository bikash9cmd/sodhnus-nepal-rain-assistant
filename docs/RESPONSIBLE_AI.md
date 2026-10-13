# Responsible AI

A short system card: what Sodhnus is for, who its mistakes would hurt, and what I did about each.

## Intended use

- **Reporters** checking a rainfall figure before publishing: how much fell, how unusual it was, whether it was a record.
- **Disaster responders and local officials** looking back at a storm: where it rained most, what the record says, which stations had gaps.
- **The public**, asking in Nepali or English.

## Not for

- **Forecasts or warnings.** Refused, with a pointer to the Department of Hydrology and Meteorology (mfd.gov.np for forecasts, hydrology.gov.np for flood warnings).
- **Safety decisions** (travel, evacuation). Refused.
- **Casualties, damage, relief.** Refused, with a pointer to the government's disaster portal.
- **Places far from a gauge.** Answered with "no number" and the nearest stations.

The refusals are fixed texts, not model output, so they are the same every time and can be reviewed by someone who reads Nepali.

## Who the errors would hurt, and what stands in the way

| Error | Who is hurt | Mitigation | Residual risk |
|---|---|---|---|
| A wrong number | A reporter who prints it; readers who trust it | Every number checked against tool results; required figure per result; rewrite then template fallback | Small amounts that coincide with date numbers ([EVALUATION.md](EVALUATION.md)) |
| A missing day reported as dry | A responder judging where it rained | Missing days have no amount in the tool result, and the answer says if it rained | None found |
| A false "record" or "unprecedented" | Public trust; it inflates fear | Record claims need a tool that found a record | On wettest-days lists, a record attached to the wrong day |
| A forecast in disguise | Someone who acts on it | Refused before the model in three scripts; guardrail denied topic; future tense rejected in answers | A cleverly phrased question the patterns miss, which the model would still have to answer only from past data |
| A distant station's rain presented as local | People in that town | 40 km limit; station and distance always stated | A nearby station in a different microclimate (Melamchi, [FAILURE_MODES.md](FAILURE_MODES.md)) |
| Stale data presented as current | Anyone asking about "today" | `data_through` on every answer; "after the data ends" answers | Someone who doesn't read the date |
| Upstream errors repeated | Everyone | Implausibly low season totals flagged | Subtler errors in Barsha pass through |

## Language and fairness

- **English and Nepali are treated as equals.** Every template, refusal and caveat exists in both; the checker reads Devanagari digits; the evaluation includes Devanagari and romanised Nepali questions; answers follow the question's language.
- **But not equally tested.** 14 of the 60 evaluation questions are answered in Nepali. A Nepali reader hasn't reviewed the answers yet, and that's the first review I'd ask for.
- **Other languages of Nepal aren't served.** Maithili, Bhojpuri and Tharu are widely spoken in the Terai, where floods do the most damage. A question in them would most likely get the help text. That gap falls on exactly the people most exposed.
- **Coverage is uneven by geography.** Sixteen stations, mostly in towns and at airports. Remote hill districts get "no number" far more often than cities. Sodhnus says so rather than filling the gap with a guess, but the gap is real.

## Transparency

- Every API response carries `data_through`, the stations used (`sources`), the source note (NOAA GSOD via Barsha) and, for refusals, the reason.
- Answers name the station they come from, the date in both calendars, and every caveat the tool returned (missing, partial, suspect, proxy, assumed year).
- This repository documents the checker's measured misses, not just its hits.

## Privacy

- The data is public weather data; no personal data is needed to answer.
- People do paste phone numbers and names (asking about a relative in a flood area). Phone numbers and emails are redacted before anything is stored; the log keeps items for 30 days; the guardrail's PII policy anonymises them on the model's side.
- No accounts, no tracking. The feedback route stores a yes/no against an answer id.

## Human oversight

- `POST /feedback` lets anyone mark an answer unhelpful; those, plus every checker rejection, are the review queue.
- Alarms go to a person when fallbacks spike (the model or prompt changed behaviour) or spend spikes.
- Model, prompt and checker are versioned together in this repository, and the evaluation runs in CI on every change.

## AWS AI Practitioner mapping

| Topic | Where |
|---|---|
| Foundation model selection, cost and latency trade-offs | [ADR-003](ALTERNATIVES.md#adr-003-which-foundation-model), [COST.md](COST.md) |
| Prompt engineering, inference parameters | [`prompts.py`](../sodhnus/prompts.py), temperature 0 / top-k 1 in [`bedrock.py`](../sodhnus/bedrock.py) |
| Tool use / function calling | [`tools.py`](../sodhnus/tools.py), [`bedrock.py`](../sodhnus/bedrock.py) |
| RAG and when not to use it | [ADR-002](ALTERNATIVES.md#adr-002-how-the-model-gets-facts-typed-tools-vs-text-to-sql-vs-rag) |
| Guardrails | [`infra/template.yaml`](../infra/template.yaml), [ADR-005](ALTERNATIVES.md#adr-005-where-the-guardrail-sits) |
| Hallucination detection and evaluation | [`checker.py`](../sodhnus/checker.py), [EVALUATION.md](EVALUATION.md) |
| Security of GenAI apps (prompt injection, least privilege, denial of wallet) | [ARCHITECTURE.md](ARCHITECTURE.md#security) |
| Responsible AI (fairness, transparency, privacy, oversight) | this document |
