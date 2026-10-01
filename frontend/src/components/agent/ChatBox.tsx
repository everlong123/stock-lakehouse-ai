import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, Sparkles, Trash2 } from "lucide-react";
import { sendChat } from "@/api/agent";
import { ChatMessage } from "@/components/agent/ChatMessage";
import { ToolCallDisplay } from "@/components/agent/ToolCallDisplay";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/api/client";
import { ChatTurn } from "@/types/agent";
import { useMarket } from "@/hooks/useMarket";
import { QUICK_PROMPTS } from "@/utils/constants";
import { Badge } from "@/components/ui/badge";

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

  const clearChat = () => setTurns([]);

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-gradient-to-r from-brand-500/8 to-brand-700/8 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-glow">
              <Bot size={18} />
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card bg-up" />
          </div>
          <div>
            <div className="font-bold text-foreground">Stock Analysis AI Agent</div>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>Tool-calling</span>
              <span>·</span>
              <span>Dữ liệu thật từ backend</span>
              <span>·</span>
              <Badge variant="primary" className="px-1.5 py-0 text-[10px]">
                <Sparkles size={9} />
                Gemini Free
              </Badge>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="primary">Symbol: {symbol}</Badge>
          {turns.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearChat}>
              <Trash2 size={14} />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-muted/30 p-5">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-glow">
              <Sparkles size={28} />
            </div>
            <h3 className="text-lg font-bold text-foreground">
              Chào thầy/cô
            </h3>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              Em có thể phân tích kỹ thuật, so sánh mô hình dự báo, chạy backtest,
              hoặc giải thích chỉ số. Dữ liệu lấy thẳng từ lakehouse phía sau.
            </p>
            <p className="mt-2 text-[11px] text-warn">
              Lưu ý: Không phải khuyến nghị đầu tư. Demo học thuật.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {turns.map((turn, index) => (
              <div key={index} className="space-y-1">
                <ChatMessage turn={turn} />
                {turn.tools && turn.tools.length > 0 ? <ToolCallDisplay tools={turn.tools} /> : null}
              </div>
            ))}
            {busy ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 size={14} className="animate-spin text-brand-600" />
                Agent đang gọi tool và suy nghĩ...
              </div>
            ) : null}
            <div ref={bottom} />
          </div>
        )}
      </div>

      {/* Quick prompts */}
      <div className="flex flex-wrap gap-2 border-t border-border bg-card px-5 py-2.5">
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.label}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-muted-foreground transition-all hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
            onClick={() => void submit(item.prompt)}
            type="button"
          >
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={onSubmit} className="flex gap-2 border-t border-border bg-card p-4">
        <input
          className="h-11 flex-1 rounded-xl border border-border bg-background px-4 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Phân tích kỹ thuật VCB 3 tháng gần nhất..."
        />
        <Button
          type="submit"
          disabled={busy || !input.trim()}
          size="lg"
          className="px-5"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          Gửi
        </Button>
      </form>
    </div>
  );
}