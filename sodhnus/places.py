"""Place names in questions, mapped to Barsha's stations.

Sixteen stations cover a mountainous country, so most places people ask about have no gauge.
Those resolve to the nearest station with the distance, and every answer says so.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .dates import to_ascii_digits


@dataclass(frozen=True)
class Station:
    station_id: str
    en: str
    ne: str
    lat: float
    lon: float
    aliases: tuple[str, ...]


# Coordinates from Barsha's station_dim (current version). Aliases are how people actually write them.
STATIONS = [
    Station("44404099999", "Dadeldhura", "डडेल्धुरा", 29.300, 80.583, ("dadeldhura", "डडेलधुरा")),
    Station("44406099999", "Dipayal", "दिपायल", 29.250, 80.950, ("dipayal", "silgadhi", "doti", "डोटी", "सिलगढी")),
    Station(
        "44409099999",
        "Dhangadhi",
        "धनगढी",
        28.800,
        80.550,
        ("dhangadhi", "dhangadi", "kailali", "कैलाली", "attariya", "अत्तरिया"),
    ),
    Station("44416099999", "Surkhet", "सुर्खेत", 28.600, 81.617, ("surkhet", "birendranagar", "वीरेन्द्रनगर", "बिरेन्द्रनगर")),
    Station(
        "44418099999", "Nepalgunj", "नेपालगन्ज", 28.100, 81.667, ("nepalgunj", "nepalganj", "banke", "बाँके", "नेपालगञ्ज")
    ),
    Station("44424099999", "Jumla", "जुम्ला", 29.283, 82.167, ("jumla",)),
    Station("44429099999", "Dang", "दाङ", 28.050, 82.500, ("dang", "ghorahi", "घोराही")),
    Station("44434099999", "Pokhara", "पोखरा", 28.201, 83.981, ("pokhara", "pokhra", "kaski", "कास्की")),
    Station(
        "44438099999",
        "Bhairahawa",
        "भैरहवा",
        27.506,
        83.416,
        ("bhairahawa", "bhairawa", "siddharthanagar", "rupandehi", "रुपन्देही", "सिद्धार्थनगर"),
    ),
    Station("44449099999", "Simara", "सिमरा", 27.159, 84.980, ("simara", "bara", "बारा")),
    Station(
        "44454099999",
        "Kathmandu Airport",
        "काठमाडौं विमानस्थल",
        27.697,
        85.359,
        ("kathmandu", "ktm", "kathmandu airport", "tia", "tribhuvan", "काठमाडौं", "काठमाण्डौ", "काठमाडौँ", "काठमाडौ"),
    ),
    Station("44461099999", "Syangboche", "स्याङबोचे", 27.817, 86.717, ("syangboche",)),
    Station("44462099999", "Okhaldhunga", "ओखलढुङ्गा", 27.300, 86.500, ("okhaldhunga", "ओखलढुंगा")),
    Station("44474099999", "Taplejung", "ताप्लेजुङ", 27.350, 87.667, ("taplejung", "ताप्लेजुंग")),
    Station("44477099999", "Dhankuta", "धनकुटा", 26.983, 87.350, ("dhankuta",)),
    Station("44478099999", "Biratnagar", "विराटनगर", 26.481, 87.264, ("biratnagar", "morang", "मोरङ", "बिराटनगर")),
]
BY_ID = {s.station_id: s for s in STATIONS}

# Towns people ask about that have no station in this network. Approximate centres; only used to
# pick and disclose the nearest station.
TOWNS = {
    "lalitpur": ("Lalitpur", "ललितपुर", 27.666, 85.319),
    "patan": ("Lalitpur", "ललितपुर", 27.666, 85.319),
    "ललितपुर": ("Lalitpur", "ललितपुर", 27.666, 85.319),
    "bhaktapur": ("Bhaktapur", "भक्तपुर", 27.671, 85.430),
    "भक्तपुर": ("Bhaktapur", "भक्तपुर", 27.671, 85.430),
    "chitwan": ("Chitwan", "चितवन", 27.683, 84.433),
    "bharatpur": ("Chitwan", "चितवन", 27.683, 84.433),
    "चितवन": ("Chitwan", "चितवन", 27.683, 84.433),
    "hetauda": ("Hetauda", "हेटौंडा", 27.428, 85.032),
    "हेटौंडा": ("Hetauda", "हेटौंडा", 27.428, 85.032),
    "birgunj": ("Birgunj", "वीरगञ्ज", 27.010, 84.877),
    "वीरगञ्ज": ("Birgunj", "वीरगञ्ज", 27.010, 84.877),
    "janakpur": ("Janakpur", "जनकपुर", 26.729, 85.926),
    "जनकपुर": ("Janakpur", "जनकपुर", 26.729, 85.926),
    "butwal": ("Butwal", "बुटवल", 27.701, 83.448),
    "बुटवल": ("Butwal", "बुटवल", 27.701, 83.448),
    "dharan": ("Dharan", "धरान", 26.812, 87.284),
    "धरान": ("Dharan", "धरान", 26.812, 87.284),
    "itahari": ("Itahari", "इटहरी", 26.663, 87.274),
    "इटहरी": ("Itahari", "इटहरी", 26.663, 87.274),
    "ilam": ("Ilam", "इलाम", 26.909, 87.928),
    "इलाम": ("Ilam", "इलाम", 26.909, 87.928),
    "gorkha": ("Gorkha", "गोरखा", 28.000, 84.628),
    "गोरखा": ("Gorkha", "गोरखा", 28.000, 84.628),
    "jomsom": ("Jomsom", "जोमसोम", 28.781, 83.723),
    "mustang": ("Jomsom", "जोमसोम", 28.781, 83.723),
    "tansen": ("Tansen", "तानसेन", 27.867, 83.546),
    "palpa": ("Tansen", "तानसेन", 27.867, 83.546),
    "melamchi": ("Melamchi", "मेलम्ची", 27.833, 85.577),
    "मेलम्ची": ("Melamchi", "मेलम्ची", 27.833, 85.577),
    "sindhupalchok": ("Sindhupalchok", "सिन्धुपाल्चोक", 27.780, 85.710),
    "सिन्धुपाल्चोक": ("Sindhupalchok", "सिन्धुपाल्चोक", 27.780, 85.710),
    "mahendranagar": ("Bhimdatta", "भीमदत्त", 28.963, 80.178),
    "kanchanpur": ("Bhimdatta", "भीमदत्त", 28.963, 80.178),
    "namche": ("Namche", "नाम्चे", 27.805, 86.713),
    "solukhumbu": ("Namche", "नाम्चे", 27.805, 86.713),
    "tulsipur": ("Tulsipur", "तुलसीपुर", 28.131, 82.297),
    "dhulikhel": ("Dhulikhel", "धुलिखेल", 27.622, 85.556),
    "baglung": ("Baglung", "बागलुङ", 28.272, 83.590),
}
# Stations that stopped reporting long ago are not offered as a "nearest" station.
RETIRED = {"44461099999"}  # Syangboche: 78 days of data, 1976-79

# Beyond this a "nearest station" is a different climate, not a proxy: Chitwan's nearest gauge in a
# straight line is Pokhara, 73 km away on the other side of the Mahabharat range.
MAX_PROXY_KM = 40


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Place:
    """What a place name resolved to. distance_km is 0 when the place has its own station."""

    query: str
    station: Station
    place_en: str
    place_ne: str
    distance_km: float
    lat: float
    lon: float

    @property
    def is_proxy(self) -> bool:
        return self.distance_km > 0

    @property
    def too_far(self) -> bool:
        return self.distance_km > MAX_PROXY_KM


_LETTER = r"[A-Za-z\u0900-\u0963\u0970-\u097f]"
# Nepali attaches postpositions to names: काठमाडौंमा, पोखराको, धरानमा. Strip them after the name.
_NE_SUFFIX = r"(?:मा|को|का|की|ले|बाट|तिर|भन्दा|सम्म)?"


def _alias_index() -> list[tuple[str, str]]:
    pairs = []
    for s in STATIONS:
        for a in (s.en.lower(), s.ne, *s.aliases):
            pairs.append((a.lower(), f"station:{s.station_id}"))
    for key in TOWNS:
        pairs.append((key, f"town:{key}"))
    return sorted(set(pairs), key=lambda p: -len(p[0]))


_ALIASES = _alias_index()


def nearest_stations(lat: float, lon: float, n: int = 1) -> list[tuple[Station, float]]:
    live = [s for s in STATIONS if s.station_id not in RETIRED]
    ranked = sorted((haversine_km(lat, lon, s.lat, s.lon), s.station_id) for s in live)
    return [(BY_ID[sid], km) for km, sid in ranked[:n]]


def nearest_station(lat: float, lon: float) -> tuple[Station, float]:
    return nearest_stations(lat, lon)[0]


def _place_for(key: str, query: str) -> Place:
    kind, ref = key.split(":", 1)
    if kind == "station":
        s = BY_ID[ref]
        return Place(query, s, s.en, s.ne, 0.0, s.lat, s.lon)
    en, ne, lat, lon = TOWNS[ref]
    s, km = nearest_station(lat, lon)
    return Place(query, s, en, ne, round(km), lat, lon)


def find_places(question: str) -> list[Place]:
    """Every station or known town named in the question, in order of appearance."""
    text = to_ascii_digits(question).lower()
    hits: list[tuple[int, Place]] = []
    taken: list[tuple[int, int]] = []
    for alias, key in _ALIASES:
        suffix = _NE_SUFFIX if re.search(r"[\u0900-\u097f]", alias) else ""
        for m in re.finditer(rf"(?<!{_LETTER}){re.escape(alias)}{suffix}(?!{_LETTER})", text):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            taken.append(m.span())
            place = _place_for(key, m.group(0))
            if all(p.station.station_id != place.station.station_id or p.place_en != place.place_en for _, p in hits):
                hits.append((m.start(), place))
    return [p for _, p in sorted(hits, key=lambda t: t[0])]


def resolve_place(name: str) -> Place | None:
    """A single place name, as a tool argument from the model."""
    found = find_places(name)
    return found[0] if found else None
