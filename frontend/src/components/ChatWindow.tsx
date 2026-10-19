import { useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import MessageInput from "./MessageInput";
import MessageList from "./MessageList";
import SourceEvidencePanel from "./SourceEvidencePanel";
import type { ChatMessage } from "../types/chat";

type Props = {
  messages: ChatMessage[];
  loading: boolean;
  disabled?: boolean;
  scopeControls?: ReactNode;
  emptyState?: ReactNode;
  onSend: (question: string) => Promise<boolean>;
  onStop?: () => void;
};

export default function ChatWindow({ messages, loading, disabled, scopeControls, emptyState, onSend, onStop }: Props) {
  const panelId = useId();
  const [selection, setSelection] = useState<{ messageId: string; chunkId: string } | null>(null);
  const openerRef = useRef<HTMLButtonElement | null>(null);
  const sources = messages.find((message) => message.id === selection?.messageId)?.sources ?? [];
  const selectedSource = sources.find((source) => source.chunk_id === selection?.chunkId);
  const activeSource = selectedSource ? selection : null;

  function closeSources() {
    setSelection(null);
    const opener = openerRef.current;
    requestAnimationFrame(() => { if (opener?.isConnected) opener.focus({ preventScroll: true }); });
  }

  return (
    <section className={`chat-window${selectedSource ? " sources-open" : ""}`}>
      <div className="chat-thread">
        <MessageList messages={messages} loading={loading} emptyState={emptyState} activeSource={activeSource} panelId={panelId} onSelectSource={(messageId, chunkId, opener) => {
          openerRef.current = opener;
          setSelection({ messageId, chunkId });
        }} onCloseSources={closeSources} />
        <div className="chat-composer">
          {scopeControls}
          <MessageInput disabled={disabled} generating={loading} onSend={onSend} onStop={onStop} />
        </div>
      </div>
      {selectedSource && activeSource && <SourceEvidencePanel id={panelId} sources={sources} selected={selectedSource} onSelect={(chunkId) => setSelection({ messageId: activeSource.messageId, chunkId })} onClose={closeSources} />}
    </section>
  );
}
