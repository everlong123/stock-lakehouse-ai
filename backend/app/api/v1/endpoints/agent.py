"""AI agent endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_agent_service, get_db
from app.schemas.agent import ChatRequest
from app.schemas.common import ok
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat")
def agent_chat(
    payload: ChatRequest,
    db: Session | None = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    result = service.chat(payload.session_id, payload.message, payload.symbol, db=db)
    return ok(result)


@router.get("/history/{session_id}")
def agent_history(
    session_id: str,
    db: Session | None = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    return ok(service.history(session_id, db=db))


@router.get("/sessions")
def agent_sessions(
    db: Session | None = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """Every past chat session, newest activity first.

    WHY THIS EXISTS: the chat page shows a "past chats" list so a
    conversation survives closing the tab. The backend already stored
    every turn in MySQL — this endpoint is what makes it reachable.
    """
    return ok(service.sessions(db=db))


@router.delete("/sessions/{session_id}")
def delete_agent_session(
    session_id: str,
    db: Session | None = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """Delete one chat session and all of its turns."""
    removed = service.delete_session(session_id, db=db)
    return ok({"session_id": session_id, "deleted": removed})


@router.delete("/messages/{message_id}")
def delete_agent_message(
    message_id: int,
    db: Session | None = Depends(get_db),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """Delete a single turn from a chat session."""
    removed = service.delete_message(message_id, db=db)
    return ok({"message_id": message_id, "deleted": removed})
