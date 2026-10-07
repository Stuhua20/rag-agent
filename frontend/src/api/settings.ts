import { request } from "./client";
import type { AppSettings } from "../types/settings";

export type SecretSettings = {
  embedding_api_key: string;
  llm_api_key: string;
};

export function fetchSettings() {
  return request<AppSettings>("/api/settings");
}

export function fetchSecretSettings() {
  return request<SecretSettings>("/api/settings/secrets");
}

export function saveSettings(settings: AppSettings) {
  return request<AppSettings>("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}
