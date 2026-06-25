import re

import httpx

from app.core.config import settings
from app.services.json_store_service import json_store


class LlmService:
    def generate_answer(self, prompt: str) -> str:
        config = self._get_config()
        if config["mock"]:
            return self._mock_answer(prompt)
        return self._api_answer(prompt, config)

    def _get_config(self) -> dict:
        settings_json = json_store.read_json("settings.json")
        llm_settings = settings_json.get("llm", {}) if isinstance(settings_json, dict) else {}
        return {
            "provider": llm_settings.get("provider", settings.llm_provider),
            "base_url": llm_settings.get("base_url", settings.llm_base_url).rstrip("/"),
            "api_key": settings.llm_api_key,
            "model": llm_settings.get("model", settings.llm_model),
            "mock": bool(llm_settings.get("mock", settings.llm_mock)),
        }

    def _mock_answer(self, prompt: str) -> str:
        context = self._extract_block(prompt, "【已检索表格资料】", "【用户问题】")
        question = self._extract_after(prompt, "【用户问题】")
        if not context.strip():
            return "知识库中未找到明确依据。"

        first_row = next((line.strip() for line in context.splitlines() if line.strip().startswith("行 ")), "")
        first_file = self._first_value(context, "文件名：")
        first_sheet = self._first_value(context, "Sheet：")
        answer = "根据已检索表格资料"
        if first_row:
            answer += f"，相关记录为：{first_row}"
        if question:
            answer += f"。针对你的问题“{question.strip()}”，请以上述表格记录为准。"
        if first_file or first_sheet:
            answer += f"\n\n参考来源：{first_file or '未知文件'} / {first_sheet or '未知 Sheet'}"
        return answer

    def _api_answer(self, prompt: str, config: dict) -> str:
        if not config["api_key"]:
            raise ValueError("LLM_API_KEY is required when LLM_MOCK=false.")
        if config["provider"] != "openai-compatible":
            raise ValueError(f"Unsupported LLM provider: {config['provider']}")

        response = httpx.post(
            f"{config['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json={
                "model": config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    def _extract_block(self, text: str, start_marker: str, end_marker: str) -> str:
        pattern = re.escape(start_marker) + r"(.*?)" + re.escape(end_marker)
        match = re.search(pattern, text, flags=re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_after(self, text: str, marker: str) -> str:
        if marker not in text:
            return ""
        return text.split(marker, 1)[1].strip()

    def _first_value(self, text: str, prefix: str) -> str:
        for line in text.splitlines():
            if line.strip().startswith(prefix):
                return line.split(prefix, 1)[1].strip()
        return ""


llm_service = LlmService()
