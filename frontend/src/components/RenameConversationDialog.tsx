import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Conversation } from "../types/conversation";

type Props = {
  conversation: Conversation;
  onSave: (title: string) => Promise<void>;
  onClose: () => void;
};

export default function RenameConversationDialog({ conversation, onSave, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);
  const mounted = useRef(false);
  const [title, setTitle] = useState(conversation.title);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const normalizedTitle = title.trim();
  const length = [...normalizedTitle].length;
  const valid = length > 0 && length <= 100;

  useEffect(() => {
    mounted.current = true;
    const dialog = dialogRef.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    inputRef.current?.focus();
    inputRef.current?.select();
    return () => {
      mounted.current = false;
      dialog?.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || !valid) return;
    if (normalizedTitle === conversation.title) { onClose(); return; }
    submitting.current = true;
    setSaving(true);
    setError("");
    try {
      await onSave(normalizedTitle);
      if (mounted.current) onClose();
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "重命名失败，请重试。");
    } finally {
      submitting.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  return (
    <dialog ref={dialogRef} className="modal-content conversation-rename-dialog" aria-labelledby="conversation-rename-title"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("input:not(:disabled), button:not(:disabled)"));
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}
      onCancel={(event) => { event.preventDefault(); if (!submitting.current) onClose(); }}
      onClick={(event) => {
        if (event.target !== event.currentTarget || submitting.current) return;
        const rect = event.currentTarget.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
      }}>
      <form onSubmit={save} aria-busy={saving}>
        <h3 id="conversation-rename-title" className="modal-title">重命名聊天</h3>
        <label className="conversation-rename-label" htmlFor="conversation-rename-input">聊天名称</label>
        <input ref={inputRef} id="conversation-rename-input" value={title} disabled={saving} autoComplete="off"
          aria-describedby="conversation-rename-hint" aria-invalid={length > 100 || Boolean(error)}
          onChange={(event) => { setTitle(event.target.value); setError(""); }}
          onKeyDown={(event) => { if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)) event.preventDefault(); }} />
        <p id="conversation-rename-hint" className={`conversation-rename-hint${length > 100 ? " invalid" : ""}`}>{length}/100 个字符，首尾空白会自动去除。</p>
        {error && <p className="conversation-rename-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="modal-cancel" disabled={saving} onClick={onClose}>取消</button>
          <button type="submit" className="modal-confirm" disabled={saving || !valid}>{saving ? "保存中…" : "保存"}</button>
        </div>
      </form>
    </dialog>
  );
}
