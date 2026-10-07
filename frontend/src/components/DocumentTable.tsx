import type { DocumentItem } from "../types/document";

type Props = {
  documents: DocumentItem[];
  selectedId?: string;
  onSelect: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
};

export default function DocumentTable({ documents, selectedId, onSelect, onDelete }: Props) {
  return (
    <div className="table-wrap document-table-wrap">
      <table className="document-table">
        <colgroup>
          <col className="doc-col-name" />
          <col className="doc-col-status" />
          <col className="doc-col-count" />
          <col className="doc-col-count" />
          <col className="doc-col-date" />
          <col className="doc-col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>文件名</th>
            <th>状态</th>
            <th>Sheets</th>
            <th>Chunks</th>
            <th>上传时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id} className={selectedId === document.id ? "selected-row" : ""}>
              <td className="document-name" title={document.file_name}>{document.file_name}</td>
              <td><span className={`status ${document.status}`}>{document.status}</span></td>
              <td className="numeric-cell">{document.sheet_count}</td>
              <td className="numeric-cell">{document.chunk_count}</td>
              <td className="date-cell">{formatDateTime(document.created_at)}</td>
              <td className="actions">
                <button type="button" onClick={() => onSelect(document)}>查看</button>
                <button type="button" onClick={() => onDelete(document)}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {documents.length === 0 && <p className="empty">暂无文件</p>}
    </div>
  );
}

function formatDateTime(value: string) {
  return value.replace("T", " ");
}
