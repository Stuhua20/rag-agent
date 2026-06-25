import type { DocumentItem } from "../types/document";

type Props = {
  documents: DocumentItem[];
  selectedId?: string;
  onSelect: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
};

export default function DocumentTable({ documents, selectedId, onSelect, onDelete }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>文件名</th>
            <th>类型</th>
            <th>部门</th>
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
              <td>{document.file_name}</td>
              <td>{document.doc_type}</td>
              <td>{document.department}</td>
              <td><span className={`status ${document.status}`}>{document.status}</span></td>
              <td>{document.sheet_count}</td>
              <td>{document.chunk_count}</td>
              <td>{document.created_at}</td>
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

