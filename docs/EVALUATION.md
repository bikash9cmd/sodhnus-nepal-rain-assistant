# Evaluation

Two questions matter for an assistant like this: does it answer correctly, and when something upstream goes wrong (usually the model), does the wrong answer get stopped? I measure them separately.

## 1. The question set

[`eval/dev.jsonl`](../eval/dev.jsonl) (35) and [`eval/holdout.jsonl`](../eval/holdout.jsonl) (25), written together before I tuned anything, then split. I fixed bugs the dev set exposed and left the holdout set alone apart from fixes to the checker that also showed up on dev.

| | Count |
|---|---:|
| Questions to answer in English | 46 |
| Questions to answer in Nepali | 14 (9 in Devanagari, 5 in romanised Nepali) |
| English questions with a Nepali date ("on असोज १२", "31 Asar 2058") | 2 |
| `rain_on_day` / `monsoon_total` / `wettest_days` / `rain_across_stations` / `station_coverage` | 26 / 9 / 6 / 3 / 3 |
| Should be refused: forecast / impact / safety / injection / unclear | 5 / 2 / 2 / 2 / 2 |
| Data traps: missing day, suspect value, proxy town, too-far town, after the data ends, implausible season | 2 / 1 / 3 / 2 / 2 / 1 |

**Scoring.** A question passes only if every check applies and passes: the answer is in the right language; it was refused for the right reason, or it called the right tool for the right station and date (or year); the status is right for trap questions (`missing`, `suspect`, `no_station_nearby`, `after_data_end`); a proxy answer states the distance; the answer contains the headline value; and the answer passed the checker.

**Expected values are independent of the code under test.** [`eval/reference.py`](../eval/reference.py) computes each headline value with DuckDB straight from the parquet files. It does not import `sodhnus.tools`, so a tool that reads the wrong column or forgets to exclude a suspect value disagrees with the reference instead of agreeing with itself.

### Results

| Backend | Dev | Holdout |
|---|---:|---:|
| Rules, first run | 31/35 | 23/25 |
| **Rules, now** | **35/35** | **24/25** |
| Nova Lite on Bedrock | not run | not run |

First-run failures, all fixed except one:

- **Three Nepali answers failed my own checker** (d11, d34, h06). "रेकर्ड" in Nepali means both "a record" and "the data", and my templates used it for the second meaning. The checker read it as a record claim. Fixed in the templates and the checker ([bug #4](CHALLENGES_AND_BUGS.md)).
- **Two station-coverage answers wrote the date as "23 August 2025"** and the scorer only looked for "2025-08-23". A scorer bug, not an answer bug.
- **h17, still failing:** "How complete is the rainfall *record* for Taplejung?" The rules backend sees "record" and lists Taplejung's wettest days. I've left it: it's the kind of ambiguity a model handles and a keyword parser doesn't, and fixing the parser against a holdout question would make the holdout number meaningless.

### What the 24/25 does and doesn't say

It says the tools, the BS calendar handling, the place resolution, the refusals, the templates and the checker work on these questions. It does not say how Nova Lite will route real people's questions, because I haven't been able to run it: my build environment has no Bedrock access. The rules backend scores well because I wrote both the questions and the parser; real users will write things neither of us expected.

`make eval-bedrock` runs the same 60 questions through Nova Lite and the same scorer, and also records tokens, rewrites and fallbacks per question. That is the number I'd want before calling this done.

## 2. Does the checker stop wrong answers?

[`eval/checker_mutations.py`](../eval/checker_mutations.py) takes the 47 correct, non-refused answers and breaks each one the ways language models break numbers, then counts how many broken answers the checker rejects. It also counts how many *right* answers it rejects: the 47 originals, plus 15 answers I wrote in the style a model tends to use (rounded, reordered, with percentages and "about"), in [`eval/paraphrases.jsonl`](../eval/paraphrases.jsonl).

| Mutation | Example | Caught |
|---|---|---:|
| `plus_3` | 194.1 mm -> 197.1 mm | 39/39 |
| `minus_1` | 194.1 -> 193.1 | 38/39 |
| `plus_10pct` | 194.1 -> 213.5 | 39/39 |
| `times_10` | 194.1 -> 1941 | 39/39 |
| `digit_swap` | 194.1 -> 914.1 | 34/34 |
| `wrong_field` | the day's 194.1 replaced by the station's 1-in-100 level, 70.1 | 34/35 |
| `invented_record` | "That is a new record for the station." | 27/34 |
| `forecast` | "More heavy rain is expected tomorrow." | 47/47 |
| `unlooked_station` | "Simara also had heavy rain." when no tool looked at Simara | 44/44 |
| **All** | | **341/350 (97%)** |

| Right answers | Rejected |
|---|---:|
| Template answers | 0/47 |
| Model-style paraphrases | 1/15 |

The one rejected paraphrase says "nearly 200 mm" for 194.1. That's rejected on purpose: rounding up to a round number is how 194 becomes "200 mm, unprecedented" in a headline.

### How the checker got here

| Version | Wrong answers caught | Notes |
|---|---:|---|
| Numbers must appear in tool results | 284/357 (80%) | `wrong_field` 0/39, `invented_record` 4/34 |
| + fix the record-claim pattern | 307/350 (88%) | "a new record **for** the station" had slipped past an exclusion meant for "the rainfall record for Taplejung" |
| + required figure per tool result | **341/350 (97%)** | `wrong_field` 0/35 -> 34/35 |

(The denominators move slightly because the mutation script itself was fixed between runs: the first version sometimes "mutated" a number into a value that was also a date component, and added stations that the tools had in fact looked at.)

### The misses, honestly

- **Small amounts collide with dates.** Melamchi on 15 June 2021 answers from Kathmandu airport: 15 mm. Mutated to 14 mm, it passes, because 14 is in the tool results (the last similar day was 14 June) and 15 is still in the answer (as the date). Membership checking is weakest exactly where values are small and dates are near them.
- **Invented records on wettest-days lists.** A list of the five wettest days contains the record day by definition, so "a new record" attached to the wrong day in the list isn't detectable by this check.
- **Anything without a number.** "Rain was widespread across the east" can't be checked by a number checker. Contextual grounding checks would be a second layer for that ([ADR-006](ALTERNATIVES.md#adr-006-my-own-checker-vs-bedrock-contextual-grounding-checks)).

## 3. Not measured yet

| What | Why it matters | How |
|---|---|---|
| Nova Lite routing accuracy on this set | The headline number for the model path | `make eval-bedrock` |
| Real token counts and latency | The cost model's main assumption | `usage` from each Converse response is logged per answer |
| How often the model needs a rewrite or falls back | If it's often, the prompt or the model is wrong | `rewrites` and `fallback` per answer, in the log and the eval output |
| Nepali quality judged by Nepali readers | Correct numbers in awkward Nepali still fail the reader | A few journalists rating 50 answers; the answer log's thumbs up/down |
| Questions real people ask | My set is my guess | The answer log, after launch |
