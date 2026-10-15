import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

type Props = {
  disabled?: boolean;
  generating?: boolean;
  onSend: (question: string) => Promise<boolean>;
};

export default function MessageInput({ disabled = false, generating = false, onSend }: Props) {
  const [value, setValue] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [value]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const question = value.trim();
    if (!question || disabled) return;
    const sent = await onSend(question);
    if (sent) {
      setValue("");
      setHistory((prev) => [...prev, question].slice(-50));
      setHistoryIndex(null);
    }
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function recallPrevious() {
    if (history.length === 0) return;
    const nextIndex = historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1);
    setHistoryIndex(nextIndex);
    setValue(history[nextIndex]);
  }

  function recallNext() {
    if (historyIndex === null) return;
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
          rows={1}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="输入问题，将在当前文档范围内检索并回答"
        />
        {value && <span className="composer-count">{value.length} 字</span>}
      </div>
      <button type="submit" disabled={disabled || !value.trim()}>
        {generating ? "生成中..." : "发送"}
      </button>
    </form>
  );
}
