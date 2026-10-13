"""Answers written from tool results by templates, in English and Nepali.

These are used when no model is available (local runs, tests, Bedrock down) and whenever a model
answer fails the checker twice. They are plain, but every sentence is built from tool fields, so
they cannot state a number the data doesn't have.
"""

from __future__ import annotations

from datetime import date

from .config import FORECAST_SOURCE_EN, FORECAST_SOURCE_NE
from .dates import ad_label, bs_label, ne_digits

CATEGORY = {
    "extremely_heavy": ("extremely heavy rain", "अत्यधिक भारी वर्षा"),
    "very_heavy": ("very heavy rain", "धेरै भारी वर्षा"),
    "heavy": ("heavy rain", "भारी वर्षा"),
    "moderate": ("moderate rain", "मध्यम वर्षा"),
    "light": ("light rain", "हल्का वर्षा"),
    "very_light": ("very light rain", "धेरै हल्का वर्षा"),
    "dry": ("no rain", "वर्षा भएन"),
}

REFUSALS = {
    "forecast": (
        f"I only report rain that has already been measured, so I can't say what will happen. "
        f"For forecasts and flood warnings, please see the {FORECAST_SOURCE_EN}.",
        f"म पहिले नापिएको वर्षाको मात्र जानकारी दिन्छु, त्यसैले आगामी मौसम भन्न सक्दिनँ। "
        f"पूर्वानुमान र बाढी सूचनाका लागि {FORECAST_SOURCE_NE} हेर्नुहोस्।",
    ),
    "impact": (
        "I only have rainfall measurements, not information about deaths, injuries or damage. "
        "The government's disaster portal (bipadportal.gov.np) records incidents.",
        "मसँग वर्षाको नाप मात्र छ, मृत्यु, घाइते वा क्षतिको जानकारी छैन। "
        "घटनाको विवरण सरकारको विपद् पोर्टल (bipadportal.gov.np) मा हेर्नुहोस्।",
    ),
    "safety": (
        "I can't tell you whether it is safe: that depends on current conditions and warnings I don't have. "
        f"Please follow the {FORECAST_SOURCE_EN} and local authorities.",
        "सुरक्षित छ कि छैन भन्न सक्दिनँ, किनकि त्यो अहिलेको अवस्था र सूचनामा भर पर्छ जुन मसँग छैन। "
        f"कृपया {FORECAST_SOURCE_NE} र स्थानीय प्रशासनको सूचना पालना गर्नुहोस्।",
    ),
    "injection": (
        "I can only answer questions about rainfall measured at Nepal's weather stations.",
        "म नेपालका मौसम स्टेशनमा नापिएको वर्षाबारे मात्र जवाफ दिन सक्छु।",
    ),
    "too_long": (
        "That is longer than a rainfall question. Please ask about one place and one date or season.",
        "प्रश्न धेरै लामो भयो। कृपया एउटा ठाउँ र एउटा मिति वा मौसमबारे सोध्नुहोस्।",
    ),
    "empty": ("Please ask a question about rainfall.", "कृपया वर्षाबारे प्रश्न सोध्नुहोस्।"),
    "unknown_place": (
        "I don't recognise the place in your question, so here is every station instead.",
        "प्रश्नमा भएको ठाउँ चिनिनँ, त्यसैले सबै स्टेशनको नाप दिएको छु।",
    ),
    "not_found": (
        "I couldn't match the place or the date in your question to the data. Please check the spelling of "
        "the place and the date.",
        "प्रश्नमा भएको ठाउँ वा मिति डाटासँग मिलाउन सकिनँ। कृपया ठाउँको नाम र मिति जाँच्नुहोस्।",
    ),
    "unclear": (
        "I answer questions about rain already measured at Nepal's weather stations, for example "
        '"How much rain fell in Pokhara on Asoj 12, 2081?" or "Kathmandu monsoon total 2023". '
        "Please include a place and a date or year.",
        'म नेपालका मौसम स्टेशनमा नापिएको वर्षाबारे जवाफ दिन्छु, जस्तै "२०८१ असोज १२ मा पोखरामा कति पानी पर्यो?" '
        'वा "काठमाडौंको २०८० को मनसुन"। कृपया ठाउँ र मिति वा वर्ष उल्लेख गर्नुहोस्।',
    ),
}


