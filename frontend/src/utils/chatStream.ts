import type { AgentEvent, ChatResult, SourceItem } from "../types/chat";

export type StreamCallbacks = {
  onSources: (conversationId: string, sources: SourceItem[]) => void;
  onDelta: (text: string) => void;
  onDone: (conversationId: string, answer: string, result: ChatResult) => void;
  onAgentEvent?: (event: AgentEvent) => void;
};

/** Parse complete SSE frames, including CRLF, UTF-8 decoder chunk boundaries and final EOF. */
export function createChatStreamParser(callbacks: StreamCallbacks) {
  let buffer = "";
  let receivedDone = false;

  function frame(value: string) {
    let event = "";
    const lines = [];
    for (const line of value.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) lines.push(line.slice(5).trimStart());
    }
    if (lines.length === 0) return;
    if (receivedDone) throw new Error("回答结束后收到额外事件，请重试。");
    let data: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(lines.join("\n"));
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("invalid payload");
      data = parsed as Record<string, unknown>;
    } catch {
      throw new Error("流式响应格式无效，请重试。");
    }
    switch (event) {
      case "sources":
        if (typeof data.conversation_id !== "string" || !Array.isArray(data.sources)) throw new Error("流式响应缺少引用信息，请重试。");
        callbacks.onSources(data.conversation_id, data.sources as SourceItem[]);
        break;
      case "delta":
        if (typeof data.text === "string") callbacks.onDelta(data.text);
        break;
      case "done": {
        if (typeof data.conversation_id !== "string" || typeof data.answer !== "string") throw new Error("流式响应缺少回答结果，请重试。");
        const result: ChatResult = {
          conversation_id: data.conversation_id, answer: data.answer,
          sources: Array.isArray(data.sources) ? data.sources as SourceItem[] : undefined,
          quality: data.quality && typeof data.quality === "object" ? data.quality as Record<string, unknown> : undefined,
          run_id: typeof data.run_id === "string" ? data.run_id : undefined,
          status: typeof data.status === "string" ? data.status : undefined,
        };
        receivedDone = true;
        callbacks.onDone(result.conversation_id, result.answer, result);
        break;
      }
      case "error":
        throw new Error(typeof data.message === "string" ? data.message : "服务端生成回答失败，请重试。");
      case "run_started":
      case "plan":
      case "step_started":
      case "step_done":
        callbacks.onAgentEvent?.({ event, run_id: typeof data.run_id === "string" ? data.run_id : undefined,
          step_id: typeof data.step_id === "string" ? data.step_id : undefined,
          label: typeof data.label === "string" ? data.label : undefined });
        break;
    }
  }

  return {
    push(text: string) {
      buffer += text;
      // Normalize CRLF only when complete, so a split CR/LF pair survives chunk boundaries.
      buffer = buffer.replace(/\r\n/g, "\n");
      let index: number;
      while ((index = buffer.indexOf("\n\n")) >= 0) {
        frame(buffer.slice(0, index));
        buffer = buffer.slice(index + 2);
      }
    },
    finish() {
      if (buffer.trim()) frame(buffer);
      if (!receivedDone) throw new Error("回答流提前结束，请重试。");
    },
  };
}
