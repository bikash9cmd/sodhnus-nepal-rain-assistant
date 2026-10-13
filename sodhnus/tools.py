"""The only way Sodhnus reads rainfall: five typed, read-only tools over Barsha's gold tables.

The model never writes SQL and never sees a table. It asks for a place and a date, and gets back
a small dict of facts. Every number an answer is allowed to contain comes from one of these dicts
(see checker.py), so the tools also decide what can be said: a missing day returns no amount, a
partial day returns "at least", a suspect value is labelled, a far-away place returns no number.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date

import pandas as pd

from . import config
from .data import Gold
from .dates import DateMention, ad_to_bs, bs_label, bs_to_ad, resolve
from .places import MAX_PROXY_KM, RETIRED, STATIONS, Place, nearest_stations, resolve_place

MONSOON_DAYS = 122  # June to September, as Barsha defines the season

QUALITY_NOTE = {
    "complete": "a full 24 hours of reports",
    "partial": "fewer than 24 hours were reported, so the true total is at least this much",
    "missing": "the station sent a report but no usable rainfall amount",
}


class ToolError(ValueError):
    """A problem with the arguments that the model (or the person) can fix by asking differently."""


# --- argument handling ------------------------------------------------------------------------


def _place(name: str) -> Place:
    place = resolve_place(name or "")
    if place is None:
        raise ToolError(f"unknown place {name!r}; known stations: " + ", ".join(s.en for s in STATIONS))
    return place


def _place_facts(place: Place) -> dict:
    s = place.station
    out = {"station": s.en, "station_ne": s.ne, "station_id": s.station_id}
    if place.is_proxy:
        out.update(
            {
                "asked_about": place.place_en,
                "asked_about_ne": place.place_ne,
                "distance_km": place.distance_km,
                "note": f"{place.place_en} has no station in this network; this is the nearest one.",
            }
        )
    return out


def _too_far(place: Place, tool: str) -> dict:
    return {
        "tool": tool,
        "status": "no_station_nearby",
        "asked_about": place.place_en,
        "asked_about_ne": place.place_ne,
        "max_proxy_km": MAX_PROXY_KM,
        "nearest": [
            {"station": s.en, "station_ne": s.ne, "distance_km": round(km)}
            for s, km in nearest_stations(place.lat, place.lon, 2)
        ],
        "note": (
            "No station is close enough to stand in for this place; rainfall changes a lot "
            "across Nepal's hills. No amount is given."
        ),
    }


def parse_date_arg(value: str, calendar: str, latest: date) -> tuple[date, bool]:
    """'2024-09-28' (AD), '2081-06-12' (BS), or '06-12' with no year (most recent such day)."""
    text = (value or "").strip()
    cal = (calendar or "AD").upper()
    if cal not in {"AD", "BS"}:
        raise ToolError("calendar must be AD or BS")
    m = re.fullmatch(r"(?:(\d{4})-)?(\d{1,2})-(\d{1,2})", text)
    if not m:
        raise ToolError(f"date must look like YYYY-MM-DD or MM-DD, got {value!r}")
    year = int(m.group(1)) if m.group(1) else None
    try:
        return resolve(DateMention(cal, year, int(m.group(2)), int(m.group(3)), text), latest)
    except ValueError as e:
        raise ToolError(f"{value} is not a valid {cal} date") from e


def _date_facts(d: date, assumed_year: bool) -> dict:
    by, bm, bd = ad_to_bs(d)
    out = {
        "date": d.isoformat(),
        "date_bs": f"{by}-{bm:02d}-{bd:02d}",
        "date_bs_label": bs_label(d, "en"),
        "date_bs_label_ne": bs_label(d, "ne"),
    }
    if assumed_year:
        out["year_assumed"] = True
        out["year_note"] = "No year was given; this is the most recent such day in the data."
    return out


def _r(x) -> float | None:
    return None if x is None or pd.isna(x) else round(float(x), 1)


# --- tools ------------------------------------------------------------------------------------


def rain_on_day(gold: Gold, place: str, date: str, calendar: str = "AD") -> dict:
    p = _place(place)
    if p.too_far:
        return _too_far(p, "rain_on_day")
    day, assumed = parse_date_arg(date, calendar, gold.latest_day)
    sid = p.station.station_id
    out = {
        "tool": "rain_on_day",
        **_place_facts(p),
        **_date_facts(day, assumed),
        "data_through": gold.latest_day.isoformat(),
    }
    station = gold.rain_daily[gold.rain_daily["station_id"] == sid]
    if day > gold.latest_day:
        out.update(status="after_data_end", note="The data does not reach this day yet.")
        return out
    if station.empty or day < station["obs_date"].min():
        out.update(
            status="before_station_records",
            station_records_from=station["obs_date"].min().isoformat() if len(station) else None,
        )
        return out
    row = station[station["obs_date"] == day]
    if row.empty:
        out.update(status="no_report", note="The station sent no report for this day.")
        return out
    r = row.iloc[0]
    quality = r["prcp_quality"]
    out["status"] = quality
    out["quality_note"] = QUALITY_NOTE[quality]
    if quality == "missing":
        out["rain_observed"] = bool(r["rain_observed"])
        if r["rain_observed"]:
            out["note"] = "Weather codes say it rained, but no amount was recorded. Do not treat this as dry."
        return out
    if quality == "partial":
        # Barsha keeps prcp_mm empty for partial days and the raw figure in prcp_reported_mm.
        reported = _r(r["prcp_reported_mm"])
        if reported:
            out["at_least_mm"] = reported
        else:
            out["note"] = "Only part of the day was reported and it shows no rain, which says nothing about the rest."
        return out
    mm = _r(r["prcp_mm"])
    out.update(
        rain_mm=mm, category=r["rain_category"], alert_level=r["alert_level"] if pd.notna(r["alert_level"]) else None
    )
    if bool(r["is_suspect"]):
        out.update(
            suspect=True,
            note="Far above anything this station has recorded, and no station within "
            "200 km saw heavy rain. Barsha holds this value back as a possible gauge error.",
        )
        return out
    # How unusual: compared with the station's own history before this day.
    complete = station[(station["prcp_quality"] == "complete") & ~station["is_suspect"]]
    before = complete[complete["obs_date"] < day]
    out["three_day"] = {"window_days": 3, "rain_mm": _r(r["rain_3day_mm"])} if pd.notna(r["rain_3day_mm"]) else None
    if len(before):
        wetter = before[before["prcp_mm"] >= r["prcp_mm"]]
        out["history_before"] = {
            "from": before["obs_date"].min().isoformat(),
            "complete_days": int(len(before)),
            "highest_mm": _r(before["prcp_mm"].max()),
            "highest_on": before.loc[before["prcp_mm"].idxmax(), "obs_date"].isoformat(),
            "days_as_wet_or_wetter": int(len(wetter)),
            "last_as_wet_or_wetter": wetter["obs_date"].max().isoformat() if len(wetter) else None,
        }
        out["is_station_record"] = bool(len(wetter) == 0 and len(before) >= 300)
    if pd.notna(r["p99_wet_mm"]) and r["p99_wet_mm"] > 0:
        out["rare_threshold"] = {
            "mm": _r(r["p99_wet_mm"]),
            "reached_on_one_in_rainy_days": 100,
            # Derived numbers a writer wants ("2.8 times", "47%") come from here, so
            # the checker never has to accept arithmetic it can't verify.
            "times_this_day": round(float(r["prcp_mm"]) / float(r["p99_wet_mm"]), 1),
            "this_day_percent": round(100 * float(r["prcp_mm"]) / float(r["p99_wet_mm"])),
        }
    return out


def wettest_days(gold: Gold, place: str, n: int = 5, year: int | None = None, calendar: str = "AD") -> dict:
    p = _place(place)
    if p.too_far:
        return _too_far(p, "wettest_days")
    n = max(1, min(int(n or 5), 10))
    rd = gold.rain_daily
    days = rd[(rd["station_id"] == p.station.station_id) & (rd["prcp_quality"] == "complete")]
    held_back = int(days["is_suspect"].sum())
    days = days[~days["is_suspect"]]
    out = {"tool": "wettest_days", **_place_facts(p), "data_through": gold.latest_day.isoformat()}
    if year:
        y = int(year) - 57 if (calendar or "AD").upper() == "BS" else int(year)
        if (calendar or "AD").upper() == "BS":
            start, end = bs_to_ad(int(year), 1, 1), bs_to_ad(int(year) + 1, 1, 1)
            days = days[(days["obs_date"] >= start) & (days["obs_date"] < end)]
            out["period"] = {"bs_year": int(year), "from": start.isoformat(), "to": end.isoformat()}
        else:
            days = days[pd.to_datetime(days["obs_date"]).dt.year == y]
            out["period"] = {"year": y}
    top = days.sort_values(["prcp_mm", "obs_date"], ascending=[False, True]).head(n)
    out["complete_days_considered"] = int(len(days))
    out["days"] = [
        {
            "rank": i + 1,
            "date": r.obs_date.isoformat(),
            "date_bs_label": bs_label(r.obs_date, "en"),
            "date_bs_label_ne": bs_label(r.obs_date, "ne"),
            "rain_mm": _r(r.prcp_mm),
            "alert_level": r.alert_level if pd.notna(r.alert_level) else None,
        }
        for i, r in enumerate(top.itertuples())
    ]
    if held_back:
        out["held_back_as_suspect"] = held_back
    return out


def monsoon_total(gold: Gold, place: str, year: int, calendar: str = "AD") -> dict:
    p = _place(place)
    if p.too_far:
        return _too_far(p, "monsoon_total")
    # A BS year contains the whole June-September monsoon of AD year (BS - 57).
    ad_year = int(year) - 57 if (calendar or "AD").upper() == "BS" else int(year)
    ms = gold.monsoon_season
    station = ms[ms["station_id"] == p.station.station_id]
    out = {
        "tool": "monsoon_total",
        **_place_facts(p),
        "year": ad_year,
        "season": "June to September",
        "data_through": gold.latest_day.isoformat(),
    }
    if (calendar or "AD").upper() == "BS":
        out["bs_year"] = int(year)
    row = station[station["year"] == ad_year]
    if row.empty:
        out["status"] = "no_data"
        return out
    r = row.iloc[0]
    if date(ad_year, 9, 30) > gold.latest_day:
        out["season_incomplete"] = True
        out["note"] = f"The data ends on {gold.latest_day.isoformat()}, before this monsoon finished."
    out["complete_days"] = int(r["complete_days"])
    out["season_days"] = MONSOON_DAYS
    out["completeness_percent"] = round(100 * float(r["completeness"]))
    out["max_1day_mm"] = _r(r["max_1day_mm"])
    out["heavy_rain_days"] = int(r["heavy_days"])
    if r["total_status"] == "published":
        out["status"] = "published"
        out["total_mm"] = _r(r["jjas_total_mm"])
        published = station[station["total_status"] == "published"]
        others = published[published["year"] != ad_year]
        if len(others) >= 2:
            median = others["jjas_total_mm"].median()
            if r["jjas_total_mm"] < 0.5 * median:
                # Seen in the real data: Dhankuta 2014 is "complete" but 62 of its monsoon days read 0.00.
                out["unusually_low"] = True
                out["low_note"] = (
                    "Less than half the median of other seasons. Real droughts are rarely this "
                    "extreme; this may be unreported days recorded as zero upstream."
                )
            out["percent_of_median"] = round(100 * float(r["jjas_total_mm"]) / float(median))
            out["percent_above_or_below_median"] = abs(out["percent_of_median"] - 100)
            out["other_published_seasons"] = {
                "count": int(len(others)),
                "years": [int(y) for y in sorted(others["year"])],
                "median_mm": _r(others["jjas_total_mm"].median()),
                "lowest_mm": _r(others["jjas_total_mm"].min()),
                "highest_mm": _r(others["jjas_total_mm"].max()),
            }
    else:
        out["status"] = "withheld"
        out["note"] = (
            f"Only {int(r['complete_days'])} of {MONSOON_DAYS} days have a complete reading; "
            "Barsha publishes a season total only above 90%, because missing days are usually rainy ones."
        )
    return out


def rain_across_stations(gold: Gold, date: str, calendar: str = "AD") -> dict:
    day, assumed = parse_date_arg(date, calendar, gold.latest_day)
    out = {"tool": "rain_across_stations", **_date_facts(day, assumed), "data_through": gold.latest_day.isoformat()}
    if day > gold.latest_day:
        out["status"] = "after_data_end"
        return out
    rows = gold.rain_daily[gold.rain_daily["obs_date"] == day]
    reports, gaps = [], []
    for s in STATIONS:
        r = rows[rows["station_id"] == s.station_id]
        if r.empty:
            if s.station_id not in RETIRED:
                gaps.append({"station": s.en, "station_ne": s.ne, "status": "no_report"})
            continue
        r = r.iloc[0]
        item = {"station": s.en, "station_ne": s.ne, "status": r["prcp_quality"]}
        if r["prcp_quality"] == "complete" and not r["is_suspect"]:
            item["rain_mm"] = _r(r["prcp_mm"])
            item["alert_level"] = r["alert_level"] if pd.notna(r["alert_level"]) else None
        elif r["prcp_quality"] == "partial" and _r(r["prcp_reported_mm"]):
            item["at_least_mm"] = _r(r["prcp_reported_mm"])
        elif r["is_suspect"]:
            item["status"] = "suspect"
        reports.append(item)
    reports.sort(key=lambda i: -(i.get("rain_mm") or i.get("at_least_mm") or -1))
    out.update(status="ok", stations_reporting=len(reports), stations=reports + gaps)
    return out


def station_coverage(gold: Gold, place: str) -> dict:
    p = _place(place)
    sid = p.station.station_id
    rd = gold.rain_daily[gold.rain_daily["station_id"] == sid]
    out = {"tool": "station_coverage", **_place_facts(p), "data_through": gold.latest_day.isoformat()}
    if p.too_far:
        out.update(_too_far(p, "station_coverage"))
    if rd.empty:
        out["status"] = "no_data"
        return out
    last = rd["obs_date"].max()
    lag = (gold.latest_day - last).days
    year_ago = gold.latest_day.replace(year=gold.latest_day.year - 1)
    recent = rd[(rd["obs_date"] > year_ago) & (rd["prcp_quality"] == "complete")]
    ms = gold.monsoon_season[gold.monsoon_season["station_id"] == sid]
    out.update(
        status="retired" if lag > 3 * 365 else "silent" if lag > config.SILENT_AFTER_DAYS else "reporting",
        first_day=rd["obs_date"].min().isoformat(),
        last_day=last.isoformat(),
        days_since_last_report=lag,
        days_with_complete_rain=int((rd["prcp_quality"] == "complete").sum()),
        complete_days_last_365=int(len(recent)),
        monsoons_published=int((ms["total_status"] == "published").sum()),
        monsoons_on_record=int(len(ms)),
    )
    return out


# --- registry ---------------------------------------------------------------------------------

_PLACE = {
    "type": "string",
    "description": "Place name as the person wrote it, in English or Nepali (e.g. 'Pokhara', 'काठमाडौं').",
}
_DATE = {
    "type": "string",
    "description": "YYYY-MM-DD, or MM-DD when the person gave no year (the most recent such day is used).",
}
_CAL = {
    "type": "string",
    "enum": ["AD", "BS"],
    "description": "AD for Gregorian dates, BS for Bikram Sambat dates such as असोज १२.",
}

SPECS = {
    "rain_on_day": {
        "description": "Rainfall at one place on one day, with how unusual it was for that station.",
        "properties": {"place": _PLACE, "date": _DATE, "calendar": _CAL},
        "required": ["place", "date", "calendar"],
    },
    "wettest_days": {
        "description": "The wettest days on record at one place, optionally within one year.",
        "properties": {
            "place": _PLACE,
            "n": {"type": "integer", "description": "How many days, 1-10."},
            "year": {"type": "integer", "description": "Optional year."},
            "calendar": _CAL,
        },
        "required": ["place"],
    },
    "monsoon_total": {
        "description": "June-September monsoon rainfall total at one place in one year, if complete enough to publish.",
        "properties": {"place": _PLACE, "year": {"type": "integer"}, "calendar": _CAL},
        "required": ["place", "year", "calendar"],
    },
    "rain_across_stations": {
        "description": "Rainfall at every station on one day, wettest first. Use for 'where did it rain most'.",
        "properties": {"date": _DATE, "calendar": _CAL},
        "required": ["date", "calendar"],
    },
    "station_coverage": {
        "description": "How long a station has reported, whether it still reports, and how complete its record is.",
        "properties": {"place": _PLACE},
        "required": ["place"],
    },
}

FUNCTIONS: dict[str, Callable[..., dict]] = {
    "rain_on_day": rain_on_day,
    "wettest_days": wettest_days,
    "monsoon_total": monsoon_total,
    "rain_across_stations": rain_across_stations,
    "station_coverage": station_coverage,
}


def bedrock_tool_config() -> dict:
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": {
                        "json": {"type": "object", "properties": spec["properties"], "required": spec["required"]}
                    },
                }
            }
            for name, spec in SPECS.items()
        ]
    }


def call(gold: Gold, name: str, args: dict) -> dict:
    """Run a tool by name. Unknown tools and bad arguments come back as data, not exceptions,
    so the model can correct itself."""
    fn = FUNCTIONS.get(name)
    if fn is None:
        return {"tool": name, "error": f"no tool named {name}"}
    allowed = set(SPECS[name]["properties"])
    clean = {k: v for k, v in (args or {}).items() if k in allowed}
    try:
        return fn(gold, **clean)
    except (ToolError, TypeError) as e:
        return {"tool": name, "error": str(e)}
