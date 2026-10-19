import { FormEvent, useEffect, useState } from "react";
import { fetchSecretSettings, fetchSettings, saveSettings } from "../api/settings";
import type { AppSettings } from "../types/settings";

type SecretName = "embedding" | "llm";

export default function SettingsForm() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [status, setStatus] = useState("");
  const [visibleSecrets, setVisibleSecrets] = useState<Record<SecretName, boolean>>({
    embedding: false,
    llm: false,
  });
  const [secretValuesLoaded, setSecretValuesLoaded] = useState(false);
  const [loadingSecret, setLoadingSecret] = useState<SecretName | null>(null);

  useEffect(() => {
    fetchSettings().then(setSettings).catch((error) => setStatus(error.message));
  }, []);

  async function toggleSecretVisibility(secretName: SecretName) {
    if (visibleSecrets[secretName]) {
      setVisibleSecrets((current) => ({ ...current, [secretName]: false }));
      return;
    }

    if (!secretValuesLoaded) {
      setLoadingSecret(secretName);
      try {
        const secrets = await fetchSecretSettings();
        setEmbeddingApiKey((current) => current || secrets.embedding_api_key);
        setLlmApiKey((current) => current || secrets.llm_api_key);
        setSecretValuesLoaded(true);
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "读取 API Key 失败");
        return;
      } finally {
        setLoadingSecret(null);
      }
    }

    setVisibleSecrets((current) => ({ ...current, [secretName]: true }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    try {
      const saved = await saveSettings({
        ...settings,
        secrets: {
          ...settings.secrets,
          embedding_api_key: embeddingApiKey,
          llm_api_key: llmApiKey,
        },
      } as AppSettings & { secrets: Record<string, string | boolean | undefined> });
      setSettings(saved);
      setVisibleSecrets({ embedding: false, llm: false });
      setStatus("设置已保存");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存失败");
    }
  }

  if (!settings) {
    return <p className="empty">{status || "正在加载设置..."}</p>;
  }

  return (
    <form className="settings-form" onSubmit={onSubmit}>
      <div className="settings-actions">
        <h1>系统设置</h1>
        {status && <p className="status-text">{status}</p>}
        <button type="submit">保存设置</button>
      </div>

      <section className="settings-section">
        <div className="settings-section-title">
          <h2>Embedding 向量化</h2>
          <label
            className="toggle-row"
            title="开启后不调用真实 Embedding API，返回固定向量，用于本地调试"
          >
            <input
              type="checkbox"
              checked={settings.embedding.mock}
              onChange={(event) => setSettings({ ...settings, embedding: { ...settings.embedding, mock: event.target.checked } })}
            />
            Mock 模式
          </label>
        </div>
        <div className="settings-fields">
          <label>
            <span>Base URL</span>
            <input
              value={settings.embedding.base_url}
              onChange={(event) => setSettings({ ...settings, embedding: { ...settings.embedding, base_url: event.target.value } })}
            />
            <small className="field-hint">Embedding 服务的 OpenAI 兼容接口地址</small>
          </label>
          <label>
            <span>Model</span>
            <input
              value={settings.embedding.model}
              onChange={(event) => setSettings({ ...settings, embedding: { ...settings.embedding, model: event.target.value } })}
            />
            <small className="field-hint">更换模型、服务地址或 Mock 模式后，请在文件库的更多操作中重新索引已有文件</small>
          </label>
          <label className="span-2">
            <span>API Key</span>
            <div className="secret-field">
              <input
                type={visibleSecrets.embedding ? "text" : "password"}
                value={embeddingApiKey}
                onChange={(event) => setEmbeddingApiKey(event.target.value)}
                placeholder={settings.secrets?.embedding_api_key_configured ? "已配置，点击显示查看" : "请输入 Embedding API Key"}
              />
              <button
                type="button"
                className="secret-toggle"
                onClick={() => void toggleSecretVisibility("embedding")}
                disabled={loadingSecret === "embedding"}
              >
                {loadingSecret === "embedding" ? "读取中..." : visibleSecrets.embedding ? "隐藏" : "显示"}
              </button>
            </div>
            <small className="field-hint">
              {settings.secrets?.embedding_api_key_configured
                ? "已配置；默认隐藏，点击“显示”查看，留空保存表示保持不变"
                : "调用 Embedding 服务所需的密钥，仅在当前页面保留，刷新后不会回显"}
            </small>
          </label>
          <label className="toggle-field span-2">
            <input
              type="checkbox"
              checked={settings.embedding.normalize}
              onChange={(event) => setSettings({ ...settings, embedding: { ...settings.embedding, normalize: event.target.checked } })}
            />
            <span>
              向量归一化
              <small className="field-hint">将向量缩放到单位长度，相似度计算更稳定，一般保持开启</small>
            </span>
          </label>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-title">
          <h2>LLM 对话模型</h2>
          <label
            className="toggle-row"
            title="开启后不调用真实 LLM API，返回固定回答；关闭后支持英文检索表达扩展"
          >
            <input
              type="checkbox"
              checked={settings.llm.mock}
              onChange={(event) => setSettings({ ...settings, llm: { ...settings.llm, mock: event.target.checked } })}
            />
            Mock 模式
          </label>
        </div>
        <div className="settings-fields">
          <label>
            <span>Base URL</span>
            <input
              value={settings.llm.base_url}
              onChange={(event) => setSettings({ ...settings, llm: { ...settings.llm, base_url: event.target.value } })}
            />
            <small className="field-hint">LLM 服务的 OpenAI 兼容接口地址</small>
          </label>
          <label>
            <span>Model</span>
            <input
              value={settings.llm.model}
              onChange={(event) => setSettings({ ...settings, llm: { ...settings.llm, model: event.target.value } })}
            />
            <small className="field-hint">用于生成回答和跨语言检索表达的对话模型名称</small>
          </label>
          <label className="span-2">
            <span>API Key</span>
            <div className="secret-field">
              <input
                type={visibleSecrets.llm ? "text" : "password"}
                value={llmApiKey}
                onChange={(event) => setLlmApiKey(event.target.value)}
                placeholder={settings.secrets?.llm_api_key_configured ? "已配置，点击显示查看" : "请输入 LLM API Key"}
              />
              <button
                type="button"
                className="secret-toggle"
                onClick={() => void toggleSecretVisibility("llm")}
                disabled={loadingSecret === "llm"}
              >
                {loadingSecret === "llm" ? "读取中..." : visibleSecrets.llm ? "隐藏" : "显示"}
              </button>
            </div>
            <small className="field-hint">
              {settings.secrets?.llm_api_key_configured
                ? "已配置；默认隐藏，点击“显示”查看，留空保存表示保持不变"
                : "调用 LLM 服务所需的密钥，仅在当前页面保留，刷新后不会回显"}
            </small>
          </label>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-title">
          <h2>检索参数</h2>
        </div>
        <div className="settings-fields">
          <label>
            <span>检索引擎</span>
            <select
              value={settings.retrieval.engine ?? "bm25_faiss"}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, engine: event.target.value as "bm25_faiss" | "legacy" } })}
            >
              <option value="bm25_faiss">BM25 + FAISS（默认）</option>
              <option value="legacy">原检索引擎（兼容回退）</option>
            </select>
            <small className="field-hint">双路召回后融合排序；需要对比或回退时可选择原引擎</small>
          </label>
          <label>
            <span>检索模式</span>
            <select
              value={settings.retrieval.search_mode}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, search_mode: event.target.value as "hybrid" | "vector" | "keyword" } })}
            >
              <option value="hybrid">混合检索（推荐）</option>
              <option value="vector">纯向量检索</option>
              <option value="keyword">纯关键词检索</option>
            </select>
            <small className="field-hint">混合检索结合关键词与语义召回；新引擎使用 RRF 融合排名</small>
          </label>
          <label>
            <span>Top K</span>
            <input
              type="number"
              value={settings.retrieval.top_k}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, top_k: Number(event.target.value) } })}
            />
            <small className="field-hint">融合、去重及文档数量限制后，最多返回 K 个片段</small>
          </label>
          <label>
            <span>{settings.retrieval.engine === "legacy" ? "相关性阈值" : "向量相似度阈值"}</span>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              disabled={settings.retrieval.engine !== "legacy" && settings.retrieval.search_mode === "keyword"}
              value={settings.retrieval.score_threshold}
              onChange={(event) =>
                setSettings({ ...settings, retrieval: { ...settings.retrieval, score_threshold: Number(event.target.value) } })
              }
            />
            <small className="field-hint">{settings.retrieval.engine === "legacy"
              ? "沿用原引擎的评分阈值，0 表示不过滤"
              : "仅过滤向量召回；BM25 和 RRF 排名分数不使用此阈值"}</small>
          </label>
          <label>
            <span>每文档最大 Chunk 数</span>
            <input
              type="number"
              min="0"
              max="10"
              value={settings.retrieval.max_chunks_per_doc}
              onChange={(event) =>
                setSettings({ ...settings, retrieval: { ...settings.retrieval, max_chunks_per_doc: Number(event.target.value) } })
              }
            />
            <small className="field-hint">限制单个文档最多召回的片段数，避免一份文档占满上下文</small>
          </label>
          <label>
            <span>全量计算最大 Chunk 数</span>
            <input
              type="number"
              min="1"
              max="10000"
              value={settings.retrieval.full_scan_max_chunks}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  retrieval: {
                    ...settings.retrieval,
                    full_scan_max_chunks: Number(event.target.value),
                  },
                })
              }
            />
            <small className="field-hint">超过此数量时不让模型基于不完整资料计算</small>
          </label>
          <label>
            <span>Chunk Size</span>
            <input
              type="number"
              value={settings.retrieval.chunk_size}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, chunk_size: Number(event.target.value) } })}
            />
            <small className="field-hint">文档入库时每个文本块的切分长度（字符）</small>
          </label>
          <label>
            <span>Overlap</span>
            <input
              type="number"
              value={settings.retrieval.overlap}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, overlap: Number(event.target.value) } })}
            />
            <small className="field-hint">相邻文本块的重叠长度，避免句子被切断影响召回</small>
          </label>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-title">
          <h2>对话上下文</h2>
        </div>
        <div className="settings-fields">
          <label>
            <span>上下文消息数</span>
            <input
              type="number"
              min="0"
              max="50"
              value={settings.conversation.context_window}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  conversation: {
                    ...settings.conversation,
                    context_window: Number(event.target.value),
                  },
                })
              }
            />
            <small className="field-hint">提问时携带最近 N 条历史消息，让多轮对话更连贯</small>
          </label>
        </div>
      </section>
    </form>
  );
}
