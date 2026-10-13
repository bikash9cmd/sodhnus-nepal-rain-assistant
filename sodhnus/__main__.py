"""Command line: python -m sodhnus <command>."""

from __future__ import annotations

import argparse
import json
import logging

from . import assistant, bedrock
from .config import Settings
from .data import load


def main(argv: list[str] | None = None) -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(prog="sodhnus", description="Rainfall questions about Nepal, answered from data")
    parser.add_argument("--gold", default=settings.gold, help="Barsha gold tables: local folder or s3://bucket/prefix")
    parser.add_argument("--backend", default=settings.backend, choices=["rules", "bedrock"])
    sub = parser.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    ask.add_argument("--debug", action="store_true", help="also print tool calls, tool results and checks")

    sub.add_parser("serve", help="HTTP API on :8000")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("sodhnus.api:app", host="127.0.0.1", port=8000)
        return

    gold = load(args.gold)
    client = bedrock.client(settings.region) if args.backend == "bedrock" else None
    a = assistant.ask(
        args.question,
        gold,
        backend=args.backend,
        bedrock_client=client,
        model_id=settings.model_id,
        guardrail_id=settings.guardrail_id,
        guardrail_version=settings.guardrail_version,
    )
    print(a.text)
    if args.debug:
        print()
        print(
            json.dumps(
                {k: v for k, v in a.record().items() if k not in {"text", "question"}},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


if __name__ == "__main__":
    main()
