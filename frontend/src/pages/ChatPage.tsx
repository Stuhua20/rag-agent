import { useState } from "react";
import { sendChatMessage } from "../api/chat";
import ChatWindow from "../components/ChatWindow";
import SourcePanel from "../components/SourcePanel";
import type { ChatMessage, SourceItem } from "../types/chat";

const initialMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content: "可以开始提问了。我会检索已上传的 Excel/CSV 知识库，并在右侧显示引用来源。",
  },
];

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSend(question: string) {
    const userMessage: ChatMessage = {
      id: `local_user_${Date.now()}`,
      role: "user",
      content: question,
    };
    setMessages((current) => [...current, userMessage]);
    setLoading(true);
    try {
      const response = await sendChatMessage({
        conversation_id: conversationId,
        question,
        top_k: 5,
      });
      setConversationId(response.conversation_id);
      setSources(response.sources);
      setMessages((current) => [
        ...current,
        {
          id: `local_assistant_${Date.now()}`,
          role: "assistant",
          content: response.answer,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: `local_error_${Date.now()}`,
          role: "assistant",
          content: error instanceof Error ? error.message : "请求失败",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="workspace three-column">
      <ChatWindow messages={messages} loading={loading} onSend={handleSend} />
      <SourcePanel sources={sources} />
    </div>
  );
}
