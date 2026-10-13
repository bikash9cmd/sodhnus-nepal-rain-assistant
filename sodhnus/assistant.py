"""One question in, one checked answer out.

    question -> guard -> backend (Bedrock or rules) -> checker -> answer
                                      |  rejected twice, or Bedrock down
                                      v
                           template answer from the tool results

Every path ends in an answer the checker has passed, or a refusal.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from . import answer, config, router, tools
from .bedrock import BedrockSession, TooManyToolRounds, apply_guardrail
from .checker import check_answer
from .data import Gold
from .guard import check_question
from .prompts import rewrite_request, system_prompt

log = logging.getLogger(__name__)


@dataclass
class Answer:
    question: str
    text: str
    lang: str
    backend: str  # bedrock | rules | refusal | guardrail
    data_through: str
    tool_calls: list = field(default_factory=list)
    tool_results: list = field(default_factory=list)
    checked: bool = False
    problems: list = field(default_factory=list)
    rewrites: int = 0
    fallback: str | None = None  # why the template answer was used instead of the model's
    refusal: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    def public(self) -> dict:
        """What the API returns: the answer and where it came from, not the internals."""
        return {
            "answer": self.text,
            "lang": self.lang,
            "data_through": self.data_through,
            "sources": sorted({r.get("station") for r in self.tool_results if r.get("station")}),
            "source_note": "NOAA Global Surface Summary of the Day, cleaned and quality-flagged by Barsha.",
            "refused": self.refusal,
        }

    def record(self) -> dict:
        return asdict(self)


def _rules(question: str, gold: Gold, lang: str, today: date | None) -> tuple[str, list, list]:
    p = router.plan(question, today=today)
    results = [tools.call(gold, name, args) for name, args in p.calls]
    text = answer.compose(results, lang)
    if p.unknown_place:
        text = answer.refusal("unknown_place", lang) + " " + text
    return text, p.calls, results


def ask(
    question: str,
    gold: Gold,
    backend: str = "rules",
    bedrock_client=None,
    model_id: str = config.MODEL_ID,
    guardrail_id: str | None = None,
    guardrail_version: str | None = None,
    today: date | None = None,
) -> Answer:
    start = time.perf_counter()
    lang = router.detect_language(question or "")
    out = Answer(question=question, text="", lang=lang, backend=backend, data_through=gold.latest_day.isoformat())

    verdict = check_question(question)
    if not verdict.ok:
        out.text, out.backend, out.refusal, out.checked = (
            answer.refusal(verdict.reason, lang),
            "refusal",
            verdict.reason,
            True,
        )
        out.latency_ms = round(1000 * (time.perf_counter() - start))
        return out

    if backend == "bedrock":
        try:
            _ask_bedrock(out, question, gold, bedrock_client, model_id, guardrail_id, guardrail_version, today)
        except (TooManyToolRounds, Exception) as e:  # noqa: BLE001 - any model failure falls back to rules
            log.warning("bedrock failed (%s); answering with rules", type(e).__name__)
            out.fallback = f"bedrock_error:{type(e).__name__}"
            out.backend = "rules"
            out.text, out.tool_calls, out.tool_results = _rules(question, gold, lang, today)
    else:
        out.text, out.tool_calls, out.tool_results = _rules(question, gold, lang, today)

    if out.backend == "guardrail":
        out.checked = True
        out.latency_ms = round(1000 * (time.perf_counter() - start))
        return out
    if not out.tool_calls and out.backend == "rules":
        # Nothing to answer from: a fixed help text, which needs no checking.
        out.text, out.backend, out.refusal, out.checked = answer.refusal("unclear", lang), "refusal", "unclear", True
        out.latency_ms = round(1000 * (time.perf_counter() - start))
        return out
    final = check_answer(out.text, out.tool_results, question)
    out.checked, out.problems = final.ok, out.problems or final.problems
    if not final.ok:
        # Templates are built from tool fields and should always pass; if one doesn't, say nothing
        # rather than something unchecked.
        log.error("answer failed the checker after all fallbacks: %s", final.problems)
        out.text, out.refusal = answer.refusal("unclear", lang), "unchecked"
    out.latency_ms = round(1000 * (time.perf_counter() - start))
    return out


def _ask_bedrock(out: Answer, question: str, gold: Gold, client, model_id, guardrail_id, guardrail_version, today):
    if guardrail_id:
        blocked = apply_guardrail(client, guardrail_id, guardrail_version or "DRAFT", question)
        if blocked:
            out.backend, out.refusal, out.text = "guardrail", "guardrail", blocked
            return
    session = BedrockSession(
        client=client, gold=gold, system=system_prompt(gold.first_day, gold.latest_day, today), model_id=model_id
    )
    turn = session.say(question)
    rewrites = 0
    while True:
        result = check_answer(turn.text, session.tool_results, question)
        if result.ok:
            break
        out.problems = result.problems
        if rewrites >= config.MAX_REWRITES:
            # The model had its chance. The tool results it fetched are correct, so answer from them.
            out.fallback = "checker_rejected"
            break
        rewrites += 1
        turn = session.say(rewrite_request(result.feedback()))
    out.rewrites = rewrites
    out.tool_calls, out.tool_results = session.tool_calls, session.tool_results
    out.input_tokens, out.output_tokens = session.usage.input_tokens, session.usage.output_tokens
    if out.fallback == "checker_rejected":
        out.backend = "rules"
        if session.tool_results:
            out.text = answer.compose(session.tool_results, out.lang)
        else:
            out.text, out.tool_calls, out.tool_results = _rules(question, gold, out.lang, today)
    else:
        out.text = turn.text
