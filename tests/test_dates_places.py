from datetime import date

import pytest

from sodhnus.dates import ad_to_bs, bs_to_ad, find_dates, resolve
from sodhnus.places import find_places, resolve_place


def test_bs_conversion_matches_the_flood_day():
    assert bs_to_ad(2081, 6, 12) == date(2024, 9, 28)
    assert ad_to_bs(date(2024, 9, 28)) == (2081, 6, 12)


@pytest.mark.parametrize(
    "question",
    [
        "असोज १२, 2081",
        "२०८१ असोज १२ गते",
        "asoj 12 2081",
        "12th of Asoj, 2081",
        "आश्विन १२ २०८१",
        "Ashwin 12 2081",
    ],
)
def test_everyday_and_formal_month_spellings(question):
    [m] = find_dates(question)
    assert resolve(m, date(2025, 8, 24)) == (date(2024, 9, 28), False)


def test_missing_year_uses_most_recent_day_and_says_so():
    [m] = find_dates("Pokhara on असोज १२")
    # Data ends 24 Aug 2025 (2082 Bhadau), so Asoj 12 2082 hasn't happened yet: 2081 is used.
    assert resolve(m, date(2025, 8, 24)) == (date(2024, 9, 28), True)


def test_english_words_that_look_like_months_are_ignored():
    assert find_dates("May I ask about rain in Pokhara?") == []
    assert find_dates("push the data") == []


def test_ad_dates_in_several_formats():
    for q in ["28 September 2024", "Sept 28, 2024", "2024-09-28", "September 28th 2024"]:
        [m] = find_dates(q)
        assert (m.calendar, m.year, m.month, m.day) == ("AD", 2024, 9, 28), q


def test_nepali_postpositions_are_stripped():
    [p] = find_places("काठमाडौंमा कति पानी पर्यो")
    assert p.station.en == "Kathmandu Airport" and not p.is_proxy


def test_town_without_station_maps_to_nearest_and_says_how_far():
    p = resolve_place("Dharan")
    assert p.station.en == "Dhankuta" and p.is_proxy and p.distance_km == 20 and not p.too_far


def test_far_town_is_not_given_a_proxy():
    # Straight-line nearest is Pokhara, across the Mahabharat range: a different climate.
    p = resolve_place("Chitwan")
    assert p.too_far
