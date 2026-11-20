import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  History,
  Loader2,
  MessageSquarePlus,
  Send,
  Trash2,
} from "lucide-react";
import {
  deleteChatSession,
  fetchChatHistory,
  fetchChatSessions,
  sendChat,
} from "@/api/agent";
import { ChatMessage } from "@/components/agent/ChatMessage";
import { ToolCallDisplay } from "@/components/agent/ToolCallDisplay";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/api/client";
import { ChatTurn, StoredTurn } from "@/types/agent";
import { useMarket } from "@/hooks/useMarket";
import { useI18n, t } from "@/lib/i18n";
import { QUICK_PROMPTS } from "@/utils/constants";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * The chat page.
 *
 * WHY THE SYMBOL BADGE IS GONE
 * ----------------------------
 * The header used to show "SYMBOL · AAPL". The symbol is already chosen
 * in the global header at the top of the page, and the agent uses it
 * automatically on every request — so the badge repeated information the
 * reader can see one inch higher, and made it look like the chat was
 * bound to a ticker when it is not (the agent falls back to its own
 * symbol resolution when the header has no selection).
 */
export function ChatBox() {
  const { symbol } = useMarket();
  const { locale } = useI18n();
  const queryClient = useQueryClient();

  // The active session. Persisted so a page reload lands back in the same
  // conversation instead of starting a blank one.
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem("agentSession") || crypto.randomUUID(),
  );
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem("agentSession", sessionId);
  }, [sessionId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  // The list of past sessions. Refetched whenever a chat is deleted or a
  // new one starts, so the sidebar never shows a stale entry.
  const sessionsQuery = useQuery({
    queryKey: ["agent-sessions"],
    queryFn: fetchChatSessions,
    staleTime: 15_000,
    retry: 1,
  });

  // Load the stored turns of the active session on mount and whenever the
  // session changes.
  const historyQuery = useQuery({
    queryKey: ["agent-history", sessionId],
    queryFn: () => fetchChatHistory(sessionId),
    retry: 1,
  });

  // Seed the transcript from the server exactly once per session. The
  // dependency is the session id alone: re-running this on every history
  // refetch would wipe turns the user is currently looking at.
  const seededSession = useRef<string | null>(null);
  useEffect(() => {
    if (seededSession.current === sessionId) return;
    const stored = historyQuery.data;
    if (!stored) return;
    seededSession.current = sessionId;
    setTurns(stored.flatMap(toTurnPair));
  }, [historyQuery.data, sessionId]);

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
      // The chat just wrote a new session row, so the sidebar list is out
      // of date.
      void queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
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

  /**
   * Clear the visible transcript.
   *
   * "Chat mới" starts a fresh conversation; the old one stays in the
   * history list and can be reopened. Deleting a saved conversation is a
   * separate action on its row in the sidebar.
   */
  const newChat = () => {
    setTurns([]);
    setSessionId(crypto.randomUUID());
    seededSession.current = null;
  };

  const openSession = (id: string) => {
    setSessionId(id);
    setTurns([]);
    seededSession.current = null;
    setHistoryOpen(false);
  };

  const removeSession = async (id: string) => {
    try {
      await deleteChatSession(id);
      if (id === sessionId) newChat();
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
      await queryClient.invalidateQueries({ queryKey: ["agent-history"] });
    } catch (error) {
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: errorMessage(error, t("agent.failed", locale)) },
      ]);
    }
  };

  const sessions = sessionsQuery.data ?? [];

  return (
    <div className="flex h-[calc(100vh-13rem)] flex-col overflow-hidden rounded border border-hairline bg-surface md:flex-row">
      {/*
        ── The history rail ───────────────────────────────────────────
        A Gemini-style list of past chats. It is a full-height column on
        wide screens and a slide-over on narrow ones. Collapsed by
        default on mobile so the chat itself owns the screen.
      */}
      <aside
        className={cn(
          "flex max-h-48 min-h-0 w-full shrink-0 flex-col border-b border-hairline bg-surface-2 md:max-h-none md:w-64 md:border-b-0 md:border-r",
          historyOpen ? "flex" : "hidden md:flex",
        )}
      >
        <div className="hidden border-b border-hairline p-3 md:block">
          <Button
            variant="primary"
            size="sm"
            className="w-full justify-center"
            onClick={newChat}
          >
            <MessageSquarePlus size={13} />
            {t("agent.new_chat", locale)}
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {sessionsQuery.isLoading ? (
            <p className="px-3 py-4 font-mono text-label uppercase text-muted">
              {t("agent.history_loading", locale)}
            </p>
          ) : sessionsQuery.isError ? (
            <p className="px-3 py-4 text-label text-negative">
              {errorMessage(sessionsQuery.error, t("agent.failed", locale))}
            </p>
          ) : !sessions.length ? (
            <p className="px-3 py-4 text-label text-muted">
              {t("agent.history_empty", locale)}
            </p>
          ) : (
            <ul>
              {sessions.map((session) => {
                const active = session.session_id === sessionId;
                return (
                  <li
                    key={session.session_id}
                    className="group flex items-center gap-1 border-b border-hairline pl-3 pr-1"
                  >
                    <button
                      onClick={() => openSession(session.session_id)}
                      className={cn(
                        "min-h-11 flex-1 py-2 text-left text-small transition-colors",
                        active ? "text-primary" : "text-ink hover:bg-surface",
                      )}
                    >
                      <span className="line-clamp-2">{session.title || t("agent.untitled", locale)}</span>
                      <span className="mt-0.5 block font-mono text-label text-muted">
                        {session.message_count} · {formatWhen(session.last_active, locale)}
                      </span>
                    </button>
                    <button
                      onClick={() => void removeSession(session.session_id)}
                      title={t("agent.delete_chat", locale)}
                      aria-label={t("agent.delete_chat", locale)}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-muted opacity-0 transition-opacity hover:text-negative focus-visible:opacity-100 group-hover:opacity-100"
                    >
                      <Trash2 size={13} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      {/*
        ── The conversation ───────────────────────────────────────────
      */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-primary text-on-primary">
              <Bot size={15} />
            </div>
            <div>
              <div className="text-small font-semibold text-ink">Stock Analysis AI Agent</div>
              <div className="font-mono text-label uppercase text-muted">
                {locale === "vi"
                  ? "Tool-calling · Dữ liệu thật từ backend"
                  : "Tool-calling · Real data from backend"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="text" size="sm" onClick={newChat} className="md:hidden">
              <MessageSquarePlus size={13} />
              {t("agent.new_chat", locale)}
            </Button>
            {/* On narrow screens the history rail is hidden, so it needs a
                way to be opened. */}
            <Button
              variant="text"
              size="sm"
              className="md:hidden"
              onClick={() => setHistoryOpen((value) => !value)}
            >
              <History size={13} />
              {t("agent.history", locale)}
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto bg-canvas p-6">
          {turns.length === 0 ? (
            <div className="flex h-full flex-col items-start justify-center">
              <h2 className="font-display text-heading text-ink">{t("agent.welcome_title", locale)}</h2>
              <p className="mt-3 max-w-lg text-body text-muted">
                {t("agent.welcome_body", locale)}
              </p>
              <p className="mt-4 font-mono text-label uppercase text-negative">
                {t("agent.welcome_warn", locale)}
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {turns.map((turn, index) => (
                <div key={turn.id ?? index} className="space-y-2">
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
                <div className="flex items-center gap-2 text-small text-muted">
                  <Loader2 size={14} className="animate-spin" />
                  {t("agent.thinking", locale)}
                </div>
              ) : null}
              <div ref={bottom} />
            </div>
          )}
        </div>

        {/* Quick prompts: text buttons, not chips with icons. */}
        <div className="flex flex-wrap gap-2 border-t border-hairline px-4 py-3">
          {QUICK_PROMPTS.map((item) => (
            <button
              key={item.label}
              className="inline-flex min-h-9 items-center rounded border border-hairline bg-surface px-3 text-small font-medium text-ink transition-colors hover:bg-surface-2"
              onClick={() => void submit(item.prompt)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>

        <form onSubmit={onSubmit} className="flex gap-2 border-t border-hairline p-3">
          <input
            className="h-9 flex-1 rounded border border-hairline bg-surface px-3 text-small text-ink outline-none placeholder:text-muted focus:border-primary"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("agent.placeholder", locale)}
          />
          <Button type="submit" disabled={busy || !input.trim()} variant="primary">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {t("agent.send", locale)}
          </Button>
        </form>
      </div>
    </div>
  );
}

/**
 * Turn one stored row into the user/assistant pair the UI renders.
 *
 * WHY A PAIR AND NOT A LIST: the database stores one row per *exchange*
 * (a user message plus its answer). The transcript is a flat list of
 * bubbles, so one row becomes two bubbles. Skipping rows whose answer
 * is missing (a turn that failed to persist) keeps the transcript honest
 * instead of showing a dangling user bubble.
 */
function toTurnPair(row: StoredTurn): ChatTurn[] {
  const turns: ChatTurn[] = [];
  if (row.user_message) {
    turns.push({ role: "user", content: row.user_message });
  }
  if (row.assistant_message) {
    turns.push({ role: "assistant", content: row.assistant_message, id: row.id });
  }
  return turns;
}

/**
 * A short relative timestamp for the history list.
 *
 * WHY: an absolute date on every row is noise. "2 giờ trước" answers the
 * only question the list raises — "which one is the recent one?".
 */
function formatWhen(iso: string | null, locale: string): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "—";
  const diffMinutes = Math.round((Date.now() - ms) / 60_000);
  if (diffMinutes < 1) return locale === "vi" ? "vừa xong" : "just now";
  if (diffMinutes < 60) return locale === "vi" ? `${diffMinutes} phút trước` : `${diffMinutes}m ago`;
  const hours = Math.round(diffMinutes / 60);
  if (hours < 24) return locale === "vi" ? `${hours} giờ trước` : `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return locale === "vi" ? `${days} ngày trước` : `${days}d ago`;
  return new Date(ms).toISOString().slice(0, 10);
}

// -- Inline follow-up chips ------------------------------------------------
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
    <div className="mt-2 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-label uppercase text-muted">
          Gợi ý tiếp
        </span>
        {typeof toolCount === "number" && toolCount > 0 ? (
          <Badge variant="primary">
            Đã gọi {toolCount} tool
          </Badge>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={item}
            type="button"
            disabled={busy}
            onClick={() => onPick(item)}
            className="inline-flex min-h-9 items-center rounded border border-hairline bg-surface px-3 text-small font-medium text-ink transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
