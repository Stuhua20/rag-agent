import type { ChatRequest } from "../types/chat";
import { createChatStreamParser } from "../utils/chatStream";
import type { StreamCallbacks } from "../utils/chatStream";
import { ApiError } from "./client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
    const detail = err?.detail;
    const message = typeof detail === "string" ? detail : typeof detail?.message === "string" ? detail.message : null;
    throw new ApiError(message ?? `请求失败（HTTP ${response.status}）`, response.status, typeof detail?.code === "string" ? detail.code : undefined);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("服务器没有返回有效的流式响应，请重试。");
  }

  const decoder = new TextDecoder();
  const parser = createChatStreamParser(callbacks);

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    if (error instanceof Error && (error.name === "AbortError" || error.name === "TypeError")) {
      throw new Error("回答流已中断，请重试。");
    }
    throw error;
  } finally {
    reader.releaseLock();
  }

}
