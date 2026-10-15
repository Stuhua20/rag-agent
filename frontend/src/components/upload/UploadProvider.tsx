import { createContext, useContext, useRef, useState } from "react";
import type { ReactNode } from "react";
import { UploadError, uploadDocument } from "../../api/documents";
import { useToast } from "../Toast";
import UploadDialog from "./UploadDialog";
import { createUploadItem } from "./uploadQueue";
import type { UploadItem } from "./uploadQueue";

type UploadContextValue = {
  items: UploadItem[];
  isOpen: boolean;
  isRunning: boolean;
  stopRequested: boolean;
  documentRevision: number;
  notice: string;
  open: () => void;
  close: () => void;
  addFiles: (files: File[]) => void;
  remove: (id: string) => void;
  clear: () => void;
  rename: (id: string, name: string) => void;
  start: (retryFailed?: boolean) => Promise<void>;
  stop: () => void;
};

const UploadContext = createContext<UploadContextValue | null>(null);

export function UploadProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const itemsRef = useRef<UploadItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const runningRef = useRef(false);
  const stopRef = useRef(false);
  const [stopRequested, setStopRequested] = useState(false);
  const [documentRevision, setDocumentRevision] = useState(0);
  const [notice, setNotice] = useState("");
  const { toast } = useToast();

  function updateItems(next: UploadItem[]) {
    itemsRef.current = next;
    setItems(next);
  }

  function updateItem(id: string, updates: Partial<UploadItem>) {
    updateItems(itemsRef.current.map((item) => item.id === id ? { ...item, ...updates } : item));
  }

  function openDialog() {
    if (!runningRef.current) {
      updateItems([]);
      setNotice("");
      setStopRequested(false);
      stopRef.current = false;
    }
    setIsOpen(true);
  }

  function addFiles(files: File[]) {
    if (runningRef.current) return;
    const ids = new Set(itemsRef.current.map((item) => item.id));
    const added: UploadItem[] = [];
    let duplicates = 0;
    for (const file of files) {
      const item = createUploadItem(file);
      if (ids.has(item.id)) {
        duplicates += 1;
      } else {
        ids.add(item.id);
        added.push(item);
      }
    }
    updateItems([...itemsRef.current, ...added]);
    const validCount = added.filter((item) => item.status === "pending").length;
    setNotice(`本次添加 ${added.length} 个文件，可上传 ${validCount} 个，跳过 ${added.length - validCount} 个${duplicates ? `；${duplicates} 个文件已在列表中` : ""}`);
  }

  async function start(retryFailed = false) {
    if (runningRef.current) return;
    const batch = itemsRef.current.filter((item) => item.status === (retryFailed ? "failed" : "pending"));
    if (!batch.length) return;
    runningRef.current = true;
    stopRef.current = false;
    setIsRunning(true);
    setStopRequested(false);
    setNotice("");
    let succeeded = 0;
    let failed = 0;
    let uncertain = 0;

    try {
      for (const item of batch) {
        if (stopRef.current) break;
        updateItem(item.id, { status: "uploading", progress: 0, message: undefined });
        try {
          const result = await uploadDocument({
            file: item.file,
            fileName: item.displayName.trim() || item.file.name,
            sourceRelativePath: item.file.webkitRelativePath || undefined,
          }, (progress) => updateItem(item.id, { progress }),
          () => updateItem(item.id, { status: "processing", progress: 100 }));
          updateItem(item.id, { status: "success", progress: 100, result });
          succeeded += 1;
        } catch (error) {
          const unknownResult = error instanceof UploadError && error.resultUncertain;
          updateItem(item.id, {
            status: unknownResult ? "uncertain" : "failed",
            message: error instanceof Error ? error.message : "上传失败，请重试",
          });
          if (unknownResult) uncertain += 1;
          else failed += 1;
        }
      }
    } finally {
      runningRef.current = false;
      setIsRunning(false);
      setStopRequested(false);
      setDocumentRevision((revision) => revision + 1);
      const summary = `${stopRef.current ? "已停止后续上传" : "本批处理结束"}：成功 ${succeeded}，失败 ${failed}${uncertain ? `，待核对 ${uncertain}` : ""}`;
      setNotice(summary);
      toast(summary, failed || uncertain ? "info" : "success");
    }
  }

  return (
    <UploadContext.Provider value={{
      items, isOpen, isRunning, stopRequested, documentRevision, notice,
      open: openDialog,
      close: () => setIsOpen(false),
      addFiles,
      remove: (id) => { if (!runningRef.current) updateItems(itemsRef.current.filter((item) => item.id !== id)); },
      clear: () => { if (!runningRef.current) { updateItems([]); setNotice(""); } },
      rename: (id, displayName) => { if (!runningRef.current) updateItem(id, { displayName }); },
      start,
      stop: () => { stopRef.current = true; setStopRequested(true); },
    }}>
      {children}
      <UploadDialog />
      {!isOpen && isRunning && (
        <button type="button" className="upload-resume" onClick={openDialog}>
          正在导入
          <span>{items.filter((item) => ["success", "failed", "uncertain"].includes(item.status)).length} / {items.filter((item) => item.status !== "skipped").length}</span>
        </button>
      )}
    </UploadContext.Provider>
  );
}

export function useUpload() {
  const context = useContext(UploadContext);
  if (!context) throw new Error("useUpload must be used within UploadProvider");
  return context;
}
