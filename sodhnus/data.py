"""Barsha's gold tables, read-only. Locally from data/barsha-gold, on AWS from the Barsha lake bucket.

Sodhnus never writes to these tables and never computes a rainfall statistic Barsha didn't
publish, except ranks and medians over Barsha's own published values.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .config import TABLES

log = logging.getLogger(__name__)


@dataclass
class Gold:
    rain_daily: pd.DataFrame
    monsoon_season: pd.DataFrame
    station_dim: pd.DataFrame
    version: str  # where it came from and when, for logs and the /health route

    @property
    def latest_day(self) -> date:
        return self.rain_daily["obs_date"].max()

    @property
    def first_day(self) -> date:
        return self.rain_daily["obs_date"].min()


def _read_local(root: str, table: str) -> tuple[pd.DataFrame, str]:
    path = Path(root) / table / "data.parquet"
    return pd.read_parquet(path), f"{path.stat().st_mtime_ns}"


def _read_s3(root: str, table: str, s3=None) -> tuple[pd.DataFrame, str]:
    import boto3

    s3 = s3 or boto3.client("s3")
    bucket, _, prefix = root.removeprefix("s3://").partition("/")
    key = f"{prefix.rstrip('/')}/{table}/data.parquet".lstrip("/")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read())), obj["ETag"].strip('"')


def _normalise(table: str, df: pd.DataFrame) -> pd.DataFrame:
    if "obs_date" in df:
        df["obs_date"] = pd.to_datetime(df["obs_date"]).dt.date
    for col in ("valid_from", "valid_to"):
        if col in df:
            df[col] = pd.to_datetime(df[col]).dt.date
    if table == "rain_daily":
        df = df.sort_values(["station_id", "obs_date"]).reset_index(drop=True)
    return df


def load(root: str, s3=None) -> Gold:
    frames, versions = {}, []
    for table in TABLES:
        reader = _read_s3 if root.startswith("s3://") else _read_local
        df, version = reader(root, table, s3) if reader is _read_s3 else reader(root, table)
        frames[table] = _normalise(table, df)
        versions.append(version)
    missing = {"station_id", "obs_date", "prcp_mm", "prcp_quality", "alert_level"} - set(frames["rain_daily"])
    if missing:
        # Barsha's schema changed under us. Refusing to start beats answering from the wrong column.
        raise ValueError(f"rain_daily is missing columns {sorted(missing)}")
    return Gold(**frames, version="|".join(versions))


class GoldCache:
    """Keeps the tables in memory across warm Lambda invocations and reloads when Barsha republishes.

    The ETag check is one HEAD request, made at most every `check_every` seconds.
    """

    def __init__(self, root: str, check_every: float = 900, s3=None):
        self.root, self.check_every, self.s3 = root, check_every, s3
        self._gold: Gold | None = None
        self._checked = 0.0

    def _remote_version(self) -> str:
        if not self.root.startswith("s3://"):
            return "|".join(_read_local(self.root, t)[1] for t in TABLES)
        import boto3

        s3 = self.s3 or boto3.client("s3")
        bucket, _, prefix = self.root.removeprefix("s3://").partition("/")
        tags = []
        for t in TABLES:
            key = f"{prefix.rstrip('/')}/{t}/data.parquet".lstrip("/")
            tags.append(s3.head_object(Bucket=bucket, Key=key)["ETag"].strip('"'))
        return "|".join(tags)

    def get(self) -> Gold:
        now = time.monotonic()
        if self._gold is None:
            self._gold, self._checked = load(self.root, self.s3), now
        elif now - self._checked > self.check_every:
            self._checked = now
            try:
                if self._remote_version() != self._gold.version:
                    log.info("gold tables changed upstream; reloading")
                    self._gold = load(self.root, self.s3)
            except Exception:
                # Serving yesterday's tables is better than failing; the freshness check in every
                # answer still tells people how old the newest day is.
                log.exception("could not check gold version; keeping the loaded tables")
        return self._gold
