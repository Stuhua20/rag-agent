"""Keep historical service-contract tests on the explicit rollback runtime.

The new graph suite opts into langgraph and exercises the real default workflow,
while the original private-method mocks continue verifying legacy compatibility.
"""
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def legacy_contract_runtime(monkeypatch):
    monkeypatch.setattr(settings, "chat_runtime", "legacy")
