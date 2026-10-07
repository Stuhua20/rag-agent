import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { deleteConversation, fetchConversations } from "../api/conversations";
import ConfirmModal from "./ConfirmModal";
import { useToast } from "./Toast";
import type { Conversation } from "../types/conversation";

const primaryLinks = [
  { to: "/", label: "新聊天", icon: "compose" },
  { to: "/documents", label: "文件库", icon: "library" },
  { to: "/prompts", label: "提示词", icon: "prompt" },
  { to: "/settings", label: "设置", icon: "settings" },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationToDelete, setConversationToDelete] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const activeConversationId = searchParams.get("conversationId");

  const recentConversations = useMemo(() => conversations.slice(0, 12), [conversations]);

  useEffect(() => {
    let ignore = false;

    async function load() {
      try {
        const items = await fetchConversations();
        if (!ignore) {
          setConversations(items);
        }
      } catch {
        if (!ignore) {
          setConversations([]);
        }
      }
    }

    load();
    window.addEventListener("conversations:changed", load);
    return () => {
      ignore = true;
      window.removeEventListener("conversations:changed", load);
    };
  }, []);

  function openNewChat() {
    navigate("/");
  }

  function openConversation(conversationId: string) {
    navigate(`/?conversationId=${conversationId}`);
  }

  async function confirmDeleteConversation() {
    if (!conversationToDelete || deleting) return;

    const deletingConversation = conversationToDelete;
    setDeleting(true);
    try {
      await deleteConversation(deletingConversation.id);
      setConversations((current) =>
        current.filter((conversation) => conversation.id !== deletingConversation.id),
      );
      setConversationToDelete(null);
      toast("聊天记录已删除", "success");
      window.dispatchEvent(new Event("conversations:changed"));
      if (deletingConversation.id === activeConversationId) {
        navigate("/", { replace: true });
      }
    } catch {
      toast("删除聊天记录失败，请重试", "error");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="brand-row">
          <div className="brand">知识库demo</div>
          <button
            type="button"
            className="sidebar-collapse"
            aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            onClick={onToggle}
          >
            <Icon name="panel" />
          </button>
        </div>

        <nav className="nav-list" aria-label="主导航">
          {primaryLinks.map((link) =>
            link.label === "新聊天" ? (
              <button key={link.label} type="button" className="nav-item" onClick={openNewChat}>
                <Icon name={link.icon} />
                <span>{link.label}</span>
              </button>
            ) : (
              <NavLink
                key={link.label}
                to={link.to}
                className={({ isActive }) =>
                  isActive && location.pathname !== "/" ? "nav-item active" : "nav-item"
                }
              >
                <Icon name={link.icon} />
                <span>{link.label}</span>
              </NavLink>
            ),
          )}
        </nav>
      </div>

      <div className="sidebar-scroll">
        <div className="sidebar-section-title">聊天</div>
        <div className="sidebar-chat-list">
          {recentConversations.map((conversation) => (
            <div
              key={conversation.id}
              className={
                conversation.id === activeConversationId
                  ? "sidebar-chat-row active"
                  : "sidebar-chat-row"
              }
            >
              <button
                type="button"
                className="sidebar-chat-item"
                title={conversation.title}
                onClick={() => openConversation(conversation.id)}
              >
                {conversation.title}
              </button>
              <button
                type="button"
                className="sidebar-chat-delete"
                title={`删除 ${conversation.title}`}
                aria-label={`删除 ${conversation.title}`}
                onClick={() => setConversationToDelete(conversation)}
              >
                <Icon name="trash" />
              </button>
            </div>
          ))}
          {recentConversations.length === 0 && (
            <p className="sidebar-empty">暂无历史聊天</p>
          )}
        </div>
      </div>

      <ConfirmModal
        open={Boolean(conversationToDelete)}
        title="删除聊天记录"
        message={`确定删除「${conversationToDelete?.title ?? ""}」吗？此操作无法撤销。`}
        confirmLabel={deleting ? "删除中..." : "删除"}
        danger
        onConfirm={confirmDeleteConversation}
        onCancel={() => {
          if (!deleting) setConversationToDelete(null);
        }}
      />
    </aside>
  );
}

function Icon({ name }: { name: string }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  switch (name) {
    case "compose":
      return (
        <svg {...common}>
          <path d="M19.5 11.5a7.5 7.5 0 0 1-7.5 7.5H7l-3 2v-4.4a7.2 7.2 0 0 1-1-3.6A7.5 7.5 0 0 1 10.5 6a7.5 7.5 0 0 1 9 5.5Z" />
          <path d="M12 9.25v5.5" />
          <path d="M9.25 12h5.5" />
        </svg>
      );
    case "library":
      return (
        <svg {...common}>
          <path d="M5 7.5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2V19H7a2 2 0 0 1-2-2Z" />
          <path d="M7 5.5v12A1.5 1.5 0 0 0 8.5 19H19" />
          <path d="M11 10h4.5" />
          <path d="M11 13.5h5.5" />
          <path d="M11 17h3.5" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common}>
          <path d="M4 7h16" />
          <circle cx="9" cy="7" r="2" />
          <path d="M4 12h16" />
          <circle cx="15" cy="12" r="2" />
          <path d="M4 17h16" />
          <circle cx="11" cy="17" r="2" />
        </svg>
      );
    case "prompt":
      return (
        <svg {...common}>
          <path d="M5 6.5A2.5 2.5 0 0 1 7.5 4H14l5 5v8.5a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 17.5Z" />
          <path d="M14 4v5h5" />
          <path d="M9 13h5.5" />
          <path d="M9 16.5h3.5" />
          <path d="m6 3 .5 1.5L8 5l-1.5.5L6 7l-.5-1.5L4 5l1.5-.5Z" />
        </svg>
      );
    case "panel":
      return (
        <svg {...common}>
          <rect x="4" y="5" width="16" height="14" rx="3" />
          <path d="M10 5v14" />
        </svg>
      );
    case "trash":
      return (
        <svg {...common}>
          <path d="M4 7h16" />
          <path d="M10 11v6" />
          <path d="M14 11v6" />
          <path d="M6 7l1 13h10l1-13" />
          <path d="M9 7V4h6v3" />
        </svg>
      );
    default:
      return null;
  }
}
