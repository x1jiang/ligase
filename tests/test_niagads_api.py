"""Unit tests for the NIAGADS Open Access API v2.0 client & ClawAgents tool integration."""

from __future__ import annotations

import pytest

from ligase.gemma_tools import gemma_extra_tools, query_niagads
from ligase.niagads_api import (
    clear_niagads_api_cache,
    execute_niagads_action,
    fetch_live_niagads_supplement,
    niagads_open_access_api,
    normalize_region,
    normalize_variant_id,
)


def test_variant_and_region_normalization():
    assert normalize_variant_id("RS429358") == "rs429358"
    assert normalize_variant_id("chr2:127135234C>T") == "2:127135234:C:T"
    assert normalize_variant_id("19:44908684:t:c") == "19:44908684:T:C"

    reg_ok, note_ok = normalize_region("2:127,134,000-127,136,000")
    assert reg_ok == "chr2:127134000-127136000"
    assert note_ok is None

    reg_clamped, note_clamped = normalize_region("chr17:45000000-46000000")
    assert reg_clamped.startswith("chr17:")
    assert note_clamped is not None
    assert "Clamped" in note_clamped


def test_execute_niagads_actions_mocked(monkeypatch: pytest.MonkeyPatch):
    clear_niagads_api_cache()

    def _fake_http_get(url: str, timeout: float = 12.0):
        if "/record/gene/APOE/structure" in url:
            return {
                "request": {"request_id": "req-struct"},
                "data": [
                    {
                        "location": "chr19:44903787-44909396",
                        "transcripts": [
                            {
                                "id": "ENST00000252486",
                                "name": "APOE-201",
                                "location": "chr19:44905791-44909393",
                                "exons": [{"location": "chr19:44905791-44905841"}],
                            }
                        ],
                    }
                ],
            }
        if "/record/gene/APOE" in url and "/associations" not in url:
            return {
                "request": {"request_id": "req-gene"},
                "data": [
                    {
                        "id": "ENSG00000130203",
                        "gene_symbol": "APOE",
                        "gene_name": "apolipoprotein E",
                        "location": "chr19:44903787-44909396",
                        "cytogenic_location": "19q13.32",
                        "gene_type": "protein_coding",
                        "associated_with_known_ad_locus": True,
                        "xrefs": {
                            "uniprot_id": "P02649",
                            "hgnc_id": "HGNC:613",
                            "entrez_id": "348",
                            "refseq_accession": "NM_000041",
                        },
                        "memberships": {
                            "pathways": [
                                {"pathway_name": "Alzheimer disease", "data_source": "KEGG", "pathway_id": "hsa05010"}
                            ]
                        },
                    }
                ],
            }
        if "/record/variant/rs429358" in url and "/associations" not in url:
            return {
                "request": {"request_id": "req-var"},
                "data": [
                    {
                        "ref_snp_id": "rs429358",
                        "id": "19:44908684:T:C",
                        "chromosome": "chr19",
                        "position": 44908684,
                        "variant_class": "single-nucleotide variant",
                        "is_adsp_variant": True,
                        "ga4gh_vrs": {"id": "ga4gh:VA.test123"},
                        "most_severe_consequence": {
                            "impact": "MODERATE",
                            "consequence_terms": ["missense_variant"],
                            "feature": {
                                "gene": {"gene_symbol": "APOE"},
                                "hgvsc": "ENST00000252486.9:c.388T>C",
                                "protein": {"hgvsp": "ENSP00000252486.3:p.Cys130Arg"},
                            },
                        },
                        "allele_frequency": {"ALFA": {"GnomAD_genomes": 0.1425}},
                    }
                ],
            }
        if "/associations" in url or "/data?" in url:
            return {
                "request": {"request_id": "req-assoc"},
                "pagination": {"total_records": 1},
                "data": [
                    {
                        "variant": "19:44908684:T:C",
                        "test_allele": "C",
                        "pvalue": "1.2e-180",
                        "neg_log10_pvalue": 179.92,
                        "effect_direction": "+",
                        "track": "NG00075_STAGE1_OA",
                        "traits": {"disease": [{"term": "Alzheimer's disease"}]},
                    }
                ],
            }
        if "/query/variants" in url:
            raise RuntimeError("HTTP 500: NotImplementedType")
        if "/service/feature" in url:
            return {"chr": "chr19", "start": 44905000, "end": 44909000}
        if "/record/region/" in url and "/variants" in url:
            return {
                "request": {"request_id": "req-reg"},
                "pagination": {"page": 1, "total_records": 1},
                "data": [
                    {
                        "ref_snp_id": "rs429358",
                        "id": "19:44908684:T:C",
                        "variant_class": "single-nucleotide variant",
                        "is_adsp_variant": True,
                        "most_severe_consequence": "missense variant",
                    }
                ],
            }
        if "FILER" in url:
            return [{"Identifier": "NG_FILER_1", "numOverlaps": 3}, {"Identifier": "NG_FILER_2", "numOverlaps": 2}]
        return {"request": {"request_id": "req-generic"}, "data": []}

    monkeypatch.setattr("ligase.niagads_api._http_get_json", _fake_http_get)

    g = execute_niagads_action(action="gene", target="APOE")
    assert g["ok"] is True
    assert "GVC Known AD Locus" in g["summary_markdown"]
    assert "P02649" in g["summary_markdown"]

    s = execute_niagads_action(action="gene_structure", target="APOE")
    assert s["ok"] is True
    assert "ENST00000252486" in s["summary_markdown"]

    v = execute_niagads_action(action="auto", target="rs429358")
    assert v["ok"] is True
    assert "ga4gh:VA.test123" in v["summary_markdown"]
    assert "NG00075_STAGE1_OA" in v["summary_markdown"]
    assert "Live FILER Functional Genomics Overlap" in v["summary_markdown"]

    # Test /query/variants HTTP 500 fallback to /service/feature + /record/region/.../variants
    sv = execute_niagads_action(action="search_variants", target="APOE")
    assert sv["ok"] is True
    assert "rs429358" in sv["summary_markdown"]

    md_tool = niagads_open_access_api(action="filer_overlap", target="chr2:127135200-127135300")
    assert "Overlapping Harmonized Regulatory Tracks" in md_tool

    # Verify ClawAgents tool registration and hybrid supplement
    extra_names = {t.name for t in gemma_extra_tools()}
    assert "niagads_open_access_api" in extra_names

    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "0")
    supp = fetch_live_niagads_supplement("Inspect rs429358 in APOE")
    assert "Live NIAGADS Open Access API v2.0" in supp

    monkeypatch.setenv("LIGASE_DISABLE_LIVE_NIAGADS", "1")
    card = query_niagads("BIN1 rs6733839")
    assert "94.6%" in card
    assert "Live NIAGADS Open Access API v2.0" not in card
