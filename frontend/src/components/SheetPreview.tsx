import type { ChunkItem, SheetItem } from "../types/document";

type Props = {
  sheets: SheetItem[];
  chunks: ChunkItem[];
  warnings?: string[];
  textDocument: boolean;
};

export default function SheetPreview({ sheets, chunks, warnings = [], textDocument }: Props) {
  return (
    <section className="document-preview-content" aria-label="文件解析内容">
      {warnings.length > 0 && (
        <div className="inline-warning" role="status">
          <strong>解析提示</strong>
          <ul>
            {warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      )}
      <details className="document-preview-sheets">
        <summary>{textDocument ? "页面与章节" : "工作表信息"}（{sheets.length}）</summary>
        {sheets.length === 0 ? (
          <p className="empty">暂无{textDocument ? "页面或章节" : "工作表"}信息</p>
        ) : (
          sheets.map((sheet) => (
            <div key={sheet.id} className="document-preview-sheet">
              <strong>{sheet.sheet_name}</strong>
              <span>{textDocument ? `${sheet.row_count} 条文本内容` : `${sheet.row_count} 行 · ${sheet.column_count} 列`}</span>
              {!textDocument && <small>表头：{sheet.headers.join("，")}</small>}
            </div>
          ))
        )}
      </details>
      <div>
        <h3>解析内容</h3>
        {chunks.length === 0 ? (
          <p className="empty">暂无可展示的解析内容</p>
        ) : (
          chunks.map((chunk, index) => (
            <details key={chunk.id} className="document-preview-chunk" open={index === 0}>
              <summary>{chunk.title}</summary>
              <pre>{chunk.content}</pre>
            </details>
          ))
        )}
      </div>
    </section>
  );
}
