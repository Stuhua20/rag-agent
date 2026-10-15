import { request } from "./client";
import type { Conversation, DocumentScope } from "../types/conversation";
import type { ChatMessage } from "../types/chat";

export function fetchConversations() {
  return request<Conversation[]>("/api/conversations");
}

export function createConversation(title?: string, documentScope?: DocumentScope, signal?: AbortSignal) {
  return request<Conversation>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, document_scope: documentScope }),
    signal,
  });
}

export function fetchConversationMessages(conversationId: string, signal?: AbortSignal) {
  return request<ChatMessage[]>(`/api/conversations/${conversationId}/messages`, { signal });
}

export function fetchConversation(conversationId: string, signal?: AbortSignal) {
  return request<Conversation>(`/api/conversations/${conversationId}`, { signal });
}

export function updateDocumentScope(conversationId: string, documentScope: DocumentScope, revision: number, signal?: AbortSignal) {
  return request<Conversation>(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_scope: documentScope, expected_scope_revision: revision }),
    signal,
  });
}

export function deleteConversation(conversationId: string) {
  return request<{ deleted: boolean }>(`/api/conversations/${conversationId}`, { method: "DELETE" });
}

export function renameConversation(conversationId: string, title: string) {
  return request<Conversation>(`/api/conversations/${conversationId}/title`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}