def refusal(reason: str, lang: str) -> str:
    en, ne = REFUSALS[reason]
    return ne if lang == "ne" else en


def _n(x, lang: str) -> str:
    if x is None:
        return "?"
    text = f"{x:g}" if isinstance(x, float) else str(x)
    return ne_digits(text) if lang == "ne" else text


def _d(iso: str, lang: str, with_bs: bool = True) -> str:
    d = date.fromisoformat(iso)
    if lang == "ne":
        return f"{bs_label(d, 'ne')} ({ne_digits(iso)})" if with_bs else ne_digits(iso)
    return f"{ad_label(d, 'en')} ({bs_label(d, 'en')})" if with_bs else ad_label(d, "en")


def _station(r: dict, lang: str) -> str:
    return r["station_ne"] if lang == "ne" else r["station"]


def _proxy_prefix(r: dict, lang: str) -> str:
    if "distance_km" not in r:
        return ""
    if lang == "ne":
        return (
            f"{r['asked_about_ne']}मा यो सञ्जालको स्टेशन छैन; सबैभन्दा नजिकको {r['station_ne']} "
            f"({_n(r['distance_km'], lang)} किमि टाढा) को नाप यस्तो छ: "
        )
    return (
        f"{r['asked_about']} has no station in this network; the nearest is {r['station']}, "
        f"{r['distance_km']} km away, and rain there can differ. "
    )


def _too_far(r: dict, lang: str) -> str:
    near = r["nearest"]
    if lang == "ne":
        lst = " र ".join(f"{s['station_ne']} ({_n(s['distance_km'], lang)} किमि)" for s in near)
        return (
            f"{r['asked_about_ne']} नजिक यो सञ्जालको कुनै स्टेशन छैन। सबैभन्दा नजिकका {lst} हुन्, तर पहाडमा "
            "यति दूरीमा वर्षा धेरै फरक पर्छ, त्यसैले म अंक दिन्नँ।"
        )
    lst = " and ".join(f"{s['station']} ({s['distance_km']} km)" for s in near)
    return (
        f"No station in this network is close enough to {r['asked_about']}. The nearest are {lst}, and rain "
        "can differ a lot over that distance in Nepal's hills, so I won't give a number for it."
    )


def _year_note(r: dict, lang: str) -> str:
    if not r.get("year_assumed"):
        return ""
    if lang == "ne":
        return " (तपाईंले साल नभन्नुभएकाले डाटामा भएको पछिल्लो यस्तो दिन लिइएको छ।)"
    return " (You didn't give a year, so this is the most recent such day in the data.)"


