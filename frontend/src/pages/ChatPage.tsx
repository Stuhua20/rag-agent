import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { sendChatMessageStream } from "../api/chat";
import { ApiError } from "../api/client";
import { createConversation, fetchConversation, fetchConversationMessages, updateDocumentScope } from "../api/conversations";
import ChatWindow from "../components/ChatWindow";
import DocumentScopeDialog from "../components/DocumentScopeDialog";
import TopBar from "../components/TopBar";
import ChatWelcome from "../components/ChatWelcome";
import SelectedDocuments from "../components/SelectedDocuments";
import { useToast } from "../components/Toast";
import type { ChatMessage } from "../types/chat";
import type { Conversation, DocumentScope } from "../types/conversation";

const ALL_DOCUMENTS: DocumentScope = { mode: "all", document_ids: [] };

export default function ChatPage() {
  const [searchParams] = useSearchParams();
  const conversationId = searchParams.get("conversationId");
  const location = useLocation();
  const navigationState = location.state as { chatSessionKey?: string } | null;
  const sessionKey = navigationState?.chatSessionKey ?? conversationId ?? `new:${location.key}`;
  // A different conversation owns a different component and cancels all prior requests.
  return <ChatSession key={sessionKey} sessionKey={sessionKey} routeConversationId={conversationId} />;
}

