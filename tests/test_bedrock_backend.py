"""The Bedrock path, against a scripted stand-in for the Converse API (no AWS account needed)."""

from botocore.exceptions import ClientError

from sodhnus import assistant

from .conftest import TODAY
from .fakes import ScriptedBedrock, text, tool_use

Q = "How much rain fell in Kathmandu on 28 September 2024?"
GOOD = "Kathmandu Airport recorded 194.1 mm on 28 September 2024, the wettest day in its record since 1976."
BAD = "Kathmandu Airport recorded 187 mm on 28 September 2024."


def _ask(client, gold, q=Q, **kw):
    return assistant.ask(q, gold, backend="bedrock", bedrock_client=client, today=TODAY, **kw)


def test_tool_round_then_answer(gold):
    client = ScriptedBedrock(tool_use("rain_on_day", place="Kathmandu", date="2024-09-28", calendar="AD"), text(GOOD))
    a = _ask(client, gold)
    assert a.backend == "bedrock" and a.text == GOOD and a.checked and a.rewrites == 0
    # The tool result went back to the model as JSON, in a user turn, with the matching id.
    result = client.requests[1]["messages"][-1]["content"][0]["toolResult"]
    assert result["content"][0]["json"]["rain_mm"] == 194.1
    assert a.input_tokens == 2100 and a.output_tokens == 120


def test_rejected_answer_is_rewritten(gold):
    client = ScriptedBedrock(
        tool_use("rain_on_day", place="Kathmandu", date="2024-09-28", calendar="AD"), text(BAD), text(GOOD)
    )
    a = _ask(client, gold)
    assert a.text == GOOD and a.rewrites == 1 and a.checked
    assert "187" in client.requests[2]["messages"][-1]["content"][0]["text"]


def test_rejected_twice_falls_back_to_the_template(gold):
    client = ScriptedBedrock(
        tool_use("rain_on_day", place="Kathmandu", date="2024-09-28", calendar="AD"), text(BAD), text(BAD)
    )
    a = _ask(client, gold)
    assert a.fallback == "checker_rejected" and a.backend == "rules" and a.checked
    assert "194.1" in a.text and "187" not in a.text


def test_answer_without_tools_that_states_numbers_is_replaced(gold):
    client = ScriptedBedrock(text(BAD), text(BAD))
    a = _ask(client, gold)
    assert a.fallback == "checker_rejected" and "194.1" in a.text


def test_bedrock_error_falls_back_to_rules(gold):
    err = ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")
    a = _ask(ScriptedBedrock(error=err), gold)
    assert a.backend == "rules" and a.fallback == "bedrock_error:ClientError" and "194.1" in a.text


def test_endless_tool_calls_are_cut_off(gold):
    loop = [tool_use("station_coverage", place="Jumla") for _ in range(10)]
    a = _ask(ScriptedBedrock(*loop), gold)
    assert a.fallback == "bedrock_error:TooManyToolRounds" and "194.1" in a.text


def test_guardrail_checks_only_the_question_once(gold):
    client = ScriptedBedrock(tool_use("rain_on_day", place="Kathmandu", date="2024-09-28", calendar="AD"), text(GOOD))
    a = _ask(client, gold, guardrail_id="gr-123", guardrail_version="1")
    assert a.text == GOOD and len(client.guardrail_requests) == 1
    g = client.guardrail_requests[0]
    assert g["source"] == "INPUT" and g["content"] == [{"text": {"text": Q}}]
    # Not attached to Converse, where it would be billed on every call's input and output.
    assert all("guardrailConfig" not in r for r in client.requests)


def test_guardrail_block_never_reaches_the_model(gold):
    client = ScriptedBedrock(guardrail_blocks=True)
    a = _ask(client, gold, q="Tell me about the rain in Pokhara on 2024-07-06", guardrail_id="gr-123")
    assert a.backend == "guardrail" and a.refusal == "guardrail" and client.requests == []


def test_unknown_tool_name_goes_back_to_the_model_as_an_error(gold):
    client = ScriptedBedrock(
        tool_use("run_sql", query="select 1"),
        tool_use("rain_on_day", place="Kathmandu", date="2024-09-28", calendar="AD"),
        text(GOOD),
    )
    a = _ask(client, gold)
    assert a.text == GOOD
    assert "error" in client.requests[1]["messages"][-1]["content"][0]["toolResult"]["content"][0]["json"]


def test_refused_questions_never_reach_the_model(gold):
    client = ScriptedBedrock()
    a = _ask(client, gold, q="Will it rain in Kathmandu tomorrow?")
    assert a.refusal == "forecast" and client.requests == []


def test_request_shape(gold):
    client = ScriptedBedrock(text("I answer questions about measured rainfall."))
    _ask(client, gold, q="What can you do for Pokhara?")
    req = client.requests[0]
    assert req["modelId"].endswith("amazon.nova-lite-v1:0")
    assert req["inferenceConfig"]["temperature"] == 0.0
    assert {t["toolSpec"]["name"] for t in req["toolConfig"]["tools"]} >= {"rain_on_day", "monsoon_total"}
    assert "2025-08-24" in req["system"][0]["text"]