def rain_on_day(r: dict, lang: str) -> str:
    ne = lang == "ne"
    if r.get("status") == "no_station_nearby":
        return _too_far(r, lang)
    st, day = _station(r, lang), _d(r["date"], lang)
    pre, note = _proxy_prefix(r, lang), _year_note(r, lang)
    status = r["status"]
    if status == "after_data_end":
        through = _d(r["data_through"], lang, with_bs=False)
        if ne:
            return f"मेरो डाटा {through} सम्मको मात्र छ, त्यसैले {day} को जानकारी छैन। हालको अवस्थाका लागि {FORECAST_SOURCE_NE} हेर्नुहोस्।"
        return f"My data ends on {through}, so I have nothing for {day}. For current conditions, see the {FORECAST_SOURCE_EN}."
    if status == "before_station_records":
        start = _d(r["station_records_from"], lang, with_bs=False)
        return f"{st}को नाप {start} बाट मात्र सुरु हुन्छ।" if ne else f"{st}'s records only start on {start}."
    if status == "no_report":
        return pre + (f"{st}ले {day} मा कुनै रिपोर्ट पठाएन।" if ne else f"{st} sent no report for {day}.") + note
    if status == "missing":
        if ne:
            text = f"{st}मा {day} को वर्षाको अंक दर्ता भएन।"
            if r.get("rain_observed"):
                text += " तर मौसम कोडले पानी परेको देखाउँछ, त्यसैले यो सुख्खा दिन होइन।"
        else:
            text = f"{st} has no usable rainfall amount for {day}."
            if r.get("rain_observed"):
                text += " Its weather codes say it rained, so this was not a dry day."
        return pre + text + note
    if status == "partial" and "at_least_mm" not in r:
        if ne:
            return pre + f"{st}मा {day} को आंशिक रिपोर्ट मात्र छ, र त्यसले दिनभरको वर्षा बताउँदैन।" + note
        return pre + f"{st} has only a partial report for {day}, which doesn't tell us the day's rainfall." + note
    if status == "partial":
        x = _n(r["at_least_mm"], lang)
        if ne:
            return (
                pre
                + f"{st}मा {day} मा कम्तीमा {x} मिमि पानी पर्यो, तर २४ घण्टाको पूरा रिपोर्ट छैन, त्यसैले वास्तविक जम्मा थाहा छैन।"
                + note
            )
        return (
            pre
            + f"{st} recorded at least {x} mm on {day}, but fewer than 24 hours were reported, so the full total is unknown."
            + note
        )
    mm = _n(r["rain_mm"], lang)
    if r.get("suspect"):
        if ne:
            return (
                pre
                + f"{st}ले {day} मा {mm} मिमि रिपोर्ट गर्यो, तर वरपरका कुनै स्टेशनमा भारी वर्षा नभएकाले यो अंक सम्भावित उपकरण त्रुटि मानेर रोकिएको छ।"
            )
        return pre + (
            f"{st} reported {mm} mm on {day}, but no station within 200 km had heavy rain, so this value is "
            "held back as a likely gauge error."
        )
    en_cat, ne_cat = CATEGORY.get(r.get("category"), (r.get("category"), r.get("category")))
    parts = [
        pre
        + (f"{st}मा {day} मा {mm} मिमि पानी पर्यो ({ne_cat})।" if ne else f"{st} recorded {mm} mm on {day}: {en_cat}.")
    ]
    h = r.get("history_before")
    if h and r.get("is_station_record"):
        since, prev = h["from"][:4], _d(h["highest_on"], lang, with_bs=False)
        parts.append(
            f"यो {_n(int(since), lang)} देखिको रेकर्डमै सबैभन्दा धेरै हो (यसअघिको अधिकतम {_n(h['highest_mm'], lang)} मिमि, {prev})।"
            if ne
            else f"That is the wettest day in its record since {since} (the previous highest was {h['highest_mm']:g} mm on {prev})."
        )
    elif h and r["rain_mm"] > 0:
        rare = r.get("rare_threshold")
        if rare and r["rain_mm"] >= rare["mm"]:
            parts.append(
                f"यो स्टेशनमा १०० वर्षा-दिनमा १ पटक मात्र पुग्ने स्तर ({_n(rare['mm'], lang)} मिमि) भन्दा बढी हो।"
                if ne
                else f"That is above the level this station reaches on only 1 in 100 rainy days ({rare['mm']:g} mm)."
            )
        k = h["days_as_wet_or_wetter"]
        last = _d(h["last_as_wet_or_wetter"], lang, with_bs=False) if h["last_as_wet_or_wetter"] else None
        if ne:
            parts.append(
                f"{_n(h['from'][:4], lang)} देखिका {_n(h['complete_days'], lang)} पूरा नाप भएका दिनमध्ये {_n(k, lang)} दिन यति वा यो भन्दा बढी पानी परेको थियो"
                + (f"; पछिल्लो पटक {last} मा।" if last else "।")
            )
        else:
            parts.append(
                f"Of {h['complete_days']} days with a complete reading since {h['from'][:4]}, {k} had as much or more"
                + (f", most recently {last}." if last else ".")
            )
    three = r.get("three_day")
    if three and three.get("rain_mm") and three["rain_mm"] >= 1.2 * r["rain_mm"] and r["rain_mm"] >= 15.6:
        parts.append(
            f"३ दिनमा जम्मा {_n(three['rain_mm'], lang)} मिमि पानी पर्यो।"
            if ne
            else f"Over 3 days, {three['rain_mm']:g} mm fell."
        )
    return " ".join(parts) + note


