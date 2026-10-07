import { useLayoutEffect, useRef, useState } from "react";
import AnswerCard from "./AnswerCard";
import type { ChatMessage } from "../types/chat";

export default function MessageList({ messages, loading }: { messages: ChatMessage[]; loading: boolean }) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useLayoutEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, loading]);

  async function copyMessage(message: ChatMessage) {
    await navigator.clipboard.writeText(message.content);
    setCopiedId(message.id);
    window.setTimeout(() => setCopiedId(null), 1200);
  }

  const lastMessage = messages[messages.length - 1];
  const hasPendingAssistant =
    loading &&
    lastMessage?.role === "assistant";

  return (
    <div className="message-list">
      {messages.map((message) => (
        <div key={message.id} className={`message-row ${message.role}`}>
          <div className={`message ${message.role}`}>
            <div className="message-header">
              <span>{message.role === "user" ? "你" : "AI"}</span>
              <span>{formatRelativeTime(message.created_at)}</span>
            </div>
            {message.role === "assistant" ? (
              <AnswerCard message={message} />
            ) : (
              <div className="message-content">{message.content}</div>
            )}
            {message.content.trim().length > 0 && (
              <button type="button" className="copy-message" onClick={() => copyMessage(message)}>
                {copiedId === message.id ? "已复制" : "复制"}
              </button>
            )}
          </div>
        </div>
      ))}
      {loading && !hasPendingAssistant && (
        <div className="message-row assistant">
          <div className="message assistant typing-message">
            <div className="message-header">
              <span>AI</span>
              <span>刚刚</span>
            </div>
            <div className="typing-indicator">
              <span>AI 正在思考</span>
              <i />
              <i />
              <i />
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function formatRelativeTime(value?: string) {
  if (!value) return "刚刚";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "刚刚";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return "刚刚";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  return `${days}天前`;
}
