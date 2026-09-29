import { ChatTurn } from "@/types/agent";

export function ChatMessage({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm ${
          isUser ? "bg-primary text-primary-foreground" : "border border-border bg-card"
        }`}
      >
        {turn.content}
      </div>
    </div>
  );
}
