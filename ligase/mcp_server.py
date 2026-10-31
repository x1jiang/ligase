"""First-Mover Open-Source NIAGADS Model Context Protocol (MCP) Server (`ligase-mcp`).

Implements the JSON-RPC 2.0 MCP `stdio` transport (protocol version `2024-11-05`) with zero
external runtime dependencies beyond Ligase itself, exposing NIAGADS Open Access v2.0,
FILER hg38 regulatory tracks, FunGen-xQTL Bayesian colocalization, Two-Sample Mendelian
Randomization, Cross-Ancestry PRS, ADSP Release 5 Rare Regulatory Scoring, Batch VCF V2F,
and AD Translational Trials to any MCP-compatible IDE or desktop research client.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from ligase import __version__
from ligase.gemma_tools import query_niagads
from ligase.niagads_api import execute_niagads_action
from ligase.niagads_v2f_engine import (
    get_niagads_literature_catalog,
    niagads_adsp_r5_power_dar,
    niagads_colocboost_mesusie,
    niagads_finemap_coloc,
    niagads_mendelian_randomization_prs,
    niagads_rare_regulatory_score,
    niagads_resilience_xwas_seaad,
    niagads_translational_trials,
    niagads_vcf_batch_v2f,
    run_niagads_v2f_benchmark,
)

MCP_PROTOCOL_VERSION = "2024-11-05"

NIAGADS_MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "niagads_locus_dossier",
        "description": (
            "Execute a 4-way parallel NIAGADS Open Access v2.0 & FILER hg38 V2F locus dossier "
            "(canonical GVC/GA4GH VRS record, GWAS -log10(p) associations, GRCh38 exons/variants, "
            "and harmonized FILER regulatory track overlaps)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Gene symbol (e.g. BIN1, APOE, TREM2), rsID (rs6733839), or GRCh38 region.",
                },
                "flank": {
                    "type": "integer",
                    "description": "Optional flanking window in base pairs (default 10000).",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_finemap_coloc",
        "description": (
            "Compute Wakefield Approximate Bayes Factor (ABF) fine-mapping, FILER enhancer-weighted "
            "95% credible sets, and Bayesian colocalization (PP.H0-PP.H4) against NIAGADS FunGen-xQTL "
            "(NG00105 MiGA microglia eQTL & NG00102 CSF pQTL)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "ADRD gene symbol or variant (e.g. BIN1, APOE, TREM2, ABCA7, PLCG2, MAPT).",
                },
                "flank": {
                    "type": "integer",
                    "description": "Genomic window around target in bp (default 50000).",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_mendelian_randomization_prs",
        "description": (
            "Run Two-Sample Mendelian Randomization (IVW, MR-Egger pleiotropy intercept, Weighted Median) "
            "and 4-ancestry NIAGADS Polygenic Risk Score calibration (IGAP NG00075 EUR, AA-AD NG00100 AFR, "
            "ADSP NG00067 AMR, NG00097 EAS + PGS Catalog)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Exposure panel: microglia_endolysosomal, ldl_cholesterol, or csf_strem2.",
                },
                "ancestry": {
                    "type": "string",
                    "enum": ["ALL", "EUR", "AFR", "AMR", "EAS"],
                    "description": "Target ancestry group for PRS calibration.",
                },
                "genotypes": {
                    "type": "string",
                    "description": "Optional carrier dosages, e.g. 'rs429358=1,rs6733839=2,rs115550680=1'.",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_rare_regulatory_score",
        "description": (
            "Score rare or non-coding ADSP Release 5 variants (0-100) across 5 NIAGADS/FILER modalities: "
            "microglia ATAC chromatin, SPI1/MEF2C enhancer binding, FunGen eQTL/caQTL, splice delta-PSI, "
            "and GA4GH VRS coding constraint."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Variant rsID, positional ID (chr:pos:ref:alt), or gene symbol.",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_vcf_batch_v2f",
        "description": (
            "Annotate and prioritize a batch of VCF lines, rsIDs, or GRCh38 coordinates through "
            "NIAGADS Open Access v2.0 batch variant lookup + FILER regulatory weighting, returning Markdown + CSV."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vcf_text": {
                    "type": "string",
                    "description": "Newline-separated VCF rows, rsIDs, or chr:pos:ref:alt strings (up to 50).",
                }
            },
            "required": ["vcf_text"],
        },
    },
    {
        "name": "niagads_translational_trials",
        "description": (
            "Map NIAGADS GVC AD/ADRD loci to therapeutic compounds, APOE e4 ARIA-E/ARIA-H boxed-warning "
            "pharmacogenomic guidance, and live ClinicalTrials.gov API v2 studies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target ADRD gene symbol (e.g. APOE, TREM2, BIN1, ABCA7, PLCG2, MAPT).",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_colocboost_mesusie",
        "description": (
            "Run TAD-window (±500 kb cis-TAD) 6-modality FunGen-xQTL ColocBoost (eQTL, sQTL, pQTL, mQTL, haQTL, "
            "snuc-eQTL+ieQTL; Li et al. Nat Genet 2025) and 4-ancestry ADSP emeraLD MESuSiE credible sets "
            "(NHW, AA, HIS, ASN; Gao et al. Nat Genet 2024) with grounded paper credits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "ADRD gene symbol or variant (e.g. BIN1, EGFR, TSPAN14, ABCA7, APOE, TREM2, PLCG2, MAPT).",
                },
                "ancestry": {
                    "type": "string",
                    "enum": ["ALL", "NHW", "AA", "HIS", "ASN"],
                    "description": "Optional ADSP emeraLD ancestry panel focus.",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_resilience_xwas_seaad",
        "description": (
            "Evaluate APOEe4/e4 blood-brain barrier resilience modifiers (FN1 rs140926439 OR=0.29, Bhattarai et al. "
            "Acta Neuropathol 2024), sex-aware chrX XWAS & XCI escape loci (SLC9A7, MID1; Belloy et al. JAMA Neurol 2024), "
            "and SEA-AD continuous pseudoprogression (CPS 0.0-1.0; Gabitto et al. Nat Neurosci 2024) spatial staging."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Gene or locus focus (e.g. APOE, FN1, SLC9A7, MID1, BIN1, TREM2).",
                },
                "sex": {
                    "type": "string",
                    "enum": ["female", "male", "all"],
                    "description": "Sex context for chrX XWAS / XCI escape interpretation.",
                },
                "apoe_genotype": {
                    "type": "string",
                    "description": "APOE background genotype (e.g. e4/e4, e3/e4, e3/e3).",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "niagads_literature_credits",
        "description": (
            "Query the 16-paper NIAGADS/ADSP scholarly attribution registry (ColocBoost, FILER, MESuSiE, ADSP R4/STAAR, "
            "NIAGADS GenomicsDB Browser, ADSP-PHC, AlphaGenome, EADB, FN1 resilience, chrX XWAS, PRS-CSx, SEA-AD, "
            "SpatialTargetAgent, HeurekaBench, Rubric Rewards) with DOIs, Europe PMC / arXiv URLs, and NIAGADS dataset anchors."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Optional filter keyword (e.g. colocboost, fn1, xwas, sea-ad, phc, browser) or empty for all 16.",
                }
            },
        },
    },
    {
        "name": "niagads_adsp_r5_power_dar",
        "description": (
            "Compute ancestry-stratified statistical power across ADSP Release 5 (58,507 WGS / 57,302 subjects: "
            "NHW 29,107, HIS 15,390, AA 6,975, ASN 5,523) and ADSP-PHC (U24AG074855) harmonized endophenotype domains, "
            "select NG* NIAGADS DSS datasets, and draft a ready-to-submit NIAGADS DARM Data Access Request (DAR) + "
            "NIH R01/R21 Specific Aims & DMS packet."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target ADRD gene symbol or variant (e.g. ABCA7, SORL1, TREM2, BIN1, APOE, FN1, rs115550680).",
                },
                "test_mode": {
                    "type": "string",
                    "enum": ["staar_o_burden", "single_variant", "endophenotype_qtl"],
                    "description": "Statistical association design.",
                },
                "phenotype_domain": {
                    "type": "string",
                    "enum": [
                        "case_control_ad",
                        "cognition_longitudinal",
                        "neuroimaging_mri_pet",
                        "fluid_biomarkers_atn",
                        "neuropathology_autopsy",
                    ],
                    "description": "ADSP-PHC harmonized phenotype domain inside NG00067.",
                },
                "effect_size": {
                    "type": "number",
                    "description": "Expected Odds Ratio (for binary traits) or SD effect beta (for quantitative traits); 0 uses locus default.",
                },
                "custom_maf": {
                    "type": "number",
                    "description": "Optional allele or cumulative burden frequency override (0 uses live NIAGADS / ADSP R5 ancestry frequencies).",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "query_niagads_catalog",
        "description": (
            "Search the curated 24-cohort NIAGADS DSS catalog (NG00049-NG00182), VCPA/FAVOR harmonization "
            "pipelines, multi-ancestry PAF benchmarks, and PSP vs. AD cross-disorder genetics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Dataset accession (e.g. NG00105, NG00100, NG00172), gene, or phenotype.",
                }
            },
            "required": ["query"],
        },
    },
]

NIAGADS_MCP_RESOURCES: List[Dict[str, Any]] = [
    {
        "uri": "niagads://benchmark/ad-v2f-bench",
        "name": "NIAGADS AD-HeurekaBench v0.7 Gold-Standard Locus & Multi-Step Workflow Suite",
        "description": "Deterministic causal-variant PIP, FunGen-xQTL colocalization (6 GVC loci), and 5 multi-step translational workflows.",
        "mimeType": "application/json",
    },
    {
        "uri": "niagads://literature/credits",
        "name": "NIAGADS v0.7 Grounded Literature & Methodological Credits (14 Papers)",
        "description": "Structured scholarly citations, DOIs, Europe PMC/arXiv URLs, and NIAGADS/ADSP dataset anchors for all 14 integrated papers.",
        "mimeType": "application/json",
    },
    {
        "uri": "niagads://dar/adsp-r5-guide",
        "name": "NIAGADS ADSP Release 5 (58,507 WGS) Power & DARM Data Access Request Packet",
        "description": "Ancestry-stratified ADSP R5 power table, NG00067/ADSP-PHC dataset selector, DARM compliance checklist, and NIH R01/R21 Specific Aims template.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "niagads://citation/u24ag041689",
        "name": "NIH/NIA U24AG041689 NIAGADS Attribution & BibTeX",
        "description": "Official NIAGADS Data Use & Cooperative Agreement U24AG041689 citation block.",
        "mimeType": "text/markdown",
    },
]

_CITATION_MD = """# NIAGADS Data Provenance & Attribution

