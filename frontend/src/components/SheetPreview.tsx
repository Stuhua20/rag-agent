import type { ChunkItem, SheetItem } from "../types/document";

type Props = {
  sheets: SheetItem[];
  chunks: ChunkItem[];
  warnings?: string[];
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
};

export default function SheetPreview({ sheets, chunks, warnings = [], loading = false, error = "", onRetry }: Props) {
  return (
    <section className="preview-panel">
      {loading ? (
        <p className="empty">正在加载文件预览...</p>
      ) : error ? (
        <div className="inline-error preview-error" role="alert">
          <span>{error}</span>
          {onRetry && <button type="button" onClick={onRetry}>重试</button>}
        </div>
      ) : (
        <>
          {warnings.length > 0 && (
            <div className="inline-warning" role="status">
              <strong>解析提示</strong>
              <ul>
                {warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </div>
          )}
          <div>
            <h3>Sheets</h3>
            {sheets.length === 0 ? (
              <p className="empty">暂无 sheet</p>
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
        </>
      )}
    </section>
  );
}
