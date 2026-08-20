from typing import Literal

from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentAskRequest(BaseModel):
    question: str
    # Prior turns in the conversation, oldest first — lets the agent answer
    # follow-ups ("what about their shipping costs?") with the earlier
    # question/answer as real context, not just the latest message in
    # isolation.
    history: list[ChatTurn] = []


class AgentAskResponse(BaseModel):
    answer: str
    route: Literal["swot", "developments", "general"]
    # Which tools the agent actually called while answering — surfaced so
    # the UI can show what grounded the answer (e.g. "Checked: price
    # history, live web search") instead of asking the user to trust an
    # opaque response.
    tools_used: list[str]
    # For swot/developments routes, whether the agent actually completed
    # the save it's instructed to always perform (save_swot_analysis /
    # save_development / save_campaign). None for "general", which has no
    # required save. A real check against the tool-call trace, not the
    # model's own self-report.
    save_verified: bool | None = None