def wettest_days(r: dict, lang: str) -> str:
    if r.get("status") == "no_station_nearby":
        return _too_far(r, lang)
    ne = lang == "ne"
    st, pre = _station(r, lang), _proxy_prefix(r, lang)
    period = r.get("period", {})
    if not r["days"]:
        return pre + (f"{st}मा यो अवधिमा पूरा नाप भएको दिन छैन।" if ne else f"{st} has no complete days in that period.")
    items = [f"{_d(d['date'], lang)}: {_n(d['rain_mm'], lang)} {'मिमि' if ne else 'mm'}" for d in r["days"]]
    if ne:
        scope = (
            f"{_n(period['bs_year'], lang)} सालमा "
            if "bs_year" in period
            else f"{_n(period['year'], lang)} मा "
            if "year" in period
            else "रेकर्डमा "
        )
        text = pre + f"{st}मा {scope}सबैभन्दा धेरै पानी परेका दिन: " + "; ".join(items) + "।"
        if r.get("held_back_as_suspect"):
            text += " सम्भावित त्रुटि भएका अंक यसमा समावेश छैनन्।"
        return text
    scope = (
        f" in {period['bs_year']} BS"
        if "bs_year" in period
        else f" in {period['year']}"
        if "year" in period
        else " on record"
    )
    text = pre + f"The wettest days at {st}{scope}: " + "; ".join(items) + "."
    if r.get("held_back_as_suspect"):
        text += " A value held back as a likely gauge error is left out."
    return text


def monsoon_total(r: dict, lang: str) -> str:
    if r.get("status") == "no_station_nearby":
        return _too_far(r, lang)
    ne = lang == "ne"
    st, pre = _station(r, lang), _proxy_prefix(r, lang)
    year = r["year"]
    if "bs_year" in r:
        # Say it back in the calendar the person used.
        year = f"{_n(r['bs_year'], lang)} ({_n(year, lang)})" if ne else f"{r['bs_year']} BS ({year})"
    if r["status"] == "no_data":
        return pre + (
            f"{st}मा {_n(year, lang)} को मनसुनको डाटा छैन।" if ne else f"{st} has no data for the {year} monsoon."
        )
    if r["status"] == "withheld":
        if ne:
            text = (
                f"{st}को {_n(year, lang)} को मनसुन (जुन–सेप्टेम्बर) को जम्मा वर्षा दिन सकिँदैन: {_n(r['season_days'], lang)} मध्ये "
                f"{_n(r['complete_days'], lang)} दिनको मात्र पूरा नाप छ, र छुटेका दिन प्रायः पानी परेका दिन हुन्छन्।"
            )
            if r.get("max_1day_mm") is not None:
                text += f" त्यो मौसमको सबैभन्दा धेरै एक दिनको वर्षा {_n(r['max_1day_mm'], lang)} मिमि थियो।"
        else:
            text = (
                f"I can't give a {year} monsoon total for {st}: only {r['complete_days']} of {r['season_days']} days "
                "have a complete reading, and the missing days are usually rainy ones, so a total would understate it."
            )
            if r.get("max_1day_mm") is not None:
                text += f" Its wettest single day that season had {r['max_1day_mm']:g} mm."
        return pre + text
    o = r.get("other_published_seasons")
    if ne:
        text = f"{st}मा {_n(year, lang)} को मनसुन (जुन–सेप्टेम्बर) मा जम्मा {_n(r['total_mm'], lang)} मिमि पानी पर्यो।"
        if o:
            text += (
                f" पूरा नाप भएका अरू {_n(o['count'], lang)} मनसुनको मध्यक {_n(o['median_mm'], lang)} मिमि हो "
                f"(सबैभन्दा कम {_n(o['lowest_mm'], lang)}, सबैभन्दा धेरै {_n(o['highest_mm'], lang)} मिमि)।"
            )
    else:
        text = f"{st}'s June to September {year} monsoon total was {r['total_mm']:g} mm."
        if o:
            text += (
                f" Across the other {o['count']} seasons complete enough to publish, the median is {o['median_mm']:g} mm "
                f"(lowest {o['lowest_mm']:g}, highest {o['highest_mm']:g})."
            )
    if r.get("unusually_low"):
        text += (
            " यो अरू वर्षको मध्यकको आधाभन्दा कम हो; रिपोर्ट नभएका दिन शून्य लेखिएका हुन सक्छन्, त्यसैले यो अंकमा सावधानी अपनाउनुहोस्।"
            if ne
            else " That is less than half the usual total, which more likely means unreported days were recorded as "
            "zero than a real drought, so treat it with caution."
        )
    if r.get("season_incomplete"):
        text += " (डाटा मौसम सकिनुअघि नै रोकिन्छ।)" if ne else " (The data stops before that season ended.)"
    return pre + text


