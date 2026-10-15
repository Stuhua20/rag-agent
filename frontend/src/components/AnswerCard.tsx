import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types/chat";
import { answerContent, groupSources } from "../utils/answerPresentation";
import ChatIcon from "./ChatIcon";

type Props = {
  message: ChatMessage;
  activeSourceId?: string;
  panelId: string;
  onSelectSource: (chunkId: string, opener: HTMLButtonElement) => void;
};

export default function AnswerCard({ message, activeSourceId, panelId, onSelectSource }: Props) {
  const content = answerContent(message);
  const groups = groupSources(message.sources ?? []);

  return (
    <article className="answer-card">
      <div className="answer-card-body">
        {content ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ node, children, ...props }) => (
                <div className="markdown-table-wrap">
                  <table {...props}>{children}</table>
                </div>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        ) : (
          <span className="typing-indicator"><span>AI 正在思考</span><i /><i /><i /></span>
        )}
      </div>
      {groups.length > 0 && (
        <section className="answer-sources" aria-label="回答来源">
          <span className="answer-sources-label">来源</span>
          {groups.map((group) => (
            <button
              key={group[0].document_id || group[0].file_name}
              type="button"
              className="answer-source-chip"
              aria-pressed={group.some((source) => source.chunk_id === activeSourceId)}
              aria-controls={activeSourceId ? panelId : undefined}
              onClick={(event) => onSelectSource(group[0].chunk_id, event.currentTarget)}
            >
              <ChatIcon name="file" />
              <span>{group[0].file_name}</span>
              {group.length > 1 && <span className="answer-source-count">{group.length} 段</span>}
            </button>
          ))}
        </section>
      )}
    </article>
  );
}
