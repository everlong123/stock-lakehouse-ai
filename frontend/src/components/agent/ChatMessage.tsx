import { Bot, User } from "lucide-react";
import { ChatTurn } from "@/types/agent";
import { cn } from "@/lib/utils";

export function ChatMessage({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";

  return (
    <div className={cn("flex items-end gap-2.5", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-soft">
          <Bot size={14} />
        </div>
      )}
      <div
        className={cn(
          "max-w-2xl rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-soft animate-slide-up",
          isUser
            ? "bg-gradient-to-br from-brand-500 to-brand-600 text-white"
            : "border border-border bg-card text-foreground",
        )}
      >
        <div className="whitespace-pre-wrap break-words">{turn.content}</div>
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <User size={14} />
        </div>
      )}
    </div>
  );
}