Data retrieved and synthesized via **NIAGADS** (National Institute on Aging Genetics of Alzheimer's Disease Data Storage Site), funded by the National Institute on Aging under NIH Cooperative Agreement **U24AG041689**.

- **NIAGADS Open Access API v2.0**: https://api.niagads.org/open-access
- **NIAGADS Alzheimer's GenomicsDB**: https://www.niagads.org/genomics
- **FILER Functional Genomics**: https://tf.lisanwanglab.org/FILER/
- **ADSP GVC TopGenes**: https://topgenes.niagads.org/
"""


def _dispatch_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    args = arguments or {}
    if name == "niagads_locus_dossier":
        res = execute_niagads_action(
            action="locus_dossier",
            target=str(args.get("target") or "BIN1"),
            flank=int(args.get("flank") or 10_000),
        )
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_finemap_coloc":
        res = niagads_finemap_coloc(
            target=str(args.get("target") or "BIN1"),
            flank=int(args.get("flank") or 50_000),
        )
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_mendelian_randomization_prs":
        res = niagads_mendelian_randomization_prs(
            target=str(args.get("target") or "microglia_endolysosomal"),
            ancestry=str(args.get("ancestry") or "ALL"),
            genotypes=str(args.get("genotypes") or ""),
        )
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_rare_regulatory_score":
        res = niagads_rare_regulatory_score(target=str(args.get("target") or "rs6733839"))
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_vcf_batch_v2f":
        res = niagads_vcf_batch_v2f(vcf_text=str(args.get("vcf_text") or ""))
        txt = (res.get("summary_markdown") or "") + "\n\n```csv\n" + (res.get("csv") or "").strip() + "\n```"
        return {"text": txt, "isError": not bool(res.get("ok", True))}
    if name == "niagads_translational_trials":
        res = niagads_translational_trials(target=str(args.get("target") or "APOE"))
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_colocboost_mesusie":
        res = niagads_colocboost_mesusie(
            target=str(args.get("target") or "BIN1"),
            ancestry=str(args.get("ancestry") or "ALL"),
        )
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_resilience_xwas_seaad":
        res = niagads_resilience_xwas_seaad(
            target=str(args.get("target") or "APOE"),
            sex=str(args.get("sex") or "female"),
            apoe_genotype=str(args.get("apoe_genotype") or "e4/e4"),
        )
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_literature_credits":
        res = get_niagads_literature_catalog(topic=str(args.get("topic") or ""))
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "niagads_adsp_r5_power_dar":
        res = niagads_adsp_r5_power_dar(
            target=str(args.get("target") or "ABCA7"),
            test_mode=str(args.get("test_mode") or "staar_o_burden"),
            phenotype_domain=str(args.get("phenotype_domain") or "case_control_ad"),
            effect_size=float(args.get("effect_size") or 0.0),
            custom_maf=float(args.get("custom_maf") or 0.0),
        )
        return {"text": res.get("summary_markdown") or "", "isError": not bool(res.get("ok", True))}
    if name == "query_niagads_catalog":
        out = query_niagads(str(args.get("query") or "NIAGADS"))
        return {"text": out, "isError": out.startswith("error:")}
    raise ValueError(f"Unknown NIAGADS MCP tool: {name}")


def handle_mcp_request(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single JSON-RPC 2.0 MCP message and return a response dict (or None for notifications)."""
    method = str(msg.get("method") or "")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method.startswith("notifications/") or msg_id is None:
        return None

    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                    },
                    "serverInfo": {
                        "name": "ligase-niagads-mcp",
                        "version": __version__,
                    },
                },
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": NIAGADS_MCP_TOOLS}}
        if method == "tools/call":
            t_name = str(params.get("name") or "")
            t_args = params.get("arguments") or {}
            dispatched = _dispatch_tool(t_name, t_args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": dispatched["text"]}],
                    "isError": dispatched["isError"],
                },
            }
        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": NIAGADS_MCP_RESOURCES}}
        if method == "resources/read":
            uri = str(params.get("uri") or "")
            if uri == "niagads://benchmark/ad-v2f-bench":
                bench = run_niagads_v2f_benchmark()
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(bench, indent=2),
                            }
                        ]
                    },
                }
            if uri == "niagads://literature/credits":
                cat = get_niagads_literature_catalog()
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(cat, indent=2),
                            }
                        ]
                    },
                }
            if uri == "niagads://dar/adsp-r5-guide":
                dar_res = niagads_adsp_r5_power_dar(target="ABCA7")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/markdown",
                                "text": dar_res["summary_markdown"],
                            }
                        ]
                    },
                }
            if uri == "niagads://citation/u24ag041689":
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/markdown",
                                "text": _CITATION_MD,
                            }
                        ]
                    },
                }
            raise ValueError(f"Unknown resource URI: {uri}")

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": str(exc)},
        }


