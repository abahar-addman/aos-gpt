import ast
import json
import logging

from uuid import uuid4

from open_webui.utils.tools import get_updated_tool_function
from open_webui.utils.middleware import (
    process_tool_result,
    get_citation_source_from_tool_result,
)

log = logging.getLogger(__name__)


async def execute_tool_call(
    tool_call: dict,
    tools_dict: dict,
    request,
    form_data: dict,
    metadata: dict,
    user,
    event_caller=None,
    extra_params: dict | None = None,
) -> dict:
    """
    Execute a single tool call, reusing the same logic as middleware.py native mode.

    Returns a dict with keys:
        tool_call_id, content, files (optional), embeds (optional), sources (list)
    """
    tool_call_id = tool_call.get("id", "")
    tool_function_name = tool_call.get("function", {}).get("name", "")
    tool_args = tool_call.get("function", {}).get("arguments", "{}")

    # Parse arguments: ast.literal_eval first, then json.loads fallback
    tool_function_params = {}
    try:
        tool_function_params = ast.literal_eval(tool_args)
    except Exception:
        try:
            tool_function_params = json.loads(tool_args)
        except Exception:
            log.error(f"Error parsing tool call arguments: {tool_args}")

    # Normalize arguments back to valid JSON
    tool_call.setdefault("function", {})["arguments"] = json.dumps(
        tool_function_params
    )

    tool_result = None
    tool = None
    tool_type = ""
    direct_tool = False

    if tool_function_name in tools_dict:
        tool = tools_dict[tool_function_name]
        spec = tool.get("spec", {})
        tool_type = tool.get("type", "")
        direct_tool = tool.get("direct", False)

        try:
            # Filter params to only allowed ones from spec
            allowed_params = spec.get("parameters", {}).get("properties", {}).keys()
            tool_function_params = {
                k: v for k, v in tool_function_params.items() if k in allowed_params
            }

            if direct_tool:
                tool_result = await event_caller(
                    {
                        "type": "execute:tool",
                        "data": {
                            "id": str(uuid4()),
                            "name": tool_function_name,
                            "params": tool_function_params,
                            "server": tool.get("server", {}),
                            "session_id": metadata.get("session_id", None),
                        },
                    }
                )
            else:
                tool_function = get_updated_tool_function(
                    function=tool["callable"],
                    extra_params={
                        "__messages__": form_data.get("messages", []),
                        "__files__": metadata.get("files", []),
                        **(extra_params or {}),
                    },
                )
                tool_result = await tool_function(**tool_function_params)

        except Exception as e:
            tool_result = str(e)
    else:
        tool_result = f"Unknown tool: {tool_function_name}"

    # Process result through existing pipeline
    tool_result, tool_result_files, tool_result_embeds = process_tool_result(
        request,
        tool_function_name,
        tool_result,
        tool_type,
        direct_tool,
        metadata,
        user,
    )

    # Extract citation sources
    sources = []
    if (
        tool_function_name
        in ["search_web", "view_knowledge_file", "query_knowledge_files"]
        and tool_result
    ):
        try:
            citation_sources = get_citation_source_from_tool_result(
                tool_name=tool_function_name,
                tool_params=tool_function_params,
                tool_result=tool_result,
                tool_id=tool.get("tool_id", "") if tool else "",
            )
            sources.extend(citation_sources)
        except Exception as e:
            log.exception(f"Error extracting citation source: {e}")

    result = {
        "tool_call_id": tool_call_id,
        "content": tool_result or "",
        "sources": sources,
    }
    if tool_result_files:
        result["files"] = tool_result_files
    if tool_result_embeds:
        result["embeds"] = tool_result_embeds

    return result
