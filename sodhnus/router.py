"""The rules backend: turns a question into tool calls without a model.

It handles the phrasings in the evaluation set and the obvious variants, and nothing clever.
It is what runs locally and in tests, and what answers when Bedrock is unavailable. The model
earns its place on everything this can't parse: follow-ups, misspellings, unusual word order,
two questions in one (docs/EVALUATION.md shows how much that is).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from .dates import find_dates, find_years, to_ascii_digits
from .places import find_places

_ROMANISED_NE = [
    r"\bkati\b",
    r"\bpani\b",
    r"\bparyo\b",
    r"\bparyeko\b",
    r"\bbarsa\b",
    r"\bbarsha\b",
    r"\bthiyo\b",
    r"\bkasto\b",
    r"\bkun\b",
    r"\bsabai bhanda\b",
    r"\bdin\b",
    r"\bsaal\b",
    r"\bko\b",
    r"\bma\b",
    r"\bgate\b",
]

_RECORD = [
    r"\bwettest\b",
    r"\brecord",
    r"\bhighest\b",
    r"\bheaviest\b",
    r"\bmost rain",
    r"\bbiggest\b",
    r"सबैभन्दा धेरै",
    r"रेकर्ड",
    r"अधिकतम",
    r"\bsabai bhanda dherai\b",
    r"\bdherai\b",
]
_MONSOON = [
    r"\bmonsoon\b",
    r"\bseason",
    r"\btotal\b",
    r"\bjjas\b",
    r"मनसुन",
    r"वर्षायाम",
    r"जम्मा",
    r"कुल",
    r"\bmanasun\b",
    r"\bmonsun\b",
    r"\bjamma\b",
]
_COVERAGE = [
    r"\bstill report",
    r"\bcoverage\b",
    r"\bsince when\b",
    r"\bhow (?:long|complete)\b",
    r"\bdata (?:for|from|about)\b",
    r"\bworking\b",
    r"\bgaps?\b",
    r"कहिलेदेखि",
    r"डाटा",
    r"रिपोर्ट गर्छ",
    r"\bkahile dekhi\b",
]
_WHERE = [
    r"\bwhere\b",
    r"\bwhich (?:station|place|town|district)s?\b",
    r"\bacross nepal\b",
    r"\ball stations\b",
    r"कहाँ",
    r"कुन (?:ठाउँ|स्टेशन)",
    r"\bkaha\b",
]
_RELATIVE = {
    0: [r"\btoday\b", r"\bthis morning\b", r"आज", r"\baaja?\b"],
    1: [r"\byesterday\b", r"\blast night\b", r"हिजो", r"\bhijo\b"],
}


@dataclass(frozen=True)
class Plan:
    lang: str
    calls: list[tuple[str, dict]]
    unknown_place: bool = False  # a date but no place we know, and not a "where" question


def detect_language(question: str) -> str:
    # Not "any Devanagari means Nepali": "How unusual was the rain in Pokhara on असोज १२?" is an
    # English question with a Nepali date in it. Month and place names don't count; Nepali grammar does.
    rest = question
    for mention in find_dates(question):
        rest = rest.replace(mention.text, " ")
    for place in find_places(question):
        rest = re.sub(re.escape(place.query), " ", rest, flags=re.IGNORECASE)
    if re.search("[\u0900-\u0963\u0972-\u097f]", rest):
        return "ne"
    if re.search("[\u0900-\u097f]", question):
        return "en"
    low = question.lower()
    hits = sum(bool(re.search(p, low)) for p in _ROMANISED_NE)
    return "ne" if hits >= 2 else "en"


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def plan(question: str, today: date | None = None) -> Plan:
    lang = detect_language(question)
    low = to_ascii_digits(question).lower()
    places = find_places(question)[:3]
    dates = [d for d in find_dates(question) if d.day is not None]
    years = find_years(question)
    today = today or date.today()

    if not dates:
        for back, patterns in _RELATIVE.items():
            if _any(patterns, low):
                d = today - timedelta(days=back)
                dates_iso = d.isoformat()
                if places:
                    return Plan(
                        lang, [("rain_on_day", {"place": p.query, "date": dates_iso, "calendar": "AD"}) for p in places]
                    )
                return Plan(lang, [("rain_across_stations", {"date": dates_iso, "calendar": "AD"})])

    if dates:
        d = dates[0]
        arg = f"{d.year}-{d.month:02d}-{d.day:02d}" if d.year else f"{d.month:02d}-{d.day:02d}"
        if places and not _any(_WHERE, low):
            return Plan(
                lang, [("rain_on_day", {"place": p.query, "date": arg, "calendar": d.calendar}) for p in places]
            )
        unknown = not places and not _any(_WHERE, low) and bool(re.search(r"\b(?:in|at|near)\s+[a-z]{3,}|मा\b", low))
        return Plan(lang, [("rain_across_stations", {"date": arg, "calendar": d.calendar})], unknown_place=unknown)

    if not places:
        return Plan(lang, [])

    year_args = {}
    if years:
        cal, y = years[0]
        year_args = {"year": y, "calendar": cal}
    if _any(_MONSOON, low) and year_args:
        return Plan(lang, [("monsoon_total", {"place": p.query, **year_args}) for p in places])
    if _any(_RECORD, low):
        return Plan(lang, [("wettest_days", {"place": p.query, "n": 5, **year_args}) for p in places])
    if _any(_COVERAGE, low):
        return Plan(lang, [("station_coverage", {"place": p.query}) for p in places])
    if year_args:
        return Plan(lang, [("monsoon_total", {"place": p.query, **year_args}) for p in places])
    return Plan(lang, [])
