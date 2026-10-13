"""Expected values for the evaluation set, computed straight from Barsha's parquet files with DuckDB.

This deliberately does not import sodhnus.tools: if a tool reads the wrong column or filters
the wrong rows, the evaluation should disagree with it, not repeat the same mistake.
"""

from __future__ import annotations

import duckdb


class Reference:
    def __init__(self, gold_root: str = "data/barsha-gold"):
        self.con = duckdb.connect()
        for t in ("rain_daily", "monsoon_season"):
            # Table names are constants and the path is ours, not user input.
            self.con.execute(f"create view {t} as select * from read_parquet('{gold_root}/{t}/data.parquet')")  # noqa: S608

    def _one(self, sql: str, *params):
        row = self.con.execute(sql, list(params)).fetchone()
        return None if row is None else row[0]

    def headline(self, expect: dict) -> float | str | None:
        """The one value a correct answer has to contain, or None when it should contain no amount."""
        tool, status = expect.get("tool"), expect.get("status")
        if status in {"no_station_nearby", "missing", "after_data_end"}:
            return None
        if tool == "rain_on_day":
            return self._one(
                "select round(prcp_mm, 1) from rain_daily where station_id = ? and obs_date::date = ?::date "
                "and prcp_quality = 'complete'",
                expect["station"],
                expect["date"],
            )
        if tool == "wettest_days":
            year_filter = "and year(obs_date::date) = ?" if expect.get("year") else ""
            params = [expect["station"]] + ([expect["year"]] if expect.get("year") else [])
            return self._one(
                f"select round(max(prcp_mm), 1) from rain_daily where station_id = ? "  # noqa: S608
                "and prcp_quality = 'complete' "
                f"and not is_suspect {year_filter}",
                *params,
            )
        if tool == "monsoon_total":
            row = self.con.execute(
                "select total_status, jjas_total_mm, complete_days from monsoon_season "
                "where station_id = ? and year = ?",
                [expect["station"], expect["year"]],
            ).fetchone()
            if row is None:
                return None
            return round(row[1], 1) if row[0] == "published" else row[2]
        if tool == "rain_across_stations":
            return self._one(
                "select round(max(prcp_mm), 1) from rain_daily where obs_date::date = ?::date "
                "and prcp_quality = 'complete' and not is_suspect",
                expect["date"],
            )
        if tool == "station_coverage":
            return str(self._one("select max(obs_date)::date from rain_daily where station_id = ?", expect["station"]))
        return None