function ChatSession({ routeConversationId, sessionKey }: { routeConversationId: string | null; sessionKey: string }) {
  const [conversationId, setConversationId] = useState(routeConversationId);
  const [title, setTitle] = useState(routeConversationId ? "正在加载聊天…" : "新聊天");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [scope, setScope] = useState<DocumentScope>(ALL_DOCUMENTS);
  const [revision, setRevision] = useState(0);
  const [invalidIds, setInvalidIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(Boolean(routeConversationId));
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [savingScope, setSavingScope] = useState(false);
  const [scopeNotice, setScopeNotice] = useState("");
  const streamControllerRef = useRef<AbortController | null>(null);
  const saveControllerRef = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  function applyConversation(conversation: Conversation) {
    setTitle(conversation.title || "新聊天");
    setScope(conversation.document_scope ?? ALL_DOCUMENTS);
    setRevision(conversation.scope_revision ?? 0);
    setInvalidIds(conversation.invalid_document_ids ?? []);
  }

  useEffect(() => {
    function handleRename(event: Event) {
      const conversation = (event as CustomEvent<Conversation>).detail;
      if (conversation.id === conversationId) setTitle(conversation.title || "新聊天");
    }
    window.addEventListener("conversation:renamed", handleRename);
    return () => window.removeEventListener("conversation:renamed", handleRename);
  }, [conversationId]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      streamControllerRef.current?.abort();
      saveControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!routeConversationId) return;
    const controller = new AbortController();
    setLoadingHistory(true);
    setLoadError("");
    Promise.all([
      fetchConversation(routeConversationId, controller.signal),
      fetchConversationMessages(routeConversationId, controller.signal),
    ]).then(([conversation, history]) => {
      if (controller.signal.aborted) return;
      applyConversation(conversation);
      setMessages(history);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setTitle("聊天加载失败");
        setLoadError(reason instanceof Error ? reason.message : "加载会话失败");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoadingHistory(false);
    });
    return () => controller.abort();
  }, [routeConversationId, retry]);

  async function refreshScope(id: string, signal: AbortSignal) {
    const conversation = await fetchConversation(id, signal);
    if (!signal.aborted && mounted.current) {
      applyConversation(conversation);
      setScopeNotice("已刷新当前检索范围，请核对后重新操作。");
    }
  }

  async function applyScope(nextScope: DocumentScope) {
    const controller = new AbortController();
    saveControllerRef.current = controller;
    setSavingScope(true);
    try {
      if (conversationId) {
        const conversation = await updateDocumentScope(conversationId, nextScope, revision, controller.signal);
        if (controller.signal.aborted || !mounted.current) return;
        applyConversation(conversation);
        if (conversation.scope_revision !== revision) setScopeNotice("检索范围已更新，后续问答将重新累计上下文。");
      } else {
        setScope(nextScope);
        setInvalidIds([]);
      }
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409 && conversationId) {
        await refreshScope(conversationId, controller.signal).catch(() => undefined);
      }
      throw reason;
    } finally {
      if (saveControllerRef.current === controller) saveControllerRef.current = null;
      if (!controller.signal.aborted && mounted.current) setSavingScope(false);
    }
  }

  async function handleSend(question: string) {
    if (streamControllerRef.current || loadingHistory || loadError || savingScope || scopeOpen || invalidIds.length) return false;
    const controller = new AbortController();
    streamControllerRef.current = controller;
    const active = () => mounted.current && !controller.signal.aborted;
    const assistantId = `local_assistant_${Date.now()}`;
    const scopeSnapshot = { document_scope: scope, scope_revision: revision };
    const userMessage: ChatMessage = { id: `local_user_${Date.now()}`, role: "user", content: question, created_at: new Date().toISOString(), ...scopeSnapshot };
    const assistantMessage: ChatMessage = { id: assistantId, role: "assistant", content: "", created_at: new Date().toISOString(), ...scopeSnapshot };
    setLoading(true);
    let targetId = conversationId;
    let appended = false;
    try {
      if (!targetId) {
        const conversation = await createConversation(question.slice(0, 30), scope, controller.signal);
        if (!active()) return false;
        targetId = conversation.id;
        setTitle(conversation.title || "新聊天");
        setConversationId(targetId);
        window.dispatchEvent(new Event("conversations:changed"));
      }
      setMessages((current) => [...current, userMessage, assistantMessage]);
      appended = true;
      await sendChatMessageStream({ conversation_id: targetId, question, expected_scope_revision: revision }, {
        onSources(_id, sources) {
          if (active()) setMessages((current) => current.map((msg) => msg.id === assistantId ? { ...msg, sources } : msg));
        },
        onDelta(text) {
          if (active()) setMessages((current) => current.map((msg) => msg.id === assistantId ? { ...msg, content: msg.content + text } : msg));
        },
        onDone(convId, answer) {
          if (!active()) return;
          setMessages((current) => current.map((msg) => msg.id === assistantId ? { ...msg, content: answer } : msg));
          window.dispatchEvent(new Event("conversations:changed"));
          if (!routeConversationId) navigate(`/?conversationId=${convId}`, { replace: true, state: { chatSessionKey: sessionKey } });
        },
      }, controller.signal);
      return active();
    } catch (reason) {
      if (!active()) return false;
      const message = reason instanceof Error ? reason.message : "回答流中断，请重试。";
      if (appended) setMessages((current) => current.map((msg) => msg.id === assistantId ? { ...msg, content: msg.content ? `${msg.content}\n\n> ⚠️ ${message}` : `⚠️ ${message}` } : msg));
      toast(message, "error");
      if (reason instanceof ApiError && reason.status === 409 && targetId) {
        await refreshScope(targetId, controller.signal).catch(() => undefined);
      }
      return false;
    } finally {
      if (streamControllerRef.current === controller) streamControllerRef.current = null;
      if (active()) setLoading(false);
    }
  }

  const blocked = loadingHistory || Boolean(loadError) || invalidIds.length > 0 || savingScope || scopeOpen;
  const scopeLabel = loadingHistory ? "正在加载…" : loadError ? "加载失败" : scope.mode === "all" ? "全部已入库文档" : `指定文档 · 已选 ${scope.document_ids.length} 个`;
  return (
    <>
    <TopBar title={title} />
    <div className="workspace chat-workspace">
      <section className="chat-layout">
        <ChatWindow messages={messages} loading={loading} disabled={blocked} onSend={handleSend}
          emptyState={loadingHistory ? <p className="chat-empty-status" role="status">正在加载聊天记录…</p> : loadError ? <p className="chat-empty-status">聊天记录加载失败，请在下方重试。</p> : <ChatWelcome />}
          scopeControls={
          <div className="document-scope-bar">
            <div className="scope-bar-row"><span>检索范围：<strong>{scopeLabel}</strong></span><button type="button" className="scope-secondary" disabled={loading || loadingHistory || Boolean(loadError) || savingScope} onClick={() => setScopeOpen(true)}>选择文档</button></div>
            {!loadingHistory && !loadError && scope.mode === "selected" && <SelectedDocuments documentIds={scope.document_ids} onEdit={() => setScopeOpen(true)} disabled={loading || savingScope} />}
            {scopeNotice && <p className="scope-hint" role="status">{scopeNotice}</p>}
            {invalidIds.length > 0 && <p className="scope-error" role="alert">{invalidIds.length} 个所选文档已不可用，请重新选择检索文档。</p>}
            {loadError && <p className="scope-error" role="alert">{loadError} <button type="button" className="scope-secondary" onClick={() => setRetry((value) => value + 1)}>重新加载会话</button></p>}
          </div>
        } />
      </section>
      {scopeOpen && <DocumentScopeDialog scope={scope} onApply={applyScope} onClose={() => setScopeOpen(false)} />}
    </div>
    </>
  );
}
