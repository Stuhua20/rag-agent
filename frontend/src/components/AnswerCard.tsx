import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types/chat";

export default function AnswerCard({ message }: { message: ChatMessage }) {
  const sources = message.sources;
  const hasSources = Array.isArray(sources) && sources.length > 0;
  const isStreaming = sources === undefined;
  const content = isStreaming
    ? message.content
    : hasSources
      ? stripCitationText(stripReferenceSection(message.content))
      : message.content;
  const [citationsOpen, setCitationsOpen] = useState(false);

  return (
    <article className="answer-card">
      <header className="answer-card-header">
        <span>回答</span>
        {hasSources && <span>{sources!.length} 条引用</span>}
      </header>
      <div className="answer-card-body">
        {content ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ node, children, ...props }) => (
                <div className="markdown-table-wrap">
                  <table {...props}>{children}</table>
                </div>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        ) : (
          <span className="typing-indicator"><span>AI 正在思考</span><i /><i /><i /></span>
        )}
      </div>
      {hasSources && (
        <section className="answer-citations">
          <div className="answer-divider" />
          <button
            type="button"
            className="citation-toggle"
            aria-expanded={citationsOpen}
            onClick={() => setCitationsOpen((open) => !open)}
          >
            <span>引用来源</span>
            <span>{citationsOpen ? "收起" : `展开 ${sources!.length} 条`}</span>
          </button>
          {citationsOpen && (
            <div className="citation-list">
              {sources!.map((source, index) => (
                <details key={source.chunk_id} className="citation-item">
                  <summary>
                    <span className="citation-index">[{index + 1}]</span>
                    <span className="citation-source">
                      {source.file_name} · {source.sheet_name} · 行 {source.row_start}-{source.row_end}
                    </span>
                    <span className="citation-action">查看详情</span>
                  </summary>
                  <div className="citation-evidence">
                    <div>
                      {source.score_type === "exact_match"
                        ? "确定性匹配：全量计算命中"
                        : `相似度：${source.score.toFixed(3)}`}
                    </div>
                    <pre>{source.content}</pre>
                  </div>
                </details>
              ))}
            </div>
          )}
        </section>
      )}
    </article>
  );
}

function stripReferenceSection(content: string) {
  const lines = content.split(/\r?\n/);
  const referenceStartIndex = lines.findIndex((line) => {
    const normalized = line.trim().replace(/^#+\s*/, "").replace(/\*\*/g, "");
    return /^参考来源[:：]?$/.test(normalized);
  });

  if (referenceStartIndex === -1) {
    return content;
  }

  return lines.slice(0, referenceStartIndex).join("\n").trim();
}

function stripCitationText(content: string) {
  return content
    .replace(/[\s　]*[（(]?\s*\[?来源\s*\d+(?:\s*[-—~至,，、]\s*\d+)*\]?\s*[）)]?/g, "")
    .replace(/([：:；;，,、])\s*([。；;，,、])/g, "$2")
    .replace(/\s+([。；;，,、])/g, "$1")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}
