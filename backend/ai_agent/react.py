from __future__ import annotations

import json
import re
from typing import Any

from backend.ai_agent.working_memory import WorkingMemory
from backend.llm.contracts import Reply, make_tool_specs
from backend.llm.router import LLMRouter
from backend.tools.base import ToolProtocol


def build_system_prompt(memory: WorkingMemory, tools: list[ToolProtocol]) -> str:
    tool_names = ", ".join(t.name for t in tools)
    plan_str = "\n".join(f"  {s.id} [{s.status.value}]: {s.desc}" for s in memory.plan)
    findings_str = "\n".join(f"  {k}: {f.value}" for k, f in memory.findings.items()) or "  (none)"
    recent = memory.executed[-4:] if len(memory.executed) > 4 else memory.executed
    history_str = (
        "\n".join(
            (
                f"  Step {r.step_ix}: tool={r.tool}"
                f" args={json.dumps(r.args)}"
                f" result_ok={r.eval_result.get('success')}"
            )
            for r in recent
        )
        or "  (none)"
    )
    return (
        f"You are a self-correcting coding agent using the ReAct pattern.\n\n"
        f"Goal: {memory.goal.spec if memory.goal else 'N/A'}\n\n"
        f"Acceptance criteria:\n"
        + "\n".join(f"  - {a}" for a in (memory.goal.acceptance if memory.goal else []))
        + "\n\n"
        f"Plan:\n{plan_str}\n\n"
        f"Findings so far:\n{findings_str}\n\n"
        f"Recent steps:\n{history_str}\n\n"
        f"Available tools: {tool_names}\n\n"
        f"For each step, you MUST:\n"
        f"1. THINK: Explain your reasoning about what to do next and why.\n"
        f"2. ACT: Call exactly one tool to execute your action.\n\n"
        f"CRITICAL: If you are generating or editing code, you MUST use the write_file tool to save it to the workspace. DO NOT output the raw code directly in your thought message!\n"
        f"IMPORTANT: You must use the provided tool calling API to perform your action. Do NOT output a JSON block for the action. Just write your thoughts and then call a tool!\n"
        f"If you cannot determine the right action, use read_file to explore first.\n"
    )

def _parse_reply(reply: Reply) -> Reply:
    if reply.action is not None:
        return reply
    raw_text = (reply.thought or "").strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    try:
        parsed = json.loads(raw_text.strip())
        return Reply(
            thought=parsed.get("thought", reply.thought),
            action=parsed.get("action"),
            finish_reason=reply.finish_reason,
            usage=reply.usage,
        )
    except (json.JSONDecodeError, TypeError):
        match = re.search(r'\{.*\}', reply.thought or "", re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return Reply(
                    thought=parsed.get("thought", reply.thought),
                    action=parsed.get("action"),
                    finish_reason=reply.finish_reason,
                    usage=reply.usage,
                )
            except (json.JSONDecodeError, TypeError):
                pass
    return reply


def react_step(
    memory: WorkingMemory,
    router: LLMRouter,
    tools: list[ToolProtocol],
    stream_callback: Any = None,
) -> Reply:
    system_prompt = build_system_prompt(memory, tools)
    tool_specs = make_tool_specs(tools)
    user_msg = (
        f"Active subtask: {memory.active_subtask.desc if memory.active_subtask else 'None'}\n"
        f"Decide the next action."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    
    reply = router.chat(messages, tools=tool_specs, stream_callback=stream_callback)
    reply = _parse_reply(reply)
    
    if reply.action is None:
        raw_output = (reply.thought or "").strip()
        retry_msg = (
            "You did NOT provide a valid tool call. You MUST choose exactly one tool "
            f"from [{', '.join(t.name for t in tools)}] and call it using the tool calling API.\n"
            "Your previous output could not be parsed into an action. Here it is so you can fix it:\n"
            f"---\n{raw_output}\n---"
        )
        messages.append({"role": "assistant", "content": reply.thought or ""})
        messages.append({"role": "user", "content": retry_msg})
        reply = router.chat(messages, tools=tool_specs, stream_callback=stream_callback)
        reply = _parse_reply(reply)
        
    return reply
