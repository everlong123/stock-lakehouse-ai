import { ChatBox } from "@/components/agent/ChatBox";
import { PageHeader } from "@/components/common/PageHeader";
import { useI18n, t } from "@/lib/i18n";

export function AIAgentPage() {
  const { locale } = useI18n();
  return (
    <div className="space-y-4">
      <PageHeader
        section="Công cụ"
        title={t("agent.title", locale)}
        subtitle={t("agent.subtitle", locale)}
      />
      <ChatBox />
    </div>
  );
}