import { useEffect, useMemo, useRef, useState } from "react";
import { deleteDocument, fetchChunks, fetchDocuments, fetchSheets } from "../api/documents";
import ConfirmModal from "../components/ConfirmModal";
import DocumentTable from "../components/DocumentTable";
import FileUploader from "../components/FileUploader";
import SheetPreview from "../components/SheetPreview";
import { useToast } from "../components/Toast";
import type { ChunkItem, DocumentItem, SheetItem } from "../types/document";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [sheets, setSheets] = useState<SheetItem[]>([]);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [keyword, setKeyword] = useState("");
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false);
  const { toast } = useToast();
  const previewRequestRef = useRef(0);

  async function loadDocuments(showErrorToast = true): Promise<boolean> {
    setLoadingDocuments(true);
    setLoadError("");
    try {
      setDocuments(await fetchDocuments());
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
  }, []);

  const visibleDocuments = useMemo(
    () => documents.filter((item) => item.file_name.toLowerCase().includes(keyword.toLowerCase())),
    [documents, keyword],
  );

  async function selectDocument(document: DocumentItem) {
    const requestId = ++previewRequestRef.current;
    setSelected(document);
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const [nextSheets, chunkPage] = await Promise.all([
        fetchSheets(document.id),
        fetchChunks(document.id),
      ]);
      if (requestId !== previewRequestRef.current) return;
      setSheets(nextSheets);
      setChunks(chunkPage.items);
    } catch (error) {
      if (requestId !== previewRequestRef.current) return;
      const message = error instanceof Error ? error.message : "加载文件预览失败";
      setSheets([]);
      setChunks([]);
      setPreviewError(message);
      toast(`加载文件预览失败：${message}`, "error");
    } finally {
      if (requestId === previewRequestRef.current) setPreviewLoading(false);
    }
  }

  function removeDocument(document: DocumentItem) {
    setPendingDelete(document);
  }

  async function confirmDelete() {
    if (!pendingDelete || deletingId) return;
    const documentToDelete = pendingDelete;
    setDeletingId(documentToDelete.id);
    try {
      await deleteDocument(documentToDelete.id);
      setDocuments((current) => current.filter((item) => item.id !== documentToDelete.id));
      if (selected?.id === documentToDelete.id) {
        previewRequestRef.current += 1;
        setSelected(null);
        setSheets([]);
        setChunks([]);
        setPreviewError("");
      }
      setPendingDelete(null);
      const refreshed = await loadDocuments(false);
      toast(
        refreshed ? "文件已删除" : "文件已删除，但文件库刷新失败，请点击重试",
        refreshed ? "success" : "error",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除失败";
      toast(`删除文件失败：${message}`, "error");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={selected ? "documents-layout has-preview" : "documents-layout"}>
      <section className="page-panel">
        <div className="section-header">
          <h1>文件库</h1>
          <div className="document-toolbar">
            <div className="upload-menu">
              <button
                type="button"
                className="upload-menu-button"
                aria-expanded={uploadMenuOpen}
                onClick={() => setUploadMenuOpen((open) => !open)}
              >
                上传文件
              </button>
              {uploadMenuOpen && (
                <div className="upload-popover">
                  <div className="upload-popover-header">
                    <strong>上传 Excel / CSV / PDF / Word</strong>
                    <button type="button" onClick={() => setUploadMenuOpen(false)} aria-label="关闭上传菜单">
                      关闭
                    </button>
                  </div>
                  <FileUploader
                    onUploaded={async () => {
                      const refreshed = await loadDocuments(false);
                      toast(
                        refreshed
                          ? "文件已上传成功，可在文件库中查看"
                          : "文件已上传成功，但文件库刷新失败，请点击重试",
                        refreshed ? "success" : "error",
                      );
                    }}
                  />
                </div>
              )}
            </div>
            <div className="search-box">
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") setKeyword("");
                }}
                placeholder="搜索文件名"
              />
              {keyword && (
                <button type="button" className="search-clear" aria-label="清空搜索" onClick={() => setKeyword("")}>
                  ×
                </button>
              )}
            </div>
          </div>
        </div>
        {documents.length > 0 && (
          <p className="search-summary">
            {keyword
              ? `匹配 ${visibleDocuments.length} / ${documents.length} 个文件`
              : `共 ${documents.length} 个文件`}
          </p>
        )}
        {loadingDocuments && <p className="status-text">正在加载文件库...</p>}
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
            onSelect={selectDocument}
            onDelete={removeDocument}
          />
        )}
      </section>
      {selected && (
        <SheetPreview
          sheets={sheets}
          chunks={chunks}
          warnings={selected.parse_warnings}
          loading={previewLoading}
          error={previewError}
          onRetry={() => void selectDocument(selected)}
        />
      )}
      <ConfirmModal
        open={Boolean(pendingDelete)}
        title="删除文件"
        message={`确定删除「${pendingDelete?.file_name ?? ""}」吗？文件及其索引将一并删除，此操作无法撤销。`}
        confirmLabel={deletingId ? "删除中..." : "删除"}
        danger
        onConfirm={confirmDelete}
        onCancel={() => {
          if (!deletingId) setPendingDelete(null);
        }}
      />
    </div>
  );
}
