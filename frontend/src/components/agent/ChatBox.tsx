import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, Trash2 } from "lucide-react";
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
    <div className="flex h-[calc(100vh-12rem)] flex-col overflow-hidden rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-foreground text-background">
            <Bot size={15} />
          </div>
          <div>
            <div className="text-[14px] font-semibold text-foreground">Stock Analysis AI Agent</div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Tool-calling · Du lieu that tu backend
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="primary">Symbol · {symbol}</Badge>
          {turns.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearChat}>
              <Trash2 size={14} />
              Clear
            </Button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-muted/30 p-4">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <h3 className="text-base font-semibold text-foreground">Chao thay/co</h3>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Em co the phan tich ky thuat, so sanh mo hinh du bao, chay backtest,
              hoac giai thich chi so. Du lieu lay thang tu lakehouse phia sau.
            </p>
            <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-warn">
              Luu y: khong phai khuyen nghi dau tu. Demo hoc thuat.
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
                <Loader2 size={14} className="animate-spin" />
                Agent dang goi tool va suy nghi
              </div>
            ) : null}
            <div ref={bottom} />
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-t border-border bg-card px-4 py-2">
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.label}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1 text-[12px] font-medium text-foreground hover:bg-muted"
            onClick={() => void submit(item.prompt)}
            type="button"
          >
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="flex gap-2 border-t border-border bg-card p-3">
        <input
          className="h-10 flex-1 rounded-md border border-input bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:border-foreground"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Phan tich ky thuat VCB 3 thang gan nhat..."
        />
        <Button
          type="submit"
          disabled={busy || !input.trim()}
          size="lg"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          Gui
        </Button>
      </form>
    </div>
  );
}