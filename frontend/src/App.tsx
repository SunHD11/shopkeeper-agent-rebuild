import { useEffect, useRef, useState } from "react";
import { Composer } from "./components/chat/Composer";
import { Conversation } from "./components/chat/Conversation";
import { EmptyState } from "./components/chat/EmptyState";
import { AppHeader } from "./components/layout/AppHeader";
import { AppSidebar } from "./components/layout/AppSidebar";
import { examples } from "./data/examples";
import { useAgentQuery } from "./hooks/useAgentQuery";
import { useServiceHealth } from "./hooks/useServiceHealth";

export default function App() {
  const [draft, setDraft] = useState("");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const agent = useAgentQuery();
  const health = useServiceHealth();

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [agent.messages]);

  const submitDraft = () => {
    const query = draft.trim();
    if (!query || agent.isStreaming) return;
    setDraft("");
    void agent.submit(query);
  };

  const submitExample = (example: string) => {
    if (agent.isStreaming) return;
    setMobileMenuOpen(false);
    void agent.submit(example);
  };

  const clearConversation = () => {
    agent.clear();
    setDraft("");
    setMobileMenuOpen(false);
  };

  const sidebarProps = {
    examples,
    disabled: agent.isStreaming,
    completedCount: agent.completedCount,
    health: health.state,
    onRefreshHealth: () => void health.refresh(),
    onExample: submitExample,
    onNew: clearConversation,
  };

  return (
    <div className="relative h-dvh overflow-hidden bg-canvas text-ink">
      <div className="ledger-grid pointer-events-none fixed inset-0" />
      <div className="grain pointer-events-none fixed inset-0" />

      <div className="relative grid h-full min-h-0 overflow-hidden md:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)]">
        <AppSidebar {...sidebarProps} className="hidden md:flex" />

        <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <AppHeader
            hasMessages={agent.messages.length > 0}
            isStreaming={agent.isStreaming}
            health={health.state}
            onRefreshHealth={() => void health.refresh()}
            onOpenMenu={() => setMobileMenuOpen(true)}
            onClear={clearConversation}
          />

          <div
            ref={scrollRef}
            className="scrollbar-thin min-h-0 flex-1 overflow-y-auto overscroll-contain"
            aria-live="polite"
          >
            {agent.messages.length === 0 ? (
              <EmptyState examples={examples} onUseExample={submitExample} />
            ) : (
              <Conversation
                messages={agent.messages}
                onRetry={(query) => void agent.retry(query)}
              />
            )}
          </div>

          <Composer
            value={draft}
            isStreaming={agent.isStreaming}
            onChange={setDraft}
            onSubmit={submitDraft}
            onStop={agent.stop}
          />
        </main>
      </div>

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-ink/35 backdrop-blur-sm"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="关闭导航"
          />
          <AppSidebar
            {...sidebarProps}
            className="absolute inset-y-0 left-0 flex w-[min(88vw,320px)] shadow-floating"
          />
        </div>
      )}
    </div>
  );
}
