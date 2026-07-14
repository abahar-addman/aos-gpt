import json
import logging
import time

from uuid import uuid4
from starlette.responses import StreamingResponse

from open_webui.models.config import Config
from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.misc import (
    get_last_user_message,
    convert_output_to_messages,
)
from open_webui.utils.middleware import output_id, serialize_output
from open_webui.utils.langgraph.tools_adapter import execute_tool_call
from open_webui.utils.langgraph.state import AgentState
from open_webui.utils.task import get_task_model_id
from open_webui.env import LANGGRAPH_AGENT_ANALYSIS_TRUNCATION

log = logging.getLogger(__name__)


async def call_llm(state: AgentState) -> dict:
    """
    Call the LLM with current messages + tools, stream response via event_emitter,
    and extract any tool_calls from the response.
    """
    request = state["request"]
    form_data = state["form_data"]
    model_id = state["model_id"]
    tools_dict = state["tools"]
    event_emitter = state["event_emitter"]
    metadata = state["metadata"]
    output = state["output"]
    iteration = state["iteration"]

    # Emit status so the user knows what phase we're in
    if iteration > 0:
        await event_emitter(
            {
                "type": "status",
                "data": {
                    "action": "tool_calling",
                    "description": f"Generating response with tool results (pass {iteration + 1})...",
                    "done": False,
                },
            }
        )

    # Build messages: original messages + any tool call/result history from output
    if iteration > 0 and output:
        messages = [
            *form_data.get("messages", []),
            *convert_output_to_messages(output, raw=True),
        ]
    else:
        messages = form_data.get("messages", [])

    # Build the request payload with tools in OpenAI format
    tool_specs = [
        {"type": "function", "function": tool.get("spec", {})}
        for tool in tools_dict.values()
    ]

    call_form_data = {
        **form_data,
        "model": model_id,
        "stream": True,
        "messages": messages,
        "tools": tool_specs,
    }

    content = ""
    tool_calls_map = {}
    pending_tool_calls = []

    try:
        response = await generate_chat_completion(
            request,
            call_form_data,
            state["user"],
            bypass_system_prompt=(iteration > 0),
        )

        if isinstance(response, StreamingResponse):
            # Stream tokens to the client via event_emitter
            async for line in response.body_iterator:
                line = line.decode("utf-8", "replace") if isinstance(line, bytes) else line
                if not line.strip() or not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                # Handle reasoning_content (Claude extended thinking)
                reasoning_text = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or delta.get("thinking")
                )
                if reasoning_text:
                    # Find or create a reasoning output item
                    reasoning_item = None
                    for item in output:
                        if item.get("type") == "reasoning" and item.get("status") == "in_progress":
                            reasoning_item = item
                            break

                    if reasoning_item is None:
                        reasoning_item = {
                            "type": "reasoning",
                            "id": output_id("reasoning"),
                            "status": "in_progress",
                            "content": [{"type": "thinking", "thinking": ""}],
                            "summary": [{"type": "summary_text", "text": "Thinking..."}],
                            "_start_time": time.time(),
                        }
                        output.append(reasoning_item)

                    reasoning_item["content"][0]["thinking"] += reasoning_text

                    await event_emitter(
                        {
                            "type": "chat:completion",
                            "data": {
                                "content": serialize_output(output),
                                "output": output,
                            },
                        }
                    )

                # Accumulate text content
                delta_content = delta.get("content")
                if delta_content:
                    content += delta_content

                    # Close any open reasoning item
                    for item in output:
                        if item.get("type") == "reasoning" and item.get("status") == "in_progress":
                            start = item.pop("_start_time", None)
                            if start:
                                item["summary"] = [{
                                    "type": "summary_text",
                                    "text": f"Thought for {time.time() - start:.1f}s",
                                }]
                            item["status"] = "completed"

                    # Update last message item in output
                    if output and output[-1].get("type") == "message":
                        msg_item = output[-1]
                        if msg_item.get("content"):
                            msg_item["content"][-1]["text"] = content
                    else:
                        output.append(
                            {
                                "type": "message",
                                "id": output_id("msg"),
                                "status": "in_progress",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": content}],
                            }
                        )

                    await event_emitter(
                        {
                            "type": "chat:completion",
                            "data": {
                                "content": serialize_output(output),
                                "output": output,
                            },
                        }
                    )

                # Accumulate tool calls
                delta_tool_calls = delta.get("tool_calls", [])
                for tc_delta in delta_tool_calls:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.get("id", ""),
                            "function": {"name": "", "arguments": ""},
                        }
                    tc = tool_calls_map[idx]
                    if tc_delta.get("id"):
                        tc["id"] = tc_delta["id"]
                    func_delta = tc_delta.get("function", {})
                    if func_delta.get("name"):
                        tc["function"]["name"] = func_delta["name"]
                    if func_delta.get("arguments"):
                        tc["function"]["arguments"] += func_delta["arguments"]

            if response.background:
                await response.background()

        else:
            # Non-streaming response
            if hasattr(response, "body"):
                data = json.loads(response.body)
            elif isinstance(response, dict):
                data = response
            else:
                data = {}

            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "") or ""

                # Handle reasoning_content in non-streaming response
                reasoning_text = (
                    message.get("reasoning_content")
                    or message.get("reasoning")
                    or message.get("thinking")
                )
                if reasoning_text:
                    output.append({
                        "type": "reasoning",
                        "id": output_id("reasoning"),
                        "status": "completed",
                        "content": [{"type": "thinking", "thinking": reasoning_text}],
                        "summary": [{"type": "summary_text", "text": "Thinking..."}],
                    })

                for tc in message.get("tool_calls", []):
                    tool_calls_map[len(tool_calls_map)] = tc

    except Exception as e:
        log.exception(f"LangGraph call_llm error: {e}")
        content = f"Error calling LLM: {e}"

    # Convert tool_calls_map to list
    if tool_calls_map:
        pending_tool_calls = [tool_calls_map[k] for k in sorted(tool_calls_map.keys())]

    # If we got content and no tool calls, mark the message as completed
    if content and not pending_tool_calls:
        if output and output[-1].get("type") == "message":
            output[-1]["status"] = "completed"

    return {
        "output": output,
        "pending_tool_calls": pending_tool_calls,
        "final_response": content if not pending_tool_calls else state.get("final_response", ""),
    }


