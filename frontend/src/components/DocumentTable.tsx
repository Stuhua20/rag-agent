import { useEffect, useRef } from "react";
import type { DocumentItem } from "../types/document";

const STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传", parsing: "解析中", chunking: "整理内容中", embedding: "建立索引中", indexed: "已入库", failed: "处理失败",
};

type Props = {
  documents: DocumentItem[];
  selectedId?: string;
  onSelect: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
  checkedIds: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  disabled: boolean;
};

export default function DocumentTable({ documents, selectedId, onSelect, onDelete, checkedIds, onToggle, onToggleAll, disabled }: Props) {
  const tableRef = useRef<HTMLDivElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const checkedCount = documents.filter((item) => checkedIds.has(item.id)).length;
  const allChecked = documents.length > 0 && checkedCount === documents.length;

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = checkedCount > 0 && !allChecked;
  }, [checkedCount, allChecked]);

  useEffect(() => {
    function closeMenus(event: PointerEvent | KeyboardEvent) {
      const escape = event instanceof KeyboardEvent && event.key === "Escape";
      if (event instanceof KeyboardEvent && !escape) return;
      tableRef.current?.querySelectorAll<HTMLDetailsElement>("details[open]").forEach((menu) => {
        if (escape || (event.target instanceof Node && !menu.contains(event.target))) {
          menu.open = false;
          if (escape) menu.querySelector("summary")?.focus();
        }
      });
    }
    document.addEventListener("pointerdown", closeMenus);
    document.addEventListener("keydown", closeMenus);
    return () => {
      document.removeEventListener("pointerdown", closeMenus);
      document.removeEventListener("keydown", closeMenus);
    };
  }, []);

  return (
    <div className="table-wrap document-table-wrap" ref={tableRef}>
      <table className="document-table">
        <colgroup>
          <col className="doc-col-check" />
          <col className="doc-col-name" />
          <col className="doc-col-type" />
          <col className="doc-col-status" />
          <col className="doc-col-count" />
          <col className="doc-col-count" />
          <col className="doc-col-date" />
          <col className="doc-col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th className="document-check-cell">
              <input ref={selectAllRef} type="checkbox" className="document-checkbox" aria-label="全选当前搜索结果" checked={allChecked} disabled={disabled || !documents.length} onChange={onToggleAll} />
            </th>
            <th>文件名</th>
            <th>文件类型</th>
            <th>状态</th>
            <th>Sheets</th>
            <th>Chunks</th>
            <th>上传时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id} className={selectedId === document.id || checkedIds.has(document.id) ? "selected-row" : ""}>
              <td className="document-check-cell">
                <input type="checkbox" className="document-checkbox" aria-label={`选择 ${document.source_relative_path || document.file_name}`} checked={checkedIds.has(document.id)} disabled={disabled} onChange={() => onToggle(document.id)} />
              </td>
              <td className="document-name" title={document.file_name}>
                {document.file_name}
                {document.source_relative_path && <span className="document-source-path">{document.source_relative_path}</span>}
              </td>
              <td>{document.file_type.toUpperCase()}</td>
              <td><span className={`status ${document.status}`}>{STATUS_LABELS[document.status] ?? "未知状态"}</span></td>
              <td className="numeric-cell">{document.sheet_count}</td>
              <td className="numeric-cell">{document.chunk_count}</td>
              <td className="date-cell">{formatDateTime(document.created_at)}</td>
              <td className="document-row-actions">
                <button type="button" className="document-view-button" disabled={disabled} onClick={() => onSelect(document)}>查看</button>
                <details className="document-row-more" name="document-row-actions">
                  <summary aria-label={`更多操作：${document.file_name}`} aria-disabled={disabled} onClick={(event) => { if (disabled) event.preventDefault(); }}>⋯</summary>
                  <div className="document-row-menu">
                    <button type="button" disabled={disabled} onClick={(event) => {
                      const menu = event.currentTarget.closest("details");
                      if (menu) menu.open = false;
                      onDelete(document);
                    }}>删除</button>
                  </div>
                </details>
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
