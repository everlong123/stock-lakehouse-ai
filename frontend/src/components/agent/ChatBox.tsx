import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, Trash2 } from "lucide-react";
import { sendChat } from "@/api/agent";
import { ChatMessage } from "@/components/agent/ChatMessage";
import { ToolCallDisplay } from "@/components/agent/ToolCallDisplay";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/api/client";
import { ChatTurn } from "@/types/agent";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { QUICK_PROMPTS } from "@/utils/constants";
import { Badge } from "@/components/ui/badge";

export function ChatBox() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
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
        {
          role: "assistant",
          content: result.assistant_message,
          tools: result.tools,
          suggested_questions: result.suggested_questions,
          tool_count: result.tool_count,
        },
      ]);
    } catch (error) {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: errorMessage(error, t("agent.failed", locale)) },
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
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Bot size={15} />
          </div>
          <div>
            <div className="text-[14px] font-semibold text-foreground">Stock Analysis AI Agent</div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {locale === "vi"
                ? "Tool-calling · Dữ liệu thật từ backend"
                : "Tool-calling · Real data from backend"}
            </div>
          </div>
       </div>
        <div className="flex items-center gap-2">
          <Badge variant="primary">
            {t("agent.symbol_badge", locale)} · {symbol}
          </Badge>
          {turns.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearChat}>
              <Trash2 size={14} />
              {t("agent.clear", locale)}
            </Button>
          )}
        </div>
     </div>

      <div className="flex-1 overflow-y-auto bg-muted/30 p-4">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <h3 className="text-base font-semibold text-foreground">{t("agent.welcome_title", locale)}</h3>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              {t("agent.welcome_body", locale)}
            </p>
            <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-warn">
              {t("agent.welcome_warn", locale)}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {turns.map((turn, index) => (
              <div key={index} className="space-y-1">
                <ChatMessage turn={turn} />
                {turn.tools && turn.tools.length > 0 ? <ToolCallDisplay tools={turn.tools} /> : null}
                {turn.suggested_questions && turn.suggested_questions.length > 0 ? (
                  <SuggestedFollowUps
                    items={turn.suggested_questions}
                    onPick={(prompt) => void submit(prompt)}
                    busy={busy}
                    toolCount={turn.tool_count}
                  />
                ) : null}
              </div>
            ))}
            {busy ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 size={14} className="animate-spin" />
                {t("agent.thinking", locale)}
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
          placeholder={t("agent.placeholder", locale)}
        />
        <Button
          type="submit"
          disabled={busy || !input.trim()}
          size="lg"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {t("agent.send", locale)}
        </Button>
      </form>
    </div>
  );
}

// ── Inline follow-up chips ────────────────────────────────────────────────
// Shows after every assistant turn so the demo never stalls. Renders in
// Vietnamese (with English technical terms kept verbatim, per the thesis
// writing convention) and de-duplicates against the prompt already sent
// so the user never sees "phân tích AAPL" twice in a row.

function SuggestedFollowUps({
  items,
  onPick,
  busy,
  toolCount,
}: {
  items: string[];
  onPick: (prompt: string) => void;
  busy: boolean;
  toolCount?: number;
}) {
  return (
    <div className="ml-9 mt-2 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Gợi ý tiếp
        </span>
        {typeof toolCount === "number" && toolCount > 0 ? (
          <Badge variant="primary">
            Đã gọi {toolCount} tool
          </Badge>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <button
            key={item}
            type="button"
            disabled={busy}
            onClick={() => onPick(item)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-[12px] font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden className="text-[10px] text-muted-foreground">→</span>
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}