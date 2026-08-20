"""LangGraph orchestrator: classifies a question, routes it to the general
Q&A agent or to the swot/developments subagent, then returns the final
answer text plus lightweight verification metadata (which tools actually
grounded the answer, and — for SWOT — whether the required save actually
happened).

Replaces the earlier Claude Agent SDK orchestrator (which used `query()` +
implicit Agent-tool delegation) with an explicit LangGraph StateGraph —
chosen as the more demonstrative pattern for graph-based agent
orchestration: routing here is a plain conditional edge you can read and
trace, rather than a delegation decision buried in the model's own tool
calls. Each subagent (app/agent/subagents/__init__.py) is itself a
LangGraph-prebuilt ReAct agent, so the graph mixes hand-written control flow
at the top level with framework-provided tool-calling loops underneath.
"""

from typing import Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agent.subagents import DEVELOPMENTS_AGENT, GENERAL_AGENT, SWOT_AGENT
from app.schemas.agent import ChatTurn

ROUTER_MODEL = "claude-haiku-4-5"

ROUTER_SYSTEM_PROMPT = """Classify what a competitor-analysis question is asking for:
- "swot": asks for a SWOT analysis (strengths/weaknesses/opportunities/threats) of a competitor.
- "developments": asks what's new/recent with a competitor, including research requests — news, launches,
  promotions/campaigns, funding, leadership changes.
- "general": anything else — price history questions, comparisons, general Q&A grounded in recorded data.

Our own company's data is tracked under the slug "gurneys" — treat "us"/"our own"/"Gardens Alive" questions
about pricing or developments the same as any competitor question, still routed by what's being asked for.

The conversation may include earlier turns — classify based on the latest question, using the earlier turns
only to resolve what a follow-up like "and what about pricing?" actually refers to."""


class RouteDecision(BaseModel):
    route: Literal["swot", "developments", "general"]


class OrchestratorState(TypedDict, total=False):
    messages: list[BaseMessage]
    route: Literal["swot", "developments", "general"]
    answer: str
    tools_used: list[str]
    save_verified: bool | None


# Haiku, low max_tokens: this call only ever produces one small structured
# tool call (the route field), not a reasoned response.
_router_model = ChatAnthropic(model=ROUTER_MODEL, max_tokens=64).with_structured_output(RouteDecision)

# Tools whose successful call is what "this SWOT actually got saved" means —
# see SWOT_SYSTEM_PROMPT's "Always call save_swot_analysis before finishing".
# Only swot has an unconditional save requirement: the developments agent is
# explicitly allowed to save nothing when there's genuinely no real finding
# ("skip it rather than record noise"), so a missing save there isn't a
# verification failure the same way it is for swot.
_REQUIRED_SAVE_TOOL: dict[str, str] = {"swot": "save_swot_analysis"}


async def classify(state: OrchestratorState) -> dict:
    question = state["messages"][-1].content
    history_messages = state["messages"][:-1]
    decision: RouteDecision = await _router_model.ainvoke(
        [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}, *history_messages, {"role": "user", "content": question}]
    )
    return {"route": decision.route}


def _route_selector(state: OrchestratorState) -> str:
    return state["route"]


def _extract_text(content: str | list) -> str:
    """AIMessage.content is a plain string only when the model didn't think.
    claude-sonnet-5 runs adaptive thinking by default, so it's normally a
    list of content blocks (thinking + text) instead — pull out just the
    text blocks.
    """
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _extract_tool_names(messages: list[BaseMessage]) -> list[str]:
    """Tools actually called AND returned during the ReAct loop, in the
    order first used — read from ToolMessage entries (the tool's real
    response), not AIMessage.tool_calls (the model's intent to call one),
    so this reflects what actually executed rather than what was merely
    requested.
    """
    seen: list[str] = []
    for message in messages:
        if isinstance(message, ToolMessage) and message.name and message.name not in seen:
            seen.append(message.name)
    return seen


async def _run_subagent(agent, state: OrchestratorState) -> dict:
    result = await agent.ainvoke({"messages": state["messages"]})
    final_message = result["messages"][-1]
    tools_used = _extract_tool_names(result["messages"])

    required_tool = _REQUIRED_SAVE_TOOL.get(state["route"])
    save_verified = required_tool in tools_used if required_tool else None

    return {
        "messages": result["messages"],
        "answer": _extract_text(final_message.content),
        "tools_used": tools_used,
        "save_verified": save_verified,
    }


async def run_general(state: OrchestratorState) -> dict:
    return await _run_subagent(GENERAL_AGENT, state)


async def run_swot(state: OrchestratorState) -> dict:
    return await _run_subagent(SWOT_AGENT, state)


async def run_developments(state: OrchestratorState) -> dict:
    return await _run_subagent(DEVELOPMENTS_AGENT, state)


_builder = StateGraph(OrchestratorState)
_builder.add_node("classify", classify)
_builder.add_node("general", run_general)
_builder.add_node("swot", run_swot)
_builder.add_node("developments", run_developments)
_builder.add_edge(START, "classify")
_builder.add_conditional_edges(
    "classify",
    _route_selector,
    {"general": "general", "swot": "swot", "developments": "developments"},
)
_builder.add_edge("general", END)
_builder.add_edge("swot", END)
_builder.add_edge("developments", END)

orchestrator_graph = _builder.compile()


def _to_lc_message(turn: ChatTurn) -> BaseMessage:
    return HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content)


class AgentAnswer(TypedDict):
    answer: str
    route: Literal["swot", "developments", "general"]
    tools_used: list[str]
    save_verified: bool | None


async def ask_agent(question: str, history: list[ChatTurn] | None = None) -> AgentAnswer:
    messages = [_to_lc_message(turn) for turn in (history or [])] + [HumanMessage(content=question)]
    result = await orchestrator_graph.ainvoke({"messages": messages})
    return {
        "answer": result["answer"],
        "route": result["route"],
        "tools_used": result["tools_used"],
        "save_verified": result["save_verified"],
    }
