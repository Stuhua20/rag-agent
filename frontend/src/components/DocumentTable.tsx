import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { DocumentItem } from "../types/document";

const STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传", parsing: "解析中", chunking: "整理内容中", embedding: "建立索引中", indexed: "已入库", failed: "处理失败",
};

type Props = {
  documents: DocumentItem[];
  selectedId?: string;
  onSelect: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
  onReindex: (document: DocumentItem) => void;
  checkedIds: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  disabled: boolean;
};

export default function DocumentTable({ documents, selectedId, onSelect, onDelete, onReindex, checkedIds, onToggle, onToggleAll, disabled }: Props) {
  const selectAllRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuOpenerRef = useRef<HTMLButtonElement>(null);
  const [menuDocument, setMenuDocument] = useState<DocumentItem | null>(null);
  const menuId = useId();
  const activeMenu = !disabled && documents.some((item) => item.id === menuDocument?.id) ? menuDocument : null;
  const checkedCount = documents.filter((item) => checkedIds.has(item.id)).length;
  const allChecked = documents.length > 0 && checkedCount === documents.length;

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = checkedCount > 0 && !allChecked;
  }, [checkedCount, allChecked]);

  useEffect(() => {
    if (disabled || !documents.some((item) => item.id === menuDocument?.id)) setMenuDocument(null);
  }, [disabled, documents, menuDocument]);

  useLayoutEffect(() => {
    const menu = menuRef.current;
    const opener = menuOpenerRef.current;
    if (!activeMenu || !menu || !opener) return;
    const anchor = opener.getBoundingClientRect();
    const bounds = menu.getBoundingClientRect();
    const left = Math.max(8, Math.min(anchor.right - bounds.width, window.innerWidth - bounds.width - 8));
    const below = anchor.bottom + 4;
    const top = below + bounds.height <= window.innerHeight - 8 ? below : Math.max(8, anchor.top - bounds.height - 4);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
  }, [activeMenu]);

  useEffect(() => {
    if (!activeMenu) return;
    function dismiss(event: PointerEvent | KeyboardEvent | Event) {
      if (event instanceof KeyboardEvent) {
        if (event.key !== "Escape") return;
        menuOpenerRef.current?.focus();
      } else if (event instanceof PointerEvent && event.target instanceof Node &&
        (menuRef.current?.contains(event.target) || menuOpenerRef.current?.contains(event.target))) {
        return;
      }
      setMenuDocument(null);
    }
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", dismiss);
    window.addEventListener("resize", dismiss);
    document.addEventListener("scroll", dismiss, true);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", dismiss);
      window.removeEventListener("resize", dismiss);
      document.removeEventListener("scroll", dismiss, true);
    };
  }, [activeMenu]);

  return (
    <>
    <div className="table-wrap document-table-wrap">
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
                <button type="button" className="document-row-more" aria-label={`更多操作：${document.file_name}`}
                  aria-expanded={activeMenu?.id === document.id} aria-controls={activeMenu?.id === document.id ? menuId : undefined}
                  disabled={disabled} onClick={(event) => {
                    menuOpenerRef.current = event.currentTarget;
                    setMenuDocument(activeMenu?.id === document.id ? null : document);
                  }}>⋯</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {documents.length === 0 && <p className="empty">暂无文件</p>}
    </div>
    {activeMenu && createPortal(
      <div ref={menuRef} id={menuId} className="document-row-menu" role="group" aria-label={`文件操作：${activeMenu.file_name}`}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== menuOpenerRef.current) setMenuDocument(null);
        }}>
        <button type="button" disabled={!["indexed", "failed"].includes(activeMenu.status)}
          title="按当前模型和分块参数重新索引，可能调用 Embedding 服务" onClick={() => {
            setMenuDocument(null);
            onReindex(activeMenu);
          }}>重新索引</button>
        <button type="button" className="danger" onClick={() => {
          setMenuDocument(null);
          onDelete(activeMenu);
        }}>删除</button>
      </div>, document.body,
    )}
    </>
  );
}

function formatDateTime(value: string) {
  return value.replace("T", " ");
}
