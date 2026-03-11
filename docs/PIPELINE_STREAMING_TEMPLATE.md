# Pipeline Streaming Template

## How Client-Side Rendering Works

The client accumulates **all** streamed content into a single `message.content` string. There are no separate channels for "thinking" vs "response" — it's one continuous text stream. The client-side parser then splits the accumulated content into sections for rendering.

### SSE Format

Every chunk from the pipeline must be:
```
data: {"choices":[{"delta":{"content":"<text chunk>"}}]}
```

Final chunk:
```
data: [DONE]
```

That's it. Everything goes through `delta.content`. The client appends each chunk to `message.content += chunk`.

---

## Streaming Phases

The pipeline should yield content in this exact order:

### Phase 1: Agent Activity Block (collapsible, live progress)

```
<details>
<summary>Thinking</summary>
- **Planning**...
- **Analyzing data**...
  - Calling: fetch_cnc_utilization, fetch_cnc_all_statuses
- **Processing results**...
- **Reviewing response**...
- **Generating charts**...
</details>
```

**Rules:**
- Open `<details><summary>Thinking</summary>` FIRST — this immediately creates the collapsible activity section
- Stream status updates as markdown bullet points (`- **Step name**...`)
- Sub-steps use indented bullets (`  - Detail`)
- Close with `</details>` when all background work is complete
- While unclosed, the client shows this expanded with a pulsing "Thinking..." indicator
- Once closed, it collapses to "Thought process" (click to expand)

**Recognized summary names** (case-insensitive): `Thinking`, `Planning`, `Review`, `Reviewing`, `Analysis`, `Reasoning`

### Phase 2: Final Response (main content body)

```markdown
# SVL Manufacturing Site Performance Analysis

**Analysis Period:** March 2-11, 2026

## Key Metrics
...
```

**Rules:**
- Standard markdown — renders in the main chat body
- Must NOT contain `<thinking>`, `<chart_plan>`, `<plan>`, or `[SYSTEM INSTRUCTION]` tags (these are stripped client-side as a safety net, but the pipeline should not emit them here)
- This is what the user sees as "the response"

### Phase 3: Charts (rendered as interactive Plotly visualizations)

````
```plotly
{"data":[{"x":["Machine A","Machine B"],"y":[45.2,38.1],"type":"bar","marker":{"color":["#2196F3","#FF9800"]}}],"layout":{"title":{"text":"Machine Utilization"},"yaxis":{"title":"Utilization %"},"template":"plotly_dark"},"config":{"responsive":true}}
```
````

**Rules:**
- Use ` ```plotly ` language tag (NOT `json`, NOT `python`)
- Content must be valid JSON with Plotly spec: `{data, layout, config}`
- `data`: Array of trace objects (required)
- `layout`: Layout configuration (optional, recommended)
- `config`: Plotly config, always include `{"responsive": true}` (optional)
- Multiple charts = multiple ` ```plotly ` blocks
- Charts render as interactive iframes (500px height) with full Plotly interactivity (hover, zoom, pan)

---

## Complete Example: What `message.content` Looks Like

```
<details>
<summary>Thinking</summary>
- **Planning** analysis approach...
- **Fetching data**...
  - Calling: fetch_cnc_utilization(plant='SVL')
  - Calling: fetch_cnc_all_statuses(plant='SVL')
- **Analyzing** 847 records across 12 machines...
- **Reviewing** response quality...
- **Generating** 2 charts...
</details>

# SVL Manufacturing Site Performance Analysis

**Analysis Period:** March 2-11, 2026 (10 days)

## Key Performance Metrics

| Machine | Utilization | Status |
|---------|------------|--------|
| CMV-2   | 55.6%      | Active |
| HMC-1   | 42.3%      | Active |

## Insights

1. **Critical Finding:** Average utilization at 22.5% is well below the 60-80% industry standard
2. **Top Performer:** CMV-2 at 55.6% utilization
3. **Improvement Opportunity:** 5 machines below 15% utilization

```plotly
{"data":[{"x":["CMV-2","HMC-1","VMC-3","MILLAC-1","MILLAC-2"],"y":[55.6,42.3,28.1,15.2,1.6],"type":"bar","marker":{"color":"#2196F3"}}],"layout":{"title":{"text":"Machine Utilization - SVL"},"yaxis":{"title":"Utilization %","range":[0,100]},"template":"plotly_dark"},"config":{"responsive":true}}
```

```plotly
{"data":[{"x":["Running","Idle","Offline","Unknown"],"y":[22.5,15.3,31.2,31.0],"type":"waterfall","connector":{"line":{"color":"rgb(63,63,63)"}},"increasing":{"marker":{"color":"#4CAF50"}},"decreasing":{"marker":{"color":"#F44336"}}}],"layout":{"title":{"text":"Status Breakdown - SVL"},"yaxis":{"title":"% of Time"},"template":"plotly_dark"},"config":{"responsive":true}}
```
```

---

## Tags Stripped Client-Side (Safety Net)

These are removed from `message.content` before rendering. The pipeline should avoid emitting them in the final response, but they're stripped as a safety net:

