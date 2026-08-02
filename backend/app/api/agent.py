from fastapi import APIRouter

from app.agent.orchestrator import ask_agent
from app.schemas.agent import AgentAskRequest, AgentAskResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskResponse)
async def ask(request: AgentAskRequest) -> AgentAskResponse:
    answer = await ask_agent(request.question)
    return AgentAskResponse(answer=answer)
