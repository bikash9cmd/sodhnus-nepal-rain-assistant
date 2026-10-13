# Alternatives considered

Ten decisions, what I chose, what I didn't, and what would make me switch.

## ADR-001: Which problem

**Chosen:** answering questions about measured rainfall, from data I already made trustworthy in Barsha.

**Considered:** a citizen-services chatbot (passports, citizenship), a farmer advisory bot, a tourist trek assistant.

**Why:** I wanted a GenAI project where being wrong has a real cost and the right answer can be checked. Government-service rules change and I had no authoritative source I could verify answers against; farmer advice is hard to evaluate without agronomists. Rainfall has a verified source (Barsha), a real audience that asks under deadline after every storm, and a failure that is easy to describe: a confident wrong number. That made it possible to measure hallucination instead of hoping about it.

## ADR-002: How the model gets facts: typed tools vs text-to-SQL vs RAG

**Chosen:** five typed, read-only tools via Converse tool use.

| Option | Why not (here) | When I'd switch |
|---|---|---|
| **Text-to-SQL** (model writes Athena/DuckDB SQL over Barsha) | The model would have to know that `prcp_quality='missing'` rows are not zeros, that partial days are lower bounds, that suspect values are excluded, and that season totals need 90% completeness. Every one of those is a silent-wrong-answer trap, and each query costs an Athena scan. SQL from a model is also an injection surface. | For analysts with open-ended questions, behind a read-only role and a review step, with the answer shown as a query, not prose. |
| **RAG / Bedrock Knowledge Bases** over the tables or bulletins | Retrieval finds text chunks; it doesn't compute. "How unusual was 194 mm?" needs the station's whole history, not the five most similar chunks. The default vector store (OpenSearch Serverless) has a minimum of about $175/month before a single question. | For unstructured sources: DHM bulletins, field reports. As a separate tool whose output is labelled as quoted text, never as measurements. S3 Vectors as the store would remove most of the fixed cost. |
| **Typed tools** | | |

The tools also make the checker possible: because every fact arrives as a field in a dict, "is this number in the tool results?" is a well-defined question.

## ADR-003: Which foundation model

**Chosen:** Amazon Nova Lite, through the APAC cross-region inference profile, temperature 0 and top-k 1.

| Option | Trade-off |
|---|---|
| Nova Micro | Cheapest, text only, fast. The job is routing plus two or three sentences, so it may be enough; I picked Lite for headroom on Nepali and mixed-script questions. **Switch** if `make eval-bedrock` shows Micro matches Lite on the holdout set. |
| **Nova Lite** | ~$0.0002 per question here. Supports tool use in Converse. |
| Nova Pro | ~13x the model cost per question ([COST.md](COST.md)). Worth it only if Lite's routing fails on real questions in a way the rules fallback can't cover. |
| Llama or Mistral models on Bedrock | Good options, and Converse makes them a config change (`SODHNUS_MODEL_ID`) plus an eval run. I'd compare them on Nepali specifically, which I haven't been able to measure. |
| Fine-tuning | Nothing to fine-tune for: the facts come from tools and the format from the prompt. Fine-tuning would bake facts into weights that go stale daily. |

The model choice is deliberately the least important decision in the system: the checker and the fallback mean a worse model gives plainer answers, not wrong ones.

## ADR-004: Bedrock Agents vs my own Converse loop

**Chosen:** my own loop (`bedrock.py`, ~80 lines).

**Why:** Bedrock Agents would manage the tool loop and session state, but the part I need control over is between the model's answer and the person: check, rewrite once, fall back to a template. That hook is natural in my own loop and awkward around a managed agent. My loop is also testable offline against a scripted stand-in, and it has hard limits I chose (4 tool rounds, 1 rewrite).

**Switch:** if the assistant needs multi-turn memory, many more tools, or action groups that call other services, Agents (or AgentCore) earn their keep.

## ADR-005: Where the guardrail sits

**Chosen:** `ApplyGuardrail` once on the question; the checker on the output.

**Alternative:** `guardrailConfig` on every Converse call, which evaluates input and output each time.