async def execute_tools(state: AgentState) -> dict:
    """
    Execute all pending tool calls and emit status events.
    """
    pending_tool_calls = state["pending_tool_calls"]
    tools_dict = state["tools"]
    request = state["request"]
    form_data = state["form_data"]
    metadata = state["metadata"]
    user = state["user"]
    event_emitter = state["event_emitter"]
    event_caller = state["event_caller"]
    extra_params = state["extra_params"]
    output = state["output"]
    all_sources = list(state.get("all_sources", []))

    # Append function_call items for each tool call
    for tc in pending_tool_calls:
        call_id = tc.get("id", "")
        func = tc.get("function", {})
        output.append(
            {
                "type": "function_call",
                "id": call_id or output_id("fc"),
                "call_id": call_id,
                "name": func.get("name", ""),
                "arguments": func.get("arguments", "{}"),
                "status": "in_progress",
            }
        )

    await event_emitter(
        {
            "type": "chat:completion",
            "data": {
                "content": serialize_output(output),
                "output": output,
            },
        }
    )

    tool_results = []
    for i, tool_call in enumerate(pending_tool_calls):
        tool_name = tool_call.get("function", {}).get("name", "tool")
        await event_emitter(
            {
                "type": "status",
                "data": {
                    "action": "tool_calling",
                    "description": f"Running {tool_name}" + (f" ({i + 1}/{len(pending_tool_calls)})" if len(pending_tool_calls) > 1 else "") + "...",
                    "done": False,
                },
            }
        )

        result = await execute_tool_call(
            tool_call=tool_call,
            tools_dict=tools_dict,
            request=request,
            form_data=form_data,
            metadata=metadata,
            user=user,
            event_caller=event_caller,
            extra_params=extra_params,
        )
        tool_results.append(result)

        # Collect citation sources
        if result.get("sources"):
            all_sources.extend(result["sources"])

    tool_names = [tc.get("function", {}).get("name", "tool") for tc in pending_tool_calls]
    await event_emitter(
        {
            "type": "status",
            "data": {
                "action": "tool_calling",
                "description": f"Completed {', '.join(tool_names)}",
                "done": True,
            },
        }
    )

    # Update function_call statuses to completed and append function_call_output items
    for tc in pending_tool_calls:
        call_id = tc.get("id", "")
        for item in output:
            if item.get("type") == "function_call" and item.get("call_id") == call_id:
                item["status"] = "completed"
                item["arguments"] = tc.get("function", {}).get("arguments", "{}")
                break

    for result in tool_results:
        output.append(
            {
                "type": "function_call_output",
                "id": output_id("fco"),
                "call_id": result.get("tool_call_id", ""),
                "output": [
                    {
                        "type": "input_text",
                        "text": result.get("content", ""),
                    }
                ],
                "status": "completed",
                **({"files": result["files"]} if result.get("files") else {}),
                **({"embeds": result["embeds"]} if result.get("embeds") else {}),
            }
        )

    # Append a new empty message for the next LLM response
    output.append(
        {
            "type": "message",
            "id": output_id("msg"),
            "status": "in_progress",
            "role": "assistant",
            "content": [{"type": "output_text", "text": ""}],
        }
    )

    # Emit citation sources
    for source in all_sources:
        await event_emitter({"type": "source", "data": source})

    await event_emitter(
        {
            "type": "chat:completion",
            "data": {
                "content": serialize_output(output),
                "output": output,
            },
        }
    )

    return {
        "output": output,
        "tool_results": tool_results,
        "all_sources": all_sources,
        "iteration": state["iteration"] + 1,
        "pending_tool_calls": [],
    }


