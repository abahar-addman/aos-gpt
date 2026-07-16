"""
Claude-powered Tool Builder.

Backs the assistant sidebar in the Tools workspace editor: streams tool-code
suggestions from the Anthropic API and validates generated code, surfacing the
real compile error (the tools CRUD path masks it — see constants.ERROR_MESSAGES).

Uses the Anthropic SDK directly (anthropic==0.86.0, already pinned). Newer request
fields (adaptive thinking) are passed via `extra_body` so this is robust to the
installed SDK's typed-parameter surface; the model id is just a string the API accepts.
"""

from __future__ import annotations

import ast
import json
import logging
import types
from typing import AsyncGenerator, Optional

from open_webui.utils.plugin import replace_imports
from open_webui.utils.tools import get_tool_specs

log = logging.getLogger(__name__)


TOOL_BUILDER_SYSTEM_PROMPT = """You are the Tool Builder, an expert assistant embedded in the Open WebUI Tools editor. You collaboratively help the user design and write a single Open WebUI **tool** in Python, which downstream AI agents will call.

## What a valid Open WebUI tool looks like
- The file MAY begin with a triple-double-quoted frontmatter docstring as its VERY FIRST line, e.g.:
  \"\"\"
  title: My Tool
  author: ...
  version: 0.1.0
  required_open_webui_version: 0.5.0
  requirements:
  \"\"\"
  Only add `requirements:` (comma-separated pip packages) if the user confirms their deployment allows package installation; otherwise rely on the Python standard library and packages already installed.
- It MUST define a top-level class named exactly `Tools`.
- `Tools()` must be constructible with no required arguments (an `__init__(self)` is fine).
- Each PUBLIC method (name not starting with `_`) becomes one callable tool function. Every public method MUST have:
  - complete type hints on all parameters and the return type, and
  - a reStructuredText docstring: a summary line, then `:param name: description` for each user-facing parameter.
- Reserved parameters injected at runtime — include them ONLY if needed, and do NOT document them: `__user__: dict`, `__request__`, `__event_emitter__`, `__id__`, `__metadata__`. They are stripped from the public schema.
- Optional nested `Valves` (admin config) and `UserValves` (per-user config) Pydantic classes are supported.

## Rules
- When you propose or update the tool, ALWAYS output the COMPLETE, ready-to-save file inside a single ```python fenced code block (never a partial snippet or a diff) — the user applies it as a whole-file replacement.
- Keep prose brief and outside the code block. Put a one or two sentence explanation before the block.
- Prefer the Python standard library. Avoid the substrings `from utils`, `from apps`, `from main`, `from config` outside of real imports — the loader rewrites them by naive string replacement.
- Write clear, correct, minimal code. Do not add features, abstractions, or error handling beyond what the task needs.
- If the user's request is ambiguous in a way that changes the tool's behavior, ask a brief clarifying question instead of guessing.
"""


def build_system_prompt(tool: Optional[dict]) -> str:
    """Compose the system prompt with the current tool context so Claude edits in place."""
    system = TOOL_BUILDER_SYSTEM_PROMPT
    tool = tool or {}
    tool_id = (tool.get("id") or "").strip()
    name = (tool.get("name") or "").strip()
    description = (tool.get("description") or "").strip()
    content = tool.get("content") or ""

    context_lines = ["\n\n## Current tool being edited"]
    context_lines.append(f"- id: {tool_id or '(not set yet — a new tool)'}")
    context_lines.append(f"- name: {name or '(not set yet)'}")
    context_lines.append(f"- description: {description or '(not set yet)'}")
    if content.strip():
        context_lines.append(
            "\nThe editor currently contains this code — modify it in place unless the user asks to start over:\n"
            f"```python\n{content}\n```"
        )
    else:
        context_lines.append("\nThe editor is currently empty. Start a new tool from scratch.")
    return system + "\n".join(context_lines)


def _sse(text: str) -> str:
    """Encode a text delta as an Open WebUI SSE chunk the frontend stream parser understands."""
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n"


async def stream_tool_builder(
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """Stream Claude's response as Open WebUI SSE chunks (`data: {choices:[{delta:{content}}]}`)."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)

        current_block_type = None
        async with client.messages.stream(
            model=model,
            max_tokens=64000,
            system=system,
            messages=messages,
            # Pass adaptive thinking via extra_body for SDK-version robustness.
            extra_body={"thinking": {"type": "adaptive", "display": "summarized"}},
        ) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_start":
                    current_block_type = getattr(event.content_block, "type", None)
                    if current_block_type == "thinking":
                        yield _sse('<details type="reasoning">\n<summary>Thinking</summary>\n')
                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", None)
                    if dtype == "thinking_delta":
                        yield _sse(getattr(delta, "thinking", "") or "")
                    elif dtype == "text_delta":
                        yield _sse(getattr(delta, "text", "") or "")
                elif etype == "content_block_stop":
                    if current_block_type == "thinking":
                        yield _sse("\n</details>\n\n")
                    current_block_type = None
        yield "data: [DONE]\n\n"
    except Exception as e:  # noqa: BLE001 — surface a real message to the client stream
        log.exception("Tool builder stream failed")
        yield "data: " + json.dumps({"error": {"detail": str(e)}}) + "\n\n"


async def validate_tool_code(content: str) -> dict:
    """Compile-check generated tool code and return the REAL error.

    Mirrors the loader chain used at save time (replace_imports -> exec -> Tools class
    -> get_tool_specs) but returns the true SyntaxError / ImportError / message instead
    of the masked '[ERROR: ...]' the CRUD endpoints return. Executes the code (arbitrary
    code execution, same as saving) but does NOT pip-install frontmatter requirements.
    """
    content = replace_imports(content or "")

    # 1) Syntax
    try:
        ast.parse(content)
    except SyntaxError as e:
        return {"ok": False, "stage": "syntax", "error": f"Line {e.lineno}: {e.msg}"}

    # 2) Compile / execute
    module = types.ModuleType("tool___tool_builder_validate__")
    try:
        exec(content, module.__dict__)  # noqa: S102 — intentional; same as save-time validation
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "compile", "error": str(e)}

    # 3) Structure
    if not hasattr(module, "Tools"):
        return {"ok": False, "stage": "structure", "error": "No Tools class found in the module"}
    try:
        instance = module.Tools()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "compile", "error": f"Tools() failed to instantiate: {e}"}

    # 4) Function specs (the shape downstream agents consume)
    try:
        specs = get_tool_specs(instance)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "specs", "error": str(e)}

    functions = [s.get("name") for s in (specs or []) if isinstance(s, dict) and s.get("name")]
    return {"ok": True, "functions": functions, "specs": specs}
