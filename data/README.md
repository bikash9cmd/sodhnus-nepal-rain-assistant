# Data

`barsha-gold/` is a snapshot of three gold tables from my [Barsha](https://github.com/bikash9cmd/barsha-nepal-monsoon-lakehouse) rainfall lakehouse, in Barsha's own layout (`<table>/data.parquet`), so Sodhnus runs and its tests pass without an AWS account.

| Table | Rows | What Sodhnus uses it for |
|---|---:|---|
| `rain_daily` | 67,215 | One row per station-day: rainfall, quality (complete / partial / missing), category, alert level, the station's thresholds from earlier years, record and suspect flags |
| `monsoon_season` | 337 | June-September totals per station and year, published only when 90% of days are complete |
| `station_dim` | 17 | Station names and positions (type 2: Bhairahawa moved in 2025) |

**Lineage.** NOAA Global Surface Summary of the Day for Nepal's 16 synoptic stations, read from the AWS Open Data bucket `s3://noaa-gsod-pds`, cleaned and quality-flagged by Barsha (`make backfill`, as of 2025-08-26). The newest day in the snapshot is **2025-08-24**: the public feed had not published a later day when the snapshot was built, and every answer says how far the data goes.

**On AWS** Sodhnus reads the same three files from Barsha's lake bucket (`SODHNUS_GOLD=s3://<bucket>/gold`) and reloads them when their ETags change, so it is always as fresh as Barsha.

**Refreshing the snapshot**: run Barsha's `make backfill`, then copy `lake/gold/{rain_daily,monsoon_season,station_dim}/data.parquet` here. `make eval` will show if anything in the answers moved.
