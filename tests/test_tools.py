from sodhnus import tools


def test_record_day_at_kathmandu(gold):
    r = tools.call(gold, "rain_on_day", {"place": "Kathmandu", "date": "2081-06-12", "calendar": "BS"})
    assert r["date"] == "2024-09-28" and r["rain_mm"] == 194.1
    assert r["is_station_record"] is True
    assert r["history_before"]["highest_mm"] == 191.0
    assert r["three_day"] == {"window_days": 3, "rain_mm": 291.1}


def test_missing_day_is_not_dry(gold):
    r = tools.call(gold, "rain_on_day", {"place": "Kathmandu", "date": "2001-07-15", "calendar": "AD"})
    assert r["status"] == "missing" and "rain_mm" not in r and r["rain_observed"] is True


def test_suspect_value_is_labelled_and_has_no_history(gold):
    r = tools.call(gold, "rain_on_day", {"place": "Taplejung", "date": "2018-04-19", "calendar": "AD"})
    assert r["suspect"] is True and "history_before" not in r


def test_suspect_value_never_ranks(gold):
    r = tools.call(gold, "wettest_days", {"place": "Taplejung", "n": 3})
    assert r["days"][0]["rain_mm"] < 404 and r["held_back_as_suspect"] == 1


def test_partial_day_without_an_amount_gives_none(gold):
    import pandas as pd

    rd = gold.rain_daily
    row = rd[(rd["prcp_quality"] == "partial")].iloc[0]
    r = tools.call(
        gold,
        "rain_on_day",
        {
            "place": "Kathmandu"
            if row.station_id == "44454099999"
            else next(s.en for s in tools.STATIONS if s.station_id == row.station_id),
            "date": pd.Timestamp(row.obs_date).date().isoformat(),
            "calendar": "AD",
        },
    )
    assert r["status"] == "partial" and "rain_mm" not in r


def test_withheld_monsoon_says_why(gold):
    r = tools.call(gold, "monsoon_total", {"place": "Kathmandu", "year": 2024, "calendar": "AD"})
    assert r["status"] == "withheld" and "total_mm" not in r and r["complete_days"] == 103


def test_bs_year_maps_to_its_monsoon(gold):
    r = tools.call(gold, "monsoon_total", {"place": "Kathmandu", "year": 2080, "calendar": "BS"})
    assert r["year"] == 2023 and r["total_mm"] == 1235.1 and r["percent_of_median"] == 102


def test_implausibly_low_season_is_flagged(gold):
    r = tools.call(gold, "monsoon_total", {"place": "Dhankuta", "year": 2014, "calendar": "AD"})
    assert r["status"] == "published" and r["unusually_low"] is True


def test_days_after_the_data_ends(gold):
    r = tools.call(gold, "rain_on_day", {"place": "Pokhara", "date": "2026-10-12", "calendar": "AD"})
    assert r["status"] == "after_data_end" and "rain_mm" not in r


def test_far_place_gets_no_number(gold):
    r = tools.call(gold, "rain_on_day", {"place": "Chitwan", "date": "2024-09-28", "calendar": "AD"})
    assert r["status"] == "no_station_nearby" and "rain_mm" not in r


def test_bad_arguments_come_back_as_data(gold):
    assert "error" in tools.call(gold, "rain_on_day", {"place": "Atlantis", "date": "2024-09-28"})
    assert "error" in tools.call(gold, "rain_on_day", {"place": "Pokhara", "date": "yesterday"})
    assert "error" in tools.call(gold, "rain_on_day", {"place": "Pokhara", "date": "2024-02-30"})
    assert "error" in tools.call(gold, "drop_table", {})
    # Unknown arguments are dropped, not passed through.
    r = tools.call(gold, "station_coverage", {"place": "Jumla", "sql": "drop table rain_daily"})
    assert r["status"] == "reporting"


def test_tool_specs_match_functions():
    config = tools.bedrock_tool_config()
    names = [t["toolSpec"]["name"] for t in config["tools"]]
    assert names == list(tools.FUNCTIONS)
