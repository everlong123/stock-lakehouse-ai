import { ChatBox } from "@/components/agent/ChatBox";
import { PageTitle } from "@/components/common/PageTitle";
import { useI18n, t } from "@/lib/i18n";

export function AIAgentPage() {
  const { locale } = useI18n();
  return (
    <div className="space-y-4">
      <PageTitle
        title={t("agent.title", locale)}
        subtitle={t("agent.subtitle", locale)}
        meta="06 · Agent"
      />
      <ChatBox />
    </div>
  );
}