| Tag | Handling |
|-----|----------|
| `<thinking>...</thinking>` | Tags stripped, content preserved (visible in activity block) |
| `<chart_plan>...</chart_plan>` | Fully removed (tags + content) |
| `<plan>...</plan>` | Fully removed (tags + content) |
| `[SYSTEM INSTRUCTION...]` | Fully removed |

---

## Tags Preserved Client-Side

| Tag | Rendering |
|-----|-----------|
| `<details><summary>Thinking</summary>...</details>` | Agent activity section (collapsible) |
| `<details type="tool_calls" ...>` | Tool call display (collapsible input/output) |
| ` ```plotly ` | Interactive Plotly chart |
| ` ```mermaid ` | Rendered flowchart/diagram |
| Standard markdown | Normal rich text rendering |

---

## Pipeline Generator Template (Python)

```python
async def stream_response(user_message, tools, llm):
    """Template for pipeline streaming generator."""

    # ── Phase 1: Open thinking block ──
    yield sse('<details>\n<summary>Thinking</summary>\n')

    # Planning
    yield sse('- **Planning** analysis approach...\n')
    plan = await run_planner(user_message, llm)

    # Data fetching
    yield sse('- **Fetching data**...\n')
    for tool_name, tool_args in plan.tool_calls:
        yield sse(f'  - Calling: {tool_name}({tool_args})\n')
        result = await execute_tool(tool_name, tool_args, tools)

    # Analysis
    yield sse('- **Analyzing** results...\n')
    response = await run_analyst(user_message, plan, tool_results, llm)

    # Review
    yield sse('- **Reviewing** response quality...\n')
    review = await run_reviewer(response, user_message, llm)
    if review.verdict == 'REVISE':
        yield sse('- **Revising** based on feedback...\n')
        response = await run_analyst_revision(response, review, llm)

    # Chart generation
    charts = extract_chart_specs(response)
    if charts:
        yield sse(f'- **Generating** {len(charts)} charts...\n')
        plotly_blocks = await generate_charts(charts, tool_results)

    # ── Phase 2: Close thinking, emit final response ──
    yield sse('</details>\n\n')
    yield sse(clean_response(response))  # Strip <thinking>, <chart_plan>, etc.

    # ── Phase 3: Append charts ──
    for chart_json in plotly_blocks:
        yield sse(f'\n\n```plotly\n{chart_json}\n```')

    yield 'data: [DONE]\n\n'


def sse(content: str) -> str:
    """Format content as SSE delta."""
    import json
    payload = json.dumps({
        "choices": [{"delta": {"content": content}}]
    })
    return f"data: {payload}\n\n"


def clean_response(text: str) -> str:
    """Strip internal tags from analyst response."""
    import re
    text = re.sub(r'</?thinking>', '', text, flags=re.I)
    text = re.sub(r'<chart_plan>.*?</chart_plan>', '', text, flags=re.S | re.I)
    text = re.sub(r'<plan>.*?</plan>', '', text, flags=re.S | re.I)
    text = re.sub(r'\[SYSTEM INSTRUCTION[^\]]*\]', '', text, flags=re.I)
    return text.strip()
```

---

## Client-Side Rendering Summary

```
message.content (accumulated string)
        │
        ├─ processResponseContent()
        │   ├─ Strip <thinking> tags (keep content)
        │   ├─ Remove <chart_plan>, <plan>, [SYSTEM INSTRUCTION]
        │   └─ Chinese text processing
        │
        ├─ extractAgentActivity()
        │   ├─ Extract <details><summary>Thinking</summary>...</details>
        │   │   → Agent activity section (collapsible, live progress)
        │   └─ Leave <details type="tool_calls"> in content
        │       → ToolCallDisplay component
        │
        ├─ displayContent → ContentRenderer → Markdown
        │   ├─ ```plotly blocks → Interactive Plotly charts (iframe)
        │   ├─ ```mermaid blocks → Rendered diagrams (SVG)
        │   ├─ Tables, headers, lists → Standard markdown
        │   └─ Other code blocks → Syntax-highlighted code
        │
        └─ Final render:
            ┌─────────────────────────────────┐
            │ ▶ Thinking... (pulsing)         │  ← While streaming
            │   - **Planning**...             │
            │   - **Fetching data**...        │
            │   - **Analyzing**...            │
            ├─────────────────────────────────┤
            │ ▶ Thought process (collapsed)   │  ← When done
            ├─────────────────────────────────┤
            │                                 │
            │ # Analysis Title                │  ← Main response
            │ Key findings...                 │
            │                                 │
            │ ┌─────────────────────────────┐ │
            │ │    [Interactive Chart 1]    │ │  ← Plotly charts
            │ └─────────────────────────────┘ │
            │ ┌─────────────────────────────┐ │
            │ │    [Interactive Chart 2]    │ │
            │ └─────────────────────────────┘ │
            │                                 │
            │ ▶ Follow-up questions           │  ← Generated after done
            └─────────────────────────────────┘
```
