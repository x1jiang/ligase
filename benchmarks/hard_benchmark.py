"""
Hard Biomedical Reasoning & Multi-Step Benchmark Suite for Ligase.

Designed to break the ~90-95% ceiling of the standard 5-task suite by testing
graduate/clinical-level multi-hop reasoning, exact reading-frame frameshift
math, kinase resistance structural biology, protective AD epistasis, CRISPR
prime editing design, and Bayesian clinical carrier risk.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI
from tabulate import tabulate

load_dotenv(override=True)
os.environ["CLAW_LEARN"] = "0"

root_dir = Path(__file__).resolve().parent.parent
for p in [root_dir, root_dir / "biomni", root_dir / "clawagents_py" / "src"]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ligase.agent import create_agent

PUBLIC_PRIVATE_ENDPOINT = "http://xxx.xx.xx.xx/v1"
SPARK_BASE = (
    os.getenv("MUSE_SPARK_BACKEND")
    or os.getenv("GLIMMER_30B_BACKEND")
    or PUBLIC_PRIVATE_ENDPOINT
)
SPARK_MODEL = (
    os.getenv("MUSE_SPARK_MODEL")
    or os.getenv("LIGASE_MODEL")
    or "meta-models/Muse-Spark-Open-816B-A42B"
)
LUNA_MODEL = os.getenv("LUNA_MODEL", "gpt-5.6-luna")
MINI_MODEL = os.getenv("MINI_MODEL", "gpt-4o-mini")


def published_endpoint(url: str) -> str:
    """Never write raw private hostnames or IPv4 addresses into committed files."""
    if not url:
        return PUBLIC_PRIVATE_ENDPOINT
    if "api.openai.com" in url or "127.0.0.1" in url or "localhost" in url:
        return url
    return PUBLIC_PRIVATE_ENDPOINT


HARD_BENCHMARK_TASKS: List[Dict[str, Any]] = [
    {
        "id": "hard_cyp2c19_clopidogrel",
        "name": "Pharmacogenomics: CYP2C19*2/*3 & Clopidogrel Bioactivation",
        "prompt": (
            "A patient with acute coronary syndrome undergoing PCI is genotyped as "
            "CYP2C19*2/*3. Answer concisely: (1) What is the metabolizer phenotype "
            "and allele function status? (2) Why is clopidogrel ineffective in this "
            "genotype (explicitly state its prodrug status and hepatic conversion to "
            "its active thiol metabolite)? (3) Which two alternative P2Y12 receptor "
            "inhibitors are recommended by CPIC guidelines?"
        ),
        "rubric": [
            ["poor metabolizer"],
            ["loss-of-function", "non-functional", "no-function", "no function", "null"],
            ["prodrug"],
            ["active metabolite", "active thiol", "thiol metabolite"],
            ["prasugrel"],
            ["ticagrelor"],
        ],
    },
    {
        "id": "hard_bcr_abl_t315i",
        "name": "Structural Oncology: BCR-ABL1 T315I Gatekeeper & STAMP Inhibition",
        "prompt": (
            "In chronic myeloid leukemia (CML), the BCR-ABL1 T315I 'gatekeeper' "
            "mutation causes resistance to imatinib, dasatinib, nilotinib, and "
            "bosutinib. Answer concisely: (1) Which non-covalent bond with the "
            "hydroxyl group of Thr315 is lost, and what steric effect does Ile315 "
            "introduce in the ATP-binding pocket? (2) Name both the third-generation "
            "ATP-competitive TKI and the allosteric STAMP inhibitor (plus the exact "
            "allosteric pocket it binds) that overcome T315I."
        ),
        "rubric": [
            ["hydrogen bond", "h-bond"],
            ["steric", "clash", "hindrance"],
            ["atp"],
            ["ponatinib"],
            ["asciminib"],
            ["myristoyl"],
        ],
    },
    {
        "id": "hard_ad_christchurch_reelin",
        "name": "AD Protective Genetics: APOE3 Christchurch & RELN-COLBOS Epistasis",
        "prompt": (
            "Two rare autosomal-dominant Alzheimer's disease (PSEN1 E280A) resilience "
            "variants protect against cognitive decline and tau pathology: APOE3 "
            "Christchurch and RELN-COLBOS. Answer concisely: (1) State the exact "
            "amino-acid substitution for both APOE3 Christchurch and RELN-COLBOS. "
            "(2) Which cell-surface glycosaminoglycan / proteoglycan family shows "
            "markedly reduced binding to APOE3 Christchurch? (3) Which intracellular "
            "adaptor protein and downstream tau kinase (GSK3beta) link Reelin receptor "
            "(ApoER2/VLDLR) signaling to reduced tau phosphorylation?"
        ),
        "rubric": [
            ["r136s", "arg136ser"],
            ["h3447r", "his3447arg"],
            ["heparan sulfate", "hspg"],
            ["dab1", "disabled-1"],
            ["gsk3", "gsk-3"],
            ["tau"],
        ],
    },
    {
        "id": "hard_frameshift_orf",
        "name": "Coding Frameshift Math: Single-Nucleotide Deletion & Premature Stop",
        "prompt": (
            "Consider the 21-nucleotide wild-type coding DNA sequence "
            "5'-ATGGCCCTGCTGAACCGCTAA-3'. (1) State the wild-type 6-amino-acid "
            "peptide sequence (1-letter code) before the terminal TAA stop. "
            "(2) If a single-nucleotide deletion removes the 10th nucleotide "
            "(c.10delC, the 'C' at position 10), write the new 4th codon in both "
            "DNA and mRNA, state what it encodes, and give the resulting truncated "
            "peptide sequence (1-letter code)."
        ),
        "rubric": [
            ["mallnr"],
            ["tga"],
            ["uga"],
            ["stop", "premature", "termination", "nonsense"],
            ["codon 4", "4th codon", "fourth codon"],
            ["mal"],
        ],
    },
    {
        "id": "hard_crispr_prime_editing",
        "name": "CRISPR Engineering: HBB E6V Transversion & pegRNA Architecture",
        "prompt": (
            "The sickle-cell mutation in human HBB (Glu6Val, GAG->GTG on the coding "
            "strand) is an A:T to T:A point mutation. Answer concisely: (1) Is this "
            "a transition or a transversion, and why can neither Cytosine Base "
            "Editors (CBE) nor Adenine Base Editors (ABE) directly revert it? "
            "(2) Which CRISPR editing platform directly reverts T:A to A:T without "
            "double-strand breaks or donor DNA templates? (3) Name the two functional "
            "sequence elements at the 3' extension of the pegRNA and the enzyme "
            "fused to the Cas9 H840A nickase."
        ),
        "rubric": [
            ["transversion"],
            ["transition"],
            ["prime edit"],
            ["primer binding site", "pbs"],
            ["reverse transcriptase template", "rtt"],
            ["reverse transcriptase", "m-mlv"],
        ],
    },
    {
        "id": "hard_hardy_weinberg_bayes",
        "name": "Quantitative Clinical Genetics: HWE & Bayesian Posterior Carrier Risk",
        "prompt": (
            "An autosomal recessive metabolic disease has an incidence of 1 in 10,000 "
            "(q^2 = 0.0001) in a Hardy-Weinberg population. Answer concisely with "
            "exact numbers: (1) Give the mutant allele frequency q, normal allele "
            "frequency p, and exact heterozygote carrier frequency 2pq (as a decimal "
            "and percentage). (2) For an unaffected sibling of an affected child "
            "(born to two obligate carrier parents), what is the prior Mendelian "
            "probability (as a fraction) of being a carrier? (3) If that unaffected "
            "sibling tests negative on a genetic panel with 90% sensitivity and 100% "
            "specificity, what is the exact posterior probability (both as a "
            "simplified fraction and percentage to 2 decimal places) that the "
            "sibling is still a carrier?"
        ),
        "rubric": [
            ["0.01"],
            ["0.99"],
            ["0.0198", "1.98%", "1.98\\%"],
            ["2/3", "\\frac{2}{3}"],
            ["1/6", "\\frac{1}{6}"],
            ["16.67%", "16.67\\%", "16.7%", "0.1667"],
        ],
    },
    {
        "id": "hard_niagads_filer_microglia",
        "name": "NIAGADS V2F Fine-Mapping: FILER/MiGA BIN1 rs6733839 PIP & TREM2/PLCG2 Epistasis",
        "prompt": (
            "Using the NIAGADS functional genomics catalog (FILER Giggle-indexed "
            "tracks, MiGA Microglia Atlas NG00105, and IGAP/ADVP NG00075): (1) Across "
            "the 2q14.3 BIN1 credible set (rs6733839, rs744373, rs4663105, rs12989701), "
            "which causal sentinel SNP overlaps the microglia-specific enhancer bound "
            "by SPI1 (PU.1) and MEF2C, and how does its Posterior Inclusion Probability "
            "(PIP) shift from uniform GWAS priors to FILER-informed priors? (2) Give "
            "the exact amino-acid substitutions, Odds Ratios, and epistatic rescue OR "
            "for the microglial coding variants in TREM2 (rs75932628), PLCG2 "
            "(rs72824905), and ABI3 (rs616338)."
        ),
        "rubric": [
            ["filer"],
            ["giggle"],
            ["spi1", "pu.1"],
            ["rs6733839"],
            ["94.6%", "0.946"],
            ["1.97", "0.68", "p522r"],
        ],
    },
    {
        "id": "hard_niagads_adsp_ancestry_abca7",
        "name": "NIAGADS Multi-Ancestry ADSP: ABCA7 rs115550680 PAF (8.7x) & VCPA/FAVOR",
        "prompt": (
            "Across the NIAGADS Alzheimer's Disease Sequencing Project (ADSP Umbrella "
            "NG00067) and African American AD GWAS meta-analysis (NG00100 vs. European "
            "IGAP NG00075): (1) Name the GCAD harmonized variant-calling pipeline and "
            "functional annotation portal used for ADSP WGS releases. (2) For ABCA7 "
            "loss-of-function / 44-bp deletion variants (rs115550680), report the "
            "African vs. European Population Attributable Fraction (PAF_AFR vs PAF_EUR "
            "and fold-enrichment), the composite Odds Ratio for a dual APOE e4 + ABCA7 "
            "LoF carrier in African ancestry, and the two cellular mechanisms (lipid "
            "efflux and microglial A-beta phagocytosis) impaired."
        ),
        "rubric": [
            ["vcpa"],
            ["favor"],
            ["abca7"],
            ["6.09%", "8.7x", "8.7"],
            ["4.39"],
            ["phagocytosis", "phospholipid", "cholesterol"],
        ],
    },
    {
        "id": "hard_niagads_psp_tauopathy_sv",
        "name": "NIAGADS Cross-Disorder Tauopathy: PSP WGS (NG00169/NG00172) 56.8x vs. AD Shift",
        "prompt": (
            "In NIAGADS whole-genome sequencing studies of primary 4R-tauopathy "
            "Progressive Supranuclear Palsy (PSP; NG00169 and NG00172) and CSF ATN "
            "biomarkers (NG00049): (1) Quantify the APOE e2/e2 (rs7412) Odds Ratio "
            "reversal between Alzheimer's disease (OR_AD) and PSP (OR_PSP). (2) How "
            "does the chromosome 17q21.31 ~900 kb paracentric inversion (MAPT H1/H1 "
            "clade) alter MAPT exon 10 splicing (delta_PSI and 4R:3R tau isoform "
            "ratio)? (3) What is the composite Relative Odds Ratio (ROR) for PSP vs. "
            "AD in a dual APOE e2/e2 + MAPT H1/H1 carrier?"
        ),
        "rubric": [
            ["0.26", "2.84", "10.9"],
            ["h1", "17q21.31", "900 kb"],
            ["exon 10"],
            ["4r", "1.63", "0.24"],
            ["15.51"],
            ["56.8", "4.04"],
        ],
    },
]


def evaluate_rubric(text: str, rubric: List[List[str]]) -> tuple[float, List[bool]]:
    if not text:
        return 0.0, [False] * len(rubric)
    blob = text.lower()
    hits = [any(alias.lower() in blob for alias in group) for group in rubric]
    return sum(hits) / len(rubric), hits


def get_model_specs() -> List[Dict[str, Any]]:
    return [
        {
            "id": "muse_spark",
            "label": "Muse-Spark-816B-A42B",
            "model": SPARK_MODEL,
            "base_url": SPARK_BASE,
            "api_key": os.getenv("MUSE_SPARK_API_KEY", "not-needed"),
            "omit_temperature": False,
            "temperature": 0,
            "extra_body": {"chat_template_kwargs": {"reasoning_effort": "low"}},
            "reasoning_effort": "low",
        },
        {
            "id": "glimmer_30b",
            "label": "Muse-Glimmer-30B",
            "model": os.getenv("GLIMMER_30B_MODEL", "Muse-Glimmer-30B"),
            "base_url": os.getenv("GLIMMER_30B_BACKEND", PUBLIC_PRIVATE_ENDPOINT),
            "api_key": os.getenv("GLIMMER_API_KEY", "not-needed"),
            "omit_temperature": False,
            "temperature": 0,
            "extra_body": None,
            "reasoning_effort": None,
        },
        {
            "id": "gpt6_luna",
            "label": "gpt-6-luna",
            "model": "gpt-6-luna",
            "base_url": None,
            "api_key": os.environ.get("OPENAI_API_KEY"),
            "omit_temperature": True,
            "temperature": None,
            "extra_body": None,
            "reasoning_effort": None,
        },
        {
            "id": "luna",
            "label": "gpt-5.6-luna",
            "model": LUNA_MODEL,
            "base_url": None,
            "api_key": os.environ.get("OPENAI_API_KEY"),
            "omit_temperature": True,
            "temperature": None,
            "extra_body": None,
            "reasoning_effort": None,
        },
        {
            "id": "gpt4o_mini",
            "label": "gpt-4o-mini (small baseline)",
            "model": MINI_MODEL,
            "base_url": None,
            "api_key": os.environ.get("OPENAI_API_KEY"),
            "omit_temperature": False,
            "temperature": 0,
            "extra_body": None,
            "reasoning_effort": None,
        },
    ]


def raw_complete(spec: Dict[str, Any], prompt: str, *, max_tokens: int = 3072) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"api_key": spec["api_key"] or "not-needed"}
    if spec["base_url"]:
        kwargs["base_url"] = spec["base_url"]
    client = OpenAI(**kwargs)
    req: Dict[str, Any] = {
        "model": spec["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "Reasoning strength: 8.\n"
                    "You are a senior biomedical scientist. Answer every numbered "
                    "part of the user's question accurately and concisely."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": max_tokens,
        "timeout": 180.0,
    }
    if not spec["omit_temperature"]:
        req["temperature"] = spec["temperature"]
    if spec.get("reasoning_effort"):
        req["reasoning_effort"] = spec["reasoning_effort"]
    if spec.get("extra_body"):
        req["extra_body"] = spec["extra_body"]

    start = time.time()
    try:
        resp = client.chat.completions.create(**req)
        elapsed = time.time() - start
        msg = resp.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None) or ""
        scored = f"{content}\n{reasoning}".strip()
        comp_toks = getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0
        return {
            "success": True,
            "elapsed": elapsed,
            "content": content,
            "scored_text": scored,
            "completion_tokens": comp_toks,
            "tok_per_sec": comp_toks / elapsed if elapsed > 0 else 0.0,
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "elapsed": time.time() - start,
            "content": "",
            "scored_text": "",
            "completion_tokens": 0,
            "tok_per_sec": 0.0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_agent_task(spec: Dict[str, Any], prompt: str, *, timeout: float = 240.0) -> Dict[str, Any]:
    start = time.time()

    def _invoke() -> str:
        agent = create_agent(
            model=spec["model"],
            data_path=str(root_dir / "data"),
            modules=["database", "literature", "genomics", "pharmacology", "biochemistry"],
            is_ad_specialized=True,
            max_iterations=6,
            streaming=False,
            api_key=spec["api_key"],
            base_url=spec["base_url"],
        )
        return agent.go(prompt)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            output = pool.submit(_invoke).result(timeout=timeout)
        return {
            "success": True,
            "elapsed": time.time() - start,
            "output": str(output or ""),
            "error": None,
        }
    except FuturesTimeout:
        return {
            "success": False,
            "elapsed": time.time() - start,
            "output": "",
            "error": f"timeout after {timeout:.0f}s",
        }
    except Exception as exc:
        return {
            "success": False,
            "elapsed": time.time() - start,
            "output": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Hard Biomedical Benchmark for Ligase")
    parser.add_argument(
        "--models",
        default="muse_spark,luna,gpt4o_mini",
        help="Comma-separated model IDs: muse_spark,luna,gpt4o_mini",
    )
    parser.add_argument(
        "--phase",
        default="raw",
        choices=("raw", "agent", "all"),
        help="Which phase to run",
    )
    parser.add_argument(
        "--output-prefix",
        default="hard_biomedical_spark",
        help="Output filename prefix in benchmarks/results/",
    )
    args = parser.parse_args()
    wanted = {m.strip() for m in args.models.split(",") if m.strip()}
    specs = [s for s in get_model_specs() if s["id"] in wanted]
    if not specs:
        raise SystemExit(f"No models matched {wanted!r}")

    rows: List[List[Any]] = []
    results: Dict[str, Any] = {
        "meta": {
            "spark_endpoint": published_endpoint(SPARK_BASE),
            "spark_model": SPARK_MODEL,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "tasks": [],
    }

    for task in HARD_BENCHMARK_TASKS:
        print(f"\n▶ {task['name']}")
        t_entry: Dict[str, Any] = {"id": task["id"], "name": task["name"], "models": {}}
        for spec in specs:
            if args.phase in ("raw", "all"):
                res = raw_complete(spec, task["prompt"])
                score, hits = evaluate_rubric(res["scored_text"], task["rubric"])
                res["score"] = score
                res["hits"] = hits
                t_entry["models"][spec["id"]] = res
                print(
                    f"  [raw]   {spec['label']:<28} {res['elapsed']:6.2f}s  "
                    f"accuracy={score*100:5.1f}% ({sum(hits)}/{len(hits)})"
                )
                rows.append(
                    [
                        task["name"],
                        spec["label"],
                        "Raw",
                        f"{res['elapsed']:.2f}s",
                        f"{sum(hits)}/{len(hits)} ({score*100:.0f}%)",
                    ]
                )
            if args.phase in ("agent", "all"):
                ares = run_agent_task(spec, task["prompt"])
                score, hits = evaluate_rubric(ares["output"], task["rubric"])
                ares["score"] = score
                ares["hits"] = hits
                t_entry["models"][f"{spec['id']}_agent"] = ares
                print(
                    f"  [agent] {spec['label']:<28} {ares['elapsed']:6.2f}s  "
                    f"accuracy={score*100:5.1f}% ({sum(hits)}/{len(hits)})"
                )
                rows.append(
                    [
                        task["name"],
                        spec["label"],
                        "Ligase Agent",
                        f"{ares['elapsed']:.2f}s",
                        f"{sum(hits)}/{len(hits)} ({score*100:.0f}%)",
                    ]
                )
        results["tasks"].append(t_entry)

    table = tabulate(
        rows,
        headers=["Hard Task", "Model", "Mode", "Latency", "Strict Rubric Score"],
        tablefmt="github",
    )
    print("\n" + "=" * 88)
    print(table)

    out_dir = root_dir / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{args.output_prefix}_results.json"
    md_path = out_dir / f"{args.output_prefix}_summary.md"
    json_path.write_text(json.dumps(results, indent=2, default=str))
    md_path.write_text(
        f"# Hard Biomedical Reasoning Benchmark\n\n"
        f"- Endpoint: `{published_endpoint(SPARK_BASE)}`\n"
        f"- Spark Model: `{SPARK_MODEL}`\n\n"
        f"{table}\n"
    )
    print(f"\nSaved {json_path.name} and {md_path.name}")


if __name__ == "__main__":
    main()
