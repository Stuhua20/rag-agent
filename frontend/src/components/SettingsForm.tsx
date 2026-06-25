import { FormEvent, useEffect, useState } from "react";
import { fetchSettings, saveSettings } from "../api/settings";
import type { AppSettings } from "../types/settings";

export default function SettingsForm() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetchSettings().then(setSettings).catch((error) => setStatus(error.message));
  }, []);

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
      setEmbeddingApiKey("");
      setLlmApiKey("");
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
      <section className="settings-section">
        <div className="settings-section-title">
          <h2>Embedding</h2>
          <label className="toggle-row">
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
            Base URL
            <input
              value={settings.embedding.base_url}
              onChange={(event) => setSettings({ ...settings, embedding: { ...settings.embedding, base_url: event.target.value } })}
            />
          </label>
          <label>
            Model
            <input
              value={settings.embedding.model}
              onChange={(event) => setSettings({ ...settings, embedding: { ...settings.embedding, model: event.target.value } })}
            />
          </label>
          <label className="span-2">
            API Key
            <input
              type="password"
              value={embeddingApiKey}
              onChange={(event) => setEmbeddingApiKey(event.target.value)}
              placeholder={settings.secrets?.embedding_api_key_configured ? "已配置，留空则不修改" : "请输入 Embedding API Key"}
            />
          </label>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-title">
          <h2>LLM</h2>
          <label className="toggle-row">
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
            Base URL
            <input
              value={settings.llm.base_url}
              onChange={(event) => setSettings({ ...settings, llm: { ...settings.llm, base_url: event.target.value } })}
            />
          </label>
          <label>
            Model
            <input
              value={settings.llm.model}
              onChange={(event) => setSettings({ ...settings, llm: { ...settings.llm, model: event.target.value } })}
            />
          </label>
          <label className="span-2">
            API Key
            <input
              type="password"
              value={llmApiKey}
              onChange={(event) => setLlmApiKey(event.target.value)}
              placeholder={settings.secrets?.llm_api_key_configured ? "已配置，留空则不修改" : "请输入 LLM API Key"}
            />
          </label>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-title">
          <h2>检索参数</h2>
        </div>
        <div className="settings-fields">
          <label>
            Top K
            <input
              type="number"
              value={settings.retrieval.top_k}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, top_k: Number(event.target.value) } })}
            />
          </label>
          <label>
            Chunk Size
            <input
              type="number"
              value={settings.retrieval.chunk_size}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, chunk_size: Number(event.target.value) } })}
            />
          </label>
          <label>
            Overlap
            <input
              type="number"
              value={settings.retrieval.overlap}
              onChange={(event) => setSettings({ ...settings, retrieval: { ...settings.retrieval, overlap: Number(event.target.value) } })}
            />
          </label>
          <label>
            Score Threshold
            <input
              type="number"
              step="0.01"
              value={settings.retrieval.score_threshold}
              onChange={(event) =>
                setSettings({ ...settings, retrieval: { ...settings.retrieval, score_threshold: Number(event.target.value) } })
              }
            />
          </label>
        </div>
      </section>

      <div className="settings-actions">
        <button type="submit">保存设置</button>
        {status && <p className="status-text">{status}</p>}
      </div>
    </form>
  );
}
