"""Verification suite for Ligase v0.8.0 NIAGADS Visualizations, Browser Tracks & ADSP R5 Power / NIH DAR Co-Pilot."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ligase
from ligase.mcp_server import handle_mcp_request
from ligase.niagads_api import (
    NIAGADS_GENOMICSDB_BROWSER_URL,
    OPEN_ACCESS_ROLLOUT_CATALOG,
    execute_niagads_action,
    export_niagads_browser_tracks,
)
from ligase.niagads_v2f_engine import (
    ADSP_PHC_PHENOTYPE_DOMAINS,
    ADSP_R5_WGS_STRATA,
    NIAGADS_LITERATURE_CREDITS,
    niagads_adsp_r5_power_dar,
    niagads_v2f_statistical_suite,
    run_niagads_v2f_benchmark,
)
from ligase.webapp.server import create_webapp


def test_v080_adsp_r5_power_engine_ancestry_domains_and_dar_copilot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    assert ligase.__version__ == "0.8.0"
    assert len(OPEN_ACCESS_ROLLOUT_CATALOG["endpoints"]) == 23
    assert len(NIAGADS_LITERATURE_CREDITS) == 16
    credit_ids = {c["id"] for c in NIAGADS_LITERATURE_CREDITS}
    assert "niagads_genomicsdb_browser_2024" in credit_ids
    assert "adsp_phc_hohman_2024" in credit_ids

    strata_by_anc = {s["ancestry"]: s for s in ADSP_R5_WGS_STRATA}
    assert strata_by_anc["ALL"]["n_subjects"] == 57_302
    assert strata_by_anc["ALL"]["n_genomes"] == 58_507
    assert set(ADSP_PHC_PHENOTYPE_DOMAINS) == {
        "case_control_ad",
        "cognition_longitudinal",
        "neuroimaging_mri_pet",
        "fluid_biomarkers_atn",
        "neuropathology_autopsy",
    }

    # ABCA7 frameshift/LoF enrichment in African-American (AA) vs NHW in ADSP R5
    abca7 = niagads_adsp_r5_power_dar(
        "ABCA7",
        test_mode="staar_o_burden",
        phenotype_domain="case_control_ad",
    )
    assert abca7["ok"] is True
    by_anc = {r["ancestry"]: r for r in abca7["rows"]}
    assert set(by_anc) == {"NHW", "HIS", "AA", "ASN", "ALL"}
    assert by_anc["AA"]["frequency"] > by_anc["NHW"]["frequency"]
    assert by_anc["AA"]["ncp_lambda"] > by_anc["NHW"]["ncp_lambda"]
    assert by_anc["AA"]["n_required_80"] < by_anc["NHW"]["n_required_80"]
    assert by_anc["ALL"]["power_pct"] >= 99.0

    # Verify visual payload for SVG power bars + multi-ancestry effect-size sweep curves
    vis = abca7["visual"]["adsp_r5_power_dar"]
    assert len(vis["strata"]) == 5
    curve_ancs = {c["ancestry"] for c in vis["power_curves"]}
    assert curve_ancs == {"NHW", "HIS", "AA", "ASN", "ALL"}
    assert len(vis["power_curves"][0]["points"]) == 7

    # Verify NIAGADS DARM compliance & NIH Specific Aims / DMS plan outputs
    dar_md = abca7["dar_specific_aims_markdown"]
    assert "NG00067" in dar_md
    assert "U24AG041689" in dar_md
    assert "U24AG074855" in dar_md
    assert "Institutional Signing Official" in dar_md
    assert "Specific Aim 1" in dar_md and "Specific Aim 2" in dar_md and "Specific Aim 3" in dar_md
    assert "NIH 2023 Data Management & Sharing" in dar_md
    assert "ancestry,stratum_label,n_subjects,n_cases,n_controls" in abca7["csv"]

    # Quantitative ADSP-PHC phenotype domain (CSF/Plasma ATN Fluid Biomarkers) + custom MAF/effect override
    sorl1_atn = niagads_adsp_r5_power_dar(
        "SORL1",
        test_mode="endophenotype_qtl",
        phenotype_domain="fluid_biomarkers_atn",
        custom_maf=0.015,
        effect_size=0.28,
        alpha=1e-6,
    )
    assert sorl1_atn["ok"] is True
    assert sorl1_atn["visual"]["adsp_r5_power_dar"]["is_quantitative"] is True
    assert sorl1_atn["raw"]["alpha"] == pytest.approx(1e-6)
    assert all(r["frequency"] == pytest.approx(0.015) for r in sorl1_atn["rows"])
    assert "NG00049" in " ".join(d["accession"] for d in sorl1_atn["raw"]["recommended_datasets"])

    # Tool wrapper + benchmark WF6
    suite_md = niagads_v2f_statistical_suite(
        analysis="adsp_r5_power_dar",
        target="TREM2",
        ancestry="cognition_longitudinal",
    )
    assert "NG00067" in suite_md and "U24AG074855" in suite_md

    bench = run_niagads_v2f_benchmark()
    wf_ids = {w["workflow_id"] for w in bench["workflows"]}
    assert "WF6_ADSP_R5_58k_WGS_Power_and_NIH_DAR_CoPilot" in wf_ids
    assert bench["workflow_pass_rate"] == 1.0


def test_v080_niagads_igv_browser_links_track_exports_webapp_mcp_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    monkeypatch.setenv("LIGASE_SKIP_WARMUP", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-v080")

    # Verify official NIAGADS GenomicsDB IGV.js browser deep-links & GRCh38 track exports
    fm_res = execute_niagads_action(action="finemap_coloc", target="BIN1")
    assert fm_res["ok"] is True
    link_urls = [lnk["url"] for lnk in fm_res["ecosystem_links"]]
    assert any(u.startswith(f"{NIAGADS_GENOMICSDB_BROWSER_URL}?locus=chr2:") for u in link_urls)
    assert any("/genomics/app/record/dataset/NG" in u for u in link_urls)

    tracks = export_niagads_browser_tracks(fm_res)
    assert tracks["niagads_browser_url"].startswith(f"{NIAGADS_GENOMICSDB_BROWSER_URL}?locus=chr2:")
    assert "track type=bedGraph" in tracks["bedgraph"]
    assert "chr2\t127135233\t127135234" in tracks["bedgraph"]
    assert "chrom\tpos\trsid\tref\talt\tneg_log10_p\tpip_filer\ttrack_or_modality" in tracks["locuszoom_tsv"]
    assert "rs6733839" in tracks["locuszoom_tsv"]

    # Webapp HTTP endpoints (POST /api/niagads/power-dar, GET /api/niagads/export-track, GET /api/niagads/live)
    app = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    client = TestClient(app)

    home_html = client.get("/").text
    assert 'id="niagads-power-dar-drawer"' in home_html
    assert 'id="oa-export-bedgraph-btn"' in home_html
    assert 'id="oa-export-lz-btn"' in home_html
    assert 'value="adsp_r5_power_dar"' in home_html

    post_power = client.post(
        "/api/niagads/power-dar",
        json={
            "target": "ABCA7",
            "test_mode": "staar_o_burden",
            "phenotype_domain": "case_control_ad",
        },
    )
    assert post_power.status_code == 200
    p_json = post_power.json()
    assert p_json["ok"] is True
    assert "dar_specific_aims_markdown" in p_json
    assert any(u.startswith(NIAGADS_GENOMICSDB_BROWSER_URL) for u in (l["url"] for l in p_json["ecosystem_links"]))

    live_power = client.get("/api/niagads/live?action=adsp_r5_power_dar&target=APOE")
    assert live_power.status_code == 200
    assert live_power.json()["ok"] is True

    bg_http = client.get("/api/niagads/export-track?action=finemap_coloc&target=BIN1&track_format=bedgraph")
    assert bg_http.status_code == 200
    assert bg_http.headers["x-niagads-browser-url"].startswith(NIAGADS_GENOMICSDB_BROWSER_URL)
    assert "track type=bedGraph" in bg_http.text

    lz_http = client.get("/api/niagads/export-track?action=finemap_coloc&target=BIN1&track_format=tsv")
    assert lz_http.status_code == 200
    assert "rs6733839" in lz_http.text

    # MCP tool & resource verification
    mcp_tool = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 81,
            "method": "tools/call",
            "params": {
                "name": "niagads_adsp_r5_power_dar",
                "arguments": {"target": "ABCA7", "phenotype_domain": "neuroimaging_mri_pet"},
            },
        }
    )
    assert mcp_tool is not None and mcp_tool["result"]["isError"] is False
    assert "NG00067" in mcp_tool["result"]["content"][0]["text"]

    mcp_res = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 82,
            "method": "resources/read",
            "params": {"uri": "niagads://dar/adsp-r5-guide"},
        }
    )
    assert mcp_res is not None
    guide_md = mcp_res["result"]["contents"][0]["text"]
    assert "NG00067" in guide_md
    assert "58,507" in guide_md

    # CLI `ligase niagads power ABCA7 --output-file <path>.json` verification
    repo_root = Path(__file__).resolve().parent.parent
    out_json = tmp_path / "abca7_power.json"
    cli_proc = subprocess.run(
        [sys.executable, "-m", "ligase.cli", "niagads", "power", "ABCA7", "--output-file", str(out_json)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    assert cli_proc.returncode == 0
    cli_payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert cli_payload["ok"] is True
    assert len(cli_payload["rows"]) == 5
