"""Where answers are logged: a JSON-lines file locally, DynamoDB on AWS. Same interface.

Logs exist to answer two questions later: which answers did the checker reject (and why), and
which answers did people mark unhelpful. Questions are redacted before they are stored.
"""

from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from pathlib import Path

from .guard import redact

RETENTION_DAYS = 30


def _entry(record: dict) -> dict:
    return {
        "question": redact(record["question"]),
        "answer": record["text"],
        "lang": record["lang"],
        "backend": record["backend"],
        "refusal": record["refusal"],
        "fallback": record["fallback"],
        "checked": record["checked"],
        "problems": record["problems"],
        "rewrites": record["rewrites"],
        "tool_calls": json.dumps(record["tool_calls"], ensure_ascii=False, default=str),
        "input_tokens": record["input_tokens"],
        "output_tokens": record["output_tokens"],
        "latency_ms": record["latency_ms"],
        "data_through": record["data_through"],
    }


class LocalLog:
    def __init__(self, path: str = "artifacts/asks.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def put(self, record: dict) -> str:
        ask_id = uuid.uuid4().hex
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": ask_id, "ts": int(time.time()), **_entry(record)}, ensure_ascii=False) + "\n")
        return ask_id

    def feedback(self, ask_id: str, helpful: bool) -> bool:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": ask_id, "feedback": helpful, "ts": int(time.time())}) + "\n")
        return True


class DynamoLog:
    def __init__(self, table_name: str, dynamodb=None):
        import boto3

        self.table = (dynamodb or boto3.resource("dynamodb")).Table(table_name)

    def put(self, record: dict) -> str:
        ask_id = uuid.uuid4().hex
        now = int(time.time())
        item = {"id": ask_id, "ts": now, "expires_at": now + RETENTION_DAYS * 86400, **_entry(record)}
        self.table.put_item(Item=json.loads(json.dumps(item, default=str), parse_float=Decimal))
        return ask_id

    def feedback(self, ask_id: str, helpful: bool) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.table.update_item(
                Key={"id": ask_id},
                UpdateExpression="SET helpful = :h",
                ConditionExpression="attribute_exists(id)",
                ExpressionAttributeValues={":h": helpful},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
