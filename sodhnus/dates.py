"""Dates in questions: Gregorian (AD) and Bikram Sambat (BS), in English, Nepali and romanised Nepali.

People in Nepal mostly talk about the monsoon in BS ("असोज १२"), the data is in AD, and the
spellings people use are not the ones calendar libraries use: the library calls the sixth month
आश्विन, almost everyone writes असोज. Every spelling below was added because a test question used it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import nepali_datetime as nd

NE_DIGITS = "०१२३४५६७८९"
_TO_ASCII = str.maketrans(NE_DIGITS, "0123456789")
_TO_NE = str.maketrans("0123456789", NE_DIGITS)

BS_MONTHS_NE = {
    1: ("बैशाख", ["बैशाख", "वैशाख", "वैसाख", "बैसाख"]),
    2: ("जेठ", ["जेठ", "जेष्ठ", "जेष्ठ"]),
    3: ("असार", ["असार", "आषाढ", "असाढ"]),
    4: ("साउन", ["साउन", "श्रावण", "सावन"]),
    5: ("भदौ", ["भदौ", "भाद्र", "भाद्रपद"]),
    6: ("असोज", ["असोज", "आश्विन", "अश्विन", "आसोज"]),
    7: ("कात्तिक", ["कात्तिक", "कार्तिक"]),
    8: ("मंसिर", ["मंसिर", "मङ्सिर", "मङसिर"]),
    9: ("पुस", ["पुस", "पौष", "पूस"]),
    10: ("माघ", ["माघ"]),
    11: ("फागुन", ["फागुन", "फाल्गुन", "फाल्गुण"]),
    12: ("चैत", ["चैत", "चैत्र"]),
}
BS_MONTHS_EN = {
    1: ("Baisakh", ["baisakh", "baishakh", "vaisakh", "baisak"]),
    2: ("Jestha", ["jestha", "jeth", "jeshtha"]),
    3: ("Asar", ["asar", "ashar", "asadh", "ashadh", "ashad"]),
    4: ("Saun", ["saun", "sawan", "shrawan", "srawan", "shravan", "sawun"]),
    5: ("Bhadau", ["bhadau", "bhadra", "bhado", "bhadrapad"]),
    6: ("Asoj", ["asoj", "aswin", "ashwin", "ashoj", "ashwin"]),
    7: ("Kartik", ["kartik", "kattik", "kartika"]),
    8: ("Mangsir", ["mangsir", "mansir", "marga"]),
    9: ("Poush", ["poush", "push", "paush", "pus"]),
    10: ("Magh", ["magh"]),
    11: ("Falgun", ["falgun", "fagun", "phagun", "phalgun"]),
    12: ("Chaitra", ["chaitra", "chait", "chaite"]),
}
AD_MONTHS = {
    m: names
    for m, names in enumerate(
        [
            None,
            ["january", "jan"],
            ["february", "feb"],
            ["march", "mar"],
            ["april", "apr"],
            ["may"],
            ["june", "jun"],
            ["july", "jul"],
            ["august", "aug"],
            ["september", "sept", "sep"],
            ["october", "oct"],
            ["november", "nov"],
            ["december", "dec"],
        ]
    )
    if names
}
AD_MONTHS_NE = {
    1: ["जनवरी"],
    2: ["फेब्रुअरी"],
    3: ["मार्च"],
    4: ["अप्रिल"],
    5: ["मे"],
    6: ["जुन"],
    7: ["जुलाई"],
    8: ["अगस्ट", "अगष्ट"],
    9: ["सेप्टेम्बर", "सेप्टेम्बर"],
    10: ["अक्टोबर"],
    11: ["नोभेम्बर"],
    12: ["डिसेम्बर"],
}


def to_ascii_digits(text: str) -> str:
    return text.translate(_TO_ASCII)


def ne_digits(value) -> str:
    return str(value).translate(_TO_NE)


def ad_to_bs(d: date) -> tuple[int, int, int]:
    b = nd.date.from_datetime_date(d)
    return b.year, b.month, b.day


def bs_to_ad(year: int, month: int, day: int) -> date:
    return nd.date(year, month, day).to_datetime_date()


def bs_label(d: date, lang: str) -> str:
    y, m, dd = ad_to_bs(d)
    if lang == "ne":
        return f"{ne_digits(y)} {BS_MONTHS_NE[m][0]} {ne_digits(dd)}"
    return f"{dd} {BS_MONTHS_EN[m][0]} {y} BS"


def ad_label(d: date, lang: str) -> str:
    if lang == "ne":
        return ne_digits(d.isoformat())
    return f"{d.day} {d.strftime('%B')} {d.year}"


@dataclass(frozen=True)
class DateMention:
    """A date found in a question. year is None when the question did not give one."""

    calendar: str  # "AD" or "BS"
    year: int | None
    month: int
    day: int | None
    text: str


def _month_patterns() -> list[tuple[str, int, str]]:
    out = []
    for m, (_, spellings) in BS_MONTHS_NE.items():
        out += [(s, m, "BS") for s in spellings]
    for m, (_, spellings) in BS_MONTHS_EN.items():
        out += [(s, m, "BS") for s in spellings]
    for m, spellings in AD_MONTHS.items():
        out += [(s, m, "AD") for s in spellings]
    for m, spellings in AD_MONTHS_NE.items():
        out += [(s, m, "AD") for s in spellings]
    # Longest first, so "sept" wins over "sep" and "जेष्ठ" over shorter overlaps.
    return sorted(set(out), key=lambda t: -len(t[0]))


_MONTHS = _month_patterns()
_ISO = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
# Word boundaries do not work for Devanagari in Python's re, so month names are matched with
# explicit "not a letter" guards on both sides.
_LETTER = r"[A-Za-z\u0900-\u0963\u0970-\u097f]"


def find_dates(question: str) -> list[DateMention]:
    """All dates mentioned in a question, in order of appearance."""
    text = to_ascii_digits(question)
    lower = text.lower()
    found: list[tuple[int, DateMention]] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in taken)

    for m in _ISO.finditer(text):
        y, mo, d = (int(g) for g in m.groups())
        if 1 <= mo <= 12 and 1 <= d <= 32:
            cal = "BS" if y >= 2030 and y > date.today().year + 1 else "AD"
            found.append((m.start(), DateMention(cal, y, mo, d, m.group(0))))
            taken.append(m.span())

    for name, month, cal in _MONTHS:
        pattern = re.compile(rf"(?<!{_LETTER}){re.escape(name)}(?!{_LETTER})")
        for m in pattern.finditer(lower):
            if not free(*m.span()):
                continue
            # Day and year can sit on either side: "Asoj 12", "12 Asoj", "2081 Asoj 12", "Sept 28, 2024".
            before = lower[max(0, m.start() - 12) : m.start()]
            after = lower[m.end() : m.end() + 14]
            day = year = None
            a = re.match(r"\s*(\d{1,2})(?:st|nd|rd|th|\s*gate|\s*गते)?\b(?:\s*,?\s*(\d{4}))?", after)
            b = re.search(r"(?:(\d{4})\s+)?(\d{1,2})(?:st|nd|rd|th|\s*gate|\s*गते)?\s*(?:of\s+)?$", before)
            if a and int(a.group(1)) <= 32:
                day = int(a.group(1))
                year = int(a.group(2)) if a.group(2) else None
                if year is None and (yb := re.search(r"(\d{4})\s*(?:साल(?:को)?\s*)?$", before)):
                    year = int(yb.group(1))
            elif b and int(b.group(2)) <= 32:
                day = int(b.group(2))
                year = int(b.group(1)) if b.group(1) else None
                if year is None and (ya := re.match(r"\s*,?\s*(\d{4})\b", after)):
                    year = int(ya.group(1))
            else:
                yb = re.search(r"(\d{4})\s*(?:साल(?:को)?\s*)?$", before)
                ya = re.match(r"\s*,?\s*(\d{4})\b", after)
                year = int(yb.group(1)) if yb else int(ya.group(1)) if ya else None
            if day is None and year is None and not re.search(r"[\u0900-\u097F]", name):
                # "may", "push", "mar" alone are ordinary words; a romanised month needs a day or year.
                continue
            if year is not None and cal == "AD" and year > date.today().year + 1:
                cal = "BS"  # "Sawan 2081" written with an English month list still means BS
            found.append((m.start(), DateMention(cal, year, month, day, m.group(0))))
            taken.append(m.span())
    return [d for _, d in sorted(found, key=lambda t: t[0])]


def find_years(question: str) -> list[tuple[str, int]]:
    """Bare four-digit years, labelled AD or BS by range."""
    text = to_ascii_digits(question)
    out = []
    for m in re.finditer(r"(?<!\d)(\d{4})(?!\d)", text):
        y = int(m.group(1))
        if 1970 <= y <= date.today().year + 1:
            out.append(("AD", y))
        elif 2030 <= y <= 2090:
            out.append(("BS", y))
    return out


def resolve(mention: DateMention, latest: date) -> tuple[date, bool]:
    """Turn a mention into an AD date. With no year, use the most recent such day on or before
    `latest` and say so (the bool), rather than guessing silently."""
    if mention.day is None:
        raise ValueError("a month without a day is not a single date")
    if mention.year is not None:
        if mention.calendar == "BS":
            return bs_to_ad(mention.year, mention.month, mention.day), False
        return date(mention.year, mention.month, mention.day), False
    if mention.calendar == "BS":
        by, _, _ = ad_to_bs(latest)
        for y in (by, by - 1):
            try:
                d = bs_to_ad(y, mention.month, mention.day)
            except ValueError:
                continue
            if d <= latest:
                return d, True
        raise ValueError("no such BS day")
    for y in (latest.year, latest.year - 1):
        d = date(y, mention.month, mention.day)
        if d <= latest:
            return d, True
    raise ValueError("no such day")
