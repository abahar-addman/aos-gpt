from typing import Any, TypedDict


class AgentState(TypedDict):
    # OpenAI-format conversation messages
    messages: list[dict]
    # Original request payload
    form_data: dict
    model_id: str
    # tools_dict from get_tools()
    tools: dict
    # __event_emitter__, __user__, etc.
    extra_params: dict
    # Current iteration counter
    iteration: int
    max_iterations: int
    # OR-aligned output items (same format as middleware)
    output: list[dict]
    # Results from current iteration's tool calls
    tool_results: list[dict]
    # Accumulated citation sources across iterations
    all_sources: list[dict]
    # tool_calls extracted from the LLM response
    pending_tool_calls: list[dict]
    # Whether the analyze step determined more tools are needed
    needs_more_tools: bool
    # Final assembled response text
    final_response: str
    # Non-serialized runtime context
    request: Any
    user: Any
    metadata: dict
    event_emitter: Any
    event_caller: Any
