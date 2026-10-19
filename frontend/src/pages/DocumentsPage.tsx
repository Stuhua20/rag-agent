import { useEffect, useMemo, useRef, useState } from "react";
import { deleteDocument, fetchDocuments, reindexDocument } from "../api/documents";
import ConfirmModal from "../components/ConfirmModal";
import DocumentTable from "../components/DocumentTable";
import { useUpload } from "../components/upload/UploadProvider";
import DocumentPreviewDialog from "../components/DocumentPreviewDialog";
import { useToast } from "../components/Toast";
import type { DocumentItem } from "../types/document";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [keyword, setKeyword] = useState("");
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<DocumentItem[]>([]);
  const [deleteProgress, setDeleteProgress] = useState<{ completed: number; total: number } | null>(null);
  const [deleteResult, setDeleteResult] = useState<{ succeeded: number; failures: { document: DocumentItem; message: string }[] } | null>(null);
  const deletingRef = useRef(false);
  const reindexingRef = useRef(false);
  const [reindexing, setReindexing] = useState<string | null>(null);
  const { open: openUpload, isOpen: uploadOpen, isRunning: uploading, documentRevision } = useUpload();
  const { toast } = useToast();

  async function loadDocuments(showErrorToast = true): Promise<boolean> {
    setLoadingDocuments(true);
    setLoadError("");
    try {
      const next = await fetchDocuments();
      setDocuments(next);
      const ids = new Set(next.map((item) => item.id));
      setCheckedIds((current) => new Set([...current].filter((id) => ids.has(id))));
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "加载失败";
      setLoadError(message);
      if (showErrorToast) toast(`文件库加载失败：${message}`, "error");
      return false;
    } finally {
      setLoadingDocuments(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, [documentRevision]);

  const visibleDocuments = useMemo(
    () => documents.filter((item) => `${item.file_name} ${item.source_relative_path ?? ""}`.toLowerCase().includes(keyword.toLowerCase())),
    [documents, keyword],
  );

  function changeKeyword(value: string) {
    setKeyword(value);
    setCheckedIds(new Set());
  }

  function toggleDocument(id: string) {
    setCheckedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    const allChecked = visibleDocuments.every((item) => checkedIds.has(item.id));
    setCheckedIds(allChecked ? new Set() : new Set(visibleDocuments.map((item) => item.id)));
  }

  function removeDocument(document: DocumentItem) {
    setPendingDelete([document]);
  }

  async function rebuildDocument(document: DocumentItem) {
    if (deletingRef.current || reindexingRef.current || uploading) return;
    reindexingRef.current = true;
    setReindexing(document.file_name);
    try {
      await reindexDocument(document.id);
      if (selected?.id === document.id) setSelected(null);
      await loadDocuments();
      toast(`${document.file_name} 已重新索引`, "success");
    } catch (error) {
      toast(error instanceof Error ? error.message : "重新索引失败，请核对文件状态后重试", "error");
    } finally {
      reindexingRef.current = false;
      setReindexing(null);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete.length || deletingRef.current || reindexingRef.current) return;
    deletingRef.current = true;
    const targets = [...pendingDelete];
    const failures: { document: DocumentItem; message: string }[] = [];
    let succeeded = 0;
    setDeleteResult(null);
    setDeleteProgress({ completed: 0, total: targets.length });
    try {
      for (const document of targets) {
        try {
          const result = await deleteDocument(document.id);
          if (!result.deleted) throw new Error("未确认删除成功，请核对文件库");
          succeeded += 1;
          setDocuments((current) => current.filter((item) => item.id !== document.id));
          if (selected?.id === document.id) {
            setSelected(null);
          }
        } catch (error) {
          failures.push({ document, message: error instanceof Error ? error.message : "删除失败" });
        }
        setDeleteProgress({ completed: succeeded + failures.length, total: targets.length });
      }
      setCheckedIds(new Set(failures.map((item) => item.document.id)));
      setDeleteResult({ succeeded, failures });
      setPendingDelete([]);
      const refreshed = await loadDocuments(false);
      const summary = failures.length ? `已删除 ${succeeded} 个文件，${failures.length} 个失败` : `已删除 ${succeeded} 个文件`;
      toast(
        refreshed ? summary : `${summary}；文件库刷新失败，请点击重试`,
        failures.length || !refreshed ? "error" : "success",
      );
    } finally {
      deletingRef.current = false;
      setDeleteProgress(null);
    }
  }

  return (
    <div className="documents-layout">
      <section className="page-panel">
        <div className="section-header">
          <h1>文件库</h1>
          <div className="document-toolbar">
            <div className="search-box">
              <input
                aria-label="搜索文件名或来源路径"
                value={keyword}
                disabled={Boolean(deleteProgress)}
                onChange={(event) => changeKeyword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") changeKeyword("");
                }}
                placeholder="搜索文件名或来源路径"
              />
              {keyword && (
                <button type="button" className="search-clear" aria-label="清空搜索" disabled={Boolean(deleteProgress)} onClick={() => changeKeyword("")}>
                  ×
                </button>
              )}
            </div>
            <button
              type="button"
              className="upload-launch-button"
              aria-haspopup="dialog"
              aria-expanded={uploadOpen}
              onClick={openUpload}
              disabled={Boolean(deleteProgress) || Boolean(reindexing)}
            >
              上传
            </button>
          </div>
        </div>
        <div className="document-list-toolbar">
          <div className="document-list-summary">
            <span className="search-summary">
              {keyword
                ? `匹配 ${visibleDocuments.length} / ${documents.length} 个文件`
                : `共 ${documents.length} 个文件`}
            </span>
            <span className="document-selection-count" role="status">
              {checkedIds.size > 0 ? `已选 ${checkedIds.size} 项` : ""}
            </span>
            {(keyword || (uploading && checkedIds.size > 0)) && (
              <span className="document-selection-hint" title={uploading && checkedIds.size > 0 ? "上传处理完成后可批量删除" : "全选仅包含当前搜索结果"}>
                {uploading && checkedIds.size > 0 ? "上传处理完成后可批量删除" : "全选仅包含当前搜索结果"}
              </span>
            )}
          </div>
          <div className={`document-selection-actions${checkedIds.size > 0 ? " is-visible" : ""}`} aria-hidden={!checkedIds.size}>
            <button
              type="button"
              className="document-clear-selection"
              disabled={!checkedIds.size || Boolean(deleteProgress)}
              onClick={() => setCheckedIds(new Set())}
            >
              取消选择
            </button>
            <button
              type="button"
              className="document-bulk-delete"
              disabled={!checkedIds.size || Boolean(deleteProgress) || Boolean(reindexing) || loadingDocuments || uploading}
              onClick={() => setPendingDelete(visibleDocuments.filter((item) => checkedIds.has(item.id)))}
            >
              {deleteProgress ? `删除中 ${deleteProgress.completed} / ${deleteProgress.total}` : "删除所选"}
            </button>
          </div>
        </div>
        {deleteResult && (
          <div className={`document-delete-result${deleteResult.failures.length ? " has-failures" : ""}`} role="status">
            <strong>已删除 {deleteResult.succeeded} 个文件{deleteResult.failures.length ? `，${deleteResult.failures.length} 个失败，失败项已保留` : ""}</strong>
            {deleteResult.failures.length > 0 && <ul>{deleteResult.failures.map(({ document, message }) => (
              <li key={document.id}>{document.source_relative_path || document.file_name}：{message}</li>
            ))}</ul>}
          </div>
        )}
        {loadingDocuments && <p className="status-text">正在加载文件库...</p>}
        {reindexing && <p className="status-text" role="status">正在重新索引：{reindexing}，完成前仍可查询原有资料。</p>}
        {loadError && (
          <div className="inline-error" role="alert">
            <span>文件库加载失败：{loadError}</span>
            <button type="button" onClick={() => void loadDocuments()}>
              重试
            </button>
          </div>
        )}
        {(!loadError || documents.length > 0) && !loadingDocuments && (
          <DocumentTable
            documents={visibleDocuments}
            selectedId={selected?.id}
            onSelect={setSelected}
            onDelete={removeDocument}
            onReindex={(document) => void rebuildDocument(document)}
            checkedIds={checkedIds}
            onToggle={toggleDocument}
            onToggleAll={toggleAll}
            disabled={Boolean(deleteProgress) || Boolean(reindexing) || uploading}
          />
        )}
      </section>
      {selected && (
        <DocumentPreviewDialog key={selected.id} document={selected} onClose={() => setSelected(null)} />
      )}
      <ConfirmModal
        open={pendingDelete.length > 0}
        title={pendingDelete.length > 1 ? "批量删除文件" : "删除文件"}
        message={`确定删除${pendingDelete.length > 1 ? `选中的 ${pendingDelete.length} 个文件` : "文件"}（${pendingDelete.slice(0, 3).map((item) => item.source_relative_path || item.file_name).join("、")}${pendingDelete.length > 3 ? "等" : ""}）吗？文件及其索引将一并删除，此操作无法撤销。`}
        confirmLabel={deleteProgress ? `删除中 ${deleteProgress.completed} / ${deleteProgress.total}` : "确认删除"}
        busy={Boolean(deleteProgress)}
        danger
        onConfirm={confirmDelete}
        onCancel={() => {
          if (!deletingRef.current) setPendingDelete([]);
        }}
      />
    </div>
  );
}
