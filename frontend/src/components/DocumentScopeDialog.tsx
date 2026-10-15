import { useEffect, useRef, useState } from "react";
import { fetchDocuments } from "../api/documents";
import type { DocumentScope } from "../types/conversation";
import type { DocumentItem } from "../types/document";

type Props = {
  scope: DocumentScope;
  onApply: (scope: DocumentScope) => Promise<void>;
  onClose: () => void;
};

const STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传", parsing: "解析中", chunking: "整理内容中", embedding: "建立索引中", indexed: "已入库", failed: "处理失败",
};

export default function DocumentScopeDialog({ scope, onApply, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState(scope.mode);
  const [selected, setSelected] = useState(new Set(scope.document_ids));
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [retry, setRetry] = useState(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    const dialog = dialogRef.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      mounted.current = false;
      dialog?.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    fetchDocuments(controller.signal).then((items) => {
      if (!controller.signal.aborted) setDocuments(items);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setLoadError(reason instanceof Error ? reason.message : "文档列表加载失败");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [retry]);

  const query = keyword.trim().toLocaleLowerCase();
  const visible = documents.filter((file) => `${file.file_name} ${file.original_name} ${file.source_relative_path ?? ""}`.toLocaleLowerCase().includes(query));
  const selectable = visible.filter((file) => file.status === "indexed");
  const validIds = new Set(documents.filter((file) => file.status === "indexed").map((file) => file.id));
  const invalidIds = [...selected].filter((id) => !validIds.has(id));
  const unavailable = mode === "selected" && (loading || Boolean(loadError) || selected.size === 0 || invalidIds.length > 0);

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
    setSaveError("");
  }

  async function apply() {
    if (saving || unavailable) return;
    setSaving(true);
    setSaveError("");
    try {
      await onApply({ mode, document_ids: mode === "selected" ? [...selected].sort() : [] });
      if (mounted.current) onClose();
    } catch (reason) {
      if (mounted.current) setSaveError(reason instanceof Error ? reason.message : "保存失败，请重试");
    } finally {
      if (mounted.current) setSaving(false);
    }
  }

  return (
    <dialog ref={dialogRef} className="document-scope-dialog" aria-labelledby="document-scope-title" aria-describedby="document-scope-description"
      onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget && !saving) onClose(); }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)")).filter((element) => element.getClientRects().length > 0);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}>
      <div className="document-scope-shell">
        <header>
          <div><h2 id="document-scope-title">选择检索文档</h2><p id="document-scope-description">仅影响当前会话的后续提问，历史回答保持原样。</p></div>
          <button type="button" className="scope-secondary" aria-label="关闭文档选择" disabled={saving} onClick={onClose}>关闭</button>
        </header>
        <fieldset className="scope-modes" disabled={saving}>
          <legend className="sr-only">检索范围</legend>
          <label><input type="radio" name="scope-mode" checked={mode === "all"} onChange={() => setMode("all")} />全部已入库文档</label>
          <label><input type="radio" name="scope-mode" checked={mode === "selected"} onChange={() => setMode("selected")} />指定文档</label>
        </fieldset>
        {mode === "all" ? <div className="scope-all-description">使用全部已入库文档。后续新入库的文档也会参与检索。</div> : (
          <div className="scope-selection">
            <input className="scope-search" type="search" aria-label="搜索检索文档" placeholder="搜索文件名或来源路径" value={keyword} disabled={saving} onChange={(event) => setKeyword(event.target.value)} />
            <div className="scope-selection-actions">
              <button type="button" className="scope-secondary" disabled={saving || loading || !selectable.length} onClick={() => setSelected((current) => new Set([...current, ...selectable.map((file) => file.id)]))}>全选当前结果</button>
              <button type="button" className="scope-secondary" disabled={saving || !selected.size} onClick={() => setSelected(new Set())}>清空选择</button>
              <span aria-live="polite">已选 {selected.size} 个文档</span>
            </div>
            {loading ? <p role="status">正在加载文档…</p> : loadError ? <div role="alert" className="scope-error">{loadError} <button type="button" className="scope-secondary" onClick={() => setRetry((value) => value + 1)}>重试加载</button></div> : (
              <div className="scope-file-list">
                {visible.length === 0 && <p className="scope-empty">{documents.length ? "没有匹配的文档" : "还没有上传文档，请先到文件库上传。"}</p>}
                {visible.map((file) => (
                  <label key={file.id} className={`scope-file${file.status !== "indexed" ? " unavailable" : ""}`}>
                    <input type="checkbox" aria-label={`选择 ${file.source_relative_path || file.file_name}`} checked={selected.has(file.id)} disabled={saving || file.status !== "indexed"} onChange={() => toggle(file.id)} />
                    <span className="scope-file-info"><strong>{file.file_name}</strong><small>{file.file_type.toUpperCase()} · {file.source_relative_path || file.original_name}</small></span>
                    <span className="scope-file-status">{STATUS_LABELS[file.status] ?? "处理中"}</span>
                  </label>
                ))}
              </div>
            )}
            {!loading && !loadError && invalidIds.length > 0 && <div className="scope-error" role="alert">{invalidIds.length} 个已选文档已删除或尚未完成入库。
              <button type="button" className="scope-secondary" disabled={saving} onClick={() => setSelected((current) => new Set([...current].filter((id) => validIds.has(id))))}>移除失效选择</button>
            </div>}
            {selected.size === 0 && <p className="scope-hint">至少选择一个已入库文档，或切换为全部文档。</p>}
          </div>
        )}
        {saveError && <p role="alert" className="scope-error">{saveError}</p>}
        <footer><span>范围改变后，后续问答将重新累计上下文。</span><button type="button" className="scope-secondary" disabled={saving} onClick={onClose}>取消</button><button type="button" disabled={saving || unavailable} onClick={apply}>{saving ? "保存中…" : "应用"}</button></footer>
      </div>
    </dialog>
  );
}
