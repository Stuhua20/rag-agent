import { request } from "./client";
import type { ChatRequest, ChatResponse } from "../types/chat";

export function sendChatMessage(payload: ChatRequest) {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
