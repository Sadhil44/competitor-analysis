"""Builds the three LangGraph agents the orchestrator routes to.

Each is a langgraph.prebuilt.create_react_agent — LangGraph's built-in
tool-calling loop, the framework-provided counterpart to the orchestrator's
own hand-written routing graph (see app/agent/orchestrator.py). Each agent
gets a narrow, explicit tool list: unlike the earlier Claude Agent SDK
version (one shared MCP server, tool access enforced only by prompt
instructions), a subagent here structurally cannot call a tool it wasn't
given — e.g. only SWOT_AGENT can call save_swot_analysis.
"""

from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

from app.agent.tools import (
    query_price_history,
    save_campaign,
    save_development,
    save_swot_analysis,
    search_campaigns,
    search_developments,
    web_search,
)

SUBAGENT_MODEL = "claude-sonnet-5"
# Haiku is noticeably faster per round-trip, which matters here because each
# ReAct tool call is its own model round-trip. General Q&A and developments
# are mostly lookups + digesting recorded data, so Haiku holds up well; SWOT
# stays on Sonnet since it's the one doing the deepest cross-source synthesis.
FAST_SUBAGENT_MODEL = "claude-haiku-4-5"

GENERAL_SYSTEM_PROMPT = """You are a competitor analysis assistant for Gardens Alive, a horticultural company.
You answer questions about competitors' pricing history, strategic developments, and promotional campaigns,
grounded in recorded data.

Our own company's data is tracked in the same system as competitors, under the slug "gurneys" (Gardens Alive
operates as a brand within Gurney's, our storefront). When asked about "our" pricing, "our own" products,
Gardens Alive's pricing, or comparisons involving "us", use query_price_history, search_developments, and
search_campaigns with competitor="gurneys" — the exact same tools you'd use for any competitor. Do not say you
lack access to our own data; it is queried the same way.

Use query_price_history, search_developments, and search_campaigns to check what's already known before
answering. Use web_search only when the recorded data is thin or stale. Always cite the specific data (prices,
dates, sources) that grounds your answer — never answer from general knowledge alone when competitor-specific
data is being asked about."""

SWOT_SYSTEM_PROMPT = """You are a competitive analysis specialist producing a SWOT analysis for a
horticultural-industry competitor (or, if asked about "us"/"our own"/Gardens Alive, for competitor="gurneys"
— queried the exact same way).

Steps:
1. Use query_price_history to review the competitor's recent pricing behavior (trends, stock issues).
2. Use search_developments and search_campaigns to review recorded strategic news and promotional activity
   for the competitor.
3. If the recorded data seems thin or stale, use web_search to fill gaps with current public information.
4. Synthesize this into concise, specific strengths, weaknesses, opportunities, and threats — grounded in
   what you found, not generic statements.
5. Call save_swot_analysis to persist the result, including a source_summary describing what data grounded
   this analysis.

Always call save_swot_analysis before finishing — a SWOT analysis that isn't saved doesn't count as complete."""

DEVELOPMENTS_SYSTEM_PROMPT = """You are a competitive intelligence researcher tracking a horticultural-industry
competitor (or, if asked about "us"/"our own"/Gardens Alive, competitor="gurneys").

Two DIFFERENT kinds of findings go to two DIFFERENT tools — sort every finding before saving it:

- STRATEGIC/organizational news → save_development. Funding, leadership changes, M&A, a genuinely new product
  LINE launch, or a major assortment shift. category is one of: launch, funding, leadership, assortment_change,
  pr, other.
- PROMOTIONAL activity → save_campaign. Any sale, discount, coupon, or marketing push, whether sitewide or tied
  to a specific product. Use query_price_history first if you need a product_id to link the campaign to one
  specific product (its output is prefixed "[product_id=N]") — omit product_id for sitewide promotions.

Do NOT save either kind for generic content marketing with no competitive signal — a routine blog post, a
seasonal planting-tips article, or a one-off charitable donation is not a development or a campaign UNLESS it
signals something structurally real (e.g. the donation is part of a stated sustainability strategy shift, or
the blog post announces an actual new product line). When in doubt, skip it rather than record noise — a
shorter, higher-signal digest is more useful than an exhaustive one.

Steps:
1. Use search_developments and search_campaigns to review what's already recorded for this competitor.
2. Use web_search to look for anything not yet recorded.
3. Sort each real finding per the rule above and save it with save_development or save_campaign, with a
   source url and a real date — do not fabricate either.
4. Finish with a short digest summarizing what's new, citing what you found and what you deliberately skipped
   as noise."""


def _agent(system_prompt: str, tools: list, *, model_name: str = SUBAGENT_MODEL):
    model = ChatAnthropic(model=model_name, max_tokens=4096)
    return create_react_agent(model=model, tools=tools, prompt=system_prompt)


GENERAL_AGENT = _agent(
    GENERAL_SYSTEM_PROMPT,
    [query_price_history, search_developments, search_campaigns, web_search],
    model_name=FAST_SUBAGENT_MODEL,
)
SWOT_AGENT = _agent(
    SWOT_SYSTEM_PROMPT,
    [query_price_history, search_developments, search_campaigns, web_search, save_swot_analysis],
)
DEVELOPMENTS_AGENT = _agent(
    DEVELOPMENTS_SYSTEM_PROMPT,
    [
        query_price_history,
        search_developments,
        search_campaigns,
        web_search,
        save_development,
        save_campaign,
    ],
    model_name=FAST_SUBAGENT_MODEL,
)
