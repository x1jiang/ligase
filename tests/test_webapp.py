"""Tests for the Ligase WebApp FastAPI server, SQLite store, SSE stream, and frontend bundle."""

from __future__ import annotations

import json
import subprocess
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ligase.webapp.server import STATIC_DIR, create_webapp


@pytest.fixture()
def webapp_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LIGASE_WEB_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-unit-key")
    app = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    return TestClient(app)


def test_health_ready_and_meta(webapp_client: TestClient):
    h = webapp_client.get("/healthz")
    assert h.status_code == 200
    assert h.json()["ok"] is True

    r = webapp_client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["model"] == "gpt-6-luna"

    meta = webapp_client.get("/api/meta").json()
    assert meta["model"] == "gpt-6-luna"
    assert len(meta["starters"]) == 6
    starter_ids = {s["id"] for s in meta["starters"]}
    assert {"niagads", "adsp", "psp", "apoe4", "imatinib", "dna"} == starter_ids
    assert len(meta["niagads"]["datasets"]) >= 8


def test_index_serves_modern_web_markup(webapp_client: TestClient):
    res = webapp_client.get("/")
    assert res.status_code == 200
    html = res.text
    assert '<meta name="color-scheme" content="light dark">' in html
    assert 'closedby="any"' in html
    assert 'id="chat-input"' in html


def test_thread_lifecycle_and_client_isolation(webapp_client: TestClient):
    h_a = {"X-Ligase-Client-Id": "client_alpha_123456"}
    h_b = {"X-Ligase-Client-Id": "client_bravo_654321"}

    created = webapp_client.post(
        "/api/threads",
        headers=h_a,
        json={"title": "BIN1 V2F Study", "profile": "ad1", "mode": "direct"},
    )
    assert created.status_code == 200
    tid = created.json()["thread"]["id"]

    assert len(webapp_client.get("/api/threads", headers=h_a).json()["threads"]) == 1
    assert len(webapp_client.get("/api/threads", headers=h_b).json()["threads"]) == 0
    assert webapp_client.get(f"/api/threads/{tid}", headers=h_b).status_code == 404

    deleted = webapp_client.delete(f"/api/threads/{tid}", headers=h_a)
    assert deleted.status_code == 200
    assert len(webapp_client.get("/api/threads", headers=h_a).json()["threads"]) == 0


def test_upload_validation_and_storage(webapp_client: TestClient):
    headers = {
        "X-Ligase-Client-Id": "client_upload_123456",
        "X-Upload-Filename": "variants.tsv",
    }
    ok = webapp_client.post("/api/uploads", headers=headers, content=b"rsid\tpval\nrs6733839\t1e-24\n")
    assert ok.status_code == 200
    assert ok.json()["token"].startswith("client_upload_123456/")

    bad = webapp_client.post(
        "/api/uploads",
        headers={"X-Ligase-Client-Id": "client_upload_123456", "X-Upload-Filename": "malware.exe"},
        content=b"MZ",
    )
    assert bad.status_code == 400


def test_sse_chat_stream_and_artifact_downloads(webapp_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    class _FakeClaw:
        on_stream_event = None
        tools = None

    class _FakeAgent:
        def __init__(self):
            self.claw_agent = _FakeClaw()
            self.last_state = SimpleNamespace(iterations=2, status="done")

        def go(self, prompt: str) -> str:
            cb = self.claw_agent.on_stream_event
            if cb:
                cb(SimpleNamespace(kind="turn_started", iteration=1))
                cb(SimpleNamespace(kind="tool_started", call_id="c1", tool_name="query_niagads", args={"query": "BIN1"}))
                cb(
                    SimpleNamespace(
                        kind="tool_result",
                        call_id="c1",
                        tool_name="query_niagads",
                        success=True,
                        output="BIN1 rs6733839 PIP=0.916",
                        error=None,
                    )
                )
                cb(SimpleNamespace(kind="assistant_delta", delta="Causal sentinel **rs6733839** reaches `PIP = 0.916`."))
            return "Causal sentinel **rs6733839** reaches `PIP = 0.916`."

    monkeypatch.setattr("ligase.webapp.server.create_agent", lambda **kwargs: _FakeAgent())

    headers = {"X-Ligase-Client-Id": "client_stream_123456"}
    with webapp_client.stream(
        "POST",
        "/api/chat/stream",
        headers=headers,
        json={"prompt": "Analyze BIN1 rs6733839 PIP", "profile": "ad1", "max_iterations": 6},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "event: run_started" in body
    assert "event: tool_started" in body
    assert "event: tool_result" in body
    assert "event: run_complete" in body

    complete_block = [blk for blk in body.split("\n\n") if "event: run_complete" in blk][0]
    data_line = [ln[5:].strip() for ln in complete_block.splitlines() if ln.startswith("data:")][0]
    payload = json.loads(data_line)
    assert payload["model"] == "gpt-6-luna"
    assert "0.916" in payload["content"]

    rep = webapp_client.get(payload["report_url"])
    assert rep.status_code == 200
    assert "Ligase Scientific Study Report" in rep.text
    assert "query_niagads" in rep.text

    bundle = webapp_client.get(payload["bundle_url"])
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_frontend_js_syntax():
    js_path = STATIC_DIR / "app.js"
    res = subprocess.run(["node", "--check", str(js_path)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
