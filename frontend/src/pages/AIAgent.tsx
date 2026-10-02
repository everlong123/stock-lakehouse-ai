import { ChatBox } from "@/components/agent/ChatBox";
import { PageTitle } from "@/components/common/PageTitle";

export function AIAgentPage() {
  return (
    <div className="space-y-4">
      <PageTitle
        title="AI Agent"
        subtitle="Agent goi tool backend. Khong bia gia, indicator, forecast hay backtest metrics."
        meta="06 · Agent"
      />
      <ChatBox />
    </div>
  );
}