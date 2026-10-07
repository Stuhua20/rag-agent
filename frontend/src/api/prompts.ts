import { request } from "./client";
import type { PromptDetail, PromptSummary } from "../types/prompt";

function encodePromptPath(path: string) {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function fetchPrompts() {
  return request<PromptSummary[]>("/api/prompts");
}

export function fetchPrompt(path: string) {
  return request<PromptDetail>(`/api/prompts/${encodePromptPath(path)}`);
}

export function savePrompt(path: string, content: string) {
  return request<PromptDetail>(`/api/prompts/${encodePromptPath(path)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}
