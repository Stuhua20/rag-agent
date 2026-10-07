import json as json_module
import re
import time
from collections.abc import Generator

import httpx

from app.core.config import settings
from app.services.json_store_service import json_store
from app.utils.config_utils import as_bool


class LlmService:
    def generate_answer(self, prompt: str, system_prompt: str | None = None) -> str:
        config = self._get_config()
        if config["mock"]:
            return self._mock_answer(prompt)
        return self._api_answer(prompt, config, system_prompt)

    def generate_answer_stream(self, prompt: str, system_prompt: str | None = None) -> Generator[str, None, None]:
        config = self._get_config()
        if config["mock"]:
            yield from self._mock_answer_stream(prompt)
        else:
            yield from self._api_answer_stream(prompt, config, system_prompt)

    def _get_config(self) -> dict:
        settings_json = json_store.read_json("settings.json")
        llm_settings = settings_json.get("llm", {}) if isinstance(settings_json, dict) else {}
        return {
            "provider": llm_settings.get("provider", settings.llm_provider),
            "base_url": llm_settings.get("base_url", settings.llm_base_url).rstrip("/"),
            "api_key": settings.llm_api_key,
            "model": llm_settings.get("model", settings.llm_model),
            "mock": as_bool(llm_settings.get("mock"), settings.llm_mock),
        }

    def _mock_answer(self, prompt: str) -> str:
        context = self._extract_block(prompt, "【已检索知识库资料】", "【用户问题】")
        if not context.strip():
            # Keep compatibility with prompts saved before generic document support.
            context = self._extract_block(prompt, "【已检索表格资料】", "【用户问题】")
        question = self._extract_after(prompt, "【用户问题】")
        if not context.strip():
            return "知识库中未找到明确依据。"

        first_row = next((line.strip() for line in context.splitlines() if line.strip().startswith("行 ")), "")
        first_file = self._first_value(context, "文件名：")
        first_sheet = self._first_value(context, "Sheet：")
        answer = "根据已检索知识库资料"
        if first_row:
            answer += f"，相关记录为：{first_row}"
        if question:
            answer += f"。针对你的问题“{question.strip()}”，请以上述资料为准。"
        if first_file or first_sheet:
            answer += f"\n\n参考来源：{first_file or '未知文件'} / {first_sheet or '未知 Sheet'}"
        return answer

    def _messages(self, prompt: str, system_prompt: str | None = None) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _api_answer(self, prompt: str, config: dict, system_prompt: str | None = None) -> str:
        if not config["api_key"]:
            raise ValueError("LLM_API_KEY is required when LLM_MOCK=false.")
        if config["provider"] != "openai-compatible":
            raise ValueError(f"Unsupported LLM provider: {config['provider']}")

        response = httpx.post(
            f"{config['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json={
                "model": config["model"],
                "messages": self._messages(prompt, system_prompt),
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    def _mock_answer_stream(self, prompt: str) -> Generator[str, None, None]:
        full_answer = self._mock_answer(prompt)
        for i in range(0, len(full_answer), 3):
            yield full_answer[i : i + 3]
            time.sleep(0.03)

    def _api_answer_stream(self, prompt: str, config: dict, system_prompt: str | None = None) -> Generator[str, None, None]:
        if not config["api_key"]:
            raise ValueError("LLM_API_KEY is required when LLM_MOCK=false.")
        if config["provider"] != "openai-compatible":
            raise ValueError(f"Unsupported LLM provider: {config['provider']}")

        with httpx.stream(
            "POST",
            f"{config['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            json={
                "model": config["model"],
                "messages": self._messages(prompt, system_prompt),
                "temperature": 0.2,
                "stream": True,
            },
            timeout=120,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json_module.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json_module.JSONDecodeError, IndexError, KeyError):
                    continue

    def _extract_block(self, text: str, start_marker: str, end_marker: str) -> str:
        pattern = re.escape(start_marker) + r"(.*?)" + re.escape(end_marker)
        match = re.search(pattern, text, flags=re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_after(self, text: str, marker: str) -> str:
        matches = list(re.finditer(rf"(?m)^\s*{re.escape(marker)}\s*$", text))
        if not matches:
            return ""
        return text[matches[-1].end() :].strip()

    def _first_value(self, text: str, prefix: str) -> str:
        for line in text.splitlines():
            if line.strip().startswith(prefix):
                return line.split(prefix, 1)[1].strip()
        return ""


llm_service = LlmService()
