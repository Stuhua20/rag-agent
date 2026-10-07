import { useEffect, useMemo, useState } from "react";
import { fetchPrompt, fetchPrompts, savePrompt } from "../api/prompts";
import { useToast } from "../components/Toast";
import type { PromptSummary } from "../types/prompt";

const PROMPT_INTROS: Record<string, { role: string; description: string; impact: string }> = {
  "system/base.md": {
    role: "基础角色",
    description: "定义助手的身份、回答边界和语言风格，是最终回答模板的基础规则。",
    impact: "会影响所有有检索资料时的回答口径。",
  },
  "query/planner.md": {
    role: "查询规划",
    description: "把用户问题转换为结构化 Query Plan，包括意图、子问题、过滤条件和检索建议。",
    impact: "会影响系统如何理解问题、检索哪些知识库资料以及返回多少上下文。",
  },
  "query/translator.md": {
    role: "检索翻译",
    description: "把检索表达翻译成另一种语言，保持实体、数字和限定条件不变。",
    impact: "会影响中英文知识库之间的检索召回范围。",
  },
  "rag/answer.md": {
    role: "答案生成",
    description: "在检索到资料后，组合系统规则、检索上下文和用户问题来生成最终回答。",
    impact: "会影响有来源资料时的回答结构、语气和限制。",
  },
  "rag/no_source.md": {
    role: "无资料回复",
    description: "没有检索到任何相关资料时，直接返回的固定文案。",
    impact: "只影响无检索结果的回答。",
  },
};

function getPromptIntro(prompt?: PromptSummary) {
  if (!prompt) {
    return {
      role: "未选择",
      description: "请选择左侧提示词文件查看说明和内容。",
      impact: "选择文件后可查看编辑影响。",
    };
  }

  return (
    PROMPT_INTROS[prompt.path] || {
      role: prompt.group === "." ? "提示词文件" : prompt.group,
      description: "项目提示词目录中的 Markdown 文件。",
      impact: "是否影响运行时取决于后端服务是否加载该文件。",
    }
  );
}

export default function PromptsPage() {
  const { toast } = useToast();
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  const selectedPrompt = useMemo(
    () => prompts.find((prompt) => prompt.path === selectedPath),
    [prompts, selectedPath],
  );
  const selectedIntro = getPromptIntro(selectedPrompt);
  const hasChanges = content !== savedContent;

  useEffect(() => {
    let ignore = false;

    async function loadPrompts() {
      try {
        const items = await fetchPrompts();
        if (ignore) return;
        setPrompts(items);
        setSelectedPath((current) => current || items[0]?.path || "");
      } catch (error) {
        if (!ignore) {
          setStatus(error instanceof Error ? error.message : "加载提示词失败");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    loadPrompts();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedPath) return;
    let ignore = false;

    async function loadPrompt() {
      setStatus("");
      try {
        const detail = await fetchPrompt(selectedPath);
        if (!ignore) {
          setContent(detail.content);
          setSavedContent(detail.content);
        }
      } catch (error) {
        if (!ignore) {
          setStatus(error instanceof Error ? error.message : "加载提示词内容失败");
        }
      }
    }

    loadPrompt();
    return () => {
      ignore = true;
    };
  }, [selectedPath]);

  async function onSave() {
    if (!selectedPath || !hasChanges) return;
    setSaving(true);
    setStatus("");
    try {
      const saved = await savePrompt(selectedPath, content);
      setContent(saved.content);
      setSavedContent(saved.content);
      toast("提示词已保存", "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存提示词失败";
      setStatus(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="page-panel">
        <h1>提示词</h1>
        <p className="empty">正在加载提示词...</p>
      </div>
    );
  }

  return (
    <div className="page-panel prompts-page">
      <div className="section-header">
        <div>
          <h1>提示词</h1>
          <p className="page-subtitle">查看和修改问题理解、检索增强、答案生成相关提示词。</p>
        </div>
        <button type="button" onClick={onSave} disabled={!hasChanges || saving || !selectedPath}>
          {saving ? "保存中..." : "保存提示词"}
        </button>
      </div>

      <div className="prompts-layout">
        <aside className="prompt-list" aria-label="提示词文件">
          {prompts.map((prompt) => (
            <button
              key={prompt.path}
              type="button"
              className={prompt.path === selectedPath ? "prompt-list-item active" : "prompt-list-item"}
              onClick={() => setSelectedPath(prompt.path)}
            >
              <span>{prompt.name}</span>
              <small>{prompt.path}</small>
              <em>{getPromptIntro(prompt).role}</em>
            </button>
          ))}
          {prompts.length === 0 && <p className="empty">没有可编辑的提示词文件</p>}
        </aside>

        <section className="prompt-editor">
          <header className="prompt-editor-head">
            <div className="prompt-editor-inner prompt-editor-bar">
              <div className="prompt-editor-title">
                <h2>{selectedPrompt?.name || "未选择提示词"}</h2>
                {selectedPrompt && <code className="prompt-path">{selectedPrompt.path}</code>}
              </div>
              {selectedPrompt && (
                <span className={hasChanges ? "prompt-state dirty" : "prompt-state"}>
                  {hasChanges ? "未保存" : "已保存"}
                </span>
              )}
            </div>
          </header>

          <div className="prompt-intro" aria-label="提示词介绍">
            <div className="prompt-editor-inner prompt-intro-grid">
              <div className="prompt-intro-item">
                <span className="prompt-intro-label">用途</span>
                <strong>{selectedIntro.role}</strong>
                <p>{selectedIntro.description}</p>
              </div>
              <div className="prompt-intro-item">
                <span className="prompt-intro-label">编辑影响</span>
                <p>{selectedIntro.impact}</p>
              </div>
            </div>
          </div>

          <div className="prompt-editor-body">
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              spellCheck={false}
              disabled={!selectedPath}
              aria-label="提示词内容"
            />
          </div>
          {status && <p className="status-text">{status}</p>}
        </section>
      </div>
    </div>
  );
}
