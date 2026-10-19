"""A context-local budget also covers nested planner/translation/model calls."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event, Lock


class BudgetExceeded(RuntimeError):
    pass


class RunCancelled(RuntimeError):
    pass


@dataclass
class RunBudget:
    seconds: float = 180
    max_llm_calls: int = 8
    max_tool_calls: int = 8
    started: float = field(default_factory=time.monotonic)
    cancelled: Event = field(default_factory=Event)
    llm_calls: int = 0
    tool_calls: int = 0
    reserved_llm_calls: int = 0
    lock: Lock = field(default_factory=Lock)

    def check(self) -> None:
        if self.cancelled.is_set():
            raise RunCancelled("运行已取消。")
        if time.monotonic() - self.started >= self.seconds:
            raise BudgetExceeded("time_budget")

    def timeout(self, default: float) -> float:
        self.check()
        return min(default, max(0.01, self.seconds - (time.monotonic() - self.started)))

    def consume(self, kind: str) -> None:
        self.check()
        with self.lock:
            name = "llm_calls" if kind == "llm" else "tool_calls"
            limit = self.max_llm_calls if kind == "llm" else self.max_tool_calls
            reserved = self.reserved_llm_calls if kind == "llm" else 0
            if getattr(self, name) + reserved >= limit:
                raise BudgetExceeded(f"{kind}_budget")
            setattr(self, name, getattr(self, name) + 1)

    def reserve_llm(self, count: int) -> None:
        self.check()
        with self.lock:
            if self.max_llm_calls - self.llm_calls < count:
                raise BudgetExceeded("llm_budget")
            self.reserved_llm_calls = count

    def release_llm(self) -> None:
        with self.lock:
            self.reserved_llm_calls = max(0, self.reserved_llm_calls - 1)

    @contextmanager
    def activate(self):
        token = current_budget.set(self)
        try:
            yield
        finally:
            current_budget.reset(token)


current_budget: ContextVar[RunBudget | None] = ContextVar("agent_budget", default=None)


def check_budget() -> None:
    budget = current_budget.get()
    if budget:
        budget.check()


def request_timeout(default: float) -> float:
    budget = current_budget.get()
    return budget.timeout(default) if budget else default


def count_llm_call() -> None:
    budget = current_budget.get()
    if budget:
        budget.consume("llm")
