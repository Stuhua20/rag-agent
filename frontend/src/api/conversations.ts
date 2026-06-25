import { request } from "./client";
import type { Conversation } from "../types/conversation";

export function fetchConversations() {
  return request<Conversation[]>("/api/conversations");
}