async def analyze_results(state: AgentState) -> dict:
    """
    The key differentiator: sends tool results + original question to a task model
    to decide whether more tool calls are needed.
    """
    request = state["request"]
    form_data = state["form_data"]
    user = state["user"]
    event_emitter = state["event_emitter"]
    tool_results = state["tool_results"]
    iteration = state["iteration"]
    max_iterations = state["max_iterations"]

    # If we've hit the limit, stop
    if iteration >= max_iterations:
        log.debug(f"LangGraph: max iterations ({max_iterations}) reached, stopping")
        return {"needs_more_tools": False}

    # Emit a "thinking" status
    await event_emitter(
        {
            "type": "status",
            "data": {
                "description": f"Analyzing results (iteration {iteration}/{max_iterations})...",
                "done": False,
            },
        }
    )

    # Get the task model for analysis
    models = request.app.state.MODELS
    task_model_id = get_task_model_id(
        form_data["model"],
        await Config.get('task.model.default'),
        await Config.get('task.model.external'),
        models,
    )

    user_question = get_last_user_message(form_data.get("messages", []))

    # Build analysis prompt
    tool_results_summary = ""
    for r in tool_results:
        content = r.get("content", "")
        # Truncate very long results for the analysis prompt
        if len(content) > LANGGRAPH_AGENT_ANALYSIS_TRUNCATION:
            content = content[:LANGGRAPH_AGENT_ANALYSIS_TRUNCATION] + "... [truncated]"
        tool_results_summary += f"- Tool result: {content}\n"

    # Available tools for context
    tools_dict = state["tools"]
    available_tools = ", ".join(tools_dict.keys())

    analysis_prompt = f"""You are an analysis agent. Based on the user's original question and the tool results so far, decide if more tool calls are needed.

User's question: {user_question}

Tool results from this iteration:
{tool_results_summary}

Available tools: {available_tools}
Current iteration: {iteration}/{max_iterations}

Respond with a JSON object:
- "needs_more_tools": true/false - whether additional tool calls would help answer the question more completely
- "reasoning": brief explanation of your decision

If the tool results already contain sufficient information to answer the user's question comprehensively, set needs_more_tools to false.
If critical information is still missing or follow-up queries would significantly improve the answer, set needs_more_tools to true.

Respond ONLY with the JSON object, no other text."""

    analysis_payload = {
        "model": task_model_id,
        "messages": [
            {"role": "user", "content": analysis_prompt},
        ],
        "stream": False,
        "metadata": {"task": "langgraph_analysis"},
    }

    needs_more = False
    try:
        response = await generate_chat_completion(
            request, form_data=analysis_payload, user=user
        )

        content = None
        if hasattr(response, "body_iterator"):
            async for chunk in response.body_iterator:
                data = json.loads(chunk.decode("utf-8", "replace"))
                content = data["choices"][0]["message"]["content"]
            if response.background is not None:
                await response.background()
        elif isinstance(response, dict):
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        if content:
            # Parse JSON from response
            content = content.strip()
            # Extract JSON from possible markdown wrapping
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
                needs_more = result.get("needs_more_tools", False)
                reasoning = result.get("reasoning", "")
                log.debug(f"LangGraph analysis: needs_more={needs_more}, reasoning={reasoning}")

    except Exception as e:
        log.exception(f"LangGraph analyze_results error: {e}")
        needs_more = False

    # Clear thinking status
    await event_emitter(
        {
            "type": "status",
            "data": {
                "description": "Analysis complete",
                "done": True,
            },
        }
    )

    return {"needs_more_tools": needs_more}


async def prepare_response(state: AgentState) -> dict:
    """
    Assemble the final output and emit completion events.
    """
    output = state["output"]
    all_sources = state.get("all_sources", [])
    event_emitter = state["event_emitter"]

    # Mark the last message as completed
    if output and output[-1].get("type") == "message":
        output[-1]["status"] = "completed"

    # Emit final sources
    for source in all_sources:
        await event_emitter({"type": "source", "data": source})

    # Emit final completion
    await event_emitter(
        {
            "type": "chat:completion",
            "data": {
                "content": serialize_output(output),
                "output": output,
                "done": True,
            },
        }
    )

    return {
        "output": output,
        "final_response": serialize_output(output),
    }
