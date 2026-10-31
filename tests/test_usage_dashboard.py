"""Comprehensive tests for v0.4.0 speed optimizations, parallel pre-grounding, and the Usage & Volume Ledger."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from ligase.webapp.server import create_webapp
from ligase.webapp.store import ThreadStore
from ligase.webapp.usage_tracker import (
    DOMAIN_LABELS,
    UsageTracker,
    classify_biomedical_domain,
    compute_token_and_cost,
)


def test_classify_biomedical_domain_all_seven_categories():
    assert classify_biomedical_domain("Lookup APOE", [], "niagads_api") == "niagads_open_access"
    assert classify_biomedical_domain("Query api.niagads.org VRS rs429358", ["niagads_open_access_api"]) == "niagads_open_access"
    assert classify_biomedical_domain("Analyze BIN1 rs6733839 in microglia", ["query_niagads"]) == "niagads_v2f"
    assert classify_biomedical_domain("Calculate ABCA7 PAF in African multi-ancestry ADSP NG00100") == "adsp_ancestry"
    assert classify_biomedical_domain("Cross-disorder PSP 4R-tauopathy MAPT 17q21.31 NG00169") == "psp_tauopathy"
    assert classify_biomedical_domain("Check Imatinib SMILES and BCR-ABL1 IC50", ["lookup_compound"]) == "pharmacology"
    assert classify_biomedical_domain("Transcribe and translate 5'-ATGGGCAAGTAA-3'", ["transcribe_translate"]) == "bioinformatics"
    assert classify_biomedical_domain("Explain TREM2 R47H neuroinflammation") == "neuro_proteomics"
    assert set(DOMAIN_LABELS.keys()) == {
        "niagads_open_access",
        "niagads_v2f",
        "adsp_ancestry",
        "psp_tauopathy",
        "neuro_proteomics",
        "pharmacology",
        "bioinformatics",
    }


def test_compute_token_and_cost_exact_and_estimated():
    exact = compute_token_and_cost(
        input_tokens=2000,
        output_tokens=500,
        cached_tokens=1000,
        prompt_chars=400,
        output_chars=900,
    )
    assert exact["tokens_exact"] == 1
    assert exact["total_tokens"] == 2500
    assert exact["cached_tokens"] == 1000
    assert exact["model_cost_usd"] > 0
    assert exact["total_cost_usd"] > exact["model_cost_usd"]

    est = compute_token_and_cost(
        input_tokens=0,
        output_tokens=0,
        cached_tokens=0,
        prompt_chars=400,
        output_chars=800,
    )
    assert est["tokens_exact"] == 0
    assert est["input_tokens"] == 100
    assert est["output_tokens"] == 200
    assert est["total_tokens"] == 300


def test_usage_tracker_backfills_historical_runs_idempotently(tmp_path: Path):
    db_path = tmp_path / "ligase_webapp.sqlite3"
    store = ThreadStore(db_path)
    t = store.create_thread(client_id="cli_alpha999999", title="Historical BIN1 Study", profile="ad1")
    store.record_run_start(
        run_id="run_hist_001",
        client_id="cli_alpha999999",
        thread_id=t["id"],
        prompt="Prioritize BIN1 rs6733839 enhancer in microglia NG00105",
        model="gpt-6-luna",
        profile="ad1",
        run_dir=str(tmp_path / "run_hist_001"),
    )
    store.record_run_finish(
        run_id="run_hist_001",
        status="completed",
        answer="## BIN1 Enhancer Analysis\nMicroglia enhancer confirmed.",
        elapsed_s=2.45,
        iterations=2,
        tool_trace=[{"tool_name": "query_niagads", "elapsed_ms": 18, "success": True}],
        usage={"input_tokens": 1200, "output_tokens": 350, "cached_input_tokens": 400},
    )

    tracker_first = UsageTracker(db_path)
    snap1 = tracker_first.get_dashboard_summary(days="all", active_model="gpt-6-luna")
    assert snap1["volume"]["studies_count"] == 1
    assert snap1["volume"]["total_tokens"] == 1550
    assert snap1["ledger"][0]["domain"] == "niagads_v2f"

    # Re-initializing on the same DB must NOT duplicate the backfilled run
    tracker_second = UsageTracker(db_path)
    snap2 = tracker_second.get_dashboard_summary(days="all", active_model="gpt-6-luna")
    assert snap2["volume"]["studies_count"] == 1


def test_lean_ssr_routes_etag_and_immutable_static_headers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LIGASE_WEB_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-unit-key")
    monkeypatch.setenv("LIGASE_SKIP_WARMUP", "1")
    app = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    client = TestClient(app)

    for route in ("/", "/usage", "/admin"):
        res = client.get(route)
        assert res.status_code == 200
        assert 'id="tab-usage"' in res.text
        assert 'id="panel-usage"' in res.text
        assert 'id="studio-speed-group"' in res.text
        m = re.search(r'<script[^>]*id="ligase-bootstrap"[^>]*>(.*?)</script>', res.text, re.DOTALL)
        assert m is not None
        boot_json_str = m.group(1).strip()
        # Lean bootstrap payload must stay compact (<12 KB raw HTML bootstrap block)
        assert len(boot_json_str.encode("utf-8")) < 12_000
        parsed_boot = json.loads(boot_json_str)
        assert "boot" in parsed_boot
        assert parsed_boot["boot"]["version"] == "0.4.0"

    # Versioned static assets get immutable 1-year cache; unversioned keeps 24h
    ver_js = client.get("/static/app.js?v=0.4.0")
    assert ver_js.status_code == 200
    assert "immutable" in (ver_js.headers.get("cache-control") or "")
    assert "max-age=31536000" in (ver_js.headers.get("cache-control") or "")

    plain_js = client.get("/static/app.js")
    assert plain_js.status_code == 200
    assert "max-age=86400" in (plain_js.headers.get("cache-control") or "")

    # Weak ETag 304 Not Modified on /api/meta, /api/mindmap, and /api/usage
    for api_path in ("/api/meta", "/api/mindmap", "/api/usage?days=30"):
        first = client.get(api_path)
        assert first.status_code == 200
        etag = first.headers.get("etag")
        assert etag and etag.startswith('W/"')
        second = client.get(api_path, headers={"If-None-Match": etag})
        assert second.status_code == 304


def test_usage_dashboard_end_to_end_and_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LIGASE_WEB_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-unit-key")
    monkeypatch.setenv("LIGASE_SKIP_WARMUP", "1")
    monkeypatch.setenv("LIGASE_FORCE_WEB_PREGROUND", "1")

    monkeypatch.setattr(
        "ligase.webapp.server.execute_niagads_action",
        lambda **kwargs: {
            "ok": True,
            "action": kwargs.get("action"),
            "endpoint": "/record/gene/APOE",
            "request_id": "req-usage-1",
            "elapsed_ms": 29,
            "summary_markdown": "### NIAGADS Open Access Gene Record\n- **APOE** (`ENSG00000130203`)",
            "rows": [{"gene_symbol": "APOE"}],
            "raw": {"data": [{"gene_symbol": "APOE"}]},
        },
    )

    class _FastFakeClaw:
        on_stream_event = None
        tools = None

    class _FastFakeAgent:
        def __init__(self):
            self.claw_agent = _FastFakeClaw()
            self.last_state = SimpleNamespace(iterations=1, status="done")

        def go(self, prompt: str) -> str:
            cb = self.claw_agent.on_stream_event
            if cb:
                cb(
                    SimpleNamespace(
                        kind="usage",
                        prompt_tokens=840,
                        input_tokens=520,
                        output_tokens=210,
                        total_tokens=1050,
                        cached_input_tokens=320,
                        time_to_first_token_ms=180,
                    )
                )
            return "## Grounded Fast Synthesis\n\nVerified APOE rs429358 and translated `MGK`."

    monkeypatch.setattr("ligase.webapp.server.create_agent", lambda **kwargs: _FastFakeAgent())

    app = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    client = TestClient(app)
    headers = {"X-Ligase-Client-Id": "cli_tester888888"}

    # 1. File upload event
    up = client.post(
        "/api/uploads",
        headers={**headers, "X-Upload-Filename": "loci.tsv"},
        content=b"rsid\tp\nrs429358\t1e-120\n",
    )
    assert up.status_code == 200

    # 2. Live NIAGADS API query event
    live = client.get("/api/niagads/live?action=gene&target=APOE", headers=headers)
    assert live.status_code == 200

    # 3. Fast study run with parallel pre-grounding (DNA + NIAGADS)
    with client.stream(
        "POST",
        "/api/chat/stream",
        headers=headers,
        json={
            "prompt": "Query APOE rs429358 in NIAGADS and translate 5'-ATGGGCAAGTAA-3'",
            "profile": "ad1",
            "speed_mode": "fast",
        },
    ) as stream_res:
        assert stream_res.status_code == 200
        raw_sse = "".join(stream_res.iter_text())

    assert "event: tool_started" in raw_sse
    assert "event: tool_result" in raw_sse
    assert "event: run_complete" in raw_sse

    # 4. Query /api/usage across ranges
    for rng in ("all", "7", "30", "90"):
        u_res = client.get(f"/api/usage?days={rng}")
        assert u_res.status_code == 200
        payload = u_res.json()
        assert payload["window"]["range"] == rng
        assert len(payload["pulse"]) == 4
        assert len(payload["brief"]) >= 2
        assert payload["volume"]["studies_count"] == 1
        assert payload["volume"]["api_queries_count"] == 1
        assert payload["volume"]["uploads_count"] == 1
        assert payload["volume"]["total_tokens"] == 1050
        assert payload["cost"]["cache_hit_pct"] > 0
        assert payload["tool_mix"]["total_calls"] >= 2
        assert payload["quality"]["completion_rate_pct"] == 100.0
        assert payload["savings"]["minutes_saved"] > 0
        assert len(payload["ledger"]) == 3
        assert len(payload["workspaces"]) == 1
        assert payload["workspaces"][0]["workspace_label"] == "Researcher · tester"

    # 5. Export JSON, Markdown, and CSV ZIP bundle
    exp_json = client.get("/api/usage/export.json?days=all")
    assert exp_json.status_code == 200
    assert "attachment" in (exp_json.headers.get("content-disposition") or "")
    assert exp_json.json()["volume"]["studies_count"] == 1

    exp_md = client.get("/api/usage/export.md?days=all")
    assert exp_md.status_code == 200
    assert "# Ligase Usage, Volume & Telemetry Executive Report" in exp_md.text
    assert "## Volume & Cost Ledger" in exp_md.text
    assert "## Biomedical Domain Distribution" in exp_md.text

    exp_zip = client.get("/api/usage/export.csv?days=all")
    assert exp_zip.status_code == 200
    assert exp_zip.headers.get("content-type") == "application/zip"
    with zipfile.ZipFile(io.BytesIO(exp_zip.content), "r") as zf:
        names = set(zf.namelist())
        assert {
            "summary.csv",
            "daily_volume.csv",
            "studies_and_api_ledger.csv",
            "tool_mix.csv",
            "domains.csv",
            "workspaces.csv",
            "README.txt",
        }.issubset(names)
        ledger_csv = zf.read("studies_and_api_ledger.csv").decode("utf-8")
        assert "study_run" in ledger_csv
        assert "niagads_api" in ledger_csv


def test_create_agent_fast_vs_deep_configuration(monkeypatch: pytest.MonkeyPatch):
    captured: Dict[str, Any] = {}

    def _fake_create_claw_agent(**kwargs):
        captured["claw_kwargs"] = kwargs
        return SimpleNamespace(invoke=lambda *a, **kw: None, llm=None)

    monkeypatch.setattr("ligase.agent.create_claw_agent", _fake_create_claw_agent)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-unit-key")

    from ligase.agent import WEB_FAST_TOOLS, create_agent

    create_agent(model="gpt-6-luna", speed_mode="fast")
    assert captured["claw_kwargs"]["reasoning_effort"] == "low"
    fast_tools = {t.name for t in captured["claw_kwargs"]["tools"]}
    assert fast_tools == WEB_FAST_TOOLS
    assert captured["claw_kwargs"]["skills"] == []
    assert captured["claw_kwargs"]["memory"] == []
    assert captured["claw_kwargs"]["rethink"] is False
    assert captured["claw_kwargs"]["tool_discovery"] is False
    assert "FAST EXECUTION PROTOCOL" in captured["claw_kwargs"]["instruction"]

    create_agent(model="gpt-6-luna", speed_mode="deep")
    assert captured["claw_kwargs"]["reasoning_effort"] == "medium"
    deep_tools = {t.name for t in captured["claw_kwargs"]["tools"]}
    assert len(deep_tools) > len(WEB_FAST_TOOLS)
