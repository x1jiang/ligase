"""End-to-end test suite for Ligase v0.6.0 NIAGADS Quantitative V2F, Fine-Mapping/Coloc,
TwoSampleMR/PRS, Rare Regulatory Scorer, Batch VCF, Translational ARIA/Trials, Critic Mode,
Jupyter .ipynb Export, Study Permalinks, and NIAGADS MCP Server.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from ligase.agent import CRITIC_EXECUTION_DIRECTIVE, WEB_FAST_TOOLS
from ligase.mcp_server import handle_mcp_request
from ligase.niagads_api import execute_niagads_action
from ligase.niagads_v2f_engine import (
    niagads_finemap_coloc,
    niagads_mendelian_randomization_prs,
    niagads_rare_regulatory_score,
    niagads_translational_trials,
    niagads_v2f_statistical_suite,
    niagads_vcf_batch_v2f,
    run_niagads_v2f_benchmark,
)
from ligase.webapp.mindmap import build_capabilities_mindmap
from ligase.webapp.server import create_webapp


def test_niagads_finemap_coloc_and_locuszoom_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    res = niagads_finemap_coloc(target="BIN1")
    assert res["ok"] is True
    assert res["action"] == "finemap_coloc"
    assert res["rows"][0]["rsid"] == "rs6733839"
    assert res["rows"][0]["pip_filer"] > 0.85
    assert res["rows"][0]["pip_filer"] > res["rows"][0]["pip_uniform"]
    coloc = res["raw"]["coloc"]
    assert coloc["PP.H4"] > 0.90
    assert abs(sum(coloc.values()) - 1.0) < 1e-3
    lz = res["visual"]["locuszoom"]
    assert lz["gene"] == "BIN1"
    assert "rs6733839" in lz["credible_set_95"]

    # Also test delegation via execute_niagads_action
    delegated = execute_niagads_action(action="finemap_coloc", target="APOE")
    assert delegated["ok"] is True
    assert delegated["rows"][0]["rsid"] == "rs429358"


def test_niagads_two_sample_mr_and_cross_ancestry_prs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    res = niagads_mendelian_randomization_prs(
        target="microglia_endolysosomal",
        ancestry="ALL",
        genotypes="rs429358=1,rs6733839=2,rs115550680=1",
    )
    assert res["ok"] is True
    mr = res["raw"]["mr"]
    assert mr["ivw"]["pvalue"] < 1e-4
    assert "mr_egger" in mr and "weighted_median" in mr
    prs = res["raw"]["prs"]
    assert {r["ancestry"] for r in prs} == {"EUR", "AFR", "AMR", "EAS"}
    afr_row = next(r for r in prs if r["ancestry"] == "AFR")
    assert afr_row["relative_or"] > 2.0


def test_niagads_rare_regulatory_vcf_batch_and_translational_aria(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")

    reg = niagads_rare_regulatory_score(target="rs6733839")
    assert reg["ok"] is True
    assert reg["raw"]["composite_score"] >= 60.0
    assert len(reg["rows"]) == 5

    vcf_res = niagads_vcf_batch_v2f(
        "#CHROM\tPOS\tID\tREF\tALT\n"
        "chr19\t44908684\trs429358\tT\tC\n"
        "chr2\t127135234\trs6733839\tC\tT\n"
        "rs72824905\n"
    )
    assert vcf_res["ok"] is True
    assert len(vcf_res["rows"]) == 3
    assert "variant,gene,grch38" in vcf_res["csv"]
    assert vcf_res["rows"][0]["v2f_score"] >= vcf_res["rows"][-1]["v2f_score"]

    trials = niagads_translational_trials(target="APOE")
    assert trials["ok"] is True
    assert "ARIA-E" in trials["summary_markdown"]
    assert len(trials["rows"]) >= 2

    suite_md = niagads_v2f_statistical_suite(analysis="finemap_coloc", target="TREM2")
    assert "TREM2" in suite_md and "PP.H4" in suite_md


def test_niagads_benchmark_and_mcp_server_jsonrpc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    bench = run_niagads_v2f_benchmark()
    assert bench["ok"] is True
    assert bench["loci_evaluated"] == 6
    assert bench["top1_causal_variant_accuracy"] == 1.0
    assert bench["mean_coloc_pp_h4"] > 0.95

    init_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "ligase-niagads-mcp"
    assert init_resp["result"]["serverInfo"]["version"] == "0.7.0"

    tools_resp = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert tools_resp is not None
    tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
    assert {
        "niagads_locus_dossier",
        "niagads_finemap_coloc",
        "niagads_mendelian_randomization_prs",
        "niagads_rare_regulatory_score",
        "niagads_vcf_batch_v2f",
        "niagads_translational_trials",
        "niagads_colocboost_mesusie",
        "niagads_resilience_xwas_seaad",
        "niagads_literature_credits",
        "query_niagads_catalog",
    } == tool_names

    call_resp = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "niagads_finemap_coloc", "arguments": {"target": "BIN1"}},
        }
    )
    assert call_resp is not None
    assert call_resp["result"]["isError"] is False
    assert "rs6733839" in call_resp["result"]["content"][0]["text"]

    res_read = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "niagads://citation/u24ag041689"},
        }
    )
    assert res_read is not None
    assert "U24AG041689" in res_read["result"]["contents"][0]["text"]


def test_webapp_v060_routes_notebook_permalink_critic_and_2d_panning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIGASE_WEB_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-v060")
    monkeypatch.setenv("LIGASE_SKIP_WARMUP", "1")
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")

    assert "niagads_v2f_statistical_suite" in WEB_FAST_TOOLS
    assert "NIAGADS Statistical Genetics & Multi-Ancestry Critic Audit" in CRITIC_EXECUTION_DIRECTIVE

    mm = build_capabilities_mindmap()
    assert mm["stats"]["components"] == 48

    app = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    client = TestClient(app)

    # Check clean Home + Critic switch + 2D panning CSS + WebMCP registration
    home_html = client.get("/").text
    assert 'id="speed-critic-btn"' in home_html
    assert 'id="niagads-vcf-drawer"' in home_html
    css_txt = client.get("/static/styles.css?v=0.7.0").text
    assert "scroll-axis-lock: none;" in css_txt
    assert "overscroll-behavior: contain;" in css_txt
    js_txt = client.get("/static/app.js?v=0.7.0").text
    assert '"modelContext" in document' in js_txt
    assert "document.modelContext.registerTool" in js_txt

    # Batch VCF endpoint
    vcf_http = client.post(
        "/api/niagads/vcf-annotate",
        json={"vcf_text": "rs429358\nrs6733839\n"},
    )
    assert vcf_http.status_code == 200
    assert len(vcf_http.json()["rows"]) == 2
    assert "rs429358" in vcf_http.json()["csv"]

    # Benchmark endpoint
    bench_http = client.get("/api/niagads/benchmark")
    assert bench_http.status_code == 200
    assert bench_http.json()["top1_causal_variant_accuracy"] == 1.0

    # Critic mode SSE run -> .ipynb download -> public ?study= shared permalink (without leaking client_id)
    captured_modes = []

    class _FakeClaw:
        on_stream_event = None
        tools = None

    class _FakeAgent:
        def __init__(self):
            self.claw_agent = _FakeClaw()
            self.last_state = SimpleNamespace(iterations=1, status="done")

        def go(self, prompt: str) -> str:
            return "## Synthesis\nGrounded BIN1 rs6733839 result.\n\n## 🏛️ NIAGADS Statistical Genetics & Multi-Ancestry Critic Audit\n| Check | Verdict |\n|---|---|"

    def _fake_factory(**kwargs):
        captured_modes.append(kwargs.get("speed_mode"))
        return _FakeAgent()

    monkeypatch.setattr("ligase.webapp.server.create_agent", _fake_factory)
    headers = {"X-Ligase-Client-Id": "cli_secret_owner_999"}
    sse_res = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"prompt": "Audit BIN1 rs6733839 in NG00105", "profile": "ad1", "speed_mode": "critic"},
    )
    assert sse_res.status_code == 200
    assert "critic" in captured_modes

    # Parse run_complete from SSE
    run_id = ""
    for chunk in sse_res.text.split("\n\n"):
        if "event: run_complete" in chunk:
            for line in chunk.splitlines():
                if line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    run_id = payload["run_id"]
                    assert payload["speed_mode"] == "critic"
                    assert payload["notebook_url"].startswith(f"/api/runs/{run_id}/notebook.ipynb")
                    assert payload["share_url"] == f"/?study={run_id}"
    assert run_id

    # Verify Jupyter Notebook (.ipynb) export
    nb_res = client.get(f"/api/runs/{run_id}/notebook.ipynb", headers=headers)
    assert nb_res.status_code == 200
    assert "application/x-ipynb+json" in nb_res.headers.get("content-type", "")
    nb_json = nb_res.json()
    assert nb_json["nbformat"] == 4
    assert nb_json["metadata"]["ligase"]["niagads_grant"] == "U24AG041689"
    assert any("https://api.niagads.org/api" in "".join(c["source"]) for c in nb_json["cells"])

    # Verify public shared permalink endpoint (and ensure client_id is NOT leaked)
    shared_res = client.get(f"/api/shared/{run_id}")
    assert shared_res.status_code == 200
    shared_json = shared_res.json()
    assert shared_json["ok"] is True
    assert shared_json["run_id"] == run_id
    assert "client_id" not in shared_json
    assert "cli_secret_owner_999" not in json.dumps(shared_json)
