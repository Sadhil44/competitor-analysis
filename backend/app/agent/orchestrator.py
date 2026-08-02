from claude_agent_sdk import ClaudeAgentOptions, query

from app.agent.subagents import DEVELOPMENTS_AGENT, SWOT_AGENT
from app.agent.tools import competitor_analysis_server

ORCHESTRATOR_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a competitor analysis assistant for Gardens Alive, a horticultural company.
You answer questions about competitors' pricing history and recent developments, grounded in recorded data.

IMPORTANT: our own company's data is tracked in the same system as competitors, under the slug
"gurneys" (Gardens Alive operates as a brand within Gurney's, our storefront). When asked about
"our" pricing, "our own" products, Gardens Alive's pricing, or comparisons involving "us", use
query_price_history and search_developments with competitor="gurneys" — the exact same tools you'd
use for any competitor. Do not say you lack access to our own data; it is queried the same way.

Use query_price_history and search_developments to check what's already known before answering.
For requests that ask you to analyze a competitor's SWOT, delegate to the swot_agent subagent.
For requests about recent news or developments, delegate to the developments_agent subagent.
Always cite the specific data (prices, dates, sources) that ground your answer — never answer from general knowledge alone when competitor-specific data is being asked about.
When you invoke a subagent via the Agent tool, always set run_in_background to false — you need its result (and its side effects, like saving records) to complete before you can respond to the user."""


async def ask_agent(question: str) -> str:
    # permission_mode="dontAsk" pairs with allowed_tools for a fully headless
    # agent: listed tools are auto-approved, everything else is denied
    # outright — no interactive canUseTool callback, since nobody's watching
    # to click "approve" on a backend API call. Without this, tool calls
    # (including the subagents' save_* calls) silently get denied.
    #
    # Note: save_swot_analysis/save_development are only meant to be called
    # by their respective subagents (see subagents.py's per-agent `tools`
    # lists), not the orchestrator directly — but permission approval is
    # session-wide, not per-agent, so they're listed here too or the
    # subagents' calls would be denied the same way this whole fix addresses.
    # The orchestrator's own restraint from calling them directly is enforced
    # by its system prompt, not by tool visibility.
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"competitor_analysis": competitor_analysis_server},
        permission_mode="dontAsk",
        allowed_tools=[
            "mcp__competitor_analysis__query_price_history",
            "mcp__competitor_analysis__search_developments",
            "mcp__competitor_analysis__save_swot_analysis",
            "mcp__competitor_analysis__save_development",
            "WebSearch",
            "WebFetch",
            "Agent",
        ],
        agents={"swot_agent": SWOT_AGENT, "developments_agent": DEVELOPMENTS_AGENT},
        model=ORCHESTRATOR_MODEL,
    )

    result_text = ""
    async for message in query(prompt=question, options=options):
        if hasattr(message, "result"):
            result_text = message.result

    return result_text
