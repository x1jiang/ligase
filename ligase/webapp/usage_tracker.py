"""Durable SQLite usage, volume, latency, and cost telemetry engine for Ligase WebApp.

Captures every agent study run, live NIAGADS Open Access v2.0 API query, Plan & Triage
call, and dataset upload in SQLite, backfills any historical runs on startup, and builds
aggregates, sparklines, funnels, domain breakdowns, and CSV/JSON/Markdown exports.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import sqlite3
import statistics
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ligase import __version__ as VERSION

# Transparent configurable pricing defaults (USD)
PRICE_INPUT_PER_MTOK = float(os.getenv("LIGASE_PRICE_INPUT_PER_MTOK", "2.50"))
PRICE_CACHED_INPUT_PER_MTOK = float(os.getenv("LIGASE_PRICE_CACHED_INPUT_PER_MTOK", "0.625"))
PRICE_OUTPUT_PER_MTOK = float(os.getenv("LIGASE_PRICE_OUTPUT_PER_MTOK", "10.00"))
CLOUD_COST_PER_STUDY_USD = float(os.getenv("LIGASE_CLOUD_COST_PER_STUDY_USD", "0.015"))
CLOUD_COST_PER_API_QUERY_USD = float(os.getenv("LIGASE_CLOUD_COST_PER_API_QUERY_USD", "0.0005"))
RESEARCHER_HOURLY_USD = float(os.getenv("LIGASE_RESEARCHER_HOURLY_USD", "85.0"))

DOMAIN_LABELS: Dict[str, str] = {
    "niagads_open_access": "Live NIAGADS Open Access v2.0",
    "niagads_v2f": "NIAGADS V2F & Microglia",
    "adsp_ancestry": "Multi-Ancestry ADSP",
    "psp_tauopathy": "PSP 4R-Tauopathy",
    "neuro_proteomics": "Neurogenetics & Proteomics",
    "pharmacology": "Pharmacology & Chemistry",
    "bioinformatics": "Molecular Bioinformatics",
}

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def classify_biomedical_domain(
    text: str,
    tool_names: Optional[List[str]] = None,
    event_type: str = "study_run",
) -> str:
    """Deterministically classify a study prompt or API query into one of 7 biomedical domains."""
    tools_set = {str(t).strip().lower() for t in (tool_names or []) if t}
    low = (text or "").lower()

    if event_type == "niagads_api":
        return "niagads_open_access"

    if any(k in low for k in ("supranuclear palsy", "psp", "4r-tau", "mapt", "ng00169", "ng00172", "17q21.31", "rs7412")):
        return "psp_tauopathy"
    if any(k in low for k in ("abca7", "rs115550680", "multi-ancestry", "african", "ng00100", "ng00067", "vcpa", "paf")):
        return "adsp_ancestry"
    if "niagads_open_access_api" in tools_set or any(
        k in low for k in ("open-access", "open access", "api.niagads.org", "vrs", "topgenes", "adsp r5", "adsp release 5", "ng00166")
    ):
        return "niagads_open_access"
    if "query_niagads" in tools_set or any(
        k in low for k in ("niagads", "bin1", "rs6733839", "miga", "ng00105", "filer", "plcg2", "abi3", "spi1", "microglia")
    ):
        return "niagads_v2f"
    if "lookup_compound" in tools_set or any(
        k in low for k in ("imatinib", "pubchem", "chembl", "smiles", "molecular weight", "ic50", "kinase", "inhibitor", "compound", "drug")
    ):
        return "pharmacology"
    if "transcribe_translate" in tools_set or any(
        k in low for k in ("transcribe", "translate", "codon", "orf", "mrna", "frameshift", "fasta", "5'-", "atgggc")
    ):
        return "bioinformatics"
    return "neuro_proteomics"


def compute_token_and_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    prompt_chars: int = 0,
    output_chars: int = 0,
    cloud_fee_usd: float = CLOUD_COST_PER_STUDY_USD,
) -> Dict[str, Any]:
    """Compute exact or transparently-estimated token counts and USD spend."""
    inp = max(0, int(input_tokens or 0))
    out = max(0, int(output_tokens or 0))
    cached = max(0, min(inp, int(cached_tokens or 0)))
    exact = (inp + out) > 0

    if not exact and (prompt_chars > 0 or output_chars > 0):
        inp = max(1, int(math.ceil(prompt_chars / 4.0)))
        out = max(0, int(math.ceil(output_chars / 4.0)))
        cached = 0

    uncached_inp = max(0, inp - cached)
    total_tok = inp + out
    model_cost = (
        (uncached_inp / 1_000_000.0) * PRICE_INPUT_PER_MTOK
        + (cached / 1_000_000.0) * PRICE_CACHED_INPUT_PER_MTOK
        + (out / 1_000_000.0) * PRICE_OUTPUT_PER_MTOK
    )
    cloud_cost = max(0.0, float(cloud_fee_usd))
    total_cost = model_cost + cloud_cost
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cached_tokens": cached,
        "total_tokens": total_tok,
        "tokens_exact": 1 if exact else 0,
        "model_cost_usd": round(model_cost, 6),
        "cloud_cost_usd": round(cloud_cost, 6),
        "total_cost_usd": round(total_cost, 6),
    }


def _clean_title(raw: str, limit: int = 84) -> str:
    cleaned = re.sub(r"\s+", " ", (raw or "").strip())
    cleaned = re.sub(r"^#+\s*", "", cleaned)
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned or "Untitled Biomedical Request"


def _workspace_label(client_id: str) -> str:
    c = (client_id or "local_default").strip()
    if c == "local_default":
        return "Portal Direct Session"
    if c.startswith("cli_") and len(c) >= 10:
        return f"Researcher · {c[4:10]}"
    return c[:22]


def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(len(sorted_vals) - 1, lo + 1)
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


EVENT_COLUMNS = (
    "id",
    "ts",
    "event_type",
    "client_id",
    "thread_id",
    "run_id",
    "model",
    "profile",
    "mode",
    "speed_mode",
    "domain",
    "status",
    "elapsed_ms",
    "ttft_ms",
    "iterations",
    "tool_count",
    "tools_json",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "total_tokens",
    "tokens_exact",
    "bytes_processed",
    "model_cost_usd",
    "cloud_cost_usd",
    "total_cost_usd",
    "title",
)


def resolve_persistent_usage_dir(db_path: Path, explicit_dir: Optional[Path] = None) -> Path:
    """Resolve the durable per-event JSON ledger directory (GCS FUSE on Cloud Run, disk locally)."""
    if explicit_dir is not None:
        return Path(explicit_dir).resolve()
    env_usage = (os.getenv("LIGASE_USAGE_PERSIST_DIR") or "").strip()
    if env_usage:
        return Path(env_usage).resolve()
    env_root = (os.getenv("LIGASE_PERSISTENT_DIR") or "").strip()
    if env_root:
        return (Path(env_root) / "usage_events").resolve()
    return (Path(db_path).resolve().parent / "usage_events").resolve()


def _safe_filename_token(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", (raw or "").strip())[:96] or "event"


def _read_json_event_file(path_str: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path_str, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) and obj.get("id") else None
    except Exception:
        return None


class UsageTracker:
    """Thread-safe usage & volume tracker combining fast local SQLite indexing with durable per-event JSON storage."""

    def __init__(
        self,
        db_path: Path,
        persistent_dir: Optional[Path] = None,
        *,
        defer_hydration: bool = False,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.persistent_dir = resolve_persistent_usage_dir(self.db_path, persistent_dir)
        if not defer_hydration:
            self.persistent_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._synced_files: Dict[str, int] = {}
        self._last_sync_monotonic: float = 0.0
        self._init_and_backfill(hydrate=not defer_hydration)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _event_file_path(self, row: Dict[str, Any]) -> Path:
        ev_type = _safe_filename_token(str(row.get("event_type") or "event"))
        run_id = str(row.get("run_id") or "").strip()
        if ev_type == "study_run" and run_id:
            return self.persistent_dir / f"study_run-{_safe_filename_token(run_id)}.json"
        ts_val = float(row.get("ts") or time.time())
        stamp = datetime.fromtimestamp(ts_val, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ev_id = _safe_filename_token(str(row.get("id") or uuid.uuid4().hex[:14]))
        return self.persistent_dir / f"{stamp}-{ev_type}-{ev_id}.json"

    def _persist_event_unlocked(self, row: Dict[str, Any]) -> None:
        """Write one self-contained JSON event file in-place (GCS FUSE safe: no temp-then-rename)."""
        try:
            self.persistent_dir.mkdir(parents=True, exist_ok=True)
            path = self._event_file_path(row)
            payload = {"schema": 1, **{col: row[col] for col in EVENT_COLUMNS}}
            path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
            try:
                self._synced_files[path.name] = path.stat().st_mtime_ns
            except OSError:
                self._synced_files[path.name] = int(time.time() * 1e9)
        except Exception:
            pass

    def _insert_row_unlocked(self, conn: sqlite3.Connection, row: Dict[str, Any], *, persist: bool = True) -> None:
        if row.get("event_type") == "study_run" and row.get("run_id"):
            conn.execute(
                "DELETE FROM usage_events WHERE run_id = ? AND event_type = 'study_run'",
                (row["run_id"],),
            )
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        cols_sql = ", ".join(EVENT_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO usage_events ({cols_sql}) VALUES ({placeholders})",
            tuple(row[c] for c in EVENT_COLUMNS),
        )
        if persist:
            self._persist_event_unlocked(row)

    def _sync_from_persistent_dir_unlocked(self, conn: sqlite3.Connection, *, force: bool = False) -> int:
        now_m = time.monotonic()
        if not force and (now_m - self._last_sync_monotonic) < 1.5:
            return 0
        self._last_sync_monotonic = now_m
        if not self.persistent_dir.is_dir():
            return 0

        pending: List[Tuple[str, str, int]] = []
        try:
            with os.scandir(self.persistent_dir) as it:
                for entry in it:
                    if not entry.name.endswith(".json") or entry.name.startswith("."):
                        continue
                    try:
                        mtime_ns = entry.stat().st_mtime_ns
                    except OSError:
                        continue
                    if self._synced_files.get(entry.name) != mtime_ns:
                        pending.append((entry.name, entry.path, mtime_ns))
        except OSError:
            return 0

        if not pending:
            return 0

        if len(pending) > 4:
            with ThreadPoolExecutor(max_workers=min(8, len(pending))) as pool:
                parsed_list = list(pool.map(_read_json_event_file, [p[1] for p in pending]))
        else:
            parsed_list = [_read_json_event_file(p[1]) for p in pending]

        ingested = 0
        for (fname, _, mtime_ns), obj in zip(pending, parsed_list):
            self._synced_files[fname] = mtime_ns
            if not obj:
                continue
            row = {
                "id": str(obj.get("id") or f"uev_{uuid.uuid4().hex[:14]}"),
                "ts": float(obj.get("ts") or time.time()),
                "event_type": str(obj.get("event_type") or "study_run"),
                "client_id": str(obj.get("client_id") or "local_default"),
                "thread_id": str(obj.get("thread_id") or ""),
                "run_id": str(obj.get("run_id") or ""),
                "model": str(obj.get("model") or "gpt-6-luna"),
                "profile": str(obj.get("profile") or "ad1"),
                "mode": str(obj.get("mode") or "direct"),
                "speed_mode": str(obj.get("speed_mode") or "fast"),
                "domain": str(obj.get("domain") or "neuro_proteomics"),
                "status": str(obj.get("status") or "completed"),
                "elapsed_ms": int(obj.get("elapsed_ms") or 0),
                "ttft_ms": int(obj.get("ttft_ms") or 0),
                "iterations": int(obj.get("iterations") or 1),
                "tool_count": int(obj.get("tool_count") or 0),
                "tools_json": str(obj.get("tools_json") or "[]")
                if isinstance(obj.get("tools_json"), str)
                else json.dumps(obj.get("tools_json") or [], ensure_ascii=False),
                "input_tokens": int(obj.get("input_tokens") or 0),
                "output_tokens": int(obj.get("output_tokens") or 0),
                "cached_tokens": int(obj.get("cached_tokens") or 0),
                "total_tokens": int(obj.get("total_tokens") or 0),
                "tokens_exact": int(obj.get("tokens_exact") if obj.get("tokens_exact") is not None else 1),
                "bytes_processed": int(obj.get("bytes_processed") or 0),
                "model_cost_usd": float(obj.get("model_cost_usd") or 0.0),
                "cloud_cost_usd": float(obj.get("cloud_cost_usd") or 0.0),
                "total_cost_usd": float(obj.get("total_cost_usd") or 0.0),
                "title": _clean_title(str(obj.get("title") or "Biomedical Request")),
            }
            self._insert_row_unlocked(conn, row, persist=False)
            ingested += 1
        return ingested

    def sync_from_persistent_storage(self, force: bool = True) -> int:
        """Public trigger to hydrate/sync any new JSON event records from persistent storage."""
        try:
            self.persistent_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        with self._lock, self._connect() as conn:
            return self._sync_from_persistent_dir_unlocked(conn, force=force)

    def _init_and_backfill(self, *, hydrate: bool = True) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL DEFAULT '',
                    run_id TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    profile TEXT NOT NULL DEFAULT 'ad1',
                    mode TEXT NOT NULL DEFAULT 'direct',
                    speed_mode TEXT NOT NULL DEFAULT 'fast',
                    domain TEXT NOT NULL DEFAULT 'neuro_proteomics',
                    status TEXT NOT NULL DEFAULT 'completed',
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    ttft_ms INTEGER NOT NULL DEFAULT 0,
                    iterations INTEGER NOT NULL DEFAULT 0,
                    tool_count INTEGER NOT NULL DEFAULT 0,
                    tools_json TEXT NOT NULL DEFAULT '[]',
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    tokens_exact INTEGER NOT NULL DEFAULT 0,
                    bytes_processed INTEGER NOT NULL DEFAULT 0,
                    model_cost_usd REAL NOT NULL DEFAULT 0.0,
                    cloud_cost_usd REAL NOT NULL DEFAULT 0.0,
                    total_cost_usd REAL NOT NULL DEFAULT 0.0,
                    title TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_usage_events_ts
                    ON usage_events(ts DESC);
                CREATE INDEX IF NOT EXISTS idx_usage_events_run
                    ON usage_events(run_id);
                """
            )
            if not hydrate:
                return
            # 1. Hydrate all durable per-event JSON records from persistent storage first
            self._sync_from_persistent_dir_unlocked(conn, force=True)

            # 2. Backfill any pre-existing finished rows from `runs` table idempotently & persist them
            has_runs = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
            ).fetchone()
            if has_runs:
                rows = conn.execute(
                    """
                    SELECT r.id, r.client_id, r.thread_id, r.prompt, r.model, r.profile,
                           r.status, r.answer, r.elapsed_s, r.iterations, r.tool_trace_json,
                           r.usage_json, r.created_at, r.finished_at
                    FROM runs r
                    LEFT JOIN usage_events u ON u.run_id = r.id AND u.event_type = 'study_run'
                    WHERE u.id IS NULL AND r.status != 'running'
                    """
                ).fetchall()
                for row in rows:
                    try:
                        trace = json.loads(row["tool_trace_json"] or "[]")
                    except Exception:
                        trace = []
                    try:
                        usage = json.loads(row["usage_json"] or "{}")
                    except Exception:
                        usage = {}
                    tools_compact = [
                        {
                            "name": str(t.get("tool_name") or "tool"),
                            "elapsed_ms": int(t.get("elapsed_ms") or 0),
                            "success": bool(t.get("success", True)),
                        }
                        for t in trace
                        if isinstance(t, dict)
                    ]
                    t_names = [t["name"] for t in tools_compact]
                    prompt_str = str(row["prompt"] or "")
                    ans_str = str(row["answer"] or "")
                    domain = classify_biomedical_domain(prompt_str, t_names, "study_run")
                    tc = compute_token_and_cost(
                        input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cached_tokens=int(usage.get("cached_input_tokens") or 0),
                        prompt_chars=len(prompt_str),
                        output_chars=len(ans_str),
                        cloud_fee_usd=CLOUD_COST_PER_STUDY_USD,
                    )
                    elapsed_ms = max(1, int(float(row["elapsed_s"] or 0.0) * 1000))
                    ts_val = float(row["finished_at"] or row["created_at"] or time.time())
                    bytes_proc = len(prompt_str.encode("utf-8")) + len(ans_str.encode("utf-8"))
                    backfill_row = {
                        "id": f"uev_{_safe_filename_token(row['id'])[:18]}",
                        "ts": ts_val,
                        "event_type": "study_run",
                        "client_id": row["client_id"] or "local_default",
                        "thread_id": row["thread_id"] or "",
                        "run_id": row["id"],
                        "model": row["model"] or "gpt-6-luna",
                        "profile": row["profile"] or "ad1",
                        "mode": "direct",
                        "speed_mode": "standard",
                        "domain": domain,
                        "status": row["status"] or "completed",
                        "elapsed_ms": elapsed_ms,
                        "ttft_ms": min(elapsed_ms, max(120, int(elapsed_ms * 0.18))),
                        "iterations": int(row["iterations"] or 1),
                        "tool_count": len(tools_compact),
                        "tools_json": json.dumps(tools_compact, ensure_ascii=False),
                        "input_tokens": tc["input_tokens"],
                        "output_tokens": tc["output_tokens"],
                        "cached_tokens": tc["cached_tokens"],
                        "total_tokens": tc["total_tokens"],
                        "tokens_exact": tc["tokens_exact"],
                        "bytes_processed": bytes_proc,
                        "model_cost_usd": tc["model_cost_usd"],
                        "cloud_cost_usd": tc["cloud_cost_usd"],
                        "total_cost_usd": tc["total_cost_usd"],
                        "title": _clean_title(prompt_str),
                    }
                    self._insert_row_unlocked(conn, backfill_row, persist=True)

    def record_study_run(
        self,
        *,
        run_id: str,
        client_id: str,
        thread_id: str,
        prompt: str,
        answer: str,
        model: str,
        profile: str,
        mode: str = "direct",
        speed_mode: str = "fast",
        status: str = "completed",
        elapsed_s: float = 0.0,
        ttft_ms: int = 0,
        iterations: int = 1,
        tool_trace: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, Any]] = None,
        attachment_bytes: int = 0,
        report_bytes: int = 0,
    ) -> None:
        tools_compact = [
            {
                "name": str(t.get("tool_name") or "tool"),
                "elapsed_ms": int(t.get("elapsed_ms") or 0),
                "success": bool(t.get("success", True)),
            }
            for t in (tool_trace or [])
            if isinstance(t, dict)
        ]
        t_names = [t["name"] for t in tools_compact]
        domain = classify_biomedical_domain(prompt, t_names, "study_run")
        u = usage or {}
        tc = compute_token_and_cost(
            input_tokens=int(u.get("input_tokens") or 0),
            output_tokens=int(u.get("output_tokens") or 0),
            cached_tokens=int(u.get("cached_input_tokens") or 0),
            prompt_chars=len(prompt or "") if status == "completed" else 0,
            output_chars=len(answer or ""),
            cloud_fee_usd=CLOUD_COST_PER_STUDY_USD,
        )
        elapsed_ms = max(1, int(round(float(elapsed_s or 0.0) * 1000)))
        resolved_ttft = int(ttft_ms) if int(ttft_ms or 0) > 0 else min(elapsed_ms, 250)
        bytes_proc = (
            len((prompt or "").encode("utf-8"))
            + len((answer or "").encode("utf-8"))
            + max(0, int(attachment_bytes or 0))
            + max(0, int(report_bytes or 0))
        )
        now = time.time()
        row = {
            "id": f"uev_{_safe_filename_token(run_id)[:18]}",
            "ts": now,
            "event_type": "study_run",
            "client_id": client_id or "local_default",
            "thread_id": thread_id or "",
            "run_id": run_id,
            "model": model or "gpt-6-luna",
            "profile": profile or "ad1",
            "mode": mode or "direct",
            "speed_mode": speed_mode or "fast",
            "domain": domain,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "ttft_ms": resolved_ttft,
            "iterations": max(1, int(iterations or 1)),
            "tool_count": len(tools_compact),
            "tools_json": json.dumps(tools_compact, ensure_ascii=False),
            "input_tokens": tc["input_tokens"],
            "output_tokens": tc["output_tokens"],
            "cached_tokens": tc["cached_tokens"],
            "total_tokens": tc["total_tokens"],
            "tokens_exact": tc["tokens_exact"],
            "bytes_processed": bytes_proc,
            "model_cost_usd": tc["model_cost_usd"],
            "cloud_cost_usd": tc["cloud_cost_usd"],
            "total_cost_usd": tc["total_cost_usd"],
            "title": _clean_title(prompt),
        }
        with self._lock, self._connect() as conn:
            self._insert_row_unlocked(conn, row, persist=True)


    def record_niagads_api_call(
        self,
        *,
        client_id: str,
        action: str,
        target: str,
        endpoint: str,
        ok: bool,
        elapsed_ms: int,
        payload_bytes: int,
    ) -> None:
        now = time.time()
        label = f"NIAGADS v2.0 [{action}] · {target or endpoint}"
        tool_entry = [{"name": "niagads_open_access_api", "elapsed_ms": max(1, int(elapsed_ms or 1)), "success": bool(ok)}]
        row = {
            "id": f"uev_{uuid.uuid4().hex[:14]}",
            "ts": now,
            "event_type": "niagads_api",
            "client_id": client_id or "local_default",
            "thread_id": "",
            "run_id": "",
            "model": "api.niagads.org/v2",
            "profile": "ad1",
            "mode": "direct",
            "speed_mode": "fast",
            "domain": "niagads_open_access",
            "status": "completed" if ok else "failed",
            "elapsed_ms": max(1, int(elapsed_ms or 1)),
            "ttft_ms": max(1, int(elapsed_ms or 1)),
            "iterations": 1,
            "tool_count": 1,
            "tools_json": json.dumps(tool_entry, ensure_ascii=False),
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
            "tokens_exact": 1,
            "bytes_processed": max(0, int(payload_bytes or 0)),
            "model_cost_usd": 0.0,
            "cloud_cost_usd": round(CLOUD_COST_PER_API_QUERY_USD, 6),
            "total_cost_usd": round(CLOUD_COST_PER_API_QUERY_USD, 6),
            "title": _clean_title(label),
        }
        with self._lock, self._connect() as conn:
            self._insert_row_unlocked(conn, row, persist=True)


    def record_plan_triage(
        self,
        *,
        client_id: str,
        thread_id: str,
        prompt: str,
        model: str,
        profile: str,
        needs_plan: bool,
        elapsed_ms: int,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = time.time()
        u = usage or {}
        tc = compute_token_and_cost(
            input_tokens=int(u.get("input_tokens") or 0),
            output_tokens=int(u.get("output_tokens") or 0),
            cached_tokens=int(u.get("cached_input_tokens") or 0),
            prompt_chars=len(prompt or ""),
            output_chars=320,
            cloud_fee_usd=CLOUD_COST_PER_API_QUERY_USD,
        )
        domain = classify_biomedical_domain(prompt, [], "plan_triage")
        prefix = "Scientific Plan" if needs_plan else "Instant Triage"
        row = {
            "id": f"uev_{uuid.uuid4().hex[:14]}",
            "ts": now,
            "event_type": "plan_triage",
            "client_id": client_id or "local_default",
            "thread_id": thread_id or "",
            "run_id": "",
            "model": model or "gpt-6-luna",
            "profile": profile or "ad1",
            "mode": "plan",
            "speed_mode": "fast",
            "domain": domain,
            "status": "completed",
            "elapsed_ms": max(1, int(elapsed_ms or 1)),
            "ttft_ms": max(1, int(elapsed_ms or 1)),
            "iterations": 1,
            "tool_count": 0,
            "tools_json": "[]",
            "input_tokens": tc["input_tokens"],
            "output_tokens": tc["output_tokens"],
            "cached_tokens": tc["cached_tokens"],
            "total_tokens": tc["total_tokens"],
            "tokens_exact": tc["tokens_exact"],
            "bytes_processed": len((prompt or "").encode("utf-8")),
            "model_cost_usd": tc["model_cost_usd"],
            "cloud_cost_usd": tc["cloud_cost_usd"],
            "total_cost_usd": tc["total_cost_usd"],
            "title": _clean_title(f"{prefix}: {prompt}"),
        }
        with self._lock, self._connect() as conn:
            self._insert_row_unlocked(conn, row, persist=True)


    def record_file_upload(
        self,
        *,
        client_id: str,
        filename: str,
        size_bytes: int,
    ) -> None:
        now = time.time()
        row = {
            "id": f"uev_{uuid.uuid4().hex[:14]}",
            "ts": now,
            "event_type": "file_upload",
            "client_id": client_id or "local_default",
            "thread_id": "",
            "run_id": "",
            "model": "workspace-io",
            "profile": "ad1",
            "mode": "direct",
            "speed_mode": "fast",
            "domain": "bioinformatics",
            "status": "completed",
            "elapsed_ms": 5,
            "ttft_ms": 5,
            "iterations": 1,
            "tool_count": 0,
            "tools_json": "[]",
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
            "tokens_exact": 1,
            "bytes_processed": max(0, int(size_bytes or 0)),
            "model_cost_usd": 0.0,
            "cloud_cost_usd": round(CLOUD_COST_PER_API_QUERY_USD, 6),
            "total_cost_usd": round(CLOUD_COST_PER_API_QUERY_USD, 6),
            "title": _clean_title(f"Dataset Upload · {filename}"),
        }
        with self._lock, self._connect() as conn:
            self._insert_row_unlocked(conn, row, persist=True)
    def record_feedback_submission(
        self,
        *,
        client_id: str,
        category: str,
        target_area: str,
        comment: str,
        attachment_count: int = 0,
        attachment_bytes: int = 0,
    ) -> None:
        now = time.time()
        domain = classify_biomedical_domain(comment, [], "feedback")
        att_note = f" (+{attachment_count} file{'s' if attachment_count != 1 else ''})" if attachment_count else ""
        row = {
            "id": f"uev_{uuid.uuid4().hex[:14]}",
            "ts": now,
            "event_type": "feedback",
            "client_id": client_id or "local_default",
            "thread_id": "",
            "run_id": "",
            "model": "feedback-ledger",
            "profile": "ad1",
            "mode": "direct",
            "speed_mode": "fast",
            "domain": domain,
            "status": "completed",
            "elapsed_ms": 12,
            "ttft_ms": 12,
            "iterations": 1,
            "tool_count": 0,
            "tools_json": "[]",
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
            "tokens_exact": 1,
            "bytes_processed": len((comment or "").encode("utf-8")) + max(0, int(attachment_bytes or 0)),
            "model_cost_usd": 0.0,
            "cloud_cost_usd": round(CLOUD_COST_PER_API_QUERY_USD, 6),
            "total_cost_usd": round(CLOUD_COST_PER_API_QUERY_USD, 6),
            "title": _clean_title(f"Feedback [{category}/{target_area}]{att_note}: {comment}"),
        }
        with self._lock, self._connect() as conn:
            self._insert_row_unlocked(conn, row, persist=True)


    def _fetch_all_events_and_threads(self) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock, self._connect() as conn:
            self._sync_from_persistent_dir_unlocked(conn, force=False)
            rows = conn.execute("SELECT * FROM usage_events ORDER BY ts DESC").fetchall()
            threads_count = 0
            has_threads = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='threads'"
            ).fetchone()
            if has_threads:
                t_row = conn.execute("SELECT COUNT(*) AS cnt FROM threads").fetchone()
                threads_count = int(t_row["cnt"] if t_row else 0)
        return [dict(r) for r in rows], threads_count

    def get_dashboard_summary(
        self,
        *,
        days: str = "all",
        active_model: str = "gpt-6-luna",
    ) -> Dict[str, Any]:
        now = time.time()
        now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
        days_norm = str(days or "all").strip().lower()
        cutoff_ts: Optional[float] = None
        if days_norm in ("7", "7d"):
            days_norm = "7"
            cutoff_ts = now - 7 * 86400
            range_label = "Last 7 days"
        elif days_norm in ("30", "30d"):
            days_norm = "30"
            cutoff_ts = now - 30 * 86400
            range_label = "Last 30 days"
        elif days_norm in ("90", "90d"):
            days_norm = "90"
            cutoff_ts = now - 90 * 86400
            range_label = "Last 90 days"
        else:
            days_norm = "all"
            range_label = "All recorded history"

        all_events, total_threads = self._fetch_all_events_and_threads()
        events = [e for e in all_events if cutoff_ts is None or float(e["ts"]) >= cutoff_ts]

        # ── 1. 7-Day Pulse Sparklines (always measured over trailing 14 UTC days) ──
        today_utc = now_dt.date()
        last_14_dates = [today_utc - timedelta(days=offset) for offset in range(13, -1, -1)]
        date_idx = {d.isoformat(): i for i, d in enumerate(last_14_dates)}
        daily_14_act = [0] * 14
        daily_14_spend = [0.0] * 14
        daily_14_tools = [0] * 14
        daily_14_ws: List[set[str]] = [set() for _ in range(14)]

        earliest_14_ts = datetime.combine(last_14_dates[0], datetime.min.time(), tzinfo=timezone.utc).timestamp()
        for e in all_events:
            ets = float(e["ts"])
            if ets < earliest_14_ts:
                continue
            d_key = datetime.fromtimestamp(ets, tz=timezone.utc).date().isoformat()
            idx = date_idx.get(d_key)
            if idx is None:
                continue
            if e["event_type"] in ("study_run", "niagads_api", "plan_triage"):
                daily_14_act[idx] += 1
            daily_14_spend[idx] += float(e["total_cost_usd"] or 0.0)
            daily_14_tools[idx] += int(e["tool_count"] or 0)
            daily_14_ws[idx].add(str(e["client_id"] or "local_default"))

        def _pulse_card(
            card_id: str,
            label: str,
            prior_7: List[float],
            curr_7: List[float],
            curr_total: float,
            prior_total: float,
            fmt: str = "int",
            sub_unit: str = "",
        ) -> Dict[str, Any]:
            if prior_total > 0:
                delta_pct = round(((curr_total - prior_total) / prior_total) * 100.0, 1)
            elif curr_total > 0:
                delta_pct = 100.0
            else:
                delta_pct = 0.0
            delta_dir = "up" if delta_pct > 2.0 else ("down" if delta_pct < -2.0 else "flat")
            if fmt == "usd":
                disp = f"${curr_total:,.2f}" if curr_total >= 0.01 or curr_total == 0 else f"${curr_total:,.4f}"
                prior_str = f"vs ${prior_total:,.2f} prior 7d"
            else:
                disp = f"{int(round(curr_total)):,}"
                prior_str = f"vs {int(round(prior_total)):,} prior 7d{(' · ' + sub_unit) if sub_unit else ''}"
            return {
                "id": card_id,
                "label": label,
                "value": round(curr_total, 4),
                "display": disp,
                "sub": prior_str,
                "delta_pct": delta_pct,
                "delta_dir": delta_dir,
                "sparkline": [round(v, 4) for v in curr_7],
                "prior_avg": round(sum(prior_7) / 7.0, 4),
            }

        ws_counts_14 = [float(len(s)) for s in daily_14_ws]
        curr_7_ws_union = set().union(*daily_14_ws[7:]) if daily_14_ws[7:] else set()
        prior_7_ws_union = set().union(*daily_14_ws[:7]) if daily_14_ws[:7] else set()

        pulse = [
            _pulse_card(
                "activity_7d",
                "Studies & Live Queries (7d)",
                [float(x) for x in daily_14_act[:7]],
                [float(x) for x in daily_14_act[7:]],
                float(sum(daily_14_act[7:])),
                float(sum(daily_14_act[:7])),
                fmt="int",
            ),
            _pulse_card(
                "spend_7d",
                "Total Spend (7d)",
                daily_14_spend[:7],
                daily_14_spend[7:],
                float(sum(daily_14_spend[7:])),
                float(sum(daily_14_spend[:7])),
                fmt="usd",
            ),
            _pulse_card(
                "tools_7d",
                "Grounded Tool Calls (7d)",
                [float(x) for x in daily_14_tools[:7]],
                [float(x) for x in daily_14_tools[7:]],
                float(sum(daily_14_tools[7:])),
                float(sum(daily_14_tools[:7])),
                fmt="int",
            ),
            _pulse_card(
                "workspaces_7d",
                "Active Workspaces (7d)",
                ws_counts_14[:7],
                ws_counts_14[7:],
                float(len(curr_7_ws_union)),
                float(len(prior_7_ws_union)),
                fmt="int",
            ),
        ]

        # ── 2. Partition Selected-Window Events ──────────────────────────────
        study_events = [e for e in events if e["event_type"] == "study_run"]
        completed_studies = [e for e in study_events if e["status"] == "completed"]
        grounded_studies = [e for e in study_events if int(e["tool_count"] or 0) > 0]
        api_events = [e for e in events if e["event_type"] == "niagads_api"]
        triage_events = [e for e in events if e["event_type"] == "plan_triage"]
        upload_events = [e for e in events if e["event_type"] == "file_upload"]

        total_model_usd = sum(float(e["model_cost_usd"] or 0.0) for e in events)
        total_cloud_usd = sum(float(e["cloud_cost_usd"] or 0.0) for e in events)
        total_spend_usd = total_model_usd + total_cloud_usd
        model_pct = round((total_model_usd / total_spend_usd) * 100.0, 1) if total_spend_usd > 0 else 0.0
        cloud_pct = round(100.0 - model_pct, 1) if total_spend_usd > 0 else 0.0

        total_inp_tok = sum(int(e["input_tokens"] or 0) for e in events)
        total_out_tok = sum(int(e["output_tokens"] or 0) for e in events)
        total_cached_tok = sum(int(e["cached_tokens"] or 0) for e in events)
        total_tok = sum(int(e["total_tokens"] or 0) for e in events)
        total_bytes = sum(int(e["bytes_processed"] or 0) for e in events)
        unique_clients = {str(e["client_id"] or "local_default") for e in events}
        cache_hit_pct = round((total_cached_tok / total_inp_tok) * 100.0, 1) if total_inp_tok > 0 else 0.0
        avg_cost_per_study = (
            sum(float(e["total_cost_usd"] or 0.0) for e in study_events) / len(study_events)
            if study_events
            else 0.0
        )

        # ── 3. Daily Timeline + Cumulative Spend & Tokens ────────────────────
        day_buckets: Dict[str, Dict[str, Any]] = {}
        if days_norm in ("7", "30", "90"):
            span = int(days_norm)
            for off in range(span - 1, -1, -1):
                dk = (today_utc - timedelta(days=off)).isoformat()
                day_buckets[dk] = {
                    "date": dk,
                    "studies": 0,
                    "api_queries": 0,
                    "triage": 0,
                    "uploads": 0,
                    "total_events": 0,
                    "total_tokens": 0,
                    "spend_usd": 0.0,
                }
        else:
            if events:
                min_date = datetime.fromtimestamp(min(float(e["ts"]) for e in events), tz=timezone.utc).date()
                span_days = min(120, max(7, (today_utc - min_date).days + 1))
            else:
                span_days = 14
            for off in range(span_days - 1, -1, -1):
                dk = (today_utc - timedelta(days=off)).isoformat()
                day_buckets[dk] = {
                    "date": dk,
                    "studies": 0,
                    "api_queries": 0,
                    "triage": 0,
                    "uploads": 0,
                    "total_events": 0,
                    "total_tokens": 0,
                    "spend_usd": 0.0,
                }

        for e in events:
            dk = datetime.fromtimestamp(float(e["ts"]), tz=timezone.utc).date().isoformat()
            if dk not in day_buckets:
                day_buckets[dk] = {
                    "date": dk,
                    "studies": 0,
                    "api_queries": 0,
                    "triage": 0,
                    "uploads": 0,
                    "total_events": 0,
                    "total_tokens": 0,
                    "spend_usd": 0.0,
                }
            b = day_buckets[dk]
            et = e["event_type"]
            if et == "study_run":
                b["studies"] += 1
            elif et == "niagads_api":
                b["api_queries"] += 1
            elif et == "plan_triage":
                b["triage"] += 1
            elif et == "file_upload":
                b["uploads"] += 1
            b["total_events"] += 1
            b["total_tokens"] += int(e["total_tokens"] or 0)
            b["spend_usd"] += float(e["total_cost_usd"] or 0.0)

        timeline: List[Dict[str, Any]] = []
        running_spend = 0.0
        running_tokens = 0
        peak_day_key = ""
        peak_day_events = -1
        for dk in sorted(day_buckets.keys()):
            b = day_buckets[dk]
            if b["total_events"] > peak_day_events:
                peak_day_events = b["total_events"]
                peak_day_key = dk
            running_spend += b["spend_usd"]
            running_tokens += b["total_tokens"]
            timeline.append(
                {
                    **b,
                    "spend_usd": round(b["spend_usd"], 5),
                    "cumulative_spend_usd": round(running_spend, 5),
                    "cumulative_tokens": running_tokens,
                    "is_peak": False,
                }
            )
        peak_day_obj = {"date": "—", "total_events": 0, "studies": 0, "api_queries": 0, "total_tokens": 0}
        for row in timeline:
            if row["date"] == peak_day_key and peak_day_events > 0:
                row["is_peak"] = True
                peak_day_obj = {
                    "date": row["date"],
                    "total_events": row["total_events"],
                    "studies": row["studies"],
                    "api_queries": row["api_queries"],
                    "total_tokens": row["total_tokens"],
                }

        # ── 4. Hero Volume Tile Wall (up to 160 most recent requests) ────────
        tiles: List[Dict[str, Any]] = []
        for e in events[:160]:
            tc = int(e["tool_count"] or 0)
            toks = int(e["total_tokens"] or 0)
            if e["status"] != "completed":
                lvl = 0
            elif e["event_type"] == "study_run":
                if tc >= 4 or toks >= 10000:
                    lvl = 4
                elif tc >= 2 or toks >= 4000:
                    lvl = 3
                elif tc >= 1 or toks >= 1200:
                    lvl = 2
                else:
                    lvl = 1
            else:
                lvl = 1 if tc == 0 else 2
            tiles.append(
                {
                    "id": e["run_id"] or e["id"],
                    "event_type": e["event_type"],
                    "title": e["title"],
                    "domain": e["domain"],
                    "domain_label": DOMAIN_LABELS.get(e["domain"], "Neurogenetics & Proteomics"),
                    "status": e["status"],
                    "speed_mode": e["speed_mode"] or "fast",
                    "tool_count": tc,
                    "total_tokens": toks,
                    "elapsed_ms": int(e["elapsed_ms"] or 0),
                    "total_cost_usd": round(float(e["total_cost_usd"] or 0.0), 5),
                    "level": lvl,
                    "ts_iso": datetime.fromtimestamp(float(e["ts"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                }
            )

        # ── 5. Scatter Plot (Latency vs Tool Calls per Study) ────────────────
        scatter: List[Dict[str, Any]] = []
        for e in study_events[:150]:
            scatter.append(
                {
                    "run_id": e["run_id"] or e["id"],
                    "title": e["title"],
                    "domain": e["domain"],
                    "domain_label": DOMAIN_LABELS.get(e["domain"], "Neurogenetics & Proteomics"),
                    "speed_mode": e["speed_mode"] or "fast",
                    "elapsed_s": round(int(e["elapsed_ms"] or 0) / 1000.0, 2),
                    "ttft_ms": int(e["ttft_ms"] or 0),
                    "tool_count": int(e["tool_count"] or 0),
                    "total_tokens": int(e["total_tokens"] or 0),
                    "cost_usd": round(float(e["total_cost_usd"] or 0.0), 5),
                    "status": e["status"],
                    "ts_iso": datetime.fromtimestamp(float(e["ts"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                }
            )

        # ── 6. Weekday × Hour Heatmap (UTC) ──────────────────────────────────
        heatmap_grid = [[0 for _ in range(24)] for _ in range(7)]
        max_slot = 0
        peak_wd = 0
        peak_hr = 0
        for e in events:
            dt = datetime.fromtimestamp(float(e["ts"]), tz=timezone.utc)
            wd = dt.weekday()
            hr = dt.hour
            heatmap_grid[wd][hr] += 1
            if heatmap_grid[wd][hr] > max_slot:
                max_slot = heatmap_grid[wd][hr]
                peak_wd = wd
                peak_hr = hr
        peak_slot_str = f"{WEEKDAY_NAMES[peak_wd]} {peak_hr:02d}:00 UTC ({max_slot})" if max_slot > 0 else "No traffic yet"

        # ── 7. Tool Execution Mix ────────────────────────────────────────────
        tool_stats: Dict[str, Dict[str, Any]] = {}
        total_tool_calls = 0
        for e in events:
            try:
                t_list = json.loads(e["tools_json"] or "[]")
            except Exception:
                t_list = []
            for item in t_list:
                if not isinstance(item, dict):
                    continue
                tname = str(item.get("name") or "tool")
                rec = tool_stats.setdefault(tname, {"count": 0, "latencies": [], "ok": 0})
                rec["count"] += 1
                rec["latencies"].append(int(item.get("elapsed_ms") or 0))
                if item.get("success", True):
                    rec["ok"] += 1
                total_tool_calls += 1

        tool_mix: List[Dict[str, Any]] = []
        for idx, (tname, rec) in enumerate(sorted(tool_stats.items(), key=lambda kv: (-kv[1]["count"], kv[0]))):
            lats = sorted(rec["latencies"])
            med_ms = int(round(statistics.median(lats))) if lats else 0
            tool_mix.append(
                {
                    "name": tname,
                    "count": rec["count"],
                    "pct": round((rec["count"] / total_tool_calls) * 100.0, 1) if total_tool_calls > 0 else 0.0,
                    "median_ms": med_ms,
                    "success_rate_pct": round((rec["ok"] / rec["count"]) * 100.0, 1) if rec["count"] > 0 else 100.0,
                    "color_idx": idx % 7,
                }
            )

        # ── 8. Workflow Funnel ───────────────────────────────────────────────
        top_requests = len(study_events) + len(api_events) + len(triage_events)
        studies_started = len(study_events)
        studies_grounded = len(grounded_studies)
        studies_completed = len(completed_studies)

        def _funnel_stage(label: str, cnt: int, prev: int, top: int) -> Dict[str, Any]:
            return {
                "label": label,
                "count": cnt,
                "pct_of_top": round((cnt / top) * 100.0, 1) if top > 0 else 0.0,
                "step_pct": round((cnt / prev) * 100.0, 1) if prev > 0 else 0.0,
            }

        funnel = [
            _funnel_stage("Portal & Live NIAGADS Requests", top_requests, top_requests, top_requests),
            _funnel_stage("Agent Research Studies Started", studies_started, top_requests, top_requests),
            _funnel_stage("Multi-Database / Tool Grounded", studies_grounded, studies_started, top_requests),
            _funnel_stage("Completed & Markdown Archived", studies_completed, studies_grounded or studies_started, top_requests),
        ]

        # ── 9. Biomedical Research Domains Breakdown ─────────────────────────
        dom_agg: Dict[str, Dict[str, Any]] = {
            did: {"id": did, "label": dlbl, "count": 0, "tokens": 0, "elapsed_list": [], "spend_usd": 0.0}
            for did, dlbl in DOMAIN_LABELS.items()
        }
        domain_source_events = [e for e in events if e["event_type"] in ("study_run", "niagads_api", "plan_triage")]
        for e in domain_source_events:
            did = e["domain"] if e["domain"] in dom_agg else "neuro_proteomics"
            rec = dom_agg[did]
            rec["count"] += 1
            rec["tokens"] += int(e["total_tokens"] or 0)
            rec["elapsed_list"].append(int(e["elapsed_ms"] or 0) / 1000.0)
            rec["spend_usd"] += float(e["total_cost_usd"] or 0.0)

        dom_total = max(1, len(domain_source_events))
        domains = []
        for did, rec in sorted(dom_agg.items(), key=lambda kv: (-kv[1]["count"], kv[1]["label"])):
            if rec["count"] == 0 and len(domain_source_events) > 0:
                continue
            avg_el = round(statistics.mean(rec["elapsed_list"]), 2) if rec["elapsed_list"] else 0.0
            domains.append(
                {
                    "id": did,
                    "label": rec["label"],
                    "count": rec["count"],
                    "pct": round((rec["count"] / dom_total) * 100.0, 1) if domain_source_events else 0.0,
                    "tokens": rec["tokens"],
                    "avg_elapsed_s": avg_el,
                    "spend_usd": round(rec["spend_usd"], 5),
                }
            )

        # ── 10. Latency, Speedup & Telemetry Quality Metrics ─────────────────
        study_secs = sorted(int(e["elapsed_ms"] or 0) / 1000.0 for e in completed_studies)
        study_ttfts = sorted(int(e["ttft_ms"] or 0) for e in completed_studies if int(e["ttft_ms"] or 0) > 0)
        fast_studies = [e for e in study_events if (e["speed_mode"] or "fast") == "fast"]
        exact_tok_studies = [e for e in study_events if int(e["tokens_exact"] or 0) == 1]
        max_tok_study = max(study_events, key=lambda x: int(x["total_tokens"] or 0), default=None)

        quality = {
            "median_elapsed_s": round(_percentile(study_secs, 0.5), 2) if study_secs else 0.0,
            "p90_elapsed_s": round(_percentile(study_secs, 0.9), 2) if study_secs else 0.0,
            "median_ttft_ms": int(round(_percentile([float(x) for x in study_ttfts], 0.5))) if study_ttfts else 0,
            "fast_mode_pct": round((len(fast_studies) / len(study_events)) * 100.0, 1) if study_events else 100.0,
            "completion_rate_pct": round((len(completed_studies) / len(study_events)) * 100.0, 1) if study_events else 100.0,
            "exact_token_pct": round((len(exact_tok_studies) / len(study_events)) * 100.0, 1) if study_events else 100.0,
            "avg_tools_per_study": round(
                sum(int(e["tool_count"] or 0) for e in study_events) / len(study_events), 2
            )
            if study_events
            else 0.0,
            "max_tokens_study": {
                "title": max_tok_study["title"] if max_tok_study else "—",
                "tokens": int(max_tok_study["total_tokens"] or 0) if max_tok_study else 0,
            },
        }

        # ── 11. Estimated Researcher Time Saved (Transparent Formula) ────────
        minutes_saved = 0.0
        for e in completed_studies:
            minutes_saved += 22.0 if int(e["tool_count"] or 0) >= 2 else 12.0
        minutes_saved += len(api_events) * 3.0 + len(triage_events) * 2.0
        hours_saved = round(minutes_saved / 60.0, 2)
        value_saved_usd = round((minutes_saved / 60.0) * RESEARCHER_HOURLY_USD, 2)
        roi_mult = round(value_saved_usd / total_spend_usd, 1) if total_spend_usd >= 0.001 else 0.0

        savings = {
            "minutes_saved": round(minutes_saved, 1),
            "hours_saved": hours_saved,
            "value_usd": value_saved_usd,
            "net_roi_multiple": roi_mult,
            "hourly_rate_usd": RESEARCHER_HOURLY_USD,
            "assumptions_note": (
                f"Assumes 22 min saved per multi-tool grounded study, 12 min per single-pass study, "
                f"and 3 min per live NIAGADS Open Access v2.0 lookup at ${RESEARCHER_HOURLY_USD:.0f}/hr biomedical researcher time."
            ),
        }

        # ── 12. Auto-Written Executive "In brief" Bullets ────────────────────
        brief: List[str] = []
        if not events:
            brief.append(
                "No studies or live NIAGADS API queries have been recorded in this range yet — run a study in Research Studio or execute a preset in NIAGADS Open Access API to populate live telemetry."
            )
        else:
            brief.append(
                f"{len(study_events):,} agent research {'study' if len(study_events) == 1 else 'studies'} and "
                f"{len(api_events):,} live NIAGADS Open Access v2.0 API {'query' if len(api_events) == 1 else 'queries'} "
                f"executed across {len(unique_clients):,} researcher {'workspace' if len(unique_clients) == 1 else 'workspaces'} "
                f"({quality['completion_rate_pct']:.0f}% study completion rate)."
            )
            brief.append(
                f"Total tracked spend is ${total_spend_usd:,.4f} (${total_model_usd:,.4f} model tokens across "
                f"{total_tok:,} tokens + ${total_cloud_usd:,.4f} Cloud Run compute), averaging "
                f"${avg_cost_per_study:,.4f} per study with {cache_hit_pct:.1f}% prompt-cache token reuse."
            )
            if completed_studies:
                brief.append(
                    f"Median end-to-end study runtime is {quality['median_elapsed_s']:.2f}s "
                    f"(median first-event TTFT {quality['median_ttft_ms']:,} ms, {total_tool_calls:,} grounded tool calls total)."
                )
            if domains and domains[0]["count"] > 0:
                top_dom = domains[0]
                brief.append(
                    f"Top biomedical workload is {top_dom['label']} ({top_dom['count']:,} requests, {top_dom['pct']:.1f}% of volume); "
                    f"peak activity occurred on {peak_day_obj['date']} ({peak_day_obj['total_events']:,} requests)."
                )

        # ── 13. Studies & API Ledger + Workspaces Table ──────────────────────
        ledger: List[Dict[str, Any]] = []
        ws_map: Dict[str, Dict[str, Any]] = {}
        for e in events:
            cid = str(e["client_id"] or "local_default")
            wrec = ws_map.setdefault(
                cid,
                {
                    "client_id": cid,
                    "workspace_label": _workspace_label(cid),
                    "studies": 0,
                    "api_queries": 0,
                    "tool_calls": 0,
                    "total_tokens": 0,
                    "spend_usd": 0.0,
                    "last_ts": 0.0,
                },
            )
            if e["event_type"] == "study_run":
                wrec["studies"] += 1
            elif e["event_type"] == "niagads_api":
                wrec["api_queries"] += 1
            wrec["tool_calls"] += int(e["tool_count"] or 0)
            wrec["total_tokens"] += int(e["total_tokens"] or 0)
            wrec["spend_usd"] += float(e["total_cost_usd"] or 0.0)
            wrec["last_ts"] = max(wrec["last_ts"], float(e["ts"]))

        for e in events[:200]:
            rid = str(e["run_id"] or "")
            cid = str(e["client_id"] or "local_default")
            report_url = (
                f"/api/runs/{rid}/report.md?client_id={cid}"
                if e["event_type"] == "study_run" and rid and e["status"] == "completed"
                else ""
            )
            ledger.append(
                {
                    "id": rid or e["id"],
                    "ts": float(e["ts"]),
                    "ts_iso": datetime.fromtimestamp(float(e["ts"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "event_type": e["event_type"],
                    "workspace_label": _workspace_label(cid),
                    "title": e["title"],
                    "profile": e["profile"],
                    "speed_mode": e["speed_mode"] or "fast",
                    "domain": e["domain"],
                    "domain_label": DOMAIN_LABELS.get(e["domain"], "Neurogenetics & Proteomics"),
                    "status": e["status"],
                    "elapsed_ms": int(e["elapsed_ms"] or 0),
                    "ttft_ms": int(e["ttft_ms"] or 0),
                    "tool_count": int(e["tool_count"] or 0),
                    "total_tokens": int(e["total_tokens"] or 0),
                    "bytes_processed": int(e["bytes_processed"] or 0),
                    "total_cost_usd": round(float(e["total_cost_usd"] or 0.0), 5),
                    "report_url": report_url,
                }
            )

        workspaces = [
            {
                "workspace_label": w["workspace_label"],
                "studies": w["studies"],
                "api_queries": w["api_queries"],
                "tool_calls": w["tool_calls"],
                "total_tokens": w["total_tokens"],
                "spend_usd": round(w["spend_usd"], 5),
                "last_seen_iso": datetime.fromtimestamp(w["last_ts"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if w["last_ts"] > 0
                else "—",
            }
            for w in sorted(ws_map.values(), key=lambda x: (-x["studies"], -x["api_queries"], -x["last_ts"]))
        ]

        gcs_bucket = (os.getenv("LIGASE_GCS_BUCKET") or "").strip()
        is_cloud_mount = bool(gcs_bucket) or str(self.persistent_dir).startswith("/mnt/")
        storage_info = {
            "persistent": True,
            "backend": "gcs_fuse" if is_cloud_mount else "local_disk",
            "label": (
                f"GCS Persistent Volume ({gcs_bucket})"
                if gcs_bucket
                else (f"Persistent Mount ({self.persistent_dir})" if is_cloud_mount else "Persistent Disk Ledger")
            ),
            "bucket": gcs_bucket,
            "path": str(self.persistent_dir),
            "persisted_files": len(self._synced_files),
        }

        return {
            "window": {
                "range": days_norm,
                "label": range_label,
                "generated_at_iso": now_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "version": VERSION,
                "model": active_model,
            },
            "storage": storage_info,
            "pulse": pulse,
            "brief": brief,
            "tiles": tiles,
            "cost": {
                "total_usd": round(total_spend_usd, 5),
                "model_usd": round(total_model_usd, 5),
                "cloud_usd": round(total_cloud_usd, 5),
                "model_pct": model_pct,
                "cloud_pct": cloud_pct,
                "avg_per_study_usd": round(avg_cost_per_study, 5),
                "cache_hit_pct": cache_hit_pct,
                "pricing_note": (
                    f"Rates: ${PRICE_INPUT_PER_MTOK:.2f}/1M input · "
                    f"${PRICE_CACHED_INPUT_PER_MTOK:.3f}/1M cached · "
                    f"${PRICE_OUTPUT_PER_MTOK:.2f}/1M output + ${CLOUD_COST_PER_STUDY_USD:.3f}/study Cloud Run compute."
                ),
            },
            "volume": {
                "total_events": len(events),
                "studies_count": len(study_events),
                "completed_studies_count": len(completed_studies),
                "api_queries_count": len(api_events),
                "triage_count": len(triage_events),
                "uploads_count": len(upload_events),
                "bytes_processed": total_bytes,
                "input_tokens": total_inp_tok,
                "output_tokens": total_out_tok,
                "cached_tokens": total_cached_tok,
                "total_tokens": total_tok,
                "unique_workspaces": len(unique_clients),
                "threads_count": total_threads,
                "avg_per_workspace": round(len(events) / len(unique_clients), 1) if unique_clients else 0.0,
                "peak_day": peak_day_obj,
            },
            "timeline": timeline,
            "scatter": scatter,
            "heatmap": {
                "weekday_labels": WEEKDAY_NAMES,
                "grid": heatmap_grid,
                "max_count": max_slot,
                "peak_slot": peak_slot_str,
            },
            "tool_mix": {
                "total_calls": total_tool_calls,
                "tools": tool_mix,
            },
            "funnel": funnel,
            "domains": domains,
            "quality": quality,
            "savings": savings,
            "ledger": ledger,
            "workspaces": workspaces,
        }

    def export_markdown_report(self, *, days: str = "all", active_model: str = "gpt-6-luna") -> str:
        snap = self.get_dashboard_summary(days=days, active_model=active_model)
        win = snap["window"]
        vol = snap["volume"]
        cost = snap["cost"]
        qual = snap["quality"]
        sav = snap["savings"]

        lines = [
            "# Ligase Usage, Volume & Telemetry Executive Report",
            "",
            f"- **Window:** {win['label']} (`days={win['range']}`)",
            f"- **Generated:** {win['generated_at_iso']}",
            f"- **Engine:** Ligase `v{win['version']}` (`{win['model']}`)",
            f"- **Persistent Storage:** {snap['storage']['label']} (`{snap['storage']['persisted_files']:,}` durable event records)",
            "",
            "## Executive Summary",
            "",
        ]
        for b in snap["brief"]:
            lines.append(f"- {b}")
        lines.extend(
            [
                "",
                "## Volume & Cost Ledger",
                "",
                "| Metric | Value |",
                "| :--- | ---: |",
                f"| Agent Studies Executed | {vol['studies_count']:,} ({vol['completed_studies_count']:,} completed) |",
                f"| Live NIAGADS Open Access v2.0 Queries | {vol['api_queries_count']:,} |",
                f"| Total Grounded Tool Calls | {snap['tool_mix']['total_calls']:,} |",
                f"| Total Model Tokens (In / Out / Cached) | {vol['total_tokens']:,} ({vol['input_tokens']:,} / {vol['output_tokens']:,} / {vol['cached_tokens']:,}) |",
                f"| Data & Report Volume Processed | {vol['bytes_processed']:,} bytes |",
                f"| Active Researcher Workspaces | {vol['unique_workspaces']:,} ({vol['threads_count']:,} saved threads) |",
                f"| Median Study Latency / Median TTFT | {qual['median_elapsed_s']:.2f}s / {qual['median_ttft_ms']:,} ms |",
                f"| Total Tracked Spend (Model + Cloud) | ${cost['total_usd']:,.4f} (${cost['model_usd']:,.4f} + ${cost['cloud_usd']:,.4f}) |",
                f"| Estimated Researcher Time Saved | {sav['hours_saved']:,.2f} hrs (${sav['value_usd']:,.2f} value) |",
                "",
                "## Grounded Tool Execution Mix",
                "",
                "| Tool Name | Calls | Share | Median Latency | Success Rate |",
                "| :--- | ---: | ---: | ---: | ---: |",
            ]
        )
        for t in snap["tool_mix"]["tools"]:
            lines.append(
                f"| `{t['name']}` | {t['count']:,} | {t['pct']:.1f}% | {t['median_ms']:,} ms | {t['success_rate_pct']:.1f}% |"
            )
        if not snap["tool_mix"]["tools"]:
            lines.append("| *(no tool calls in window)* | 0 | 0.0% | 0 ms | — |")

        lines.extend(
            [
                "",
                "## Biomedical Domain Distribution",
                "",
                "| Biomedical Domain | Requests | Share | Tokens | Avg Latency | Spend |",
                "| :--- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for d in snap["domains"]:
            lines.append(
                f"| {d['label']} | {d['count']:,} | {d['pct']:.1f}% | {d['tokens']:,} | {d['avg_elapsed_s']:.2f}s | ${d['spend_usd']:,.4f} |"
            )
        lines.extend(["", f"> *{cost['pricing_note']}*", f"> *{sav['assumptions_note']}*", ""])
        return "\n".join(lines)

    def export_csv_bundle_zip(self, *, days: str = "all", active_model: str = "gpt-6-luna") -> bytes:
        snap = self.get_dashboard_summary(days=days, active_model=active_model)
        mem = io.BytesIO()

        def _csv_bytes(headers: List[str], rows: List[List[Any]]) -> bytes:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            writer.writerows(rows)
            return buf.getvalue().encode("utf-8")

        vol = snap["volume"]
        cost = snap["cost"]
        qual = snap["quality"]
        sav = snap["savings"]

        summary_csv = _csv_bytes(
            ["metric", "value"],
            [
                ["window", snap["window"]["label"]],
                ["generated_at_iso", snap["window"]["generated_at_iso"]],
                ["version", snap["window"]["version"]],
                ["model", snap["window"]["model"]],
                ["studies_count", vol["studies_count"]],
                ["completed_studies_count", vol["completed_studies_count"]],
                ["niagads_api_queries_count", vol["api_queries_count"]],
                ["total_tool_calls", snap["tool_mix"]["total_calls"]],
                ["total_tokens", vol["total_tokens"]],
                ["input_tokens", vol["input_tokens"]],
                ["output_tokens", vol["output_tokens"]],
                ["cached_tokens", vol["cached_tokens"]],
                ["bytes_processed", vol["bytes_processed"]],
                ["unique_workspaces", vol["unique_workspaces"]],
                ["median_study_elapsed_s", qual["median_elapsed_s"]],
                ["median_ttft_ms", qual["median_ttft_ms"]],
                ["total_spend_usd", cost["total_usd"]],
                ["model_spend_usd", cost["model_usd"]],
                ["cloud_spend_usd", cost["cloud_usd"]],
                ["estimated_hours_saved", sav["hours_saved"]],
                ["estimated_value_saved_usd", sav["value_usd"]],
            ],
        )

        daily_csv = _csv_bytes(
            ["date", "studies", "api_queries", "triage", "total_events", "total_tokens", "spend_usd", "cumulative_spend_usd"],
            [
                [
                    d["date"],
                    d["studies"],
                    d["api_queries"],
                    d["triage"],
                    d["total_events"],
                    d["total_tokens"],
                    d["spend_usd"],
                    d["cumulative_spend_usd"],
                ]
                for d in snap["timeline"]
            ],
        )

        ledger_csv = _csv_bytes(
            [
                "id",
                "ts_iso",
                "event_type",
                "workspace",
                "title",
                "profile",
                "speed_mode",
                "domain",
                "status",
                "elapsed_ms",
                "ttft_ms",
                "tool_count",
                "total_tokens",
                "bytes_processed",
                "total_cost_usd",
            ],
            [
                [
                    r["id"],
                    r["ts_iso"],
                    r["event_type"],
                    r["workspace_label"],
                    r["title"],
                    r["profile"],
                    r["speed_mode"],
                    r["domain_label"],
                    r["status"],
                    r["elapsed_ms"],
                    r["ttft_ms"],
                    r["tool_count"],
                    r["total_tokens"],
                    r["bytes_processed"],
                    r["total_cost_usd"],
                ]
                for r in snap["ledger"]
            ],
        )

        tools_csv = _csv_bytes(
            ["tool_name", "calls", "share_pct", "median_ms", "success_rate_pct"],
            [[t["name"], t["count"], t["pct"], t["median_ms"], t["success_rate_pct"]] for t in snap["tool_mix"]["tools"]],
        )

        domains_csv = _csv_bytes(
            ["domain_id", "domain_label", "requests", "share_pct", "tokens", "avg_elapsed_s", "spend_usd"],
            [[d["id"], d["label"], d["count"], d["pct"], d["tokens"], d["avg_elapsed_s"], d["spend_usd"]] for d in snap["domains"]],
        )

        workspaces_csv = _csv_bytes(
            ["workspace", "studies", "api_queries", "tool_calls", "total_tokens", "spend_usd", "last_seen_iso"],
            [
                [w["workspace_label"], w["studies"], w["api_queries"], w["tool_calls"], w["total_tokens"], w["spend_usd"], w["last_seen_iso"]]
                for w in snap["workspaces"]
            ],
        )

        readme_txt = (
            f"Ligase Usage & Volume Telemetry Export (v{VERSION})\n"
            f"Generated: {snap['window']['generated_at_iso']}\n"
            f"Window: {snap['window']['label']}\n\n"
            "Files in this archive:\n"
            "  - summary.csv                 Headline volume, latency, token, and spend totals\n"
            "  - daily_volume.csv            UTC daily studies, NIAGADS v2.0 API queries, tokens, and spend\n"
            "  - studies_and_api_ledger.csv  Per-request audit ledger\n"
            "  - tool_mix.csv                Per-tool execution counts, latencies, and success rates\n"
            "  - domains.csv                 Biomedical domain volume & cost distribution\n"
            "  - workspaces.csv              Per-workspace aggregated activity\n\n"
            f"{cost['pricing_note']}\n"
            f"{sav['assumptions_note']}\n"
        ).encode("utf-8")

        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("summary.csv", summary_csv)
            zf.writestr("daily_volume.csv", daily_csv)
            zf.writestr("studies_and_api_ledger.csv", ledger_csv)
            zf.writestr("tool_mix.csv", tools_csv)
            zf.writestr("domains.csv", domains_csv)
            zf.writestr("workspaces.csv", workspaces_csv)
            zf.writestr("README.txt", readme_txt)

        return mem.getvalue()
