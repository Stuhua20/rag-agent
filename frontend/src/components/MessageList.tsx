import type { ChatMessage } from "../types/chat";

export default function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="message-list">
      {messages.map((message) => (
        <div key={message.id} className={`message ${message.role}`}>
          <div className="message-role">{message.role === "user" ? "你" : "助手"}</div>
          <div className="message-content">{message.content}</div>
        </div>
      ))}
    </div>
  );
}

