import MessageInput from "./MessageInput";
import MessageList from "./MessageList";
import type { ChatMessage } from "../types/chat";

type Props = {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (question: string) => Promise<void>;
};

export default function ChatWindow({ messages, loading, onSend }: Props) {
  return (
    <section className="chat-window">
      <MessageList messages={messages} />
      <MessageInput disabled={loading} onSend={onSend} />
    </section>
  );
}
