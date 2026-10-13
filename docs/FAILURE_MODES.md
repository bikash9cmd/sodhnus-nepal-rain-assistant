# What breaks

The rule for every failure below: the person gets a correct answer, a plainer correct answer, or an honest "I can't", never a confident wrong one.

| # | Failure | What the person sees | How I know | Covered by |
|---|---|---|---|---|
| 1 | **The model invents a number** | The model is asked to rewrite once with the exact problem ("the number 187 does not come from any tool result"); if it fails again, the template answer from the tools it already called | `CheckerRejected` and `Fallbacks` metrics; the log stores the problems | `test_rejected_answer_is_rewritten`, `test_rejected_twice_falls_back_to_the_template`, `eval/checker_mutations.py` |
| 2 | **The model answers without calling a tool** | Any number in it fails the checker; the rules backend answers instead | As above | `test_answer_without_tools_that_states_numbers_is_replaced` |
| 3 | **A real number in the wrong place** (the old record quoted as the day's rain) | Caught when it displaces the required figure; a swapped secondary number can still get through | Measured: 34 of 35 swaps caught | `test_checker_rejects_wrong_answers`, mutation test |
| 4 | **Bedrock throttles, times out or errors** | The rules backend answers (in ~30 ms); the answer is plainer, the facts are the same | `Fallbacks` alarm: 10 in an hour | `test_bedrock_error_falls_back_to_rules` |
| 5 | **The model loops on tool calls** | Cut off after 4 rounds; rules backend answers | `Fallbacks` with reason `bedrock_error:TooManyToolRounds` | `test_endless_tool_calls_are_cut_off` |
| 6 | **The model calls a tool that doesn't exist, or passes junk arguments** | The error goes back to the model as data so it can correct itself; unknown arguments are dropped | Tool errors in the log | `test_unknown_tool_name_goes_back_to_the_model_as_an_error`, `test_bad_arguments_come_back_as_data` |
| 7 | **Someone asks for a forecast** (in any of three scripts) | A fixed refusal pointing to DHM's forecasts and flood warnings; no model call | `Refusals` metric | `test_forecasts_are_refused_in_three_scripts`, `test_refused_questions_never_reach_the_model` |
| 8 | **Prompt injection** | Refused by `guard.py` or the guardrail's prompt-attack filter. If something new gets through, the model can still only call read-only tools and its answer still has to pass the checker | Refusals with reason `injection` / `guardrail` | `test_other_refusals`, `test_guardrail_block_never_reaches_the_model` |
| 9 | **Barsha's data stops updating** (it has: the public feed's newest day is 24 August 2025) | "My data ends on 24 August 2025, so I have nothing for ..."; every API response carries `data_through` | `/health` reports `data_age_days`; Barsha's own stale-source alarm pages | `test_days_after_the_data_ends` |
| 10 | **Barsha changes its schema** | The function fails to load rather than reading the wrong column; requests error until fixed | Lambda `Errors` alarm | `test_schema_change_upstream_fails_loudly` |
| 11 | **Barsha republishes the tables** | The next answer after the 15-minute ETag check uses the new tables; if the check itself fails, the loaded tables keep serving | Reload logged | `test_cache_reloads_when_barsha_republishes`, `test_cache_keeps_serving_when_the_version_check_fails` |
| 12 | **Barsha publishes something wrong** | Partly caught: a season total under half the station's usual is flagged as probably unreported days recorded as zero (Dhankuta 2014). Subtler errors are repeated faithfully | Feedback on the answer | `test_implausibly_low_season_is_flagged` |
| 13 | **A place with no gauge** | Within 40 km: the nearest station's reading, named, with the distance. Beyond: no number, the two nearest stations named | Log | `test_town_without_station_maps_to_nearest_and_says_how_far`, `test_far_place_gets_no_number` |
| 14 | **A spike in traffic or scripted abuse** | Throttled at 5 requests a second (burst 20); at most 10 answers in flight; requests beyond get HTTP 429 | `TokenSpendAlarm`, budget alarm | Template review (cfn-lint) |

## The missing-day trap, end to end

This is the failure Sodhnus exists to prevent, so it is worth following through. On 15 July 2001, Kathmandu airport's record has no usable rainfall amount, and its weather codes say it rained. A naive reading of the raw data says 0 mm.

- **Barsha** keeps the day as `prcp_quality = 'missing'` with `rain_observed = true`, not as 0.
- **The tool** returns `status: "missing"` and no amount at all, so there is no number for the model to repeat.
- **The checker** would reject any amount in the answer, because no tool returned one.
- **The answer:** "Kathmandu Airport has no usable rainfall amount for 15 July 2001 (31 Asar 2058 BS). Its weather codes say it rained, so this was not a dry day."

## The proxy-station risk, seen in real data

The Melamchi flood that began on 15 June 2021 destroyed much of Melamchi Bazaar. Ask Sodhnus about Melamchi that day and it answers from Kathmandu airport, 26 km away: 15 mm, light rain. It says that this is a different station and that rain there can differ, and both statements are true. The number still describes the wrong place, because the flood came from rain and debris in the mountains upstream, not from the valley floor. The 40 km limit and the disclosure are the best this network allows. The real fix is more stations, which is outside what software can do.

## What I'd add next

- **A daily review job** over the answer log: rejected answers and thumbs-down answers, grouped by problem, so prompt or tool changes are driven by real failures.
- **`make eval-bedrock` in a scheduled job** against the deployed model, so a model version change that hurts routing shows up as a number, not as complaints.
- **A canary question** ("Kathmandu rain on 2024-09-28") answered every hour by the deployed API and checked for 194.1, which tests the whole path including Bedrock.
