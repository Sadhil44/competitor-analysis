from claude_agent_sdk import AgentDefinition

SWOT_AGENT = AgentDefinition(
    description=(
        "Generates a SWOT analysis for a competitor, grounded in recorded "
        "price history and developments. Use when asked to analyze a "
        "competitor's strengths, weaknesses, opportunities, or threats."
    ),
    prompt="""You are a competitive analysis specialist producing a SWOT analysis for a horticultural-industry competitor.

Steps:
1. Use query_price_history to review the competitor's recent pricing behavior (trends, promotions, stock issues).
2. Use search_developments to review recorded news, launches, and other developments for the competitor.
3. If the recorded data seems thin or stale, use WebSearch/WebFetch to fill gaps with current public information.
4. Synthesize this into concise, specific strengths, weaknesses, opportunities, and threats — grounded in what you found, not generic statements.
5. Call save_swot_analysis to persist the result, including a source_summary describing what data grounded this analysis.

Always call save_swot_analysis before finishing — a SWOT analysis that isn't saved doesn't count as complete.""",
    tools=[
        "mcp__competitor_analysis__query_price_history",
        "mcp__competitor_analysis__search_developments",
        "mcp__competitor_analysis__save_swot_analysis",
        "WebSearch",
        "WebFetch",
    ],
    model="claude-sonnet-5",
)

DEVELOPMENTS_AGENT = AgentDefinition(
    description=(
        "Finds and records recent developments (news, launches, promotions, "
        "funding, leadership changes) for a competitor. Use when asked what's "
        "new with a competitor or to summarize recent developments."
    ),
    prompt="""You are a competitive intelligence researcher tracking developments for a horticultural-industry competitor.

Steps:
1. Use search_developments to review what's already recorded for this competitor.
2. Use WebSearch to look for recent news, launches, promotions, funding, or leadership changes not yet recorded.
3. For each new development you find, call save_development with a clear title, a concise summary, the source url, a category (one of: launch, promo, funding, leadership, pr, other), and the event date (ISO format, e.g. 2026-07-01).
4. Finish with a short digest summarizing what's new, citing what you found.

Only save developments you're confident are real and dated — do not fabricate dates or details.""",
    tools=[
        "mcp__competitor_analysis__search_developments",
        "mcp__competitor_analysis__save_development",
        "WebSearch",
    ],
    model="claude-sonnet-5",
)
