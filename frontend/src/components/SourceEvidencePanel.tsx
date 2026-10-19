import { useEffect, useRef, useState } from "react";
import type { SourceItem } from "../types/chat";
import { sourceLocation, sourceScoreLabel } from "../utils/answerPresentation";
import ChatIcon from "./ChatIcon";

type Props = {
  id: string;
  sources: SourceItem[];
  selected: SourceItem;
  onSelect: (chunkId: string) => void;
  onClose: () => void;
};

export default function SourceEvidencePanel({ id, sources, selected, onSelect, onClose }: Props) {
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 1100px)").matches);
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1100px)");
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!compact) {
      closeRef.current?.focus({ preventScroll: true });
      return;
    }
    const dialog = dialogRef.current;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = overflow;
    };
  }, [compact]);

  const content = (
    <div className="source-evidence-shell">
      <header className="source-evidence-header">
        <h2 id={`${id}-title`}>来源证据 <span>{sources.length} 段</span></h2>
        <button ref={closeRef} type="button" className="source-evidence-close" aria-label="关闭来源面板" onClick={onClose}><ChatIcon name="close" /></button>
      </header>
      <div className="source-evidence-body">
        <section className="source-evidence-detail" aria-label="当前证据" aria-live="polite">
          <div className="source-evidence-file"><ChatIcon name="file" /><strong>{selected.file_name}</strong></div>
          <p className="source-evidence-location">{sourceLocation(selected)}</p>
          <h3>原文片段</h3>
          <pre className="source-evidence-excerpt">{selected.content}</pre>
          <details className="source-evidence-match">
            <summary>匹配信息</summary>
            <p>{sourceScoreLabel(selected)}</p>
            {selected.retrieval_methods?.length ? <p>命中方式：{selected.retrieval_methods.map((method) => method === "bm25" ? "关键词" : "语义").join("、")}</p> : null}
            {selected.retrieval_warning && <p role="status">{selected.retrieval_warning}</p>}
          </details>
        </section>
        {sources.length > 1 && <nav className="source-evidence-list" aria-label="本回答的证据片段">
          <h3>本回答的来源片段</h3>
          {sources.map((source, index) => (
            <button key={source.chunk_id} type="button" className="source-evidence-option" aria-pressed={source.chunk_id === selected.chunk_id} onClick={() => onSelect(source.chunk_id)}>
              <span className="source-evidence-index">{index + 1}</span>
              <span><strong>{source.file_name}</strong><small>{sourceLocation(source)}</small></span>
            </button>
          ))}
        </nav>}
      </div>
      <footer>展示文档解析后的内容片段。</footer>
    </div>
  );

  if (compact) return (
    <dialog id={id} ref={dialogRef} className="source-evidence-drawer" aria-labelledby={`${id}-title`} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      {content}
    </dialog>
  );

  return <aside id={id} className="source-evidence-panel" aria-labelledby={`${id}-title`} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}>{content}</aside>;
}
