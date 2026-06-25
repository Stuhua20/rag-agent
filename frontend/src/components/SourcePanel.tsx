import type { SourceItem } from "../types/chat";

export default function SourcePanel({ sources }: { sources: SourceItem[] }) {
  return (
    <aside className="source-panel">
      <h2>引用来源</h2>
      {sources.length === 0 ? (
        <p className="empty">暂无引用来源</p>
      ) : (
        sources.map((source) => (
          <details key={source.chunk_id} className="source-item">
            <summary>
              {source.file_name} · {source.sheet_name}
            </summary>
            <div>行号：{source.row_start}-{source.row_end}</div>
            <div>相似度：{source.score.toFixed(2)}</div>
            <p>{source.content}</p>
          </details>
        ))
      )}
    </aside>
  );
}

