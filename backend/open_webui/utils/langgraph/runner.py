import logging

from open_webui.env import (
    LANGGRAPH_AGENT_MAX_ITERATIONS,
    LANGGRAPH_AGENT_THINKING_DEPTH,
)
from open_webui.utils.langgraph.graph import build_agent_graph
from open_webui.utils.langgraph.state import AgentState
from open_webui.utils.middleware import output_id

log = logging.getLogger(__name__)


async def run_langgraph_agent(
    request,
    form_data: dict,
    tools_dict: dict,
    extra_params: dict,
    user,
    metadata: dict,
    model_id: str,
    event_emitter,
    event_caller,
    max_iterations: int | None = None,
    thinking_depth: int | None = None,
) -> dict:
    """
    Entry point for the LangGraph agent execution mode.

    Returns a dict with:
        - output: list of OR-aligned output items
        - sources: list of citation sources
        - content: serialized content string
        - done: True
    """
    if max_iterations is None:
        max_iterations = LANGGRAPH_AGENT_MAX_ITERATIONS
    if thinking_depth is None:
        thinking_depth = LANGGRAPH_AGENT_THINKING_DEPTH

    # Cap max_iterations to a reasonable upper bound
    max_iterations = min(max_iterations, 25)

    # Build initial state
    initial_output = [
        {
            "type": "message",
            "id": output_id("msg"),
            "status": "in_progress",
            "role": "assistant",
            "content": [{"type": "output_text", "text": ""}],
        }
    ]

    initial_state: AgentState = {
        "messages": form_data.get("messages", []),
        "form_data": form_data,
        "model_id": model_id,
        "tools": tools_dict,
        "extra_params": extra_params,
        "iteration": 0,
        "max_iterations": max_iterations,
        "output": initial_output,
        "tool_results": [],
        "all_sources": [],
        "pending_tool_calls": [],
        "needs_more_tools": False,
        "final_response": "",
        "request": request,
        "user": user,
        "metadata": metadata,
        "event_emitter": event_emitter,
        "event_caller": event_caller,
    }

    # Build and compile the graph
    graph = build_agent_graph()
    compiled = graph.compile()

    log.debug(
        f"LangGraph agent starting: model={model_id}, "
        f"max_iterations={max_iterations}, tools={list(tools_dict.keys())}"
    )

    # Run the graph
    try:
        final_state = await compiled.ainvoke(initial_state)
    except Exception as e:
        log.exception(f"LangGraph agent error: {e}")
        return {
            "output": initial_output,
            "sources": [],
            "content": f"Error in LangGraph agent: {e}",
            "done": True,
        }

    return {
        "output": final_state.get("output", []),
        "sources": final_state.get("all_sources", []),
        "content": final_state.get("final_response", ""),
        "done": True,
    }
