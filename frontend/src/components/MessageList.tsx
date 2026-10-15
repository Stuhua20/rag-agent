import { Fragment, useLayoutEffect, useRef, useState } from "react";
import AnswerCard from "./AnswerCard";
import ChatIcon from "./ChatIcon";
import { useToast } from "./Toast";
import type { ChatMessage } from "../types/chat";
import { answerContent } from "../utils/answerPresentation";

type Props = {
  messages: ChatMessage[];
  loading: boolean;
  activeSource?: { messageId: string; chunkId: string } | null;
  panelId: string;
  onSelectSource: (messageId: string, chunkId: string, opener: HTMLButtonElement) => void;
  onCloseSources: () => void;
};

export default function MessageList({ messages, loading, activeSource, panelId, onSelectSource, onCloseSources }: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const followingRef = useRef(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const { toast } = useToast();

  useLayoutEffect(() => {
    if (followingRef.current) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, loading]);

  async function copyMessage(message: ChatMessage) {
    try {
      await navigator.clipboard.writeText(message.role === "assistant" ? answerContent(message) : message.content);
      setCopiedId(message.id);
      window.setTimeout(() => setCopiedId(null), 1200);
    } catch {
      toast("复制失败，请选择正文手动复制。", "error");
    }
  }

  const lastMessage = messages[messages.length - 1];
  const hasPendingAssistant =
    loading &&
    lastMessage?.role === "assistant";

  return (
    <div className="message-list" ref={listRef} onScroll={() => {
      const list = listRef.current;
      if (list) followingRef.current = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
    }}>
      {messages.map((message, index) => (
        <Fragment key={message.id}>
        {(message.scope_revision ?? 0) > 0 && (index === 0 || (messages[index - 1].scope_revision ?? 0) !== message.scope_revision) && (
          <div className="scope-history-marker">检索范围已更新 · {message.document_scope?.mode === "selected" ? `指定 ${message.document_scope.document_ids.length} 个文档` : "全部文档"} · 上下文重新开始</div>
        )}
        <div className={`message-row ${message.role}`}>
          <div className={`message ${message.role}`}>
            <div className="message-header">
              <span className="message-author">{message.role === "assistant" && <span className="assistant-avatar">AI</span>}{message.role === "user" ? "你" : "知识库助手"}</span>
              <span>{formatRelativeTime(message.created_at)}</span>
            </div>
            {message.role === "assistant" ? (
              <AnswerCard
                message={message}
                activeSourceId={activeSource?.messageId === message.id ? activeSource.chunkId : undefined}
                panelId={panelId}
                onSelectSource={(chunkId, opener) => onSelectSource(message.id, chunkId, opener)}
              />
            ) : (
              <div className="message-content">{message.content}</div>
            )}
            <div className="message-actions">
              {message.content.trim().length > 0 && (
                <button type="button" className="copy-message" onClick={() => copyMessage(message)}>
                  <ChatIcon name="copy" />{copiedId === message.id ? "已复制" : message.role === "assistant" ? "复制回答" : "复制"}
                </button>
              )}
              {message.role === "assistant" && Boolean(message.sources?.length) && (
                <button type="button" className="copy-message" aria-expanded={activeSource?.messageId === message.id} aria-controls={activeSource?.messageId === message.id ? panelId : undefined} onClick={(event) => {
                  if (activeSource?.messageId === message.id) onCloseSources();
                  else onSelectSource(message.id, message.sources![0].chunk_id, event.currentTarget);
                }}>
                  <ChatIcon name="panel" />{activeSource?.messageId === message.id ? "收起来源" : "查看来源"}
                </button>
              )}
            </div>
          </div>
        </div>
        </Fragment>
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
