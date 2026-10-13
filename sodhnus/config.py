"""Constants and environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Barsha's gold tables. Locally a snapshot in data/barsha-gold; on AWS the Barsha lake bucket.
# Both use Barsha's layout: <root>/<table>/data.parquet
DEFAULT_GOLD = "data/barsha-gold"
TABLES = ("rain_daily", "monsoon_season", "station_dim")

# A question longer than this is not a rainfall question; it is usually a pasted document or an attack.
MAX_QUESTION_CHARS = 400

# Bedrock. Amazon Nova Lite through the APAC cross-region profile, served from Mumbai (closest to Nepal).
BEDROCK_REGION = "ap-south-1"
MODEL_ID = "apac.amazon.nova-lite-v1:0"
MAX_TOOL_ROUNDS = 4
MAX_OUTPUT_TOKENS = 500
# One rewrite is allowed when the checker rejects an answer; after that the template answer is used.
MAX_REWRITES = 1

# A station that has not reported for this many days (relative to the newest day in the data) is "silent".
SILENT_AFTER_DAYS = 3

# Where people should go for what Sodhnus refuses to do.
FORECAST_SOURCE_EN = (
    "Department of Hydrology and Meteorology forecasts (mfd.gov.np) and flood warnings (hydrology.gov.np)"
)
FORECAST_SOURCE_NE = "जल तथा मौसम विज्ञान विभागको पूर्वानुमान (mfd.gov.np) र बाढी पूर्वसूचना (hydrology.gov.np)"


@dataclass(frozen=True)
class Settings:
    gold: str
    backend: str
    model_id: str
    region: str
    guardrail_id: str | None
    guardrail_version: str | None
    log_table: str | None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            gold=os.environ.get("SODHNUS_GOLD", DEFAULT_GOLD),
            backend=os.environ.get("SODHNUS_BACKEND", "rules"),
            model_id=os.environ.get("SODHNUS_MODEL_ID", MODEL_ID),
            region=os.environ.get("SODHNUS_BEDROCK_REGION", BEDROCK_REGION),
            guardrail_id=os.environ.get("SODHNUS_GUARDRAIL_ID") or None,
            guardrail_version=os.environ.get("SODHNUS_GUARDRAIL_VERSION") or None,
            log_table=os.environ.get("SODHNUS_LOG_TABLE") or None,
        )
