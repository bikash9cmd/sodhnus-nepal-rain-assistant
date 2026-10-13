"""Run the evaluation set through the assistant and score it.

    python eval/run_eval.py                      # rules backend, dev + holdout
    python eval/run_eval.py --backend bedrock    # same questions against Amazon Nova on Bedrock

Writes eval/results/<backend>.json and prints the table that docs/EVALUATION.md reports.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reference import Reference  # noqa: E402

from sodhnus import assistant, bedrock  # noqa: E402
from sodhnus.config import Settings  # noqa: E402
from sodhnus.data import load  # noqa: E402
from sodhnus.dates import ne_digits  # noqa: E402

# Fixed so "yesterday" and "today" questions give the same result on any day the eval runs.
EVAL_TODAY = date(2026, 10, 13)


def variants(value) -> list[str]:
    if isinstance(value, str):  # a date
        d = date.fromisoformat(value)
        return [value, ne_digits(value), f"{d.day} {d.strftime('%B')} {d.year}"]
    v = float(value)
    texts = {f"{v:g}", f"{v:.1f}"}
    if v == int(v):
        texts.add(str(int(v)))
    return sorted(texts | {ne_digits(t) for t in texts})


def score(item: dict, a: assistant.Answer, ref: Reference) -> dict:
    e = item["expect"]
    checks = {"lang": a.lang == e["lang"]}
    if "refusal" in e:
        checks["refusal"] = a.refusal == e["refusal"]
    else:
        first = a.tool_results[0] if a.tool_results else {}
        name = a.tool_calls[0][0] if a.tool_calls else None
        checks["tool"] = name == e["tool"]
        if "station" in e:
            checks["station"] = first.get("station_id") == e["station"]
        if "date" in e:
            checks["date"] = first.get("date") == e["date"]
        if "year" in e:
            checks["year"] = first.get("year", (first.get("period") or {}).get("year")) == e["year"]
        if "status" in e:
            got = "suspect" if first.get("suspect") else first.get("status")
            checks["status"] = got == e["status"]
        if e.get("proxy"):
            checks["proxy_disclosed"] = "distance_km" in first and str(first["distance_km"]) in a.text.translate(
                str.maketrans("०१२३४५६७८९", "0123456789")
            )
        head = ref.headline(e)
        if head is not None:
            checks["headline"] = any(v in a.text for v in variants(head))
        checks["checker_passed"] = a.checked and a.refusal is None
    return {
        "id": item["id"],
        "question": item["question"],
        "ok": all(checks.values()),
        "failed": [k for k, v in checks.items() if not v],
        "answer": a.text,
        "backend": a.backend,
        "fallback": a.fallback,
        "rewrites": a.rewrites,
        "latency_ms": a.latency_ms,
        "input_tokens": a.input_tokens,
        "output_tokens": a.output_tokens,
    }


def run(split: str, backend: str, gold, ref: Reference, client=None, settings=None) -> list[dict]:
    rows = []
    for line in Path(f"eval/{split}.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        kwargs = {}
        if backend == "bedrock":
            kwargs = {
                "bedrock_client": client,
                "model_id": settings.model_id,
                "guardrail_id": settings.guardrail_id,
                "guardrail_version": settings.guardrail_version,
            }
        a = assistant.ask(item["question"], gold, backend=backend, today=EVAL_TODAY, **kwargs)
        rows.append(score(item, a, ref))
    return rows


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    refusals = [r for r in rows if r["backend"] == "refusal"]
    return {
        "questions": n,
        "correct": sum(r["ok"] for r in rows),
        "accuracy": round(sum(r["ok"] for r in rows) / n, 3) if n else None,
        "refused": len(refusals),
        "fallbacks": sum(r["fallback"] is not None for r in rows),
        "p50_latency_ms": sorted(r["latency_ms"] for r in rows)[n // 2] if n else None,
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="rules", choices=["rules", "bedrock"])
    parser.add_argument("--gold", default="data/barsha-gold")
    parser.add_argument("--splits", nargs="*", default=["dev", "holdout"])
    args = parser.parse_args()

    settings = Settings.from_env()
    gold, ref = load(args.gold), Reference(args.gold)
    client = bedrock.client(settings.region) if args.backend == "bedrock" else None
    out = {
        "backend": args.backend,
        "model": settings.model_id if args.backend == "bedrock" else None,
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "splits": {},
    }
    for split in args.splits:
        rows = run(split, args.backend, gold, ref, client, settings)
        out["splits"][split] = {"summary": summary(rows), "rows": rows}
        s = out["splits"][split]["summary"]
        print(f"{split:8s} {s['correct']}/{s['questions']} correct ({s['accuracy']:.0%})")
        for r in rows:
            if not r["ok"]:
                print(f"   {r['id']} failed {r['failed']}: {r['question']}")
    Path("eval/results").mkdir(exist_ok=True)
    Path(f"eval/results/{args.backend}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
