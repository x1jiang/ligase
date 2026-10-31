"""Durable SQLite + optional GCS FUSE JSON persistence for Ligase WebApp threads, messages, and run records."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_id(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", (raw or "").strip())[:96] or "item"


class ThreadStore:
    """Thread-safe SQLite store scoped per client workspace key, with optional persistent-volume mirroring."""

    def __init__(self, db_path: Path, persistent_root: Optional[Path] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.persistent_root = Path(persistent_root).resolve() if persistent_root is not None else None
        self.threads_dir: Optional[Path] = None
        self.runs_meta_dir: Optional[Path] = None
        if self.persistent_root is not None:
            self.threads_dir = self.persistent_root / "threads"
            self.runs_meta_dir = self.persistent_root / "runs_meta"
            self.threads_dir.mkdir(parents=True, exist_ok=True)
            self.runs_meta_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._synced_threads: Dict[str, int] = {}
        self._synced_runs: Dict[str, int] = {}
        self._last_sync_m: float = 0.0
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
            self._sync_from_persistent_unlocked(conn, force=True)

    def _persist_thread_unlocked(self, conn: sqlite3.Connection, thread_id: str) -> None:
        if self.threads_dir is None:
            return
        try:
            t_row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
            if not t_row:
                return
            m_rows = conn.execute(
                "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,),
            ).fetchall()
            payload = {
                "schema": 1,
                "thread": dict(t_row),
                "messages": [dict(m) for m in m_rows],
            }
            p = self.threads_dir / f"{_safe_id(thread_id)}.json"
            p.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
            try:
                self._synced_threads[p.name] = p.stat().st_mtime_ns
            except OSError:
                pass
        except Exception:
            pass

    def _persist_run_unlocked(self, conn: sqlite3.Connection, run_id: str) -> None:
        if self.runs_meta_dir is None:
            return
        try:
            r_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not r_row:
                return
            payload = {"schema": 1, **dict(r_row)}
            p = self.runs_meta_dir / f"{_safe_id(run_id)}.json"
            p.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
            try:
                self._synced_runs[p.name] = p.stat().st_mtime_ns
            except OSError:
                pass
        except Exception:
            pass

    def _sync_from_persistent_unlocked(self, conn: sqlite3.Connection, *, force: bool = False) -> None:
        if self.persistent_root is None:
            return
        now_m = time.monotonic()
        if not force and (now_m - self._last_sync_m) < 2.0:
            return
        self._last_sync_m = now_m

        if self.threads_dir and self.threads_dir.is_dir():
            try:
                with os.scandir(self.threads_dir) as it:
                    for entry in it:
                        if not entry.name.endswith(".json") or entry.name.startswith("."):
                            continue
                        try:
                            mtime_ns = entry.stat().st_mtime_ns
                        except OSError:
                            continue
                        if self._synced_threads.get(entry.name) == mtime_ns:
                            continue
                        self._synced_threads[entry.name] = mtime_ns
                        try:
                            obj = json.loads(Path(entry.path).read_text(encoding="utf-8"))
                            th = obj.get("thread") or {}
                            if th.get("id") and th.get("client_id"):
                                conn.execute(
                                    """
                                    INSERT OR REPLACE INTO threads
                                    (id, client_id, title, profile, mode, created_at, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        th["id"],
                                        th["client_id"],
                                        th.get("title") or "New Biomedical Study",
                                        th.get("profile") or "ad1",
                                        th.get("mode") or "direct",
                                        float(th.get("created_at") or time.time()),
                                        float(th.get("updated_at") or time.time()),
                                    ),
                                )
                                for m in obj.get("messages") or []:
                                    if m.get("id"):
                                        conn.execute(
                                            """
                                            INSERT OR REPLACE INTO messages
                                            (id, thread_id, role, content, run_id, metadata_json, created_at)
                                            VALUES (?, ?, ?, ?, ?, ?, ?)
                                            """,
                                            (
                                                m["id"],
                                                th["id"],
                                                m.get("role") or "user",
                                                m.get("content") or "",
                                                m.get("run_id"),
                                                m.get("metadata_json") or "{}",
                                                float(m.get("created_at") or time.time()),
                                            ),
                                        )
                        except Exception:
                            pass
            except OSError:
                pass

        if self.runs_meta_dir and self.runs_meta_dir.is_dir():
            try:
                with os.scandir(self.runs_meta_dir) as it:
                    for entry in it:
                        if not entry.name.endswith(".json") or entry.name.startswith("."):
                            continue
                        try:
                            mtime_ns = entry.stat().st_mtime_ns
                        except OSError:
                            continue
                        if self._synced_runs.get(entry.name) == mtime_ns:
                            continue
                        self._synced_runs[entry.name] = mtime_ns
                        try:
                            r = json.loads(Path(entry.path).read_text(encoding="utf-8"))
                            if r.get("id") and r.get("client_id"):
                                conn.execute(
                                    """
                                    INSERT OR REPLACE INTO runs
                                    (id, client_id, thread_id, prompt, model, profile, status, answer,
                                     elapsed_s, iterations, tool_trace_json, usage_json, run_dir, created_at, finished_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        r["id"],
                                        r["client_id"],
                                        r.get("thread_id") or "",
                                        r.get("prompt") or "",
                                        r.get("model") or "gpt-6-luna",
                                        r.get("profile") or "ad1",
                                        r.get("status") or "completed",
                                        r.get("answer") or "",
                                        float(r.get("elapsed_s") or 0.0),
                                        int(r.get("iterations") or 0),
                                        r.get("tool_trace_json") or "[]",
                                        r.get("usage_json") or "{}",
                                        r.get("run_dir") or "",
                                        float(r.get("created_at") or time.time()),
                                        r.get("finished_at"),
                                    ),
                                )
                        except Exception:
                            pass
            except OSError:
                pass

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
            self._persist_thread_unlocked(conn, tid)
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
            self._sync_from_persistent_unlocked(conn)
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
            self._sync_from_persistent_unlocked(conn)
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
            self._persist_thread_unlocked(conn, thread_id)
        return True

    def delete_thread(self, client_id: str, thread_id: str) -> bool:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            cur = conn.execute(
                "DELETE FROM threads WHERE id = ? AND client_id = ?",
                (thread_id, client_id),
            )
            deleted = cur.rowcount > 0
            if deleted and self.threads_dir is not None:
                p = self.threads_dir / f"{_safe_id(thread_id)}.json"
                try:
                    p.unlink(missing_ok=True)
                    self._synced_threads.pop(p.name, None)
                except OSError:
                    pass
        return deleted

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
            self._persist_thread_unlocked(conn, thread_id)
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
            self._persist_run_unlocked(conn, run_id)

    def get_run(self, client_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            self._sync_from_persistent_unlocked(conn)
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
