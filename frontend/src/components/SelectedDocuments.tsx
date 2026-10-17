import { useEffect, useState } from "react";
import { fetchDocuments } from "../api/documents";
import type { DocumentItem } from "../types/document";
import ChatIcon from "./ChatIcon";
import DocumentPreviewDialog from "./DocumentPreviewDialog";
import { useUpload } from "./upload/UploadProvider";

type Props = { documentIds: string[]; onEdit: () => void; disabled: boolean };

export default function SelectedDocuments({ documentIds, onEdit, disabled }: Props) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [preview, setPreview] = useState<DocumentItem | null>(null);
  const { documentRevision } = useUpload();

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetchDocuments(controller.signal).then((items) => {
      if (!controller.signal.aborted) setDocuments(items);
    }).catch(() => {
      if (!controller.signal.aborted) setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [documentIds, documentRevision, retry]);

  if (loading) return <p className="scope-hint" role="status">正在加载已选文档名称…</p>;
  if (error) return <p className="scope-hint" role="status">文档名称加载失败，检索范围未改变。<button type="button" className="scope-retry" onClick={() => setRetry((value) => value + 1)}>重试</button></p>;

  const documentsById = new Map(documents.map((document) => [document.id, document]));
  return (
    <>
      <div className="selected-documents" aria-label="已选检索文档">
        {documentIds.map((id) => {
          const document = documentsById.get(id);
          const available = document?.status === "indexed";
          const name = document?.file_name ?? "文档已不可用";
          return <button key={id} type="button" className={`selected-document${available ? "" : " unavailable"}`}
            disabled={!available && disabled}
            title={`${document?.source_relative_path || name}${available ? " · 点击查看文档" : " · 点击调整检索范围"}`}
            aria-label={available ? `查看文档：${name}` : `${name}，调整检索范围`}
            onClick={() => { if (available && document) setPreview(document); else onEdit(); }}>
            <ChatIcon name="file" /><span>{name}</span>{!available && document && <small>不可用</small>}
          </button>;
        })}
      </div>
      {preview && <DocumentPreviewDialog document={preview} onClose={() => setPreview(null)} />}
    </>
  );
}
