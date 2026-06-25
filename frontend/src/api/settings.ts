import { request } from "./client";
import type { AppSettings } from "../types/settings";

export function fetchSettings() {
  return request<AppSettings>("/api/settings");
}

export function saveSettings(settings: AppSettings) {
  return request<AppSettings>("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

