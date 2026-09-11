import { useVisitorOpenRouterKey } from "@/stores/keys";
import { AssistantPanel } from "./AssistantPanel";
/**
 * Mount point for the assistant panel.
 *
 * Lives in `AppShell` so one conversation spans every route — which it has
 * to, because the assistant can navigate the user between them. The button
 * that opens it is `AssistantTrigger`, in the top bar.
 */
import { useAssistantHealth } from "./useAssistant";

export function AssistantDock() {
  const health = useAssistantHealth();
  const visitorKey = useVisitorOpenRouterKey();
  if (!health.data?.enabled || !(health.data?.configured || visitorKey)) return null;
  return <AssistantPanel />;
}
