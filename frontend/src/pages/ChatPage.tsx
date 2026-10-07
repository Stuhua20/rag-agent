import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { sendChatMessageStream } from "../api/chat";
import { fetchConversationMessages } from "../api/conversations";
import ChatWindow from "../components/ChatWindow";
import { useToast } from "../components/Toast";
import type { ChatMessage } from "../types/chat";

const initialMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content: "可以开始提问了。我会检索已上传的 Excel、CSV、文字型 PDF 或 Word，并在回答下方显示引用证据。",
    created_at: new Date().toISOString(),
  },
];

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [loading, setLoading] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const messageCountRef = useRef(0);
  const routeConversationId = searchParams.get("conversationId");
  const streamControllerRef = useRef<AbortController | null>(null);

  const resetConversation = useCallback(() => {
    setConversationId(null);
    setMessages(initialMessages);
    messageCountRef.current = 0;
  }, []);

  useEffect(() => {
    return () => {
      streamControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!routeConversationId) {
      resetConversation();
      return;
    }

    const selectedConversationId = routeConversationId;
    let ignore = false;
    async function loadConversation() {
      setConversationId(selectedConversationId);
      try {
        const history = await fetchConversationMessages(selectedConversationId);
        if (!ignore) {
          setMessages(history.length ? history : initialMessages);
          messageCountRef.current = history.length;
        }
      } catch {
        if (!ignore) {
          toast("加载会话历史失败", "error");
        }
      }
    }
    loadConversation();
    return () => {
      ignore = true;
    };
  }, [resetConversation, routeConversationId, toast]);

  async function handleSend(question: string) {
    const isFirstMessage = messageCountRef.current === 0;
    const userMessage: ChatMessage = {
      id: `local_user_${Date.now()}`,
      role: "user",
      content: question,
      created_at: new Date().toISOString(),
    };

    const assistantId = `local_assistant_${Date.now()}`;
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: undefined,
      created_at: new Date().toISOString(),
    };

    const controller = new AbortController();
    streamControllerRef.current = controller;
    setMessages((current) => [...current, userMessage, assistantMessage]);
    setLoading(true);

    try {
      await sendChatMessageStream(
        { conversation_id: conversationId, question, top_k: 5 },
        {
          onSources(convId, sources) {
            setConversationId(convId);
            setMessages((current) =>
              current.map((msg) =>
                msg.id === assistantId ? { ...msg, sources } : msg,
              ),
            );
          },
          onDelta(text) {
            setMessages((current) =>
              current.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, content: msg.content + text }
                  : msg,
              ),
            );
          },
          onDone(convId, answer) {
            setConversationId(convId);
            setMessages((current) =>
              current.map((msg) =>
                msg.id === assistantId ? { ...msg, content: answer } : msg,
              ),
            );
            messageCountRef.current += 2;
            window.dispatchEvent(new Event("conversations:changed"));
            if (isFirstMessage || conversationId !== convId) {
              navigate(`/?conversationId=${convId}`, { replace: true });
            }
          },
        },
        controller.signal,
      );
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "回答流中断，请重试。";
      setMessages((current) =>
        current.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: msg.content
                  ? `${msg.content}\n\n> ⚠️ ${message}`
                  : `⚠️ ${message}`,
              }
            : msg,
        ),
      );
      toast(message, "error");
      return false;
    } finally {
      if (streamControllerRef.current === controller) {
        streamControllerRef.current = null;
      }
      setLoading(false);
    }
  }

  return (
    <div className="workspace chat-workspace">
      <section className="chat-layout">
        <ChatWindow messages={messages} loading={loading} onSend={handleSend} />
      </section>
    </div>
  );
}
