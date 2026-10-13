# Challenges and bugs

Real problems I hit while building this, in roughly the order I hit them, with what I changed. The ones about language and dates were the most surprising; the ones about the checker taught me the most.

## 1. The example from my own pitch got answered in the wrong language

The question I'd been using to describe the project, "How unusual was the rain in Pokhara on असोज १२?", came back in Nepali. My language detection said "any Devanagari means Nepali", and the date was in Devanagari. People mix scripts constantly: an English sentence with a Nepali date, a Nepali sentence with an English place name.

**Fix:** remove the dates and place names the parser recognised, then decide by what's left. Nepali grammar words (को, मा, कति, पर्यो) mean Nepali; an English sentence with a Nepali date stays English. Romanised Nepali ("kati pani paryo") is detected by marker words and answered in Devanagari.

## 2. असोज is not आश्विन, and "May" is not a month

The calendar library names the sixth month आश्विन (Aswin). Almost everyone writes असोज (Asoj). The same goes for साउन/श्रावण, जेठ/जेष्ठ, पुस/पौष, and romanised spellings vary even more (Sawan, Shrawan, Saun). Going the other way, "May I ask...", "push" (a spelling of Poush) and "mar" are ordinary English words.

**Fix:** a table of the spellings people use, every one added because a question used it, matched longest first with explicit not-a-letter guards (Python's `\b` doesn't work for Devanagari). A romanised month counts only with a day or a year next to it. Tests cover six spellings of the same day.

## 3. Without a year, which Asoj 12?

"Pokhara on असोज १२" has no year. The data ends on 24 August 2025, which is 2082 Bhadau, so Asoj 12 2082 hasn't happened in the data yet.

**Fix:** the most recent such day on or before the end of the data (2081 Asoj 12 = 28 September 2024), and the answer says the year was assumed. The tool result carries `year_assumed: true`, so the model has to say so as well.

## 4. रेकर्ड means two things, and my checker failed my own Nepali answers

The first evaluation run failed three Nepali questions on answers my own templates wrote. In Nepali, "पूरा रेकर्ड भएका दिन" means "days with a complete reading", but the checker's record-claim rule looked for रेकर्ड and decided the answer claimed a record without evidence. English has the same ambiguity ("the rainfall record for Taplejung").

**Fix:** the templates now say नाप (measurement) for data, and the checker only matches phrases that claim an extreme: रेकर्डमै, रेकर्ड तोड्यो, नयाँ रेकर्ड, "a new record", "record high".

## 5. Partial days came back as "at least ? mm"

While picking evaluation cases I looked for a partial day (fewer than 24 hours reported) and found that Barsha leaves `prcp_mm` empty for them and keeps the raw figure in `prcp_reported_mm`. My tool read `prcp_mm` and would have produced "at least None mm".

**Fix:** read `prcp_reported_mm` for partial days, and when it's 0 (which it is for nearly all of them), say only that part of the day was reported. The lesson was to read the producer's schema, not assume it: I wrote Barsha, and still got this wrong.

## 6. The nearest station to Chitwan is across a mountain range

To answer for towns without a gauge, I used the nearest station in a straight line. For Chitwan that is Pokhara, 73 km away on the other side of the Mahabharat range, at 827 m, one of the wettest places in Nepal. Simara, in the same lowland belt, is 79 km away. Neither stands in for Chitwan.

**Fix:** a station is used as a proxy only within 40 km, and the answer names it and gives the distance. Beyond that, no number: the answer names the two nearest stations and says why it won't guess.

## 7. Even a 26 km proxy can describe the wrong place

Melamchi is 26 km from Kathmandu airport, within the limit. On 15 June 2021, the day the Melamchi flood began, the airport had 15 mm: light rain. The flood came from the mountains upstream. Sodhnus says the reading is from a different station and that rain there can differ, and both statements are true, but the number still describes Kathmandu.

**Kept as is**, with this example in [FAILURE_MODES.md](FAILURE_MODES.md). The honest fix is more stations, not more code.

## 8. Sodhnus repeated a 277 mm monsoon with full confidence

Barsha publishes a June-September 2014 total of 277.2 mm for Dhankuta. Its other published seasons are 689 and 695 mm. The 2014 season passes Barsha's completeness rule because the days are flagged complete, but 62 of them read 0.00 in the middle of the monsoon. Sodhnus reported it as fact.

