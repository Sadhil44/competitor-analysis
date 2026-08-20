from fastapi import APIRouter

from app.agent.orchestrator import ask_agent
from app.schemas.agent import AgentAskRequest, AgentAskResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskResponse)
async def ask(request: AgentAskRequest) -> AgentAskResponse:
    result = await ask_agent(request.question, request.history)
    return AgentAskResponse(
        answer=result["answer"],
        route=result["route"],
        tools_used=result["tools_used"],
        save_verified=result["save_verified"],
    )
