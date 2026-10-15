import type { ChatRequest, SourceItem } from "../types/chat";
import { ApiError } from "./client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type StreamCallbacks = {
  onSources: (conversationId: string, sources: SourceItem[]) => void;
  onDelta: (text: string) => void;
  onDone: (conversationId: string, answer: string) => void;
};

type StreamPayload = {
  conversation_id?: unknown;
  sources?: unknown;
  text?: unknown;
  answer?: unknown;
  message?: unknown;
};

export async function sendChatMessageStream(
  payload: ChatRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("回答流已中断，请重试。");
    }
    throw new Error("无法连接后端服务，请确认后端已启动。");
  }

  if (!response.ok) {
    const err = await response.json().catch(() => null);
    const detail = err && typeof err.detail === "string" ? err.detail : null;
    throw new ApiError(detail ?? `请求失败（HTTP ${response.status}）`, response.status);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("服务器没有返回有效的流式响应，请重试。");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";
  let receivedDone = false;

  function processLine(rawLine: string) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.startsWith("event:")) {
      currentEvent = line.slice(6).trim();
      return;
    }
    if (!line.startsWith("data:")) return;

    const dataStr = line.slice(5).trim();
    if (!dataStr) return;

    let data: StreamPayload;
    try {
      const parsed: unknown = JSON.parse(dataStr);
      if (!parsed || typeof parsed !== "object") {
        throw new Error("not an object");
      }
      data = parsed as StreamPayload;
    } catch {
      throw new Error("流式响应格式无效，请重试。");
    }

    switch (currentEvent) {
      case "sources":
        if (typeof data.conversation_id !== "string" || !Array.isArray(data.sources)) {
          throw new Error("流式响应缺少引用信息，请重试。");
        }
        callbacks.onSources(data.conversation_id, data.sources as SourceItem[]);
        break;
      case "delta":
        if (typeof data.text === "string") callbacks.onDelta(data.text);
        break;
      case "done":
        if (typeof data.conversation_id !== "string" || typeof data.answer !== "string") {
          throw new Error("流式响应缺少回答结果，请重试。");
        }
        receivedDone = true;
        callbacks.onDone(data.conversation_id, data.answer);
        break;
      case "error":
        throw new Error(typeof data.message === "string" ? data.message : "服务端生成回答失败，请重试。");
    }
    currentEvent = "";
  }

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) processLine(line);
    }
    buffer += decoder.decode();
    if (buffer) {
      for (const line of buffer.split("\n")) processLine(line);
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    if (error instanceof Error && (error.name === "AbortError" || error.name === "TypeError")) {
      throw new Error("回答流已中断，请重试。");
    }
    throw error;
  } finally {
    reader.releaseLock();
  }

  if (!receivedDone) {
    throw new Error("回答流提前结束，请重试。");
  }
}
