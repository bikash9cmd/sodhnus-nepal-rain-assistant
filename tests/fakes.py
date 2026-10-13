"""A stand-in for the bedrock-runtime client: replays scripted Converse responses.

It records every request, so tests can check what was sent (tool results, the rewrite request,
the guardrail config) as well as what came back.
"""

from __future__ import annotations

import copy
import itertools

_ids = itertools.count(1)


def tool_use(name: str, **args) -> dict:
    return {
        "stopReason": "tool_use",
        "usage": {"inputTokens": 900, "outputTokens": 40},
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": f"t{next(_ids)}", "name": name, "input": args}}],
            }
        },
    }


def text(answer: str, stop: str = "end_turn") -> dict:
    return {
        "stopReason": stop,
        "usage": {"inputTokens": 1200, "outputTokens": 80},
        "output": {"message": {"role": "assistant", "content": [{"text": answer}]}},
    }


class ScriptedBedrock:
    def __init__(self, *responses, error: Exception | None = None, guardrail_blocks: bool = False):
        self.responses = list(responses)
        self.error = error
        self.guardrail_blocks = guardrail_blocks
        self.requests: list[dict] = []
        self.guardrail_requests: list[dict] = []

    def apply_guardrail(self, **request):
        self.guardrail_requests.append(request)
        if self.guardrail_blocks:
            return {"action": "GUARDRAIL_INTERVENED", "outputs": [{"text": "Sorry, I can't help with that."}]}
        return {"action": "NONE", "outputs": []}

    def converse(self, **request):
        # Deep copy: the session keeps appending to the same messages list.
        self.requests.append(copy.deepcopy(request))
        if self.error:
            raise self.error
        if not self.responses:
            raise AssertionError("the assistant made more Converse calls than the script has")
        return self.responses.pop(0)
