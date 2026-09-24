import { FormEvent, useEffect, useRef, useState } from "react";
import { sendChat } from "@/api/agent";
import { ChatMessage } from "@/components/agent/ChatMessage";
import { ToolCallDisplay } from "@/components/agent/ToolCallDisplay";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/api/client";
import { ChatTurn } from "@/types/agent";
import { useMarket } from "@/hooks/useMarket";

const SUGGESTIONS = [
  "Phân tích kỹ thuật AAPL",
  "So sánh 3 mô hình dự báo cho MSFT",
  "Backtest MA Crossover TSLA năm 2025",
  "Dự báo NVDA bằng LSTM",
];

export function ChatBox() {
  const { symbol } = useMarket();
  const [sessionId] = useState(() => localStorage.getItem("agentSession") || crypto.randomUUID());
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem("agentSession", sessionId);
  }, [sessionId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const submit = async (message: string) => {
    if (!message.trim() || busy) return;
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    setBusy(true);
    try {
      const result = await sendChat(sessionId, message, symbol);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: result.assistant_message, tools: result.tools },
      ]);
    } catch (error) {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: errorMessage(error, "Agent request failed.") },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit(input);
  };

  return (
    <div className="flex h-[calc(100vh-11rem)] flex-col rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <div className="font-semibold">Stock Analysis AI Agent</div>
        <div className="text-xs text-muted-foreground">
          Tool calling · dữ liệu thật từ backend · không phải khuyến nghị đầu tư
        </div>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {turns.map((turn, index) => (
          <div key={index} className="space-y-2">
            <ChatMessage turn={turn} />
            {turn.tools ? <ToolCallDisplay tools={turn.tools} /> : null}
          </div>
        ))}
        {busy ? <div className="text-sm text-muted-foreground">Agent đang gọi tool...</div> : null}
        <div ref={bottom} />
      </div>
      <div className="flex flex-wrap gap-2 border-t border-border px-4 py-2">
        {SUGGESTIONS.map((item) => (
          <button
            key={item}
            className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
            onClick={() => void submit(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </div>
      <form onSubmit={onSubmit} className="flex gap-2 border-t border-border p-3">
        <input
          className="h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Phân tích RSI của AAPL 3 tháng gần đây."
        />
        <Button type="submit" disabled={busy}>
          Send
        </Button>
      </form>
    </div>
  );
}
