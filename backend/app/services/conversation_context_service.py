from app.services.json_store_service import json_store


class ConversationContextService:
    def build_context(
        self, messages: list[dict], window_size: int | None = None, *, scope_revision: int = 0,
    ) -> str:
        window_size = self._window_size() if window_size is None else self._clamp_window_size(window_size)
        if window_size <= 0:
            return "无"

        history = [
            message
            for message in messages
            if message.get("scope_revision", 0) == scope_revision
            and message.get("role") in {"user", "assistant"} and str(message.get("content") or "").strip()
        ]
        history = history[-window_size:]
        if not history:
            return "无"

        lines = []
        for message in history:
            role = "用户" if message.get("role") == "user" else "助手"
            content = str(message.get("content") or "").strip()
            lines.append(f"{role}：{content}")
        return "\n".join(lines) if lines else "无"

    def _window_size(self) -> int:
        settings = json_store.read_json("settings.json")
        conversation_settings = settings.get("conversation", {}) if isinstance(settings, dict) else {}
        return self._clamp_window_size(conversation_settings.get("context_window", 8))

    def _clamp_window_size(self, value) -> int:
        try:
            return min(max(int(value), 0), 50)
        except (TypeError, ValueError):
            return 8


conversation_context_service = ConversationContextService()