def rain_across_stations(r: dict, lang: str) -> str:
    ne = lang == "ne"
    day = _d(r["date"], lang)
    if r["status"] == "after_data_end":
        through = _d(r["data_through"], lang, with_bs=False)
        return f"मेरो डाटा {through} सम्मको मात्र छ।" if ne else f"My data ends on {through}, so I have nothing for {day}."
    measured = [s for s in r["stations"] if "rain_mm" in s][:5]
    silent = [s for s in r["stations"] if s["status"] in {"no_report", "missing"}]
    if not measured:
        return f"{day} मा कुनै स्टेशनको पूरा नाप छैन।" if ne else f"No station has a complete reading for {day}."
    unit = "मिमि" if ne else "mm"
    items = ", ".join(f"{s['station_ne'] if ne else s['station']} {_n(s['rain_mm'], lang)} {unit}" for s in measured)
    if ne:
        text = f"{day} मा सबैभन्दा धेरै पानी: {items}।"
        if silent:
            text += f" {_n(len(silent), lang)} स्टेशनको अंक छैन, त्यसैले त्यहाँ बढी परेको पनि हुन सक्छ।"
    else:
        text = f"Wettest stations on {day}: {items}."
        if silent:
            text += f" {len(silent)} stations have no amount for that day, so rain there could have been higher."
    return text + _year_note(r, lang)


def station_coverage(r: dict, lang: str) -> str:
    ne = lang == "ne"
    st = _station(r, lang)
    if r.get("status") == "no_data":
        return f"{st}को डाटा छैन।" if ne else f"There is no data for {st}."
    first, last = _d(r["first_day"], lang, with_bs=False), _d(r["last_day"], lang, with_bs=False)
    status_en = {"reporting": "still reporting", "silent": "currently silent", "retired": "no longer reporting"}[
        r["status"]
    ]
    status_ne = {"reporting": "अझै रिपोर्ट गर्दैछ", "silent": "हाल रिपोर्ट आएको छैन", "retired": "अब रिपोर्ट गर्दैन"}[
        r["status"]
    ]
    if ne:
        return (
            f"{st}ले {first} देखि {last} सम्म रिपोर्ट गरेको छ ({status_ne})। {_n(r['days_with_complete_rain'], lang)} दिनको "
            f"वर्षाको पूरा नाप छ, र {_n(r['monsoons_on_record'], lang)} मध्ये {_n(r['monsoons_published'], lang)} मनसुन "
            "जम्मा प्रकाशित गर्न पुग्ने गरी पूरा छन्।"
        )
    return (
        f"{st} has reported from {first} to {last} ({status_en}). It has {r['days_with_complete_rain']} days with a "
        f"complete rainfall reading, and {r['monsoons_published']} of its {r['monsoons_on_record']} monsoons are "
        "complete enough to publish a total."
    )


WRITERS = {
    "rain_on_day": rain_on_day,
    "wettest_days": wettest_days,
    "monsoon_total": monsoon_total,
    "rain_across_stations": rain_across_stations,
    "station_coverage": station_coverage,
}


def compose(results: list[dict], lang: str) -> str:
    if not results:
        return refusal("unclear", lang)
    texts = []
    for r in results:
        writer = WRITERS.get(r.get("tool"))
        texts.append(writer(r, lang) if writer and "error" not in r else refusal("not_found", lang))
    return "\n\n".join(dict.fromkeys(texts))
