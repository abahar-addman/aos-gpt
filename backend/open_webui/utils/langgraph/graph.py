from langgraph.graph import StateGraph, END

from open_webui.utils.langgraph.state import AgentState
from open_webui.utils.langgraph.nodes import (
    call_llm,
    execute_tools,
    analyze_results,
    prepare_response,
)


def should_execute_tools(state: AgentState) -> str:
    """Route after call_llm: execute tools if there are pending tool calls."""
    if state.get("pending_tool_calls"):
        return "execute_tools"
    return "prepare_response"


def should_continue(state: AgentState) -> str:
    """Route after analyze_results: loop back or finish."""
    if state.get("needs_more_tools") and state["iteration"] < state["max_iterations"]:
        return "call_llm"
    return "prepare_response"


def build_agent_graph() -> StateGraph:
    """
    Build the LangGraph state graph:

        Entry -> call_llm
                  |-- has tool_calls? -> execute_tools -> analyze_results
                  |                                        |-- needs more + under limit? -> call_llm (loop)
                  |                                        |-- done -> prepare_response -> END
                  |-- no tool_calls -> prepare_response -> END
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("call_llm", call_llm)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("analyze_results", analyze_results)
    graph.add_node("prepare_response", prepare_response)

    # Set entry point
    graph.set_entry_point("call_llm")

    # Conditional edges
    graph.add_conditional_edges(
        "call_llm",
        should_execute_tools,
        {
            "execute_tools": "execute_tools",
            "prepare_response": "prepare_response",
        },
    )

    graph.add_edge("execute_tools", "analyze_results")

    graph.add_conditional_edges(
        "analyze_results",
        should_continue,
        {
            "call_llm": "call_llm",
            "prepare_response": "prepare_response",
        },
    )

    graph.add_edge("prepare_response", END)

    return graph
