import { Bot, User } from "lucide-react";
import { ChatTurn } from "@/types/agent";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/agent/Markdown";

/**
 * A chat bubble.
 *
 * WHY THE USER BUBBLE IS A SOLID BRAND BLOCK: Yahoo's own conversational
 * surfaces (and most finance dashboards) use one solid "sender" block and
 * one flat bordered "receiver" block, so the direction of the exchange is
 * readable at a glance. There is no drop shadow ? the border and the fill
 * do the separating.
 */
export function ChatMessage({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";

  return (
    <div className={cn("flex items-end gap-2", isUser ? "justify-end" : "justify-start")}>
      {!isUser ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-primary text-on-primary">
          <Bot size={13} />
        </div>
      ) : null}
      <div
        className={cn(
          "max-w-2xl rounded px-4 py-3 text-small leading-relaxed",
          isUser
            ? "bg-primary text-on-primary"
            : "border border-hairline bg-surface text-ink",
        )}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{turn.content}</div>
        ) : (
          <Markdown source={turn.content} />
        )}
      </div>
      {isUser ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-hairline bg-surface-2 text-muted">
          <User size={13} />
        </div>
      ) : null}
    </div>
  );
}
