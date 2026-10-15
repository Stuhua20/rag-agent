import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useUpload } from "./UploadProvider";
import { formatFileSize, SUPPORTED_FILES } from "./uploadQueue";
import type { UploadItem } from "./uploadQueue";

function statusText(item: UploadItem) {
  switch (item.status) {
    case "pending": return "等待上传";
    case "uploading": return `上传中 ${item.progress}%`;
    case "processing": return "正在解析入库…";
    case "success": return "已入库";
    case "failed": return "失败";
    case "uncertain": return "待核对";
    case "skipped": return "已跳过";
  }
}

export default function UploadDialog() {
  const upload = useUpload();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [dropNotice, setDropNotice] = useState("");
  const [supportsFolder] = useState(() => "webkitdirectory" in document.createElement("input"));
  const { items, isOpen, isRunning } = upload;
  const eligible = items.filter((item) => item.status !== "skipped");
  const succeeded = items.filter((item) => item.status === "success").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const uncertain = items.filter((item) => item.status === "uncertain").length;
  const pending = items.filter((item) => item.status === "pending").length;
  const completed = succeeded + failed + uncertain;
  const overallProgress = eligible.length ? Math.round(completed / eligible.length * 100) : 0;
  const active = items.find((item) => item.status === "uploading" || item.status === "processing");

  useEffect(() => {
    folderInputRef.current?.setAttribute("webkitdirectory", "");
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) {
      dialog.showModal();
      setDropNotice("");
    } else if (!isOpen && dialog.open) {
      dialog.close();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [isOpen]);

  return (
    <dialog
      ref={dialogRef}
      className="upload-dialog"
      aria-labelledby="upload-dialog-title"
      aria-describedby="upload-dialog-description"
      onCancel={(event) => {
        if (event.target !== event.currentTarget) return;
        event.preventDefault();
        upload.close();
      }}
      onClick={(event) => { if (event.target === event.currentTarget) upload.close(); }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input:not([hidden]):not(:disabled), select:not(:disabled), a[href]",
        )).filter((element) => element.getClientRects().length > 0);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
    >
      <div className="upload-dialog-shell">
        <header className="upload-dialog-header">
          <div>
            <h2 id="upload-dialog-title">上传资料</h2>
            <p id="upload-dialog-description">选择多个文件或整个文件夹，统一导入文件库。</p>
          </div>
          <button type="button" className="upload-secondary" onClick={upload.close} aria-label="收起上传窗口">×</button>
        </header>

        <div className="upload-dialog-body">
          <div
            className={`upload-dropzone${dragging ? " dragging" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = isRunning ? "none" : "copy";
              if (!isRunning) setDragging(true);
            }}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (isRunning) return;
              const hasDirectory = Array.from(event.dataTransfer.items).some((item) => item.webkitGetAsEntry?.()?.isDirectory);
              if (hasDirectory) {
                setDropNotice("拖入的内容包含文件夹，请使用“选择文件夹”导入。");
                return;
              }
              setDropNotice("");
              upload.addFiles(Array.from(event.dataTransfer.files));
            }}
          >
            <div className="upload-dropzone-icon" aria-hidden="true">↑</div>
            <strong>添加文件，或将多个文件拖拽到这里</strong>
            <p>支持 XLSX / CSV / PDF / DOCX，单文件不超过 30 MB</p>
            <div className="upload-picker-actions">
              <button type="button" autoFocus disabled={isRunning} onClick={() => fileInputRef.current?.click()}>选择文件</button>
              <button type="button" className="upload-secondary" disabled={isRunning || !supportsFolder} onClick={() => folderInputRef.current?.click()}>选择文件夹</button>
            </div>
            {!supportsFolder && <small>当前浏览器不支持文件夹选择，请使用多选文件。</small>}
            <input
              ref={fileInputRef}
              type="file"
              accept={SUPPORTED_FILES}
              multiple
              hidden
              disabled={isRunning}
              aria-label="选择多个文件"
              onChange={(event) => {
                setDropNotice("");
                upload.addFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              hidden
              disabled={isRunning}
              aria-label="选择上传文件夹"
              onChange={(event) => {
                setDropNotice("");
                upload.addFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
          </div>

          <div className="upload-list-toolbar">
            <span>共 {items.length} 个文件 · {formatFileSize(items.reduce((total, item) => total + item.file.size, 0))}</span>
          </div>
          <p className="upload-notice" role="status">{dropNotice || upload.notice || "文件夹会包含所有子目录；同名文件按来源路径区分。"}</p>

          {items.length ? (
            <ul className="upload-file-list" aria-label="上传文件清单">
              {items.map((item) => (
                <li key={item.id} className={`upload-file-row upload-file-${item.status}`}>
                  <div className="upload-file-details">
                    <strong title={item.displayName}>{item.displayName || item.file.name}</strong>
                    <span className="upload-source-path" title={item.relativePath}>{item.relativePath}</span>
                    {item.message && <span className="upload-file-message">{item.message}</span>}
                    {item.result && <span>{item.result.sheet_count} 个 Sheet · {item.result.chunk_count} 个 Chunk</span>}
                  </div>
                  <span className="upload-file-size">{formatFileSize(item.file.size)}</span>
                  <span className="upload-file-state">{statusText(item)}</span>
                  <button type="button" className="upload-remove" disabled={isRunning} aria-label={`移除 ${item.relativePath}`} onClick={() => upload.remove(item.id)}>移除</button>
                </li>
              ))}
            </ul>
          ) : <div className="upload-empty">还没有添加文件，选择文件或文件夹后即可开始。</div>}

          {eligible.length === 1 && eligible[0].status === "pending" && (
            <label className="upload-rename">文件名称
              <input value={eligible[0].displayName} disabled={isRunning} placeholder="默认使用原文件名" onChange={(event) => upload.rename(eligible[0].id, event.target.value)} />
            </label>
          )}
          {uncertain > 0 && (
            <p className="upload-uncertain-note">有 {uncertain} 个文件的入库结果待核对，未加入失败重试。
              <Link to="/documents" onClick={upload.close}>前往文件库核对</Link>
            </p>
          )}
        </div>

        <footer className="upload-dialog-footer">
          <div className="upload-progress-summary" aria-live="polite">
            <strong>已处理 {completed} / {eligible.length}</strong>
            <span>成功 {succeeded} · 失败 {failed} · 跳过 {items.length - eligible.length}{uncertain ? ` · 待核对 ${uncertain}` : ""}</span>
          </div>
          <progress className="upload-progress" max={100} value={overallProgress} aria-label="整批处理进度" />
          <div className="upload-current">
            {active ? <>
              <span title={active.relativePath}>当前：{active.relativePath}</span>
              {active.status === "uploading" ? <>
                <span>文件传输 {active.progress}%</span>
                <progress className="upload-progress" max={100} value={active.progress} aria-label="当前文件传输进度" />
              </> : <span className="upload-processing"><i aria-hidden="true" />上传完成，正在解析并建立索引…</span>}
            </> : <span>{pending ? `${pending} 个文件等待上传` : eligible.length ? "本次处理结束，重新打开窗口可开始新的上传" : "添加文件后开始上传"}</span>}
          </div>
          <div className="upload-dialog-actions">
            <button type="button" className="upload-secondary" disabled={isRunning || !items.length} onClick={upload.clear}>清空列表</button>
            <div>
              {isRunning ? <button type="button" className="upload-secondary" disabled={upload.stopRequested} onClick={upload.stop}>
                {upload.stopRequested ? "当前文件完成后停止…" : "停止后续上传"}
              </button> : <>
                {failed > 0 && <button type="button" className="upload-secondary" onClick={() => void upload.start(true)}>重试失败项（{failed}）</button>}
                <button type="button" disabled={!pending} onClick={() => void upload.start()}>{completed ? "继续上传" : "开始上传"}{pending ? `（${pending}）` : ""}</button>
              </>}
            </div>
          </div>
          <small className="upload-session-hint">上传中收起可继续处理；处理结束后重新打开为新清单。刷新页面或关闭浏览器会丢失当前队列。</small>
        </footer>
      </div>
    </dialog>
  );
}
