"""AI agent application service."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from sqlalchemy.orm import Session

from app.agent.agent import StockAnalysisAgent
from app.core.config import settings
from app.core.exceptions import AgentError, AgentTimeoutError
from app.core.logging_config import get_logger
from app.database.repositories.conversation_repository import ConversationRepository
from app.database.session import check_database_connection

logger = get_logger(__name__)


def _dump_agent_threads() -> None:
    """Log the stack of every live thread when an agent request times out.

    WHY: the deadline fires on a wall clock, and the worker thread cannot be
    killed. Without a stack dump there is no way to tell whether the stall was
    Python (GIL starvation from the background refresh) or an external wait
    (MinIO pool, the Gemini socket, MySQL). The dump turns a guess into a
    fact, so the fix can target the real blocker.
    """
    import sys
    import traceback

    frames = sys._current_frames()
    counts: dict[str, int] = {}
    for thread in threading.enumerate():
        frame = frames.get(thread.ident)
        if frame is None:
            continue
        stack = traceback.format_stack(frame)
        leaf = stack[-1].strip() if stack else "?"
        # Bucket by the leaf frame so the hot path is visible at a glance.
        key = f"{thread.name} | {leaf}"
        counts[key] = counts.get(key, 0) + 1
    for key, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        logger.warning("Agent timeout thread state (%s): %s", count, key)

    for thread in threading.enumerate():
        frame = frames.get(thread.ident)
        if frame is None:
            continue
        stack = traceback.format_stack(frame)
        logger.warning(
            "Stack dump for thread %s (alive=%s):\n%s",
            thread.name,
            thread.is_alive(),
            "".join(stack[-10:]),
        )


class AgentService:
    def __init__(self) -> None:
        self.agent = StockAnalysisAgent()

    def chat(self, session_id: str, message: str, symbol: str | None, db: Session | None = None) -> dict:
        result = self._reply_with_deadline(message, symbol)
        tools = result.get("tools") or []
        first_tool = tools[0] if tools else {}
        if db is not None and check_database_connection():
            try:
                ConversationRepository(db).create(
                    {
                        "session_id": session_id,
                        "user_message": message,
                        "assistant_message": result.get("assistant_message"),
                        "tool_name": ",".join(item.get("tool_name") or "" for item in tools) or None,
                        "tool_arguments": json.dumps(first_tool.get("tool_arguments"), default=str)
                        if first_tool
                        else None,
                        "tool_result": json.dumps([item.get("tool_result") for item in tools], default=str)
                        if tools
                        else None,
                    }
                )
            except Exception as exc:
                logger.warning("Unable to persist agent conversation: %s", exc)
        return {
            "session_id": session_id,
            "assistant_message": result.get("assistant_message"),
            "tools": tools,
            # Forward UI hints the offline / LLM path computed: the chat
            # front-end surfaces them as quick-reply chips + a citation
            # badge ("Đã gọi N tool"). Stripping them here would silently
            # break the UX even though the agent already produced them.
            "suggested_questions": result.get("suggested_questions") or [],
            "tool_count": result.get("tool_count"),
        }

    def _reply_with_deadline(self, message: str, symbol: str | None) -> dict:
        """Run the agent under a wall-clock deadline.

        WHY: the browser aborts the request after 90s and renders "Yêu cầu
        mất quá lâu". Without a server-side deadline the backend keeps
        working on an abandoned request, and that orphaned work competes for
        CPU and MinIO connections with whatever the user asks next - so one
        slow request made the following ones slow too.

        The agent call runs in a worker thread so the HTTP request can be
        answered with a real 504 instead of hanging. A worker thread cannot
        be force-killed in Python, so the thread is left to finish on its own
        (daemon=True means it dies with the process) - but the client gets a
        clear, actionable error rather than an opaque timeout.
        """
        timeout = settings.agent_request_timeout_seconds
        if timeout <= 0:
            return self.agent.reply(message, default_symbol=symbol)

        box: dict[str, dict] = {}

        def _work() -> None:
            try:
                box["result"] = self.agent.reply(message, default_symbol=symbol)
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller
                box["error"] = exc

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-chat")
        try:
            future = executor.submit(_work)
            try:
                # `future.result()` returns whatever `_work` RETURNED, and
                # `_work` returns None (it stashes the answer in `box`).
                # Reading `box` directly is what actually gets the answer -
                # using `future.result()` silently produced a None reply and
                # every agent call blew up with
                # "'NoneType' object has no attribute 'get'".
                future.result(timeout=timeout)
            except FuturesTimeout:
                logger.warning(
                    "Agent request exceeded the %ss deadline; returning 504 to the client.",
                    timeout,
                )
                _dump_agent_threads()
                future.cancel()
                raise AgentTimeoutError(
                    f"Yêu cầu vượt quá giới hạn {timeout}s. Backend vẫn đang xử lý — "
                    "hãy thử lại với câu hỏi ngắn hơn hoặc bỏ bớt số mã."
                )
            if "error" in box:
                raise box["error"]
            result = box.get("result")
            if result is None:
                raise AgentError("Agent returned an empty response.")
            return result
        finally:
            # Do not block on a still-running worker: the thread is daemonic
            # and will be abandoned when the process exits.
            executor.shutdown(wait=False)

    def history(self, session_id: str, db: Session | None = None) -> list[dict]:
        if db is None or not check_database_connection():
            return []
        rows = ConversationRepository(db).list_by_session(session_id)
        return [
            {
                "id": row.id,
                "session_id": row.session_id,
                "user_message": row.user_message,
                "assistant_message": row.assistant_message,
                "tool_name": row.tool_name,
                "tool_arguments": row.tool_arguments,
                "tool_result": row.tool_result,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
