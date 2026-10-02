import { Bot, User } from "lucide-react";
import { ChatTurn } from "@/types/agent";
import { cn } from "@/lib/utils";

export function ChatMessage({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";

  return (
    <div className={cn("flex items-end gap-2.5", isUser ? "justify-end" : "justify-start")}>
      {!isUser ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-foreground text-background">
          <Bot size={13} />
        </div>
      ) : null}
      <div
        className={cn(
          "max-w-2xl rounded-md px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-foreground text-background"
            : "border border-border bg-card text-foreground",
        )}
      >
        <div className="whitespace-pre-wrap break-words">{turn.content}</div>
      </div>
      {isUser ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <User size={13} />
        </div>
      ) : null}
    </div>
  );
}