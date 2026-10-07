import { request } from "./client";
import type { Conversation } from "../types/conversation";
import type { ChatMessage } from "../types/chat";

export function fetchConversations() {
  return request<Conversation[]>("/api/conversations");
}

export function createConversation(title?: string) {
  return request<Conversation>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export function fetchConversationMessages(conversationId: string) {
  return request<ChatMessage[]>(`/api/conversations/${conversationId}/messages`);
}

export function deleteConversation(conversationId: string) {
  return request<{ deleted: boolean }>(`/api/conversations/${conversationId}`, { method: "DELETE" });
}
