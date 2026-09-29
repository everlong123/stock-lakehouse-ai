"""Run the AI Agent in headless CLI mode.

Test the agent pipeline without a frontend::

    python scripts/run_agent.py "Phân tích kỹ thuật AAPL 90 ngày qua"
    python scripts/run_agent.py "Forecast giá MSFT 5 ngày tới bằng LSTM"
    python scripts/run_agent.py "Backtest MA crossover cho NVDA 2 năm qua"

Hoặc chạy với fallback (không cần OpenAI key)::

    python scripts/run_agent.py --fallback "Giá AAPL hôm nay"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI Agent headless (CLI).")
    parser.add_argument("query", nargs="*", help="Câu hỏi / yêu cầu phân tích")
    parser.add_argument("--session-id", default=None,
                        help="Session ID để lưu lịch sử hội thoại.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.query:
        print("Vui lòng nhập câu hỏi. Ví dụ:")
        print('  python scripts/run_agent.py "Phân tích AAPL"')
        sys.exit(1)

    query = " ".join(args.query).strip()

    from app.core.config import settings
    from app.services.agent_service import AgentService

    service = AgentService()
    session_id = args.session_id or "cli-session"

    response = service.chat(
        session_id=session_id,
        message=query,
        symbol=None,
        db=None,  # CLI mode - skip DB persistence
    )

    print()
    print("=" * 70)
    print(f"User:    {query}")
    print("=" * 70)
    print(response.get("assistant_message", ""))
    print("=" * 70)
    if response.get("tools"):
        names = [item.get("tool_name") for item in response["tools"] if item.get("tool_name")]
        if names:
            print("Tools used:", ", ".join(names))


if __name__ == "__main__":
    main()