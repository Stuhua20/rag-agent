import assert from "node:assert/strict";
import test from "node:test";
import { createChatStreamParser } from "../src/utils/chatStream.ts";
import type { AgentEvent, ChatResult } from "../src/types/chat.ts";

function setup() {
  const deltas: string[] = [];
  const events: AgentEvent[] = [];
  const results: ChatResult[] = [];
  const parser = createChatStreamParser({
    onSources: () => undefined,
    onDelta: (text) => deltas.push(text),
    onDone: (_id, _answer, result) => results.push(result),
    onAgentEvent: (event) => events.push(event),
  });
  return { parser, deltas, events, results };
}

test("chunked CRLF events preserve progress, draft and full verified result", () => {
  const { parser, deltas, events, results } = setup();
  const stream = [
    'event: run_started\r\ndata: {"run_id":"run-1"}\r\n\r\n',
    'event: step_started\r\ndata: {"step_id":"execute:1","label":"检索资料"}\r\n\r\n',
    'event: delta\r\ndata: {"text":"草稿"}\r\n\r\n',
    'event: done\r\ndata: {"conversation_id":"c","answer":"校验后的答案","run_id":"run-1","status":"verification_failed","sources":[],"quality":{"agent":{"tool_calls":2}}}\r\n\r\n',
  ].join("");
  for (const character of stream) parser.push(character);
  parser.finish();
  assert.deepEqual(deltas, ["草稿"]);
  assert.equal(events[1].label, "检索资料");
  assert.equal(results[0].answer, "校验后的答案");
  assert.equal(results[0].status, "verification_failed");
  assert.deepEqual(results[0].quality, { agent: { tool_calls: 2 } });
});

test("legacy done event without agent fields remains supported", () => {
  const { parser, results } = setup();
  parser.push('event: done\ndata: {"conversation_id":"c","answer":"旧答案"}\n\n');
  parser.finish();
  assert.equal(results[0].answer, "旧答案");
  assert.equal(results[0].run_id, undefined);
});

test("premature EOF and explicit errors cannot report completion", () => {
  const { parser } = setup();
  parser.push('event: delta\ndata: {"text":"未完成"}\n\n');
  assert.throws(() => parser.finish(), /提前结束/);
  assert.throws(() => parser.push('event: error\ndata: {"message":"工具失败"}\n\n'), /工具失败/);
});

test("malformed payload and missing final answer fail clearly", () => {
  const { parser } = setup();
  assert.throws(() => parser.push('event: done\ndata: not-json\n\n'), /格式无效/);
  assert.throws(() => setup().parser.push('event: done\ndata: {"conversation_id":"c"}\n\n'), /缺少回答/);
});

test("UTF-8 decoding across byte boundaries retains Chinese content", () => {
  const { parser, results } = setup();
  const decoder = new TextDecoder();
  const bytes = new TextEncoder().encode('event: done\ndata: {"conversation_id":"c","answer":"付款条件"}\n\n');
  for (const byte of bytes) parser.push(decoder.decode(new Uint8Array([byte]), { stream: true }));
  parser.push(decoder.decode());
  parser.finish();
  assert.equal(results[0].answer, "付款条件");
});

