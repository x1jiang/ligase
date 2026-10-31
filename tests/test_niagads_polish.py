"""Tests for v0.5.0 NIAGADS V2F Locus Dossier, visual metadata, ecosystem cross-links, and portal polish."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient
import pytest

import ligase
from ligase.niagads_api import clear_niagads_api_cache, execute_niagads_action
from ligase.webapp.mindmap import build_capabilities_mindmap
from ligase.webapp.server import _format_markdown_report, create_webapp


def _mock_niagads_router(url: str) -> Any:
    if "get_overlapping_tracks_by_coord.php" in url:
        return [{"trackId": "ENCFF001", "numOverlaps": 4}, {"trackId": "ENCFF002", "numOverlaps": 9}]

    if "/record/gene/BIN1/associations" in url:
        return {
            "request": {"request_id": "req-bin1-assoc"},
            "pagination": {"total_records": 2, "page": 1},
            "data": [
                {
                    "variant": "rs6733839",
                    "test_allele": "T",
                    "pvalue": "1.2e-44",
                    "neg_log10_pvalue": 43.92,
                    "effect_direction": "+",
                    "track": "NG00075_STAGE1_EUR",
                    "traits": [{"term": "Alzheimer's disease"}],
                },
                {
                    "variant": "rs744373",
                    "test_allele": "G",
                    "pvalue": "3.1e-18",
                    "neg_log10_pvalue": 17.51,
                    "effect_direction": "+",
                    "track": "NG00100_AA_GWAS",
                    "traits": [{"term": "Alzheimer's disease"}],
                },
            ],
        }

    if "/record/gene/BIN1/structure" in url:
        return {
            "data": [
                {
                    "id": "ENSG00000136717",
                    "gene_symbol": "BIN1",
                    "location": "chr2:127048023-127107288",
                    "strand": "-",
                    "transcripts": [
                        {
                            "id": "ENST00000316724",
                            "name": "BIN1-201",
                            "is_canonical": True,
                            "location": "chr2:127048023-127107288:-",
                            "exons": [
                                {"id": "ENSE0001", "location": "chr2:127048023-127048450:-"},
                                {"id": "ENSE0002", "location": "chr2:127060100-127060320:-"},
                                {"id": "ENSE0003", "location": "chr2:127106900-127107288:-"},
                            ],
                        }
                    ],
                }
            ]
        }

    if "/record/gene/?ids=" in url or "/record/gene/BIN1" in url:
        return {
            "request": {"request_id": "req-bin1-gene"},
            "data": [
                {
                    "id": "ENSG00000136717",
                    "gene_symbol": "BIN1",
                    "gene_name": "bridging integrator 1",
                    "gene_type": "protein_coding",
                    "location": "chr2:127048023-127107288",
                    "cytogenetic_location": "2q14.3",
                    "associated_with_known_ad_locus": True,
                    "xrefs": {"uniprot_id": "O00499", "hgnc_id": "HGNC:1052"},
                    "pathways": [{"pathway_name": "Clathrin-mediated endocytosis"}],
                }
            ],
        }

    if "/record/variant/rs6733839/associations" in url:
        return {
            "request": {"request_id": "req-rs6733839-assoc"},
            "pagination": {"total_records": 1, "page": 1},
            "data": [
                {
                    "variant": "rs6733839",
                    "test_allele": "T",
                    "pvalue": "1.2e-44",
                    "neg_log10_pvalue": 43.92,
                    "effect_direction": "+",
                    "track": "NG00166_04BE648F_STD_OA",
                    "traits": [{"term": "Alzheimer's disease"}],
                }
            ],
        }

    if "/record/variant/" in url:
        return {
            "request": {"request_id": "req-rs6733839-var"},
            "data": [
                {
                    "id": "2:127135234:C:T",
                    "ref_snp_id": "rs6733839",
                    "chromosome": "chr2",
                    "position": 127135234,
                    "variant_class": "SNV",
                    "is_adsp_variant": True,
                    "ga4gh_vrs": {"id": "ga4gh:VA.example_digest"},
                    "most_severe_consequence": {
                        "impact": "MODIFIER",
                        "consequence_terms": ["upstream_gene_variant"],
                        "feature": {"gene": {"gene_symbol": "BIN1", "id": "ENSG00000136717"}},
                    },
                    "allele_frequency": {
                        "ALFA": {
                            "GnomAD_genomes": 0.3912,
                            "TOPMED": 0.3885,
                            "1000Genomes": 0.3721,
                        },
                        "GnomAD": {
                            "afr": 0.4412,
                            "nfe": 0.3890,
                        },
                    },
                }
            ],
        }

    if "/record/region/" in url and "/variants" in url:
        return {
            "pagination": {"total_records": 2, "page": 1},
            "data": [
                {
                    "ref_snp_id": "rs6733839",
                    "id": "2:127135234:C:T",
                    "variant_class": "SNV",
                    "is_adsp_variant": True,
                    "most_severe_consequence": {"consequence_terms": ["regulatory_region_variant"]},
                }
            ],
        }

    if "/record/region/" in url and "/associations" in url:
        return {
            "request": {"request_id": "req-reg-assoc"},
            "pagination": {"total_records": 1, "page": 1},
            "data": [
                {
                    "variant": "rs6733839",
                    "test_allele": "T",
                    "pvalue": "1.2e-44",
                    "neg_log10_pvalue": 43.92,
                    "effect_direction": "+",
                    "track": "NG00166_04BE648F_STD_OA",
                    "traits": [{"term": "Alzheimer's disease"}],
                }
            ],
        }

    if "/service/feature" in url:
        return {"chr": "chr2", "start": 127048023, "end": 127098023}

    raise AssertionError(f"Unexpected mocked URL: {url}")


def test_locus_dossier_gene_and_variant_visual_and_ecosystem_links(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_niagads_api_cache()
    monkeypatch.setattr("ligase.niagads_api._http_get_json", _mock_niagads_router)

    gene_res = execute_niagads_action(action="locus_dossier", target="BIN1", flank=10000)
    assert gene_res["ok"] is True
    assert gene_res["action"] == "locus_dossier"
    assert "NIAGADS V2F Locus Dossier" in gene_res["summary_markdown"]
    assert "GVC Known AD Locus" in gene_res["summary_markdown"]

    vis = gene_res["visual"]
    assert vis["associations"]["mode"] == "pvalues"
    assert vis["associations"]["items"][0]["neg_log10_p"] == pytest.approx(43.92)
    assert vis["gene_structure"]["gene"] == "BIN1"
    assert vis["gene_structure"]["exon_count"] == 3
    assert vis["filer"]["overlapping_tracks"] == 2
    assert vis["filer"]["overlapping_intervals"] == 13

    urls = [x["url"] for x in gene_res["ecosystem_links"]]
    assert any("niagads.org/genomics/app/record/gene/ENSG00000136717" in u for u in urls)
    assert any("topgenes.niagads.org" in u for u in urls)
    assert any("dss.niagads.org/datasets/ng00075/" in u for u in urls)
    assert any("FILER" in u for u in urls)

    var_res = execute_niagads_action(action="locus_dossier", target="rs6733839")
    assert var_res["ok"] is True
    assert var_res["visual"]["allele_frequencies"][0]["af"] == pytest.approx(0.3912)
    var_urls = [x["url"] for x in var_res["ecosystem_links"]]
    assert any("niagads.org/genomics/app/record/variant/2:127135234:C:T" in u for u in var_urls)
    assert any("advp.niagads.org" in u for u in var_urls)
    assert any("ncbi.nlm.nih.gov/snp/rs6733839" in u for u in var_urls)
    assert any("gnomad.broadinstitute.org/variant/2-127135234-C-T" in u for u in var_urls)


def test_portal_polish_security_headers_landmarks_and_provenance(tmp_path: Path) -> None:
    webapp = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    client = TestClient(webapp)

    res = client.get("/")
    assert res.status_code == 200
    assert res.headers.get("cross-origin-opener-policy") == "same-origin-allow-popups"
    assert res.headers.get("permissions-policy") == "camera=(), geolocation=(), microphone=()"

    html = res.text
    assert html.count("<h1") == 1
    assert f"?v={ligase.__version__}" in html
    assert 'id="command-palette-dialog"' in html
    assert "<search" in html
    assert 'class="niagads-bond-strip"' in html
    assert "U24AG041689" in html
    assert '<pre tabindex="0"><code id="oa-result-json">' in html

    m = re.search(r'<script id="ligase-bootstrap" type="application/json">(.*?)</script>', html, re.S)
    assert m is not None
    boot_bytes = m.group(1).encode("utf-8")
    assert len(boot_bytes) < 12_000
    parsed = json.loads(m.group(1))
    assert parsed["boot"]["version"] == "0.5.2"

    # Organized 3-shelf Studio Home architecture preserving Find-in-Page indexing
    assert 'id="studio-home-shelf"' in html
    assert ':not([hidden="until-found"])[hidden]' in html
    assert 'id="shelf-pane-studies"' in html
    assert 'id="shelf-pane-video"' in html and 'hidden="until-found"' in html
    assert 'id="shelf-pane-niagads"' in html
    assert 'id="shelf-expand-all-btn"' in html
    assert "NG00105" in html and "NG00100" in html and "NG00169" in html

    mm = build_capabilities_mindmap()
    assert mm["stats"]["components"] >= 36
    assert any(c["id"] == "mm_oa_dossier" for b in mm["branches"] for c in b["components"])

    rep = _format_markdown_report(
        run_id="run_test_050",
        model="gpt-6-luna",
        profile="ad1",
        prompt="Evaluate BIN1 rs6733839",
        answer="Grounded synthesis for BIN1.",
        elapsed_s=1.2,
        iterations=1,
        tool_trace=[{"tool_name": "niagads_open_access_api", "elapsed_ms": 210, "args_preview": "BIN1", "success": True}],
    )
    assert "U24AG041689" in rep
    assert "NIAGADS Data Attribution & Provenance" in rep


def test_grok_narrated_showcase_video_embed_and_range_streaming(tmp_path: Path) -> None:
    webapp = create_webapp(state_dir=tmp_path / "state", runs_root=tmp_path / "runs")
    client = TestClient(webapp)

    html = client.get("/").text
    assert 'id="ligase-showcase-video"' in html
    assert 'loading="lazy"' in html
    assert 'preload="none"' in html
    assert 'width="1280"' in html
    assert 'height="720"' in html
    assert 'kind="captions"' in html
    assert 'srclang="en"' in html
    assert 'aria-details="showcase-video-transcript"' in html
    assert 'id="showcase-video-transcript"' in html
    assert "data-video-seek=" in html

    # Verify poster WebP
    poster_res = client.get("/static/media/ligase-showcase-poster.webp?v=0.5.2")
    assert poster_res.status_code == 200
    assert "image/webp" in poster_res.headers.get("content-type", "")
    assert "immutable" in poster_res.headers.get("cache-control", "")

    # Verify synchronous WebVTT captions
    vtt_res = client.get("/static/media/ligase-showcase-en.vtt?v=0.5.2")
    assert vtt_res.status_code == 200
    assert "text/vtt" in vtt_res.headers.get("content-type", "")
    assert vtt_res.text.startswith("WEBVTT")
    assert "Grok Voice (Ara)" in vtt_res.text
    assert "Grok Voice (Rex)" in vtt_res.text

    # Verify byte-range 206 Partial Content video streaming without gzip interference
    range_res = client.get(
        "/static/media/ligase-showcase.mp4?v=0.5.2",
        headers={"Range": "bytes=0-1023", "Accept-Encoding": "gzip"},
    )
    assert range_res.status_code == 206
    assert "video/mp4" in range_res.headers.get("content-type", "")
    assert range_res.headers.get("content-encoding") is None
    assert len(range_res.content) == 1024

    pyproject_txt = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "webapp/static/media/*" in pyproject_txt
