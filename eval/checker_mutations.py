"""How well does the checker catch wrong answers, and how often does it reject right ones?

Wrong answers are made by mutating correct ones (the rules backend's answers to the evaluation
set) in the ways a language model actually goes wrong: a slightly different number, a transposed
digit, a number taken from the wrong field, an invented record, a forecast, a station nobody
looked up. Right answers are the template answers plus eval/paraphrases.jsonl, which I wrote the
way a model tends to phrase things (rounded, reordered, with percentages).

    python eval/checker_mutations.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_eval import EVAL_TODAY  # noqa: E402

from sodhnus import assistant  # noqa: E402
from sodhnus.checker import check_answer, numbers_in  # noqa: E402
from sodhnus.data import load  # noqa: E402
from sodhnus.dates import ne_digits, to_ascii_digits  # noqa: E402
from sodhnus.places import STATIONS  # noqa: E402


def _headline(text: str) -> str | None:
    """The first rainfall amount in the answer (a number followed by mm / मिमि)."""
    m = re.search(r"([\d०-९][\d०-९,]*(?:\.[\d०-९]+)?) ?(?:mm|मिमि)", text)
    return m.group(1) if m else None


def _fmt(value: float, like: str) -> str:
    text = f"{value:g}" if "." in to_ascii_digits(like) else str(round(value))
    return ne_digits(text) if re.search("[०-९]", like) else text


def _mm_values(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (k.endswith("_mm") or k == "mm") and isinstance(v, int | float) and not isinstance(v, bool):
                yield v
            else:
                yield from _mm_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _mm_values(v)


def mutants(a: assistant.Answer) -> list[tuple[str, str]]:
    text, out = a.text, []
    head = _headline(text)
    if head:
        v = float(to_ascii_digits(head).replace(",", ""))
        for kind, new in [
            ("plus_3", v + 3),
            ("plus_10pct", round(v * 1.1, 1)),
            ("times_10", v * 10),
            ("minus_1", v - 1),
        ]:
            out.append((kind, text.replace(head, _fmt(new, head), 1)))
        digits = to_ascii_digits(head)
        whole = digits.split(".")[0]
        if len(whole) >= 2 and whole[0] != whole[1]:
            swapped = whole[1] + whole[0] + whole[2:] + digits[len(whole) :]
            out.append(("digit_swap", text.replace(head, _fmt(float(swapped), head), 1)))
        # A rainfall amount that is in the tool results, attached to the wrong thing.
        amounts = sorted({float(x) for r in a.tool_results for x in _mm_values(r) if abs(float(x) - v) > 0.5})
        if amounts:
            out.append(("wrong_field", text.replace(head, _fmt(amounts[0], head), 1)))
    ne = a.lang == "ne"
    if not any(r.get("is_station_record") for r in a.tool_results):
        out.append(("invented_record", text + (" यो नयाँ रेकर्ड हो।" if ne else " That is a new record for the station.")))
    out.append(("forecast", text + (" भोलि पनि भारी वर्षा हुनेछ।" if ne else " More heavy rain is expected tomorrow.")))
    looked = {r.get("station_id") for r in a.tool_results}
    looked |= {
        s.station_id
        for r in a.tool_results
        for x in r.get("stations", []) + r.get("nearest", [])
        for s in STATIONS
        if s.en == x.get("station")
    }
    other = next((s for s in STATIONS if s.station_id not in looked and s.en != "Syangboche"), None)
    if other is None:  # every station was looked at; naming any of them is fine
        return out
    out.append(
        ("unlooked_station", text + (f" {other.ne}मा पनि धेरै पानी पर्यो।" if ne else f" {other.en} also had heavy rain."))
    )
    return out


def main() -> None:
    gold = load("data/barsha-gold")
    questions = [
        json.loads(line)
        for split in ("dev", "holdout")
        for line in Path(f"eval/{split}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    caught, total = defaultdict(int), defaultdict(int)
    examples_missed = defaultdict(list)
    template_rejects = templates = 0
    for item in questions:
        a = assistant.ask(item["question"], gold, today=EVAL_TODAY)
        if a.refusal or not a.tool_results:
            continue
        templates += 1
        template_rejects += not check_answer(a.text, a.tool_results, a.question).ok
        for kind, wrong in mutants(a):
            if numbers_in(wrong) == numbers_in(a.text) and kind not in {
                "invented_record",
                "forecast",
                "unlooked_station",
            }:
                continue  # the mutation didn't change anything
            total[kind] += 1
            if not check_answer(wrong, a.tool_results, a.question).ok:
                caught[kind] += 1
            elif len(examples_missed[kind]) < 2:
                examples_missed[kind].append(wrong[:160])

    para_rejects, para_total, rejected = 0, 0, []
    for line in Path("eval/paraphrases.jsonl").read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        a = assistant.ask(p["question"], gold, today=EVAL_TODAY)
        para_total += 1
        result = check_answer(p["answer"], a.tool_results, p["question"])
        if not result.ok:
            para_rejects += 1
            rejected.append({"answer": p["answer"], "why": result.problems})

    report = {
        "wrong_answers": {
            k: {"caught": caught[k], "total": total[k], "rate": round(caught[k] / total[k], 3)} for k in sorted(total)
        },
        "wrong_answers_overall": {
            "caught": sum(caught.values()),
            "total": sum(total.values()),
            "rate": round(sum(caught.values()) / sum(total.values()), 3),
        },
        "missed_examples": dict(examples_missed),
        "right_answers": {
            "template_answers": templates,
            "template_rejected": template_rejects,
            "paraphrases": para_total,
            "paraphrases_rejected": para_rejects,
            "rejected": rejected,
        },
    }
    Path("eval/results").mkdir(exist_ok=True)
    Path("eval/results/checker.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'mutation':18s} caught")
    for k, v in report["wrong_answers"].items():
        print(f"{k:18s} {v['caught']}/{v['total']}")
    o = report["wrong_answers_overall"]
    print(f"{'all wrong answers':18s} {o['caught']}/{o['total']} ({o['rate']:.0%})")
    print(f"right answers rejected: templates {template_rejects}/{templates}, paraphrases {para_rejects}/{para_total}")
    for r in rejected:
        print("  rejected:", r["answer"][:90], "->", r["why"])
    for k, ex in examples_missed.items():
        print(f"  missed {k}: {ex[0][:120]}")


if __name__ == "__main__":
    main()
