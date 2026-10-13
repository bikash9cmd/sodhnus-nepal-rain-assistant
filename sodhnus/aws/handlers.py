"""Lambda entry point for API Gateway (HTTP API, payload v2). Routes: POST /ask, POST /feedback, GET /health.

Everything slow happens once per container: loading the gold tables from Barsha's bucket,
creating the Bedrock client. Metrics go to CloudWatch as embedded metric format log lines.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime

from .. import assistant, bedrock
from ..config import MAX_QUESTION_CHARS, Settings
from ..data import GoldCache

log = logging.getLogger()
log.setLevel(logging.INFO)

_settings: Settings | None = None
_cache: GoldCache | None = None
_client = None
_store = None


def _init():
    global _settings, _cache, _client, _store
    if _settings is None:
        from ..store import DynamoLog

        _settings = Settings.from_env()
        _cache = GoldCache(_settings.gold)
        _client = bedrock.client(_settings.region) if _settings.backend == "bedrock" else None
        _store = DynamoLog(_settings.log_table) if _settings.log_table else None
    return _settings, _cache, _client, _store


def _metrics(a: assistant.Answer) -> None:
    """One EMF line per answer. The alarms in infra/template.yaml read these.

    No dimensions on purpose: every metric-dimension pair is a billed custom metric ($0.30/month),
    and splitting seven metrics by backend made monitoring cost more than the model (docs/COST.md).
    Per-backend breakdowns come from Logs Insights over these same lines, at query time.
    """
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "Sodhnus",
                            "Dimensions": [[]],
                            "Metrics": [
                                {"Name": n, "Unit": u}
                                for n, u in [
                                    ("Answers", "Count"),
                                    ("Refusals", "Count"),
                                    ("CheckerRejected", "Count"),
                                    ("Fallbacks", "Count"),
                                    ("InputTokens", "Count"),
                                    ("LatencyMs", "Milliseconds"),
                                ]
                            ],
                        }
                    ],
                },
                "Answers": 1,
                "Refusals": int(a.refusal is not None),
                "CheckerRejected": int(bool(a.problems)),
                "Fallbacks": int(a.fallback is not None),
                "InputTokens": a.input_tokens,
                "LatencyMs": a.latency_ms,
                # Not metrics, but searchable in Logs Insights.
                "Backend": a.backend,
                "OutputTokens": a.output_tokens,
                "Lang": a.lang,
                "Refusal": a.refusal,
                "Fallback": a.fallback,
            }
        )
    )


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def api(event, context):
    settings, cache, client, store = _init()
    route = event.get("routeKey", "")
    if route == "GET /health":
        gold = cache.get()
        age = (datetime.now(UTC).date() - gold.latest_day).days
        return _response(
            200,
            {
                "ok": True,
                "backend": settings.backend,
                "data_through": gold.latest_day.isoformat(),
                "data_age_days": age,
                "model": settings.model_id,
            },
        )
    if route == "POST /feedback":
        body = _body(event)
        if not isinstance(body.get("id"), str) or not isinstance(body.get("helpful"), bool):
            return _response(400, {"error": "need id (string) and helpful (true/false)"})
        found = store.feedback(body["id"], body["helpful"]) if store else False
        return _response(200 if found else 404, {"ok": found})
    if route == "POST /ask":
        body = _body(event)
        question = body.get("question")
        if not isinstance(question, str) or len(question) > 2 * MAX_QUESTION_CHARS:
            return _response(400, {"error": "need a question (string)"})
        a = assistant.ask(
            question,
            cache.get(),
            backend=settings.backend,
            bedrock_client=client,
            model_id=settings.model_id,
            guardrail_id=settings.guardrail_id,
            guardrail_version=settings.guardrail_version,
        )
        _metrics(a)
        ask_id = store.put(a.record()) if store else None
        return _response(200, {"id": ask_id, **a.public()})
    return _response(404, {"error": f"no route {route}"})


if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    logging.basicConfig(level=logging.INFO)
