import type { ChunkItem, SheetItem } from "../types/document";

export default function SheetPreview({ sheets, chunks }: { sheets: SheetItem[]; chunks: ChunkItem[] }) {
  return (
    <section className="preview-panel">
      <div>
        <h3>Sheets</h3>
        {sheets.length === 0 ? (
          <p className="empty">请选择文件查看 sheet</p>
        ) : (
          sheets.map((sheet) => (
            <div key={sheet.id} className="mini-card">
              <strong>{sheet.sheet_name}</strong>
              <span>{sheet.row_count} 行 · {sheet.column_count} 列</span>
              <small>表头：{sheet.headers.join("，")}</small>
            </div>
          ))
        )}
      </div>
      <div>
        <h3>Chunks</h3>
        {chunks.length === 0 ? (
          <p className="empty">暂无 chunk</p>
        ) : (
          chunks.map((chunk) => (
            <details key={chunk.id} className="mini-card">
              <summary>{chunk.title}</summary>
              <pre>{chunk.content}</pre>
            </details>
          ))
        )}
      </div>
    </section>
  );
}

