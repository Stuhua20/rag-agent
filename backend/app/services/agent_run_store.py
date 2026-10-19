import json
import sqlite3
from pathlib import Path
from threading import RLock

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from app.utils.time_utils import utc_now_iso


class AgentRunStore:
    """Local single-process persistence. Business messages remain in JSON."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.conn = sqlite3.connect(directory / "runs.sqlite", check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS agent_runs (
            run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
            status TEXT NOT NULL, updated_at TEXT NOT NULL, summary TEXT NOT NULL
        )""")
        self.conn.execute("UPDATE agent_runs SET status='interrupted' WHERE status='running'")
        self.conn.commit()
        self.checkpoint_conn = sqlite3.connect(directory / "checkpoints.sqlite", check_same_thread=False)
        self.checkpointer = SqliteSaver(
            self.checkpoint_conn, serde=JsonPlusSerializer(pickle_fallback=False),
        )
        self.checkpointer.setup()
        self.prune()

    def record(self, run_id: str, conversation_id: str, status: str, summary: dict) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO agent_runs VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, "
                "updated_at=excluded.updated_at, summary=excluded.summary",
                (run_id, conversation_id, status, utc_now_iso(), json.dumps(summary, ensure_ascii=False)),
            )

    def delete_conversation(self, conversation_id: str) -> None:
        with self.lock:
            ids = [row[0] for row in self.conn.execute(
                "SELECT run_id FROM agent_runs WHERE conversation_id=?", (conversation_id,),
            )]
            for run_id in ids:
                self.checkpointer.delete_thread(run_id)
            with self.conn:
                self.conn.execute("DELETE FROM agent_runs WHERE conversation_id=?", (conversation_id,))

    def prune(self) -> None:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        with self.lock:
            ids = [row[0] for row in self.conn.execute(
                "SELECT run_id FROM agent_runs WHERE status!='running' AND updated_at<? LIMIT 100", (cutoff,),
            )]
            for run_id in ids:
                self.checkpointer.delete_thread(run_id)
            with self.conn:
                self.conn.executemany("DELETE FROM agent_runs WHERE run_id=?", [(item,) for item in ids])

    def close(self) -> None:
        self.checkpoint_conn.close()
        self.conn.close()
