import { useEffect, useMemo, useState } from "react";
import { deleteDocument, fetchChunks, fetchDocuments, fetchSheets } from "../api/documents";
import DocumentTable from "../components/DocumentTable";
import SheetPreview from "../components/SheetPreview";
import type { ChunkItem, DocumentItem, SheetItem } from "../types/document";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [sheets, setSheets] = useState<SheetItem[]>([]);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");

  async function loadDocuments() {
    setStatus("正在加载文件库...");
    try {
      setDocuments(await fetchDocuments());
      setStatus("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "加载失败");
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
    setSelected(document);
    setSheets(await fetchSheets(document.id));
    const chunkPage = await fetchChunks(document.id);
    setChunks(chunkPage.items);
  }

  async function removeDocument(document: DocumentItem) {
    if (!window.confirm(`删除 ${document.file_name}？`)) return;
    await deleteDocument(document.id);
    setSelected(null);
    setSheets([]);
    setChunks([]);
    await loadDocuments();
  }

  return (
    <div className="documents-layout">
      <section className="page-panel">
        <div className="section-header">
          <h1>文件库</h1>
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索文件名" />
        </div>
        {status && <p className="status-text">{status}</p>}
        <DocumentTable
          documents={visibleDocuments}
          selectedId={selected?.id}
          onSelect={selectDocument}
          onDelete={removeDocument}
        />
      </section>
      <SheetPreview sheets={sheets} chunks={chunks} />
    </div>
  );
}

