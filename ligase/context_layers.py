"""
Biomedical Context Layers for Ligase (ClawAgents Engine)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure biomni can be imported from parent or installed env
_pkg_root = Path(__file__).resolve().parent.parent
for _candidate in [_pkg_root / "biomni", _pkg_root.parent / "biomni"]:
    if _candidate.exists() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))


_DATALAKE_CATALOG_CACHE: dict[bool, str] = {}
_KNOWHOW_DOC_LIST_CACHE: dict[bool, str] = {}


class BiomniDataLakeLayer:
    """Injects Biomni curated datalake dataset index and lazy S3 paths."""

    name = "biomni_datalake"

    def __init__(self, data_path: str = "./data", commercial_mode: bool = False):
        self.data_path = data_path
        self.commercial_mode = commercial_mode

    def inject(self, run_context: Any) -> str | None:
        catalog_text = _DATALAKE_CATALOG_CACHE.get(self.commercial_mode)
        if catalog_text is None:
            try:
                if self.commercial_mode:
                    from biomni.env_desc_cm import data_lake_dict
                else:
                    from biomni.env_desc import data_lake_dict

                items = [f"- {k}: {desc}" for k, desc in list(data_lake_dict.items())[:25]]
                catalog_text = "\n".join(items)
            except Exception:
                catalog_text = (
                    "- BindingDB: Drug-target binding affinities\n"
                    "- STRING: Protein-protein interaction network\n"
                    "- GWAS_Catalog: Genome-wide association study variants\n"
                    "- ClinVar: Clinical genomic variant classifications\n"
                    "- AlphaFoldDB: Predicted 3D protein structures"
                )
            _DATALAKE_CATALOG_CACHE[self.commercial_mode] = catalog_text

        return (
            "### BIOMEDICAL DATA LAKE RESOURCES\n"
            f"Data Root Directory: {self.data_path}\n"
            "You have access to pre-indexed biological datasets (S3 lazy-loaded & local):\n"
            f"{catalog_text}\n"
            "(Use available domain tools or execute Python/Bash scripts to process these datasets)\n"
        )


class BiomniKnowHowLayer:
    """Injects standard biomedical operating procedures (SOPs) and protocol guides."""

    name = "biomni_knowhow"

    def __init__(self, commercial_mode: bool = False):
        self.commercial_mode = commercial_mode

    def inject(self, run_context: Any) -> str | None:
        doc_list = _KNOWHOW_DOC_LIST_CACHE.get(self.commercial_mode)
        if doc_list is None:
            try:
                from biomni.know_how import KnowHowLoader

                loader = KnowHowLoader()
                docs = loader.documents
                doc_titles = [d.get("title", d.get("id", "Protocol")) for d in docs[:10]]
                doc_list = "\n".join(f"- {title}" for title in doc_titles)
            except Exception:
                doc_list = (
                    "- CRISPR guide RNA (sgRNA) design and off-target screening\n"
                    "- Single-cell RNA-seq clustering and cell type annotation\n"
                    "- GWAS causal variant mapping and fine-mapping\n"
                    "- Molecular docking and pharmacokinetics screening"
                )
            _KNOWHOW_DOC_LIST_CACHE[self.commercial_mode] = doc_list

        return (
            "### BIOMEDICAL PROTOCOL & KNOW-HOW GUIDELINES\n"
            "Available Standard Operating Protocols:\n"
            f"{doc_list}\n"
        )


def warmup_context_layers() -> None:
    """Pre-populate DataLake and KnowHow caches so the first agent run skips disk I/O."""
    BiomniDataLakeLayer().inject(None)
    BiomniKnowHowLayer().inject(None)


class BiomniADLayer:
    """Injects Alzheimer's Disease (AD) data priorities and NIAGADS/ADRD catalogs."""

    name = "biomni_ad_catalog"

    def __init__(self, ad_data_path: Optional[str] = None):
        self.ad_data_path = ad_data_path or "./data/biomniAD"

    def inject(self, run_context: Any) -> str | None:
        return (
            "### ALZHEIMER'S DISEASE (AD) & NIAGADS DATA PRIORITY POLICY\n"
            "When answering AD, tauopathy, or neurodegeneration genomics tasks:\n"
            "1. NIAGADS LIVE OPEN ACCESS API + CATALOG FIRST: Use `niagads_open_access_api` (live NIAGADS Open Access API v2.0 at `https://api.niagads.org/api` + live FILER hg38 overlap) for real-time GRCh38 gene records, GVC TopGenes flags, transcript/exon structures, ADSP Release 5 SNVs/INDELs, GA4GH VRS digests, live GWAS/WGS association p-values, `<100 kb` genomic regions, track locus slices, and semantic track search; and/or call `query_niagads` (never use `ls`, `glob`, or `grep` to search directories) for curated quantitative multi-cohort panels:\n"
            "   - NIAGADS DSS & ADSP Umbrella (`NG00067` R4 36k WGS called with GCAD `VCPA` pipeline Leung et al. 2019 & `FAVOR` functional annotation) + ADSP R5 SNVs/INDELs via Open Access API v2.0.\n"
            "   - NIAGADS `FILER` (Kuksa et al. 2022 Nucleic Acids Research) & `MiGA` (`NG00105`): >58,000 Giggle-indexed functional genomics tracks showing non-coding AD GWAS loci (`BIN1`, `PICALM`, `MS4A6A`, `CD33`) colocalize with microglia enhancers bound by `SPI1` (`PU.1`).\n"
            "   - NIAGADS `ADVP` (Kuksa et al. 2022) & IGAP (`NG00075` Kunkle et al. 2019): curated coding variants `TREM2 R47H` (loss-of-function risk), `PLCG2 P522R` (protective hypermorphic gain-of-function), `ABI3 S209F` (risk), and resilience alleles `APOE3 Christchurch` (`R136S`/`Arg136Ser`, reduced HSPG binding) & `RELN-COLBOS` (`H3447R`/`His3447Arg`, Dab1 -> GSK3beta tau suppression).\n"
            "   - Multi-Ancestry AD (`NG00100` Kunkle et al. 2021): `ABCA7` loss-of-function/deletion risk in African American cohorts impairing phospholipid/cholesterol efflux and microglial A-beta phagocytosis.\n"
            "   - Primary 4R-Tauopathy PSP WGS (`NG00169` Farrell et al. 2024; `NG00172` Wang et al. 2024): `APOE` e2 risk reversal (protective in AD, risk-increasing in PSP) and `17q21.31` `MAPT` `H1/H2` ~900 kb inversion (`H1` risk clade, `exon 10` `4R` tau splicing).\n"
            "2. Ground truth integrity: Never fabricate genomic variants, dataset accessions, or clinical phenotypes.\n"
        )
