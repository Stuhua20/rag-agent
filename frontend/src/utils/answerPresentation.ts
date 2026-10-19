import type { ChatMessage, SourceItem } from "../types/chat";

export function answerContent(message: ChatMessage) {
  if (!message.sources?.length) return message.content;
  const lines = message.content.split(/\r?\n/);
  const referenceStart = lines.findIndex((line) =>
    /^参考来源[:：]?$/.test(line.trim().replace(/^#+\s*/, "").replace(/\*\*/g, "")),
  );
  const content = referenceStart === -1 ? message.content : lines.slice(0, referenceStart).join("\n");
  return content
    .replace(/[ \t　]*[（(]?[ \t]*\[?来源[ \t]*\d+(?:[ \t]*[-—~至,，、][ \t]*\d+)*\]?[ \t]*[）)]?/g, "")
    .replace(/([：:；;，,、])[ \t]*([。；;，,、])/g, "$2")
    .replace(/[ \t]+([。；;，,、])/g, "$1")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

export function sourceLocation(source: SourceItem) {
  const range = source.row_start === source.row_end ? `${source.row_start}` : `${source.row_start}—${source.row_end}`;
  const position = /\.(pdf|docx)$/i.test(source.file_name) ? `第 ${range} 个内容块` : `第 ${range} 行`;
  return [source.sheet_name, position].filter(Boolean).join(" · ");
}

export function sourceScoreLabel(source: SourceItem) {
  if (source.score_type === "exact_match") return "确定性匹配：全量计算命中";
  if (source.score_type === "rrf") return `融合排序分：${source.score.toFixed(5)}（用于排名）`;
  if (source.score_type === "bm25") return `关键词得分：${source.score.toFixed(3)}（用于排名）`;
  return `检索相似度：${source.score.toFixed(3)}`;
}

export function groupSources(sources: SourceItem[]) {
  const groups = new Map<string, SourceItem[]>();
  for (const source of sources) {
    const key = source.document_id || source.file_name;
    const group = groups.get(key);
    if (group) group.push(source);
    else groups.set(key, [source]);
  }
  return Array.from(groups.values());
}
