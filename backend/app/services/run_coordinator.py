from threading import RLock


class RunCoordinator:
    """One active knowledge-QA run per conversation (single process)."""
    def __init__(self):
        self.lock = RLock()
        self.active = {}
        self.streams = {}

    def cancel(self, conversation_id):
        with self.lock:
            budget = self.active.get(conversation_id)
            if budget:
                budget.cancelled.set()
