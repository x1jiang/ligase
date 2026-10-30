"""Durable SQLite persistence for Ligase WebApp threads, messages, and run records."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class ThreadStore:
    """Thread-safe SQLite store scoped per client workspace key."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    profile TEXT NOT NULL DEFAULT 'ad1',
                    mode TEXT NOT NULL DEFAULT 'direct',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_threads_client
                    ON threads(client_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    run_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_thread
                    ON messages(thread_id, created_at ASC);

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    model TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    answer TEXT NOT NULL DEFAULT '',
                    elapsed_s REAL NOT NULL DEFAULT 0.0,
                    iterations INTEGER NOT NULL DEFAULT 0,
                    tool_trace_json TEXT NOT NULL DEFAULT '[]',
                    usage_json TEXT NOT NULL DEFAULT '{}',
                    run_dir TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    finished_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_client
                    ON runs(client_id, created_at DESC);
                """
            )

    def create_thread(
        self,
        client_id: str,
        title: str = "New Biomedical Study",
        profile: str = "ad1",
        mode: str = "direct",
    ) -> Dict[str, Any]:
        now = time.time()
        tid = f"thr_{uuid.uuid4().hex[:12]}"
        profile_norm = "a1" if str(profile).lower() == "a1" else "ad1"
        mode_norm = "plan" if str(mode).lower() == "plan" else "direct"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO threads (id, client_id, title, profile, mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tid, client_id, title[:120] or "New Biomedical Study", profile_norm, mode_norm, now, now),
            )
        return {
            "id": tid,
            "title": title[:120] or "New Biomedical Study",
            "profile": profile_norm,
            "mode": mode_norm,
            "created_at": now,
            "updated_at": now,
        }

    def list_threads(self, client_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, profile, mode, created_at, updated_at
                FROM threads
                WHERE client_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (client_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_thread(self, client_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            t_row = conn.execute(
                """
                SELECT id, title, profile, mode, created_at, updated_at
                FROM threads
                WHERE id = ? AND client_id = ?
                """,
                (thread_id, client_id),
            ).fetchone()
            if not t_row:
                return None
            m_rows = conn.execute(
                """
                SELECT id, role, content, run_id, metadata_json, created_at
                FROM messages
                WHERE thread_id = ?
                ORDER BY created_at ASC
                """,
                (thread_id,),
            ).fetchall()
        messages: List[Dict[str, Any]] = []
        for m in m_rows:
            try:
                meta = json.loads(m["metadata_json"] or "{}")
            except Exception:
                meta = {}
            messages.append(
                {
                    "id": m["id"],
                    "role": m["role"],
                    "content": m["content"],
                    "run_id": m["run_id"],
                    "metadata": meta,
                    "created_at": m["created_at"],
                }
            )
        out = dict(t_row)
        out["messages"] = messages
        return out

    def update_thread(
        self,
        client_id: str,
        thread_id: str,
        *,
        title: Optional[str] = None,
        profile: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> bool:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT title, profile, mode FROM threads WHERE id = ? AND client_id = ?",
                (thread_id, client_id),
            ).fetchone()
            if not row:
                return False
            new_title = (title[:120] if title else row["title"]) or row["title"]
            new_profile = ("a1" if str(profile).lower() == "a1" else "ad1") if profile else row["profile"]
            new_mode = ("plan" if str(mode).lower() == "plan" else "direct") if mode else row["mode"]
            conn.execute(
                """
                UPDATE threads
                SET title = ?, profile = ?, mode = ?, updated_at = ?
                WHERE id = ? AND client_id = ?
                """,
                (new_title, new_profile, new_mode, now, thread_id, client_id),
            )
        return True

    def delete_thread(self, client_id: str, thread_id: str) -> bool:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            cur = conn.execute(
                "DELETE FROM threads WHERE id = ? AND client_id = ?",
                (thread_id, client_id),
            )
            return cur.rowcount > 0

    def append_message(
        self,
        client_id: str,
        thread_id: str,
        role: str,
        content: str,
        *,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        mid = f"msg_{uuid.uuid4().hex[:12]}"
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            t_row = conn.execute(
                "SELECT title FROM threads WHERE id = ? AND client_id = ?",
                (thread_id, client_id),
            ).fetchone()
            if not t_row:
                raise KeyError(f"Thread '{thread_id}' not found")
            new_title = t_row["title"]
            if role == "user" and new_title in ("New Biomedical Study", "Untitled Study"):
                cleaned = " ".join(content.strip().split())
                if cleaned:
                    new_title = cleaned[:72] + ("…" if len(cleaned) > 72 else "")
            conn.execute(
                """
                INSERT INTO messages (id, thread_id, role, content, run_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, thread_id, role, content, run_id, meta_json, now),
            )
            conn.execute(
                "UPDATE threads SET title = ?, updated_at = ? WHERE id = ?",
                (new_title, now, thread_id),
            )
        return {
            "id": mid,
            "role": role,
            "content": content,
            "run_id": run_id,
            "metadata": metadata or {},
            "created_at": now,
            "thread_title": new_title,
        }

    def record_run_start(
        self,
        *,
        run_id: str,
        client_id: str,
        thread_id: str,
        prompt: str,
        model: str,
        profile: str,
        run_dir: str,
    ) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs
                (id, client_id, thread_id, prompt, model, profile, status, run_dir, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (run_id, client_id, thread_id, prompt, model, profile, run_dir, now),
            )

    def record_run_finish(
        self,
        *,
        run_id: str,
        status: str,
        answer: str,
        elapsed_s: float,
        iterations: int,
        tool_trace: List[Dict[str, Any]],
        usage: Dict[str, Any],
    ) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, answer = ?, elapsed_s = ?, iterations = ?,
                    tool_trace_json = ?, usage_json = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    answer,
                    round(elapsed_s, 3),
                    int(iterations),
                    json.dumps(tool_trace, ensure_ascii=False),
                    json.dumps(usage, ensure_ascii=False),
                    now,
                    run_id,
                ),
            )

    def get_run(self, client_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ? AND client_id = ?",
                (run_id, client_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["tool_trace"] = json.loads(out.pop("tool_trace_json", "[]") or "[]")
        except Exception:
            out["tool_trace"] = []
        try:
            out["usage"] = json.loads(out.pop("usage_json", "{}") or "{}")
        except Exception:
            out["usage"] = {}
        return out
