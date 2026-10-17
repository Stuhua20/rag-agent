import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from "react";

type Props = {
  disabled?: boolean;
  generating?: boolean;
  onSend: (question: string) => Promise<boolean>;
};

function resizeTextarea(textarea: HTMLTextAreaElement) {
  textarea.style.height = "auto";
  const height = textarea.scrollHeight + textarea.offsetHeight - textarea.clientHeight;
  textarea.style.height = `${Math.min(height, 180)}px`;
  textarea.style.overflowY = height > 180 ? "auto" : "hidden";
}

export default function MessageInput({ disabled = false, generating = false, onSend }: Props) {
  const [value, setValue] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const hintId = useId();
  const submittingRef = useRef(false);
  const editRevision = useRef(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    resizeTextarea(textarea);
  }, [value]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    let previousWidth = 0;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width === previousWidth) return;
      previousWidth = entry.contentRect.width;
      resizeTextarea(textarea);
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const question = value.trim();
    if (!question || disabled || generating || submittingRef.current) return;
    submittingRef.current = true;
    const submittedValue = value;
    const submittedRevision = editRevision.current;
    setValue("");
    setHistoryIndex(null);
    textareaRef.current?.focus();
    let sent = false;
    try {
      sent = await onSend(question);
    } finally {
      submittingRef.current = false;
      if (mounted.current) {
        if (sent) setHistory((prev) => [...prev, question].slice(-50));
        else if (editRevision.current === submittedRevision) setValue(submittedValue);
      }
    }
  }

  function recallPrevious() {
    if (history.length === 0) return;
    editRevision.current += 1;
    const nextIndex = historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1);
    setHistoryIndex(nextIndex);
    setValue(history[nextIndex]);
  }

  function recallNext() {
    if (historyIndex === null) return;
    editRevision.current += 1;
    const nextIndex = historyIndex + 1;
    if (nextIndex >= history.length) {
      setHistoryIndex(null);
      setValue("");
    } else {
      setHistoryIndex(nextIndex);
      setValue(history[nextIndex]);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
      return;
    }
    if (event.shiftKey) return;
    const { selectionStart, selectionEnd } = event.currentTarget;
    if (event.key === "ArrowUp" && selectionStart === 0 && selectionEnd === 0) {
      event.preventDefault();
      recallPrevious();
      return;
    }
    if (event.key === "ArrowDown" && historyIndex !== null) {
      const length = event.currentTarget.value.length;
      if (selectionStart === length && selectionEnd === length) {
        event.preventDefault();
        recallNext();
      }
    }
  }

  return (
    <form className="message-input" onSubmit={onSubmit}>
      <div className="composer-box">
        <textarea
          ref={textareaRef}
          disabled={disabled}
          aria-label="输入问题"
          aria-describedby={hintId}
          rows={1}
          value={value}
          onChange={(event) => { editRevision.current += 1; setValue(event.target.value); }}
          onKeyDown={onKeyDown}
          placeholder="输入问题，将在当前文档范围内检索并回答"
        />
        {value && <span className="composer-count">{value.length} 字</span>}
      </div>
      <button type="submit" disabled={disabled || generating || !value.trim()}>
        {generating ? "生成中..." : "发送"}
      </button>
      <p id={hintId} className="composer-hint"><span>Enter 发送 · Shift + Enter 换行</span>{generating && <span role="status">回答生成中，可先编辑下一条问题</span>}</p>
    </form>
  );
}
