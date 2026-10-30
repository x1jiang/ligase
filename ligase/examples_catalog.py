"""Lightweight ready-made study catalog shared by the CLI and WebApp without importing Rich/Pygments."""

from __future__ import annotations

from typing import Any, Dict

EXAMPLES: Dict[str, Dict[str, Any]] = {
    "apoe4": {
        "title": "Alzheimer's genetics: APOE4 via UniProt + Ensembl",
        "question": (
            "Look up APOE in UniProt. Which chromosome is APOE on, which amino-acid residues "
            "distinguish the APOE4 isoform from APOE3 and APOE2, and how does APOE4 impair "
            "amyloid-beta clearance?"
        ),
        "ad": True,
        "max_iterations": 6,
    },
    "imatinib": {
        "title": "Drug lookup: Imatinib formula, weight and target via PubChem",
        "question": (
            "Look up the oncology drug Imatinib in PubChem: give its exact molecular formula, "
            "molecular weight, and primary target kinase."
        ),
        "ad": False,
        "max_iterations": 4,
    },
    "dna": {
        "title": "Sandboxed code: transcribe and translate a DNA sequence",
        "question": (
            "Write and execute a Python script to verify: (1) transcribe DNA sequence "
            "'ATGGGCAAGTAA' to mRNA, (2) translate it to amino acids, and (3) output the "
            "resulting peptide sequence."
        ),
        "ad": False,
        "max_iterations": 6,
    },
    "niagads": {
        "title": "NIAGADS Variant-to-Function (FILER + MiGA NG00105): BIN1 rs6733839 Bayesian PIP fine-mapping & TREM2/PLCG2 epistasis",
        "question": (
            "Query the NIAGADS catalog to perform a quantitative Variant-to-Function (V2F) and microglial "
            "epistasis analysis: (1) Across the 2q14.3 BIN1 credible set (rs6733839, rs744373, rs4663105, "
            "rs12989701), how does integrating NIAGADS FILER (Giggle-indexed SPI1/PU.1 + MEF2C microglia "
            "enhancer peaks) and MiGA (NG00105) microglia eQTLs shift the Posterior Inclusion Probability "
            "(PIP) of causal sentinel SNP rs6733839 compared to uniform GWAS priors? "
            "(2) In NIAGADS IGAP/ADSP rare-variant data (NG00075 / ADVP), report the exact rsIDs, MAFs, and "
            "Odds Ratios for TREM2 R47H, PLCG2 P522R, and ABI3 S209F, and quantify how protective hypermorphic "
            "PLCG2 P522R rescues TREM2 R47H epistatic risk."
        ),
        "ad": True,
        "max_iterations": 6,
    },
    "adsp": {
        "title": "NIAGADS Multi-Ancestry ADSP (NG00067/NG00100): ABCA7 rs115550680 PAF enrichment & APOE e4 stratification",
        "question": (
            "Query NIAGADS ADSP Umbrella (NG00067, VCPA/FAVOR) and African American AD GWAS (NG00100 vs. "
            "European IGAP NG00075) to quantify ancestry-stratified genetic risk: "
            "(1) Compare carrier frequencies, Odds Ratios, and Population Attributable Fractions (PAF) of "
            "ABCA7 loss-of-function / 44-bp deletion variants (rs115550680) between African and European "
            "ancestry cohorts, and explain the lipid efflux and microglial A-beta phagocytic mechanisms. "
            "(2) Contrast APOE e4 (rs429358) effect-size attenuation on an African local ancestry background "
            "against European ancestry, and compute the composite Odds Ratio for a dual APOE e4 + ABCA7 LoF carrier."
        ),
        "ad": True,
        "max_iterations": 6,
    },
    "psp": {
        "title": "NIAGADS Cross-Disorder Tauopathy (NG00169/NG00172 + NG00049): APOE e2/e2 + MAPT H1/H1 56.8x PSP vs. AD shift",
        "question": (
            "Query NIAGADS datasets NG00169 and NG00172 (Progressive Supranuclear Palsy WGS SNVs and structural "
            "variants) and NG00049 (CSF Abeta42/tau endophenotypes): "
            "(1) Quantify the single-locus Odds Ratio reversal of APOE e2/e2 (rs7412) between Alzheimer's "
            "disease (AD) and primary 4R-tauopathy PSP. "
            "(2) How does the chromosome 17q21.31 ~900 kb paracentric inversion (MAPT H1/H1 clade) alter "
            "MAPT exon 10 inclusion (delta_PSI and 4R:3R tau ratio), and what is the composite Relative Odds "
            "Ratio (ROR) and log-likelihood shift (delta_LLR) for PSP vs. AD in an APOE e2/e2 + MAPT H1/H1 carrier?"
        ),
        "ad": True,
        "max_iterations": 6,
    },
    "niagads_live": {
        "title": "NIAGADS Open Access API v2.0 Live: ADSP R5 SNVs/VRS, GVC TopGenes & Multi-Ancestry GWAS",
        "question": (
            "Use `niagads_open_access_api` to query the live NIAGADS Open Access API v2.0 (`api.niagads.org`): "
            "(1) Retrieve the live GRCh38 gene record and GVC TopGenes status for `TREM2` and its exon structure, "
            "(2) Inspect the live ADSP Release 5 variant record, GA4GH VRS allele digest, population frequencies, "
            "GWAS track associations, and FILER hg38 regulatory track overlap for `rs6733839` and `rs429358`, and "
            "(3) Summarize the cross-cohort evidence in a structured Markdown table."
        ),
        "ad": True,
        "max_iterations": 8,
    },
}