**Why:** measured in the cost model, attaching it costs ~4.2x as much (about 4 text units per question instead of 1), making the guardrail eight times the model's cost. On the output side the risks are wrong numbers, invented records and forecasts, which a content filter doesn't check and my checker does, for free. The trade-off I accept: no content filter on the model's output. Nova Lite at temperature 0, answering about rainfall from tool results, is a low-risk producer of hate or violence, and the checker rejects anything that names unexpected stations or numbers.

**Switch:** if the assistant starts producing free-form text (summaries of field reports, longer explanations), put the output filter back.

## ADR-006: My own checker vs Bedrock contextual grounding checks

**Chosen:** a deterministic checker.

**Why:** contextual grounding scores whether a response is supported by a source, as a probability with a threshold. My failure of interest is "194.1" written as "191", which a similarity score can easily miss and a set lookup can't. The checker is also free, instant, works in Nepali digits, runs in CI, and tells the model exactly what was wrong ("the number 187 does not come from any tool result") so the rewrite usually fixes it.

**Where grounding would help:** sentences without numbers ("rain was widespread across the east"), which my checker can't judge. If answers get longer, I'd add grounding as a second layer, not a replacement.

## ADR-007: A rules backend at all

**Chosen:** keep a deterministic parser and templates alongside the model.

**Why:** it is the fallback that makes Bedrock failures harmless; it lets the whole system run and be tested without an AWS account; and it gives a baseline the model has to beat. On my question set it gets 59 of 60, which mostly says my set is too easy for it. Real people write follow-ups, misspellings and two questions at once; that long tail is where the model earns its cost. Holdout question h17 ("How complete is the rainfall *record* for Taplejung?") is the kind of thing the rules get wrong and a model shouldn't.

**Cost option I haven't taken:** answer with the rules backend first when it parses the question with confidence, and call the model only otherwise. It would cut model and guardrail spend for simple questions, at the price of plainer answers. Worth measuring once real traffic exists.

## ADR-008: Compute: Lambda vs containers

**Chosen:** one Lambda function (container image, arm64, 1 GB), reserved concurrency 10.

| Option | Why not |
|---|---|
| App Runner / ECS Fargate | Always-on cost for a service that is idle most days. Better if answers streamed for a long time or traffic were steady. |
| Lambda zip | pandas + pyarrow are near the 250 MB unzipped limit. |
| Lambda with response streaming | Answers are two to four sentences; streaming adds complexity for little gain. Would switch for longer answers in a chat UI. |

Cold start is the cost of Lambda here: imports (~0.6 s) and loading the tables (~0.3 s), once per container. Provisioned concurrency of 1 would remove it for roughly $10 a month; not worth it until people complain.

## ADR-009: Region

**Chosen:** ap-south-1 (Mumbai), the nearest region to Nepal, with Nova Lite through the APAC cross-region inference profile.

**Trade-off:** Barsha runs in us-east-1 next to NOAA's bucket, so Sodhnus reads the gold tables across regions. That is three small files reloaded at most once a day (they change daily), so the transfer cost rounds to zero, and the round trip only matters on cold start. The cross-region profile means requests can be served from other APAC regions; there is no residency requirement for public rainfall data. **Switch** to us-east-1 if latency from Nepal turned out to be dominated by the model rather than the network.

## ADR-010: The answer log

**Chosen:** DynamoDB on-demand, one item per answer, TTL 30 days, redacted questions.

**Alternatives:** S3 (Firehose) for analytics; no log at all. A log is how I'll find which answers the checker rejected and why, and which answers people marked unhelpful; DynamoDB makes the feedback update a single conditional write. If logs became an analytics source, I'd stream them to S3 and query with Athena, the same pattern as Barsha.

## Smaller choices

- **Channel:** an HTTP API first. A Viber or WhatsApp bot is how most people in Nepal would actually ask; it would sit in front of the same `/ask` route.
- **Translation:** no Amazon Translate step. The model answers in the question's language and the templates exist in both, so numbers never pass through a translation step that could reformat them.
- **Prompt management:** the system prompt is code (`prompts.py`), reviewed and versioned with the checker it depends on. Bedrock Prompt Management would help if non-engineers edited prompts.
