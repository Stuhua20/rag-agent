import { useEffect, useRef, useState } from "react";
import { fetchChunks, fetchDocument, fetchSheets } from "../api/documents";
import type { ChunkPage, DocumentItem, SheetItem } from "../types/document";
import SheetPreview from "./SheetPreview";

type Props = {
  document: DocumentItem;
  onClose: () => void;
};

const PAGE_SIZE = 50;
const STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传", parsing: "解析中", chunking: "整理内容中", embedding: "建立索引中", indexed: "已入库", failed: "处理失败",
};

function formatTime(value: string) {
  // The backend's utc_now_iso stores UTC without a timezone suffix.
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}

export default function DocumentPreviewDialog({ document: file, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [detail, setDetail] = useState(file);
  const [sheets, setSheets] = useState<SheetItem[]>([]);
  const [chunkPage, setChunkPage] = useState<ChunkPage | null>(null);
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState<"content" | "info">("content");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const textDocument = ["pdf", "docx"].includes(detail.file_type.toLowerCase());
  const total = chunkPage?.total ?? detail.chunk_count;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    const dialog = dialogRef.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      fetchDocument(file.id, controller.signal),
      fetchSheets(file.id, controller.signal),
      fetchChunks(file.id, page, PAGE_SIZE, controller.signal),
    ]).then(([nextDetail, nextSheets, nextChunks]) => {
      if (!active) return;
      setDetail(nextDetail);
      setSheets(nextSheets);
      setChunkPage(nextChunks);
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "文件详情加载失败");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [file.id, page, retry]);

  useEffect(() => { bodyRef.current?.scrollTo({ top: 0 }); }, [page, tab, retry]);

  return (
    <dialog
      ref={dialogRef}
      className="document-preview-dialog"
      aria-labelledby="document-preview-title"
      aria-describedby="document-preview-description"
      onCancel={(event) => {
        if (event.target !== event.currentTarget) return;
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
          "button:not(:disabled):not([tabindex='-1']), summary",
        )).filter((element) => element.getClientRects().length > 0);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault(); last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); first?.focus();
        }
      }}
    >
      <div className="document-preview-shell">
        <header className="document-preview-header">
          <div>
            <span className="document-preview-eyebrow">文件详情</span>
            <h2 id="document-preview-title" title={detail.file_name}>{detail.file_name}</h2>
            <p id="document-preview-description">{detail.file_type.toUpperCase()} · {STATUS_LABELS[detail.status] || detail.status}</p>
            {detail.source_relative_path && <p className="document-preview-path" title={detail.source_relative_path}>来源：{detail.source_relative_path}</p>}
          </div>
          <button type="button" autoFocus className="document-preview-close" aria-label="关闭文件详情" onClick={onClose}>×</button>
        </header>

        <div className="document-preview-tabs" role="tablist" aria-label="文件详情视图" onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("[role='tab']"));
          const index = event.key === "Home" ? 0 : event.key === "End" ? 1 : tab === "content" ? 1 : 0;
          tabs[index]?.click(); tabs[index]?.focus();
        }}>
          <button id="document-preview-content-tab" role="tab" type="button" aria-selected={tab === "content"} aria-controls="document-preview-panel" tabIndex={tab === "content" ? 0 : -1} onClick={() => setTab("content")}>内容预览</button>
          <button id="document-preview-info-tab" role="tab" type="button" aria-selected={tab === "info"} aria-controls="document-preview-panel" tabIndex={tab === "info" ? 0 : -1} onClick={() => setTab("info")}>文件信息</button>
        </div>

        <div className="document-preview-body" ref={bodyRef} id="document-preview-panel" role="tabpanel" aria-labelledby={`document-preview-${tab}-tab`} aria-busy={loading}>
          {loading ? <p className="document-preview-empty" role="status">正在加载文件详情…</p> : error ? (
            <div className="document-preview-error" role="alert">
              <strong>文件详情加载失败</strong><p>{error}</p>
              <button type="button" onClick={() => setRetry((value) => value + 1)}>重试</button>
            </div>
          ) : <>
            {detail.error_message && <div className="document-preview-error" role="alert"><strong>文件处理失败</strong><p>{detail.error_message}</p></div>}
            {tab === "content" ? <SheetPreview sheets={sheets} chunks={chunkPage?.items ?? []} warnings={detail.parse_warnings} textDocument={textDocument} /> : (
              <dl className="document-preview-info">
                <div><dt>文件名称</dt><dd>{detail.file_name}</dd></div>
                <div><dt>原始名称</dt><dd>{detail.original_name}</dd></div>
                <div><dt>文件类型</dt><dd>{detail.file_type.toUpperCase()}</dd></div>
                <div><dt>来源路径</dt><dd>{detail.source_relative_path || "单独上传"}</dd></div>
                <div><dt>处理状态</dt><dd>{STATUS_LABELS[detail.status] || detail.status}</dd></div>
                <div><dt>上传时间</dt><dd>{formatTime(detail.created_at)}</dd></div>
                <div><dt>更新时间</dt><dd>{formatTime(detail.updated_at)}</dd></div>
                <div><dt>{textDocument ? "已解析页面 / 章节" : "工作表数量"}</dt><dd>{detail.sheet_count}</dd></div>
                <div><dt>解析内容数量</dt><dd>{total}</dd></div>
                <div><dt>{textDocument ? "提取内容条目" : "总数据行数"}</dt><dd>{detail.row_count}</dd></div>
                {!textDocument && <div><dt>最大列数</dt><dd>{detail.column_count}</dd></div>}
              </dl>
            )}
          </>}
        </div>

        <footer className="document-preview-footer">
          {tab === "content" ? <>
            <span aria-live="polite">第 {page} 页 / 共 {pageCount} 页 · 共 {total} 段内容</span>
            <div>
              <button type="button" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</button>
              <button type="button" disabled={loading || page >= pageCount} onClick={() => setPage((value) => value + 1)}>下一页</button>
            </div>
          </> : <span>时间按北京时间显示</span>}
          <small>展示解析后的内容；原文件中的排版、图片等可能未包含在内。</small>
        </footer>
      </div>
    </dialog>
  );
}
