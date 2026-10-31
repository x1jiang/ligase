"""Verification suite for Ligase v0.7.0 Literature-Grounded NIAGADS Priorities & Paper Credits."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import ligase
from ligase.mcp_server import handle_mcp_request
from ligase.niagads_v2f_engine import (
    NIAGADS_LITERATURE_CREDITS,
    evaluate_niagads_rubric_audit,
    get_niagads_literature_catalog,
    niagads_colocboost_mesusie,
    niagads_mendelian_randomization_prs,
    niagads_rare_regulatory_score,
    niagads_resilience_xwas_seaad,
    niagads_v2f_statistical_suite,
    niagads_vcf_batch_v2f,
    run_niagads_v2f_benchmark,
)
from ligase.webapp.mindmap import build_capabilities_mindmap
from ligase.webapp.server import create_webapp


def test_v070_literature_credits_registry_and_priorities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    assert ligase.__version__ == "0.8.0"
    assert len(NIAGADS_LITERATURE_CREDITS) == 16

    cat = get_niagads_literature_catalog()
    assert cat["ok"] is True
    assert len(cat["rows"]) == 16
    dois_joined = " | ".join(r["doi_or_id"] for r in cat["rows"])
    assert "PMC11709351" in dois_joined  # ColocBoost / FunGen-xQTL (Cifello et al. 2025)
    assert "10.1038/s41588-023-01604-7" in dois_joined  # MESuSiE (Gao et al. 2024)
    assert "10.1007/s00401-024-02721-1" in dois_joined  # FN1 rs140926439 resilience (Bhattarai et al. 2024)
    assert "10.1001/jamaneurol.2024.2843" in dois_joined  # chrX XWAS SLC9A7 & MID1 (Belloy et al. 2024)
    assert "10.1038/s41588-025-02227-w" in dois_joined  # PRS-CSx admixture (Nicolas et al. 2025)
    assert "10.1038/s41593-024-01774-5" in dois_joined  # SEA-AD CPS (Gabitto et al. 2024)
    assert "10.1038/s41586-025-10014-0" in dois_joined  # AlphaGenome (Avsec et al. 2026)

    # Priority 1: TAD-Window 6-Modality ColocBoost + 4-Ancestry MESuSiE
    cb_bin1 = niagads_colocboost_mesusie("BIN1")
    assert cb_bin1["ok"] is True
    assert len(cb_bin1["rows"]) == 6
    anc_nhw = cb_bin1["raw"]["mesusie_ancestries"][0]
    assert anc_nhw["pip_mesusie_shared"] > anc_nhw["pip_single"]
    assert cb_bin1["raw"]["mesusie_joint_cs_size"] == 1
    assert len(cb_bin1["paper_credits"]) >= 4
    assert "colocboost_mesusie" in cb_bin1["visual"]

    # Distal cis-TAD enhancer loop (SEC61G -> EGFR +245.8 kb) & TSPAN14 cryptic splicing
    cb_egfr = niagads_colocboost_mesusie("EGFR")
    assert cb_egfr["raw"]["lead_variant"] == "rs76928645"
    assert "SEC61G" in cb_egfr["summary_markdown"]

    reg_tspan = niagads_rare_regulatory_score("TSPAN14")
    assert reg_tspan["ok"] is True
    assert len(reg_tspan["rows"]) == 5
    assert "alphagenome_1mb" in reg_tspan["raw"]
    assert "staar_sv_burden" in reg_tspan["raw"]
    assert len(reg_tspan["paper_credits"]) >= 3

    # Priority 2: APOEe4 FN1 Resilience + chrX XWAS/XCI + SEA-AD CPS + PRS-CSx
    res_apoe = niagads_resilience_xwas_seaad("APOE", sex="female", apoe_genotype="e4/e4")
    assert res_apoe["ok"] is True
    fn1_entry = next(m for m in res_apoe["raw"]["resilience_modifiers"] if m["gene"] == "FN1")
    assert "rs140926439" in fn1_entry["variant"]
    assert fn1_entry["protective_or"] == pytest.approx(0.29)
    chrx_genes = " ".join(x["gene"] for x in res_apoe["raw"]["xwas_loci"])
    assert "SLC9A7" in chrx_genes and "MID1" in chrx_genes
    assert len(res_apoe["raw"]["seaad_epochs"]) == 2
    assert "resilience_xwas_seaad" in res_apoe["visual"]

    mr_prs = niagads_mendelian_randomization_prs("microglia_endolysosomal")
    assert mr_prs["raw"]["admixture_transferability"]["eur_prs_afr_90pct_non_apoe_or"] == pytest.approx(1.09)

    vcf_res = niagads_vcf_batch_v2f("rs140926439\nrs188959992\nrs6733839")
    genes_found = {r["gene"] for r in vcf_res["rows"]}
    assert {"FN1", "SLC9A7", "BIN1"} <= genes_found

    # Priority 3: Deterministic Rubric Verifier & AD-HeurekaBench v0.7
    audit = evaluate_niagads_rubric_audit(
        "Audit BIN1 rs6733839 across multi-ancestry cohorts",
        "BIN1 rs6733839 (chr2:127135234, NG00105, NG00075, NHW vs AFR/AA) shows PIP = 0.946, OR = 1.22, p = 2.1e-44 "
        "with ColocBoost PP.H4 = 0.961 (Li et al. 2025, 10.1038/s41588-025-02182-6; Gao et al. 2024). "
        "Validate via CRISPRi base-editing of the SPI1 enhancer in iPSC-microglia.",
    )
    assert audit["ok"] is True
    assert audit["rubric_score"] >= 80.0
    assert audit["gates_total"] == 6

    bench = run_niagads_v2f_benchmark()
    assert bench["benchmark"] == "NIAGADS-AD-HeurekaBench-v0.8"
    assert bench["loci_evaluated"] == 6
    assert bench["multi_step_workflows_evaluated"] == 6
    assert bench["workflow_pass_rate"] == 1.0

    # Tool wrapper dispatch
    md_suite = niagads_v2f_statistical_suite(analysis="colocboost_mesusie", target="ABCA7")
    assert "MESuSiE" in md_suite and "ColocBoost" in md_suite


def test_v070_webapp_routes_mcp_literature_and_closed_loop_critic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    monkeypatch.setenv("LIGASE_SKIP_WARMUP", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-v070")

    # MCP Literature resource & new tools
    mcp_lit = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "resources/read",
            "params": {"uri": "niagads://literature/credits"},
        }
    )
    assert mcp_lit is not None
    lit_payload = json.loads(mcp_lit["result"]["contents"][0]["text"])
    assert len(lit_payload["rows"]) == 16

    mcp_cb = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "niagads_colocboost_mesusie", "arguments": {"target": "EGFR"}},
        }
    )
    assert mcp_cb is not None and mcp_cb["result"]["isError"] is False
    assert "rs76928645" in mcp_cb["result"]["content"][0]["text"]

    mm = build_capabilities_mindmap()
    assert mm["stats"]["components"] == 50

    class DummyClaw:
        on_stream_event: Any = None
        tools = None

    class DummyAgent:
        def __init__(self) -> None:
            self.claw_agent = DummyClaw()
            self.last_state = SimpleNamespace(iterations=1)

        def go(self, prompt: str) -> str:
            if callable(self.claw_agent.on_stream_event):
                self.claw_agent.on_stream_event(
                    SimpleNamespace(kind="assistant_delta", data={"delta": "Draft synthesis for APOE FN1."})
                )
            return (
                "APOE e4/e4 (`chr19:44908684`, `NG00067`/`NG00100`, EUR vs AFR) is modified by `FN1 rs140926439` "
                "(`OR = 0.29`, `p = 3.2e-6`, Bhattarai et al. 2024 `10.1007/s00401-024-02721-1`) with iPSC-BBB CRISPRi validation."
            )

    monkeypatch.setattr("ligase.webapp.server.create_agent", lambda **kwargs: DummyAgent())
    app = create_webapp(
        state_dir=tmp_path / "state",
        runs_root=tmp_path / "runs",
    )
    client = TestClient(app)

    # Literature HTTP endpoint
    lit_http = client.get("/api/niagads/literature?topic=fn1")
    assert lit_http.status_code == 200
    assert any(r["id"] == "fn1_bhattarai_2024" for r in lit_http.json()["rows"])

    # Live Explorer v0.7 endpoints
    cb_http = client.get("/api/niagads/live?action=colocboost_mesusie&target=BIN1")
    assert cb_http.status_code == 200
    assert len(cb_http.json()["paper_credits"]) >= 4

    rx_http = client.get("/api/niagads/live?action=resilience_xwas_seaad&target=APOE")
    assert rx_http.status_code == 200
    assert len(rx_http.json()["paper_credits"]) >= 4

    # Closed-loop Critic SSE stream executes `niagads_rubric_verifier` and appends deterministic rubric table
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "prompt": "Audit APOE e4/e4 FN1 rs140926439 resilience across ancestries",
            "profile": "ad1",
            "speed_mode": "critic",
            "mode": "direct",
        },
    ) as stream_res:
        assert stream_res.status_code == 200
        sse_body = "".join(stream_res.iter_text())

    assert "niagads_rubric_verifier" in sse_body
    assert "Closed-Loop NIAGADS Rubric Verifier" in sse_body
