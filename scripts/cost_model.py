"""Monthly cost model behind docs/COST.md.

Prompt and tool sizes are measured from the code and from real tool results on the evaluation
set; tokens are estimated from characters (I can't count Nova's tokens offline). Prices are the
list prices I used, in one place, so they are easy to update. Check the AWS pricing pages before
quoting these numbers.

    python scripts/cost_model.py
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sodhnus import assistant, tools  # noqa: E402
from sodhnus.data import load  # noqa: E402
from sodhnus.prompts import system_prompt  # noqa: E402

PRICES = {
    # Amazon Nova Lite on Bedrock, on-demand, per 1,000 tokens.
    "nova_lite_in": 0.00006,
    "nova_lite_out": 0.00024,
    # Nova Pro, for comparison.
    "nova_pro_in": 0.0008,
    "nova_pro_out": 0.0032,
    # Bedrock Guardrails, per 1,000 text units (a text unit is up to 1,000 characters).
    "guardrail_content_filter": 0.15,
    "guardrail_denied_topics": 0.15,
    "guardrail_pii": 0.10,
    # Lambda arm64 per GB-second, and per million requests.
    "lambda_gb_s": 0.0000133334,
    "lambda_req": 0.20 / 1e6,
    # HTTP API per million requests; DynamoDB on-demand per million writes.
    "http_api": 1.00 / 1e6,
    "ddb_write": 1.25 / 1e6,
    # CloudWatch: per custom metric per month, per alarm per month, per GB of logs ingested.
    "cw_metric": 0.30,
    "cw_alarm": 0.10,
    "cw_logs_gb": 0.50,
    # OpenSearch Serverless, the default vector store for Bedrock Knowledge Bases: per OCU-hour,
    # with a minimum of 1 OCU (0.5 indexing + 0.5 search) for a dev-mode collection.
    "aoss_ocu_hour": 0.24,
}

CHARS_PER_TOKEN_EN = 4.0  # English and JSON
CHARS_PER_TOKEN_NE = 1.5  # Devanagari splits into many more tokens; a conservative guess


def measured_sizes() -> dict:
    gold = load("data/barsha-gold")
    sys_chars = len(system_prompt(gold.first_day, gold.latest_day))
    spec_chars = len(json.dumps(tools.bedrock_tool_config()))
    results, answers = [], []
    for split in ("dev", "holdout"):
        for line in Path(f"eval/{split}.jsonl").read_text(encoding="utf-8").splitlines():
            a = assistant.ask(json.loads(line)["question"], gold, today=date(2026, 10, 13))
            results += [len(json.dumps(r, ensure_ascii=False)) for r in a.tool_results]
            if a.tool_results:
                answers.append(len(a.text))
    return {
        "system_chars": sys_chars,
        "tool_spec_chars": spec_chars,
        "tool_result_chars": statistics.median(results),
        "answer_chars": statistics.median(answers),
    }


def per_question(
    sizes: dict, share_nepali: float = 0.5, rewrite_rate: float = 0.1, model: str = "nova_lite", guard_once: bool = True
) -> dict:
    cpt = 1 / ((1 - share_nepali) / CHARS_PER_TOKEN_EN + share_nepali / CHARS_PER_TOKEN_NE)
    fixed = (sizes["system_chars"] + sizes["tool_spec_chars"]) / CHARS_PER_TOKEN_EN
    question, tool_call, result = 60 / cpt, 60, sizes["tool_result_chars"] / CHARS_PER_TOKEN_EN
    answer = sizes["answer_chars"] / cpt
    # Call 1: prompt + question -> tool call. Call 2: all of that + tool result -> answer.
    tokens_in = (fixed + question) + (fixed + question + tool_call + result)
    tokens_out = tool_call + answer
    # A rewrite is a third call carrying everything so far plus the checker's note.
    tokens_in += rewrite_rate * (fixed + question + tool_call + result + answer + 60)
    tokens_out += rewrite_rate * answer
    model_cost = tokens_in / 1000 * PRICES[f"{model}_in"] + tokens_out / 1000 * PRICES[f"{model}_out"]
    # Guardrail: ApplyGuardrail once on the question (under 400 characters, so one text unit).
    # Attached to Converse instead, it is billed on each call's input and output: ~4.2 units.
    units = 1 if guard_once else 2 + 2 + rewrite_rate * 2
    per_unit = (PRICES["guardrail_content_filter"] + PRICES["guardrail_denied_topics"] + PRICES["guardrail_pii"]) / 1000
    lam = 1.0 * 2.5 * PRICES["lambda_gb_s"] + PRICES["lambda_req"]  # 1 GB, ~2.5 s mostly waiting on Bedrock
    return {
        "tokens_in": round(tokens_in),
        "tokens_out": round(tokens_out),
        "model": model_cost,
        "guardrail": units * per_unit,
        "lambda": lam,
        "api": PRICES["http_api"],
        "dynamodb": PRICES["ddb_write"],
    }


def monthly(q: dict, questions: int) -> dict:
    fixed = {"cloudwatch_metrics": 6 * PRICES["cw_metric"], "cloudwatch_alarms": 4 * PRICES["cw_alarm"]}
    variable = {k: q[k] * questions for k in ("model", "guardrail", "lambda", "api", "dynamodb")}
    variable["logs"] = questions * 3000 / 1e9 * PRICES["cw_logs_gb"]
    total = sum(fixed.values()) + sum(variable.values())
    return {**{k: round(v, 2) for k, v in {**variable, **fixed}.items()}, "total": round(total, 2)}


def main() -> None:
    sizes = measured_sizes()
    print("Measured sizes (characters):", sizes)
    q = per_question(sizes)
    print(f"Per question: ~{q['tokens_in']} input tokens, ~{q['tokens_out']} output tokens")
    print(f"  model ${q['model']:.5f}  guardrail ${q['guardrail']:.5f}  lambda ${q['lambda']:.5f}")
    print()
    print("| Questions per month | Nova Lite | Guardrail | Lambda | CloudWatch | Other | Total |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for n in (1_000, 10_000, 100_000):
        m = monthly(q, n)
        cw = m["cloudwatch_metrics"] + m["cloudwatch_alarms"] + m["logs"]
        other = m["api"] + m["dynamodb"]
        cells = [m["model"], m["guardrail"], m["lambda"], cw, other]
        print(f"| {n:,} | " + " | ".join(f"${c:.2f}" for c in cells) + f" | **${m['total']:.2f}** |")
    pro = per_question(sizes, model="nova_pro")
    print()
    print(f"Nova Pro instead: model ${pro['model']:.5f} per question ({pro['model'] / q['model']:.0f}x Nova Lite)")
    attached = per_question(sizes, guard_once=False)
    print(
        f"Guardrail attached to every Converse call instead: ${attached['guardrail']:.5f} per question "
        f"({attached['guardrail'] / q['guardrail']:.1f}x), ${attached['guardrail'] * 10_000:.2f} at 10,000 questions"
    )
    aoss = 1 * PRICES["aoss_ocu_hour"] * 730
    print(f"Bedrock Knowledge Base on OpenSearch Serverless (1 OCU minimum): ${aoss:.0f}/month before any question")
    old_metrics = 7 * 4 * PRICES["cw_metric"]
    now = 6 * PRICES["cw_metric"]
    print(f"First metrics design (7 metrics x 4 backend values): ${old_metrics:.2f}/month vs ${now:.2f} now")


if __name__ == "__main__":
    main()
