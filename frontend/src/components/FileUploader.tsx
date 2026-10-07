import { FormEvent, useState } from "react";
import { uploadDocument } from "../api/documents";

const MAX_FILE_SIZE = 30 * 1024 * 1024;

type Props = {
  onUploaded?: () => void | Promise<void>;
};

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export default function FileUploader({ onUploaded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [permissionLevel, setPermissionLevel] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [statusText, setStatusText] = useState("");
  const [result, setResult] = useState<{ documentId: string; sheetCount: number; chunkCount: number } | null>(null);

  function acceptFile(next: File | null | undefined) {
    if (!next) return;
    if (!/\.(xlsx|csv|pdf|docx)$/i.test(next.name)) {
      setStatus("error");
      setStatusText("仅支持 xlsx / csv / PDF / DOCX 文件");
      return;
    }
    if (next.size > MAX_FILE_SIZE) {
      setStatus("error");
      setStatusText("文件超过 30MB 限制，请压缩后再上传");
      return;
    }
    setStatus("idle");
    setStatusText("");
    setFile(next);
    setFileName(next.name);
  }

  function resetForm() {
    setFile(null);
    setFileName("");
    setStatus("idle");
    setStatusText("");
    setResult(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setStatus("error");
      setStatusText("请选择 xlsx、csv、PDF 或 DOCX 文件");
      return;
    }
    setStatus("uploading");
    setStatusText("正在上传并解析文件...");
    try {
      const res = await uploadDocument({
        file,
        fileName: fileName || file.name,
        permissionLevel,
      });
      setStatus("success");
      setStatusText("上传成功");
      setResult({
        documentId: res.document_id,
        sheetCount: res.sheet_count,
        chunkCount: res.chunk_count,
      });
      await onUploaded?.();
    } catch (error) {
      setStatus("error");
      setStatusText(error instanceof Error ? error.message : "上传失败");
    }
  }

  if (status === "success" && result) {
    return (
      <div className="upload-success">
        <div className="upload-success-icon">&#10003;</div>
        <strong>上传成功</strong>
        <div className="upload-success-stats">
          <span><b>{result.sheetCount}</b> 个 Sheet</span>
          <span><b>{result.chunkCount}</b> 个 Chunk</span>
        </div>
        <p className="upload-success-id">文档 ID：{result.documentId}</p>
        <button type="button" className="upload-again-btn" onClick={resetForm}>
          继续上传
        </button>
      </div>
    );
  }

  return (
    <form className="form-panel" onSubmit={onSubmit}>
      <label>
        文件
        <div
          className={`dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            acceptFile(event.dataTransfer.files?.[0]);
          }}
        >
          <input
            type="file"
            accept=".xlsx,.csv,.pdf,.docx"
            className="visually-hidden-input"
            onChange={(event) => acceptFile(event.target.files?.[0])}
          />
          {file ? (
            <span className="dropzone-name">
              {file.name}
              <span>{formatFileSize(file.size)} · 点击可更换</span>
            </span>
          ) : (
            <span className="dropzone-hint">点击选择或拖拽 xlsx / csv / PDF / DOCX 文件到此处</span>
          )}
        </div>
      </label>
      <label>
        文件名称
        <input value={fileName} onChange={(event) => setFileName(event.target.value)} placeholder="默认使用原文件名" />
      </label>
      <label>
        权限等级
        <input
          type="number"
          min={1}
          max={3}
          value={permissionLevel}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (Number.isNaN(next)) return;
            setPermissionLevel(Math.min(3, Math.max(1, Math.round(next))));
          }}
        />
        <small className="field-hint">1 最宽松，3 最严格，范围 1 - 3</small>
      </label>
      <button type="submit" disabled={status === "uploading"}>
        {status === "uploading" ? "处理中..." : "上传并解析"}
      </button>
      {statusText && (
        <p className={`status-text ${status === "error" ? "status-error" : ""}`}>
          {statusText}
        </p>
      )}
    </form>
  );
}
