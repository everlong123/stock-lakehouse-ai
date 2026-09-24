import { ChatBox } from "@/components/agent/ChatBox";
import { PageTitle } from "@/components/common/PageTitle";

export function AIAgentPage() {
  return (
    <div className="space-y-4">
      <PageTitle
        title="AI Agent"
        subtitle="Agent gọi tool backend. Không bịa giá, indicator, forecast hay backtest metrics."
      />
      <ChatBox />
    </div>
  );
}
