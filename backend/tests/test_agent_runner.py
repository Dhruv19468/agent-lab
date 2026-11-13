"""The agent loop, driven by a fake model."""

from __future__ import annotations

from pathlib import Path

from app.runtime.agent_runner import AgentToolSpec, run_agent, tool_specs
from app.runtime.tools.registry import BUILTIN_TOOLS
from tests.fakes import FakeLLM, reply

TOOLS = [
    AgentToolSpec(name=t.name, description=t.description, parameters=t.parameters)
    for t in BUILTIN_TOOLS.values()
]


async def run(llm: FakeLLM, data_root: Path, **options):
    return await run_agent(
        llm=llm, system_message="SYSTEM", user_message="Plan P06", tools=TOOLS, data_root=data_root, **options
    )


def test_tool_specs_skip_tools_without_code() -> None:
    specs = tool_specs(
        [*TOOLS, AgentToolSpec(name="send_email", description="x", parameters={"type": "object"})]
    )
    assert [spec["function"]["name"] for spec in specs] == list(BUILTIN_TOOLS)


async def test_tool_round_then_answer(data_root: Path) -> None:
    llm = FakeLLM(
        [
            reply(
                calls=[
                    ("list_files", '{"folder": "raw/validation/P06"}'),
                    ("view_image", '{"path": "raw/validation/P06/P06_Demo_Architecture.png"}'),
                ]
            ),
            reply(content="# Master Test Plan", tokens=(300, 50)),
        ]
    )
    outcome = await run(llm, data_root)

    assert outcome.status == "completed" and outcome.answer == "# Master Test Plan"
    assert outcome.tool_rounds == 1
    assert (outcome.prompt_tokens, outcome.completion_tokens) == (400, 60)
    assert [call["name"] for call in outcome.tool_calls] == ["list_files", "view_image"]
    assert all(call["ok"] for call in outcome.tool_calls)

    # second request: system, user, assistant(tool_calls), tool, tool, user(image)
    roles = [message["role"] for message in llm.requests[1]["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "tool", "user"]
    image_message = llm.requests[1]["messages"][-1]["content"]
    assert image_message[1]["image_url"]["url"].startswith("data:image/png;base64,")
    # the big data URL never goes into a tool message or the run log
    assert "_image_data_url" not in llm.requests[1]["messages"][4]["content"]
    assert "base64" not in str(outcome.tool_calls)


async def test_tool_error_goes_back_to_the_model(data_root: Path) -> None:
    llm = FakeLLM(
        [reply(calls=[("read_file", '{"path": "gold/validation/P06/gold_testplan.json"}')]), reply("done")]
    )
    outcome = await run(llm, data_root)

    assert outcome.status == "completed"
    assert outcome.tool_calls[0]["ok"] is False
    tool_message = llm.requests[1]["messages"][3]
    assert tool_message["role"] == "tool" and "answer keys" in tool_message["content"]


async def test_cut_off_answer_fails(data_root: Path) -> None:
    outcome = await run(FakeLLM([reply("# Plan, half", finish_reason="length")]), data_root)
    assert outcome.status == "failed" and "max_tokens" in (outcome.error or "")
    assert outcome.answer == "# Plan, half"  # kept, so you can see how far it got


async def test_last_round_offers_no_tools(data_root: Path) -> None:
    def script(request):
        if request.get("tools"):
            return reply(calls=[("list_files", "{}")])
        return reply("forced answer")

    llm = FakeLLM(script)
    outcome = await run(llm, data_root, max_tool_rounds=2)
    assert outcome.status == "completed" and outcome.answer == "forced answer"
    assert outcome.tool_rounds == 2
    assert [bool(request.get("tools")) for request in llm.requests] == [True, True, False]


async def test_settings_are_passed_to_the_model(data_root: Path) -> None:
    llm = FakeLLM([reply("ok")])
    await run(llm, data_root, deployment="gpt-x", temperature=0.2, max_tokens=999)
    request = llm.requests[0]
    assert (request["deployment"], request["temperature"], request["max_tokens"]) == ("gpt-x", 0.2, 999)
