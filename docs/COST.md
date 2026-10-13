# Cost

**About $2.80 a month at 1,000 questions, $8.60 at 10,000, $66 at 100,000.** Nothing runs between questions.

All numbers come from [`scripts/cost_model.py`](../scripts/cost_model.py) (`make cost`). Prompt and tool sizes are measured from the code and from real tool results on the evaluation set; tokens are estimated from characters, because I can't count Nova's tokens offline; prices are list prices kept in one dictionary at the top of the script. Check the AWS pricing pages before quoting them, and replace the estimates with the token counts Bedrock returns (`usage` in every Converse response, logged per answer) once deployed.

## One question

| | Estimate |
|---|---:|
| System prompt + 5 tool specs | 4,542 characters, ~1,140 tokens, sent on every call |
| Tool result (median) | 760 characters |
| Answer (median) | 216 characters |
| Converse calls | 2 (tool call, answer), plus a rewrite on an assumed 10% of questions |
| **Input / output tokens** | **~2,730 / ~170** |
| Nova Lite | $0.00020 |
| Guardrail (one text unit, three policies) | $0.00040 |
| Lambda (1 GB arm64, ~2.5 s mostly waiting on Bedrock) | $0.00003 |
| API Gateway + DynamoDB write | $0.000002 |

Refused questions (forecasts, injection, out of scope) and fallback answers cost no tokens: they're answered before or instead of the model.

## Per month

| Questions per month | Nova Lite | Guardrail | Lambda | CloudWatch | Other | Total |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | $0.20 | $0.40 | $0.03 | $2.20 | $0.00 | **$2.84** |
| 10,000 | $2.05 | $4.00 | $0.34 | $2.21 | $0.02 | **$8.62** |
| 100,000 | $20.45 | $40.00 | $3.35 | $2.35 | $0.22 | **$66.38** |

CloudWatch is 6 custom metrics ($1.80) and 4 alarms ($0.40), plus a little log ingestion. Not included: the container image in ECR (~$0.03) and Barsha itself (~$1.20/month, which Sodhnus shares rather than duplicates).

## Where the money goes, and what I changed

**1. The guardrail, not the model, was the biggest line.** With the guardrail attached to each Converse call, it is evaluated on the input and the output of every call, about 4.2 text units per question. At 10,000 questions that is $16.80 for the guardrail against $2.05 for the model. Calling `ApplyGuardrail` once on the question costs one text unit: $4.00. The output side is covered by the checker, which costs nothing ([ADR-005](ALTERNATIVES.md#adr-005-where-the-guardrail-sits)).

**2. No vector store.** A Bedrock Knowledge Base on OpenSearch Serverless has a minimum of about $175 a month (1 OCU) before the first question, roughly 20 times this system's total at 10,000 questions. The data is 320 KB of tables, held in memory.

**3. Nova Lite, not Nova Pro.** Pro would be about 13x the model cost per question. The job is routing and two to four sentences; the checker catches the mistakes a smaller model makes, and the fallback absorbs them.

**4. Metrics without dimensions.** My first version split 7 metrics by 4 backend values: 28 custom metrics, $8.40 a month, more than the model at 1,000 questions. Now 6 metrics, no dimensions, $1.80. Breakdowns by backend come from Logs Insights over the same log lines, paid per query.

**5. Spend caps, because an LLM endpoint is a billing endpoint.** HTTP API throttling (5 requests/s, burst 20), reserved concurrency 10, `maxTokens` 500, at most 4 tool rounds and 1 rewrite, a token-spend alarm and a budget. The worst case under the throttle is bounded and alarmed, not open-ended.

**6. The system prompt is short.** The tool specs are the larger fixed cost (3,000 characters). If token counts from real traffic show the fixed part dominating, Bedrock prompt caching for the system prompt and tool specs is the next lever.

## Options I haven't taken

| Option | Saving | Cost of it |
|---|---|---|
| Answer with the rules backend when it parses the question confidently; call the model only otherwise | Most of the model and guardrail spend for simple questions | Plainer answers; two code paths to keep in step (they already share tools and checker) |
| Cache identical questions for 10 minutes (the data changes daily) | Large on storm days, when many people ask the same thing | A cache to run (DynamoDB TTL would do) |
| Nova Micro | Roughly half the model line | Needs `make eval-bedrock` to show it routes as well on Nepali |
| Drop the PII policy from the guardrail (the app redacts before logging) | A quarter of the guardrail line | Personal details would reach the model; they don't go anywhere else, but I'd rather they didn't |
| Batch inference | ~50% on model tokens | Not applicable: a person is waiting |