def _serve_stdio() -> int:
    """Serve JSON-RPC 2.0 over stdin/stdout (supports both newline JSON and Content-Length framing)."""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        use_framing = False
        if stripped.lower().startswith(b"content-length:"):
            use_framing = True
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr = stdin.readline()
                if not hdr or hdr in (b"\r\n", b"\n"):
                    break
            body = stdin.read(length)
            raw_str = body.decode("utf-8", errors="replace")
        else:
            raw_str = stripped.decode("utf-8", errors="replace")

        try:
            msg = json.loads(raw_str)
        except json.JSONDecodeError:
            continue

        resp = handle_mcp_request(msg)
        if resp is None:
            continue
        encoded = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        if use_framing:
            stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii") + encoded)
        else:
            stdout.write(encoded + b"\n")
        stdout.flush()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ligase-mcp",
        description="NIAGADS Open Access v2.0 & Statistical V2F Model Context Protocol (MCP) stdio server.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a local JSON-RPC 2.0 self-test across initialize, tools/list, and AD-V2F-Bench.",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        init_res = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        tools_res = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        bench_res = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/read",
                "params": {"uri": "niagads://benchmark/ad-v2f-bench"},
            }
        )
        summary = {
            "ok": True,
            "server": init_res["result"]["serverInfo"],
            "tools_count": len(tools_res["result"]["tools"]),
            "benchmark": json.loads(bench_res["result"]["contents"][0]["text"]),
        }
        print(json.dumps(summary, indent=2))
        return 0
    return _serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
