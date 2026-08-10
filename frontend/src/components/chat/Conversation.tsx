import type { ChatMessage } from "../../types/agent";
import { MessageBubble } from "./MessageBubble";

export function Conversation({
  messages,
  onRetry,
}: {
  messages: ChatMessage[];
  onRetry: (query: string) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-3 py-5 sm:px-6 sm:py-7 lg:px-8">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} onRetry={onRetry} />
      ))}
    </div>
  );
}
