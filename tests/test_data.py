import shutil

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from sodhnus.data import GoldCache, load

from .conftest import GOLD


def test_schema_change_upstream_fails_loudly(tmp_path):
    shutil.copytree(GOLD, tmp_path / "gold")
    path = tmp_path / "gold" / "rain_daily" / "data.parquet"
    pd.read_parquet(path).rename(columns={"prcp_quality": "quality"}).to_parquet(path)
    with pytest.raises(ValueError, match="prcp_quality"):
        load(str(tmp_path / "gold"))


def test_cache_reloads_when_barsha_republishes(tmp_path):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="lake")
        for t in ("rain_daily", "monsoon_season", "station_dim"):
            s3.upload_file(f"{GOLD}/{t}/data.parquet", "lake", f"gold/{t}/data.parquet")
        cache = GoldCache("s3://lake/gold", check_every=0, s3=s3)
        first = cache.get()
        assert cache.get() is first  # same ETags: no reload

        rd = pd.read_parquet(f"{GOLD}/rain_daily/data.parquet")
        rd = rd[pd.to_datetime(rd["obs_date"]) < "2025-01-01"]
        rd.to_parquet(tmp_path / "rd.parquet")
        s3.upload_file(str(tmp_path / "rd.parquet"), "lake", "gold/rain_daily/data.parquet")
        second = cache.get()
        assert second is not first and second.latest_day.isoformat() == "2024-12-31"


def test_cache_keeps_serving_when_the_version_check_fails():
    cache = GoldCache(GOLD, check_every=0)
    first = cache.get()
    cache.root = "/does/not/exist"
    assert cache.get() is first
