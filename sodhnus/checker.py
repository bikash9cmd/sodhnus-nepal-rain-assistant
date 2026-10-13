"""Every answer is checked against the tool results before it goes out.

The rule is simple enough to explain to a reporter: every number in the answer must be a number a
tool returned in this conversation (or one the person typed). On top of that, three claim checks:
"record" language needs a tool that found a record, future-tense language is not allowed at all,
and every station named must be one the tools actually looked at.

Membership alone can't see a real number attached to the wrong thing (saying the old record,
191 mm, fell on the day that had 194 mm): both numbers are in the tool results. So each result
also has one required figure, the one that answers the question, and the answer must contain it.
That catches a swapped headline; a swapped secondary number still gets through
(docs/EVALUATION.md has the measurements).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

from .dates import ad_to_bs, to_ascii_digits
from .places import STATIONS

_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\d])")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# "Record" also means "the data" ("the rainfall record for Taplejung"; in Nepali, पूरा रेकर्ड भएका दिन
# is "days with a complete reading"), so only phrases that claim an extreme count.
_RECORD_WORDS = [
    r"\brecord[- ]breaking\b",
    r"\b(?:new|all-time) record\b",
    r"\b(?:a|station) record\b(?! (?:of|shows))",
    r"\brecord (?:high|rain|rainfall|day)\b",
    r"\bwettest day (?:on|in) (?:its )?record\b",
    r"\bhighest ever\b",
    r"\bbroke (?:the|its|a) record\b",
    r"\bnever (?:before|been)\b",
    r"रेकर्डमै",
    r"रेकर्ड तोड",
    r"रेकर्ड हो",
    r"नयाँ रेकर्ड",
    r"कीर्तिमान",
    r"इतिहासमै",
    r"अहिलेसम्मकै",
]
_FUTURE_WORDS = [
    r"\bwill (?:rain|be|flood|continue)\b",
    r"\bexpect(?:ed)? (?:rain|more)\b",
    r"\btomorrow\b",
    r"\bforecast(?:s|ed)? (?:is|are|shows?)\b",
    r"भोलि",
    r"पर्नेछ",
    r"हुनेछ",
    r"पूर्वानुमान अनुसार",
]


@dataclass
class CheckResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    numbers_checked: int = 0

    def feedback(self) -> str:
        return "; ".join(self.problems)


def _walk(obj, out: list) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _walk(v, out)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, int | float):
        out.append(float(obj))
    elif isinstance(obj, str):
        text = to_ascii_digits(obj)
        for m in _DATE.finditer(text):
            y, mo, d = (int(x) for x in m.group(0).split("-"))
            out += [y, mo, d]
            try:
                # Any AD date may be restated in BS, and the other way round is already there.
                if y < 2030:
                    out += list(ad_to_bs(date(y, mo, d)))
            except ValueError:
                pass
        for m in _NUMBER.finditer(text):
            out.append(float(m.group(1).replace(",", "") + (f".{m.group(2)}" if m.group(2) else "")))


def allowed_numbers(tool_results: list[dict], question: str) -> set[float]:
    raw: list[float] = []
    _walk(tool_results, raw)
    _walk(question, raw)
    allowed = {0.0, 1.0}  # "1 in 100", "0 mm"
    for v in raw:
        allowed |= {v, round(v), round(v, 1), math.floor(v), math.ceil(v)}
        # Percentages written from fractions, and the other way round.
        if 0 < v < 1:
            allowed |= {round(100 * v), round(100 * v, 1)}
    return allowed


def numbers_in(text: str) -> list[float]:
    t = to_ascii_digits(text)
    out = []
    for m in _NUMBER.finditer(t):
        whole = m.group(1).replace(",", "")
        out.append(float(whole + (f".{m.group(2)}" if m.group(2) else "")))
    return out


def stations_named(text: str) -> set[str]:
    low = text.lower()
    found = set()
    for s in STATIONS:
        names = {s.en.lower(), s.ne, *(a for a in s.aliases if len(a) > 3)}
        if any(n in low for n in names):
            found.add(s.station_id)
    return found


def required_figure(result: dict) -> float | None:
    """The number that answers the question this result was fetched for."""
    tool = result.get("tool")
    if tool == "rain_on_day" and not result.get("suspect"):
        return result.get("rain_mm", result.get("at_least_mm"))
    if tool == "monsoon_total":
        return result.get("total_mm", result.get("complete_days"))
    if tool == "wettest_days" and result.get("days"):
        return result["days"][0]["rain_mm"]
    if tool == "rain_across_stations":
        return next((s["rain_mm"] for s in result.get("stations", []) if "rain_mm" in s), None)
    return None


def _close(n: float, targets: set[float]) -> bool:
    return n in targets or any(abs(n - t) < 0.051 for t in targets)


def check_answer(answer: str, tool_results: list[dict], question: str) -> CheckResult:
    problems = []
    allowed = allowed_numbers(tool_results, question)
    nums = numbers_in(answer)
    for n in nums:
        if not _close(n, allowed):
            problems.append(f"the number {n:g} does not come from any tool result")
    for r in tool_results:
        fig = required_figure(r)
        if fig is not None and not any(_close(n, {fig, round(fig), math.floor(fig), math.ceil(fig)}) for n in nums):
            where = r.get("station") or r.get("date") or r.get("tool")
            problems.append(f"it leaves out the main figure for {where} ({fig:g})")

    low = answer.lower()
    if any(re.search(p, low) for p in _RECORD_WORDS):
        record_found = any(
            r.get("is_station_record") or any(d.get("rank") == 1 for d in r.get("days", [])) for r in tool_results
        )
        negated = re.search(r"\bnot (?:a|the) (?:station )?record\b|रेकर्ड होइन|रेकर्ड भने होइन|\bbelow the record\b", low)
        if not record_found and not negated:
            problems.append("it claims a record, but no tool found one")

    if any(re.search(p, low) for p in _FUTURE_WORDS):
        problems.append("it talks about the future; Sodhnus only reports what was measured")

    looked_at = {r.get("station_id") for r in tool_results}
    for r in tool_results:
        for s in r.get("stations", []) + r.get("nearest", []):
            looked_at |= {st.station_id for st in STATIONS if st.en == s.get("station")}
    unknown = stations_named(answer) - looked_at
    if unknown:
        names = ", ".join(sorted(s.en for s in STATIONS if s.station_id in unknown))
        problems.append(f"it names stations no tool looked at: {names}")

    return CheckResult(ok=not problems, problems=problems, numbers_checked=len(nums))