**Fix in Sodhnus:** a published total under half the station's median of other seasons is flagged, and the answer says it more likely reflects unreported days recorded as zero than a real drought. **The real fix belongs in Barsha:** a monsoon run of "complete" zeros should fail its quality gate. That's a Barsha change I haven't made yet, and Sodhnus can't fix the source.

## 9. The help text failed the checker

"Hello" was logged as an answer that failed the fact check. The help message has example questions in it ("Pokhara on Asoj 12, 2081", "Kathmandu monsoon total 2023"), and the checker rejected it because no tool had returned 12, 2081 or 2023, or looked at Pokhara.

**Fix:** fixed texts (help, refusals) are trusted and skip the checker; anything built from data goes through it. The tool-error message no longer contains examples, so it can be mixed with data answers safely.

## 10. The checker couldn't see a real number in the wrong place

The first measurement of the checker caught 0 of 39 answers where the day's rainfall had been replaced by another number from the same tool result: "Kathmandu Airport recorded 70.1 mm" (its 1-in-100 level) instead of 194.1. Membership checking, "is this number in the tool results?", can't see it, because 70.1 is in the tool results.

**Fix:** each tool result has one required figure, the number that answers the question (the day's rain, the season total, the top of a list), and the answer must contain it. Swaps caught went from 0/35 to 34/35. The miss left is a small amount that collides with a date (15 mm on 15 June).

## 11. "A new record for the station" slipped through

The record-claim pattern excluded "record for" so that "the rainfall record for Taplejung" wouldn't trigger it. That also excluded "a new record for the station", the exact sentence the mutation test used. Invented records caught: 4 of 34.

**Fix:** "new record" and "all-time record" always count; only "a record of" and "the record shows" are excluded. Now 27 of 34. The rest are on wettest-days lists, where the record day is in the results by definition.

## 12. My own "model-style" answer had a wrong number in it

To measure false rejections, I wrote 15 correct answers the way a model would phrase them. The checker rejected three. One was "about 47% of its 1-in-100 rainy day level": the real figure is 90.4/190.1 = 47.6%, which rounds to 48. The checker was right and my paraphrase was wrong. The other two used numbers the model would have to compute ("2% above the typical season").

**Fix:** the tools now return the derived numbers a writer reaches for (`this_day_percent`, `times_this_day`, `percent_of_median`), so the model never has to do arithmetic the checker can't verify. Rejected paraphrases went from 3 to 1; the last is "nearly 200 mm" for 194.1, rejected on purpose.

## 13. The guardrail would have cost eight times the model

Building the cost model, I found that a guardrail attached to Converse is evaluated on the input and the output of every call, two or three calls per question. At 10,000 questions a month: $16.80 for the guardrail, $2.05 for the model.

**Fix:** `ApplyGuardrail` once on the question ($4.00), and the deterministic checker on the output. The trade-off is in [ADR-005](ALTERNATIVES.md#adr-005-where-the-guardrail-sits).

## 14. Metrics by backend cost more than the model

My first metrics line put a `Backend` dimension on seven metrics. Four backend values make 28 custom metrics, $8.40 a month, more than Nova Lite at 1,000 questions.

**Fix:** six metrics, no dimensions ($1.80); the backend is a field in the same log line, so Logs Insights can split by it when I need it.

## 15. An unknown place got an answer for the whole country

"Rain in Xyzpur on 2024-09-28" found a date but no place it knew, so the rules backend answered "where did it rain most" for all stations, without mentioning that it had ignored the place.

**Fix:** when the question names a place (an "in/at/near" phrase or a Nepali मा) that isn't recognised, the answer starts with "I don't recognise the place in your question, so here is every station instead."

## 16. The Bedrock stand-in remembered the future

Three Bedrock-path tests failed with messages that looked impossible: the first request contained the tool result that only arrived in the second. My scripted Converse stand-in stored a reference to the session's `messages` list, which the session kept appending to.

**Fix:** the stand-in deep-copies every request. Worth remembering whenever a test double records arguments that the caller mutates.

## Smaller things

- **Say the year back in the calendar it was asked in.** "Pokhara monsoon 2081" was answered as "the 2024 monsoon". Now "2081 BS (2024)".
- **Nepali postpositions attach to names.** काठमाडौंमा, पोखराको: the place matcher strips मा, को, का, ले, बाट and a few others after a Devanagari name, and the templates write पोखरामा, not पोखरा मा.
- **"How complete is the rainfall *record* for Taplejung?"** still goes to the wettest-days tool in the rules backend. Left unfixed on purpose: it's a holdout question ([EVALUATION.md](EVALUATION.md)).
