"""Step 4 check: the Azure OpenAI client, a plain answer, and one tool call done by hand.

Run from the backend/ folder:
    uv run python scripts/check_llm.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.azure_openai import get_llm_client  # noqa: E402

# A pretend tool. The model only ever sees this description; the "result" below is made up by us.
STATUS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_project_status",
        "description": "Look up the current testing status of a project by its id, e.g. P06.",
        "parameters": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "Project id like P06"}},
            "required": ["project_id"],
        },
    },
}


async def main() -> None:
    client = get_llm_client()
    print(f"Deployment: {client.default_deployment}\n")

    # 1) Plain question, no tools.
    reply = await client.chat(
        messages=[{"role": "user", "content": "In one sentence: what is a test plan?"}],
        max_tokens=80,
    )
    print("1) Plain answer")
    print(f"   {reply.content}")
    print(f"   finish_reason={reply.finish_reason} tokens={reply.prompt_tokens}+{reply.completion_tokens}\n")

    # 2) Same client, but now the model may call a tool.
    messages = [
        {"role": "system", "content": "Use your tools to look up facts. Never guess a project's status."},
        {"role": "user", "content": "Is testing finished for project P06?"},
    ]
    reply = await client.chat(messages=messages, tools=[STATUS_TOOL], temperature=0)
    print("2) The model asks for a tool instead of answering")
    print(f"   content={reply.content!r} finish_reason={reply.finish_reason}")
    for call in reply.tool_calls:
        print(f"   tool_call id={call.id} name={call.name} arguments={call.arguments}")
    if not reply.tool_calls:
        print("   (no tool call this time - run again; the model chose to answer directly)")
        return

    # 3) We "run" the tool, add its result to the conversation, and ask again.
    messages.append(reply.as_assistant_message())
    for call in reply.tool_calls:
        args = json.loads(call.arguments)
        result = {"project_id": args.get("project_id"), "status": "in progress", "test_cases_passed": 41, "test_cases_total": 58}
        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    reply = await client.chat(messages=messages, tools=[STATUS_TOOL], temperature=0)
    print("\n3) After we send the tool result back")
    print(f"   {reply.content}")
    print(f"   finish_reason={reply.finish_reason} tokens={reply.prompt_tokens}+{reply.completion_tokens}")


if __name__ == "__main__":
    asyncio.run(main())