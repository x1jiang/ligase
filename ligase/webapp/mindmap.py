"""Authoritative component mindmap specification for the Ligase Web Portal."""

from __future__ import annotations

from typing import Any, Dict, List

from ligase import __version__ as VERSION


def build_capabilities_mindmap(model_name: str = "gpt-6-luna") -> Dict[str, Any]:
    """Return the complete hierarchical Mindmap of components supported by Ligase."""
    branches: List[Dict[str, Any]] = [
        {
            "id": "niagads_api",
            "title": "NIAGADS Open Access API v2.0",
            "short_title": "NIAGADS Open Access API",
            "badge": "Live REST · 19 Paths",
            "accent": "#4f46e5",
            "icon": "🌐",
            "summary": (
                "Direct live integration with https://api.niagads.org/open-access (OpenAPI v2.0) "
                "for real-time GRCh38 genes, ADSP Release 5 SNVs/INDELs, GA4GH VRS digests, GWAS "
                "associations, <100 kb genomic intervals, track locus slices, and semantic search."
            ),
            "components": [
                {
                    "id": "mm_oa_genes",
                    "title": "Gene Records & GVC TopGenes",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Fetches canonical GRCh38 gene coordinates, cytogenetic bands, Ensembl/HGNC/"
                        "UniProt/RefSeq cross-references, ADSP Gene Verification Committee (GVC) "
                        "`associated_with_known_ad_locus` flags, and KEGG/Reactome/GO pathways."
                    ),
                    "backing": ["GET /api/record/gene/{gene}", "GET /api/record/gene/", "niagads_open_access_api(action='gene')"],
                    "sample_prompt": (
                        "Use `niagads_open_access_api` (action='gene') to inspect `APOE`, `BIN1`, and `ABCA7` on "
                        "GRCh38, comparing their GVC Known AD Locus flags, cytogenetic bands, UniProt IDs, and top KEGG/Reactome pathways."
                    ),
                    "live_api_preset": {"action": "gene", "target": "APOE", "loc": ""},
                },
                {
                    "id": "mm_oa_gene_assoc",
                    "title": "Gene GWAS Signals & Exon Structure",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Retrieves gene-level AD/ADRD GWAS summary-statistic associations (with optional flanking "
                        "windows up to 1 Mb) alongside full GRCh38 `ENST` transcript and ranked `ENSE` exon coordinates."
                    ),
                    "backing": [
                        "GET /api/record/gene/{gene}/associations",
                        "GET /api/record/gene/{gene}/structure",
                    ],
                    "sample_prompt": (
                        "Use `niagads_open_access_api` to retrieve the GRCh38 transcript and exon structure of `TREM2` "
                        "and summarize its genome-wide significant AD associations."
                    ),
                    "live_api_preset": {"action": "gene_structure", "target": "TREM2", "loc": ""},
                },
                {
                    "id": "mm_oa_variants",
                    "title": "ADSP R5 SNVs/INDELs & GA4GH VRS",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Queries single-nucleotide variants and short INDELs from ADSP Release 5 WGS, returning "
                        "GA4GH VRS allele digests (`ga4gh:VA.*`), MANE Select coding/protein consequences, and "
                        "ALFA / gnomAD / TOPMed / 1000G population allele frequencies."
                    ),
                    "backing": ["GET /api/record/variant/{variant}", "GET /api/record/variant/"],
                    "sample_prompt": (
                        "Query `niagads_open_access_api` (action='variant') for `rs429358` and `rs7412` to report their "
                        "ADSP R5 status, GA4GH VRS digests, HGVSc/HGVSp consequences on APOE, and gnomAD/TOPMed allele frequencies."
                    ),
                    "live_api_preset": {"action": "variant", "target": "rs429358", "loc": ""},
                },
                {
                    "id": "mm_oa_var_assoc",
                    "title": "Variant GWAS & WGS Associations",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Extracts live association p-values, `-log10(p)`, test alleles, effect directions, and "
                        "HANCESTRO/DOID population ontology annotations across NIAGADS open-access cohorts."
                    ),
                    "backing": ["GET /api/record/variant/{variant}/associations"],
                    "sample_prompt": (
                        "Use `niagads_open_access_api` (action='variant_associations') for `rs6733839` and rank all "
                        "open-access NIAGADS GWAS/WGS tracks by `-log10(p)` across European, African American, and Hispanic cohorts."
                    ),
                    "live_api_preset": {"action": "variant_associations", "target": "rs6733839", "loc": ""},
                },
                {
                    "id": "mm_oa_regions",
                    "title": "Genomic Region Queries (<100 kb)",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Scans any GRCh38 genomic window (<100,000 bp, auto-clamped when wider) for ordered "
                        "ADSP R5 SNVs/INDELs and multi-cohort ADRD association signals."
                    ),
                    "backing": [
                        "GET /api/record/region/{region}/associations",
                        "GET /api/record/region/{region}/variants",
                    ],
                    "sample_prompt": (
                        "Query `niagads_open_access_api` across `chr19:44908500-44909000` (APOE exon 4 locus) to summarize "
                        "total ADSP Release 5 SNVs/INDELs and top association p-values."
                    ),
                    "live_api_preset": {"action": "region_variants", "target": "chr19:44908500-44909000", "loc": ""},
                },
                {
                    "id": "mm_oa_tracks",
                    "title": "Track Metadata & Locus Data Slices",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Retrieves study design, sample provenance, and phenotype ontology metadata for NIAGADS "
                        "`NG*` tracks and slices live summary-statistic rows within any GRCh38 interval."
                    ),
                    "backing": [
                        "GET /api/record/track/{track}",
                        "GET /api/record/track/{track}/data?loc=...",
                    ],
                    "sample_prompt": (
                        "Use `niagads_open_access_api` (action='track_data') on track `NG00166_04BE648F_STD_OA` at "
                        "`chr2:127134000-127136000` and interpret the trans-ancestry BIN1 association signal."
                    ),
                    "live_api_preset": {
                        "action": "track_data",
                        "target": "NG00166_04BE648F_STD_OA",
                        "loc": "chr2:127134000-127136000",
                    },
                },
                {
                    "id": "mm_oa_search",
                    "title": "Semantic Search & Coordinate Resolver",
                    "badge": "Available Now · v2.0",
                    "status": "live",
                    "summary": (
                        "Full-text search across NIAGADS tracks, cohorts, biomarkers, and gene nomenclature plus "
                        "`/service/feature` GRCh38 coordinate resolution with configurable flanking windows."
                    ),
                    "backing": [
                        "GET /api/query",
                        "GET /api/query/tracks",
                        "GET /api/query/genes",
                        "GET /api/service/feature",
                    ],
                    "sample_prompt": (
                        "Search NIAGADS Open Access tracks (`niagads_open_access_api`, action='search_tracks') for "
                        "`African American` and `CSF` studies and list the returned `NG*` track IDs and designs."
                    ),
                    "live_api_preset": {"action": "search_tracks", "target": "African American", "loc": ""},
                },
            ],
        },
        {
            "id": "niagads_ecosystem",
            "title": "NIAGADS Ecosystem & ADRD Panels",
            "short_title": "NIAGADS ADRD Panels",
            "badge": "24 NG* Cohorts + FILER",
            "accent": "#0d9488",
            "icon": "🧬",
            "summary": (
                "Curated quantitative AD/ADRD reference panels bridging live Open Access API v2.0 data with "
                "FILER (>58k functional tracks), ADVP, MiGA microglia xQTLs, ADSP VCPA/FAVOR, and PSP WGS."
            ),
            "components": [
                {
                    "id": "mm_eco_filer",
                    "title": "FILER Functional Genomics (58k+ Tracks)",
                    "badge": "Live Overlap + V2F",
                    "status": "live",
                    "summary": (
                        "Queries live hg38 Giggle-indexed regulatory track overlaps at any variant or interval "
                        "across ENCODE, Roadmap, and brain/microglia ATAC-seq & ChIP-seq (`SPI1`/`PU.1`, `MEF2C`)."
                    ),
                    "backing": [
                        "FILER get_overlapping_tracks_by_coord.php",
                        "niagads_open_access_api(action='filer_overlap')",
                    ],
                    "sample_prompt": (
                        "Use `niagads_open_access_api` (action='filer_overlap') at `rs6733839` (`chr2:127135200-127135300`) "
                        "and combine with `query_niagads` to explain microglia enhancer colocalization at BIN1."
                    ),
                    "live_api_preset": {"action": "filer_overlap", "target": "chr2:127135200-127135300", "loc": ""},
                },
                {
                    "id": "mm_eco_dss",
                    "title": "NIAGADS DSS Catalog (NG00049–NG00182)",
                    "badge": "24 Indexed Studies",
                    "status": "curated",
                    "summary": (
                        "Structured metadata, sample files, and cohort summaries across 24 NIAGADS Data Sharing "
                        "Service accessions spanning IGAP, ADSP WGS/WES, CSF/plasma pQTLs, APOE4, and resilience."
                    ),
                    "backing": ["ligase/resources/niagads_catalog.json", "query_niagads"],
                    "sample_prompt": (
                        "Query `query_niagads` to map which NIAGADS `NG*` datasets cover CSF ATN biomarkers, "
                        "brain/plasma proteomics pQTLs, and multi-ancestry WGS."
                    ),
                },
                {
                    "id": "mm_eco_bin1",
                    "title": "BIN1 rs6733839 Bayesian PIP & MiGA (NG00105)",
                    "badge": "PIP 52.8% → 94.6%",
                    "status": "curated",
                    "summary": (
                        "Quantifies how integrating FILER microglia `SPI1/MEF2C` enhancer priors and MiGA (`NG00105`) "
                        "microglia eQTLs concentrates `BIN1 rs6733839` causal posterior probability from 52.8% to 94.6%."
                    ),
                    "backing": ["query_niagads (bin1_filer_v2f)", "NG00105 · NG00075"],
                    "sample_prompt": (
                        "Perform a quantitative V2F fine-mapping analysis across the 2q14.3 `BIN1` credible set "
                        "(`rs6733839`, `rs744373`, `rs4663105`, `rs12989701`) using NIAGADS FILER and MiGA (`NG00105`)."
                    ),
                },
                {
                    "id": "mm_eco_adsp_paf",
                    "title": "Multi-Ancestry ADSP & ABCA7 8.7× PAF",
                    "badge": "NG00067 · NG00100",
                    "status": "curated",
                    "summary": (
                        "Contrasts `ABCA7` LoF (`rs115550680`) Population Attributable Fraction in African (`6.09%`) "
                        "vs. European (`0.70%`) ancestry alongside `APOE ε4` local-ancestry attenuation (`VCPA`/`FAVOR`)."
                    ),
                    "backing": ["query_niagads (adsp_multi_ancestry_paf)", "NG00067 · NG00100 · NG00075"],
                    "sample_prompt": (
                        "Compare `ABCA7` (`rs115550680`) PAF enrichment and `APOE ε4` (`rs429358`) attenuation across "
                        "African (`NG00100`) and European (`NG00075`) cohorts in ADSP (`NG00067`)."
                    ),
                },
                {
                    "id": "mm_eco_psp",
                    "title": "4R-Tauopathy PSP WGS & 56.8× APOE ε2 Shift",
                    "badge": "NG00169 · NG00172",
                    "status": "curated",
                    "summary": (
                        "Models the `10.9×` single-locus `APOE ε2/ε2` (`rs7412`) reversal between AD and PSP, the "
                        "`17q21.31 MAPT H1/H1` ~900 kb inversion (`ΔΨ=+0.24` exon 10), and `56.8×` composite ROR."
                    ),
                    "backing": ["query_niagads (psp_vs_ad_differential)", "NG00169 · NG00172 · NG00049"],
                    "sample_prompt": (
                        "Quantify the `APOE ε2/ε2` (`rs7412`) risk reversal and `MAPT H1/H1` 17q21.31 inversion "
                        "composite Relative Odds Ratio between PSP (`NG00169`/`NG00172`) and AD (`NG00049`)."
                    ),
                },
                {
                    "id": "mm_eco_resilience",
                    "title": "Microglial Epistasis & Resilience Alleles",
                    "badge": "ADVP · NG00075",
                    "status": "curated",
                    "summary": (
                        "Covers `TREM2 R47H` × protective hypermorphic `PLCG2 P522R` epistasis, `ABI3 S209F`, "
                        "`APOE3 Christchurch` (`R136S`), and `RELN-COLBOS` (`H3447R`)."
                    ),
                    "backing": ["query_niagads", "ADVP · NG00075 · NG00127"],
                    "sample_prompt": (
                        "Explain the molecular epistasis between `TREM2 R47H` and `PLCG2 P522R` and compare "
                        "resilience mechanisms of `APOE3 Christchurch` (`R136S`) and `RELN-COLBOS` (`H3447R`)."
                    ),
                },
            ],
        },
        {
            "id": "engine",
            "title": "Agent Core & Reasoning Harnesses",
            "short_title": "Agent Core & Models",
            "badge": f"{model_name} + Local",
            "accent": "#7c3aed",
            "icon": "⚡",
            "summary": (
                "Dual-profile biomedical agent runtime pairing frontier cloud reasoning (`gpt-6-luna`) "
                "with ClawAgents streaming orchestration, Plan-then-Approve triage, and local 30B harnesses."
            ),
            "components": [
                {
                    "id": "mm_eng_luna",
                    "title": f"Frontier {model_name} Co-Scientist (AD1 / A1)",
                    "badge": "Cloud Run Default",
                    "status": "live",
                    "summary": (
                        "Supports specialized `AD1` (Alzheimer's & NIAGADS priority policy) and `A1` (General "
                        "Biomedical) profiles with multi-turn context retention and grounded tool verification."
                    ),
                    "backing": ["ligase/agent.py", "ligase/context_layers.py"],
                    "sample_prompt": (
                        "Compare how `APOE4` impairs astroglial/microglial lipidated Aβ clearance with how `TREM2` "
                        "and `ABCA7` regulate microglial phagocytic flux."
                    ),
                },
                {
                    "id": "mm_eng_planner",
                    "title": "Biomni-Style Intake Triage & Plan-Approve",
                    "badge": "Interactive Gate",
                    "status": "live",
                    "summary": (
                        "Classifies incoming prompts (`NEEDS_PLAN` vs. instant answer) and drafts a structured "
                        "JSON/Markdown scientific methodology (`steps`, `tools`, `datasets`) researchers can approve or revise."
                    ),
                    "backing": ["POST /api/plan", "ligase/webapp/planner.py"],
                    "sample_prompt": (
                        "Design a step-by-step multi-cohort study linking `SORL1` coding and non-coding variants "
                        "across NIAGADS Open Access API v2.0, UniProt, and Ensembl."
                    ),
                },
                {
                    "id": "mm_eng_claw",
                    "title": "ClawAgents ReAct Graph & Context Layers",
                    "badge": "Streaming Loop",
                    "status": "live",
                    "summary": (
                        "Executes iterative tool-calling turns with real-time event hooks (`turn_started`, "
                        "`tool_started`, `tool_result`, `assistant_delta`, `usage`) and biomedical SOP injection."
                    ),
                    "backing": ["clawagents>=6.20.0", "BiomniDataLakeLayer", "BiomniKnowHowLayer", "BiomniADLayer"],
                    "sample_prompt": (
                        "Run a multi-tool cross-check of `MAPT` across `niagads_open_access_api`, `query_uniprot`, "
                        "and `query_ensembl`."
                    ),
                },
                {
                    "id": "mm_eng_local",
                    "title": "Local Glimmer-30B / Gemma 1-Pass Harness",
                    "badge": "Private / On-Prem",
                    "status": "live",
                    "summary": (
                        "Shrinks the tool surface, pre-grounds deterministic sequence/HWE/NIAGADS cards, caps "
                        "redundant lookups, and merges exact numeric facts for private local checkpoints."
                    ),
                    "backing": ["ligase/local_harness.py", "ligase/gemma_harness.py"],
                    "sample_prompt": (
                        "In an autosomal recessive disorder with disease incidence 1 in 10,000, compute 2pq and the "
                        "posterior carrier risk for an unaffected sibling after a negative 90%-sensitivity genetic test."
                    ),
                },
                {
                    "id": "mm_eng_sandbox",
                    "title": "Multi-Layer Execution & Secret Sandbox",
                    "badge": "AST + OS Isolation",
                    "status": "live",
                    "summary": (
                        "Combines AST attribute/import allowlisting in `run_python`, environment secret scrubbing "
                        "in Cloud Run, and macOS `sandbox-exec` / Linux `bwrap` workspace confinement."
                    ),
                    "backing": ["ligase/sandbox.py", "ligase/gemma_tools.py (_validate_ast)"],
                    "sample_prompt": (
                        "Use `run_python` to compute exact 95% confidence intervals and log-odds ratios for a "
                        "2x2 case-control allele table (cases: 142 alt / 1858 ref; controls: 84 alt / 1916 ref)."
                    ),
                },
            ],
        },
        {
            "id": "biomni_domains",
            "title": "Biomedical Domain Suite (180+ Tools)",
            "short_title": "180+ Biomni Tools",
            "badge": "5 Scientific Modules",
            "accent": "#0284c7",
            "icon": "🧪",
            "summary": (
                "Adapts the Biomni tool ecosystem (`database`, `genomics`, `pharmacology`, `biochemistry`, "
                "`literature`) into native ClawAgents tools with fault-tolerant schema binding."
            ),
            "components": [
                {
                    "id": "mm_bio_genomics",
                    "title": "Genomics & Variant Databases",
                    "badge": "Ensembl · ClinVar · NCBI",
                    "status": "live",
                    "summary": (
                        "Queries Ensembl REST (GRCh38 genes, VEP consequences), NCBI Entrez Gene, ClinVar clinical "
                        "classifications, and NHGRI-EBI GWAS Catalog associations."
                    ),
                    "backing": ["query_ensembl", "query_ncbi_gene", "query_clinvar", "query_gwas_catalog"],
                    "sample_prompt": (
                        "Look up `PSEN1` in Ensembl and ClinVar to summarize its chromosomal coordinates, canonical "
                        "transcript, and pathogenic early-onset Alzheimer's variant spectrum."
                    ),
                },
                {
                    "id": "mm_bio_proteomics",
                    "title": "Proteomics, Isoforms & 3D Structure",
                    "badge": "UniProt · PDB · AlphaFold",
                    "status": "live",
                    "summary": (
                        "Retrieves curated UniProtKB domain architectures, missense isoform differences, RCSB PDB "
                        "experimental structures, AlphaFoldDB predictions, and STRING PPI networks."
                    ),
                    "backing": ["query_uniprot", "query_pdb", "query_alphafold", "query_stringdb"],
                    "sample_prompt": (
                        "Query UniProt for human `APOE` (`P02649`): identify its lipid-binding and LDL-receptor "
                        "domains, compare Cys/Arg residues at 112 and 158, and list key interaction partners."
                    ),
                },
                {
                    "id": "mm_bio_pharma",
                    "title": "Pharmacology, Chemistry & Drug Targets",
                    "badge": "PubChem · ChEMBL · OpenTargets",
                    "status": "live",
                    "summary": (
                        "Provides exact molecular formulas, monoisotopic/molecular weights, IUPAC names, IC50/Ki "
                        "bioactivity profiles, and target-disease tractability."
                    ),
                    "backing": ["lookup_compound", "query_pubchem", "query_chembl", "query_opentarget"],
                    "sample_prompt": (
                        "Look up `Donepezil` and `Memantine` via `lookup_compound`: compare their exact molecular "
                        "formulas, molecular weights, IUPAC names, and primary CNS mechanisms of action."
                    ),
                },
                {
                    "id": "mm_bio_pathways",
                    "title": "Pathways, Biochemistry & Functional Omics",
                    "badge": "KEGG · Physicochemical",
                    "status": "live",
                    "summary": (
                        "Analyzes KEGG signaling/metabolic pathways, protein physicochemical properties (isoelectric "
                        "point, GRAVY, instability index), and optional single-cell / enrichment workflows."
                    ),
                    "backing": ["query_kegg", "calculate_physicochemical_properties", "biomni.tool.genomics"],
                    "sample_prompt": (
                        "Query KEGG and UniProt to map how `TREM2`, `TYROBP` (`DAP12`), `SYK`, and `PLCG2` "
                        "couple in microglial lipid-sensing and phagocytic signaling."
                    ),
                },
                {
                    "id": "mm_bio_lit",
                    "title": "Biomedical Literature & Evidence Synthesis",
                    "badge": "PubMed E-utilities",
                    "status": "live",
                    "summary": (
                        "Searches peer-reviewed biomedical publications, clinical trial reports, and PMIDs via "
                        "NCBI E-utilities for evidence-grounded citation."
                    ),
                    "backing": ["search_pubmed", "biomni.tool.literature"],
                    "sample_prompt": (
                        "Search PubMed for recent whole-genome sequencing studies of Progressive Supranuclear Palsy "
                        "and summarize key structural variant and `APOE ε2` findings."
                    ),
                },
            ],
        },
        {
            "id": "quant_compute",
            "title": "Deterministic Compute & Sequence Tools",
            "short_title": "Quantitative & Sequence",
            "badge": "Exact Verification",
            "accent": "#d97706",
            "icon": "📐",
            "summary": (
                "Zero-hallucination deterministic calculators for sequence transcription/translation, "
                "frameshift consequences, exact rational population genetics, and Python biostatistics."
            ),
            "components": [
                {
                    "id": "mm_qnt_python",
                    "title": "Sandboxed Python Biostatistics (`run_python`)",
                    "badge": "5s Timeout · AST Safe",
                    "status": "live",
                    "summary": (
                        "Executes verified Python snippets using `math`, `statistics`, `fractions`, `decimal`, "
                        "`collections`, `itertools`, and `json` for exact numeric verification."
                    ),
                    "backing": ["run_python", "ligase/gemma_tools.py"],
                    "sample_prompt": (
                        "Use `run_python` to calculate the Levin Population Attributable Fraction `PAF = f*(OR-1) / "
                        "(1 + f*(OR-1))` for `ABCA7` in African (`f=0.072, OR=1.90`) vs. European (`f=0.009, OR=1.78`) cohorts."
                    ),
                },
                {
                    "id": "mm_qnt_seq",
                    "title": "DNA/mRNA Translation & Frameshift Engine",
                    "badge": "c.<pos>del Aware",
                    "status": "live",
                    "summary": (
                        "Transcribes coding DNA to mRNA, translates via the standard genetic code, and pinpoints "
                        "`c.<pos>del` frameshift codon changes and premature termination."
                    ),
                    "backing": ["transcribe_translate"],
                    "sample_prompt": (
                        "Use `transcribe_translate` on `5'-ATGCGATCGATCGAA-3'` with mutation `c.7delG` to report "
                        "the wild-type peptide, mutated mRNA, altered codon, and truncated peptide."
                    ),
                },
                {
                    "id": "mm_qnt_hwe",
                    "title": "Exact Rational HWE & Bayesian Carrier Solver",
                    "badge": "Exact Fractions",
                    "status": "live",
                    "summary": (
                        "Computes exact `fractions.Fraction` Hardy-Weinberg allele/carrier frequencies (`q`, `p`, `2pq`) "
                        "and post-test Bayesian carrier probabilities under imperfect sensitivity/specificity."
                    ),
                    "backing": ["solve_hwe_bayes"],
                    "sample_prompt": (
                        "For an autosomal recessive disease with `q^2 = 0.0001`, calculate `2pq` and the exact "
                        "posterior probability that an unaffected sibling of an affected child is a carrier after a "
                        "negative genetic test with 90% sensitivity and 100% specificity."
                    ),
                },
                {
                    "id": "mm_qnt_v2f_math",
                    "title": "Bayesian Fine-Mapping & Cross-Disorder ROR",
                    "badge": "Wakefield ABF · LLR",
                    "status": "live",
                    "summary": (
                        "Verifies functional-prior Posterior Inclusion Probabilities (`PIP`), epistatic rescue "
                        "ratios, and cross-disorder Relative Odds Ratios (`ROR` / `ΔLLR` in nats)."
                    ),
                    "backing": ["run_python", "query_niagads"],
                    "sample_prompt": (
                        "Use `run_python` and `query_niagads` to verify how a 10× FILER microglia enhancer prior "
                        "shifts `rs6733839` PIP across the 4-SNP `BIN1` credible set."
                    ),
                },
            ],
        },
        {
            "id": "portal_outputs",
            "title": "Web Portal, CLI & Study Artifacts",
            "short_title": "Portal & Exports",
            "badge": "Cloud Run + Local",
            "accent": "#e11d48",
            "icon": "📊",
            "summary": (
                "End-to-end researcher workspace combining real-time SSE streaming, interactive Mindmap "
                "inspection, live NIAGADS API exploration, dataset uploads, and reproducible `.md`/`.zip` exports."
            ),
            "components": [
                {
                    "id": "mm_ui_studio",
                    "title": "Streaming Research Studio & Tool Trace",
                    "badge": "SSE + KaTeX + GFM",
                    "status": "live",
                    "summary": (
                        "Streams live `gpt-6-luna` synthesis, collapsible per-tool latency/argument traces, "
                        "KaTeX scientific math, and responsive sticky-column comparison tables."
                    ),
                    "backing": ["POST /api/chat/stream", "ligase/webapp/static/app.js"],
                    "sample_prompt": (
                        "Run a comprehensive NIAGADS + UniProt synthesis on `APOE`, `TREM2`, and `BIN1` with a "
                        "formatted comparison table."
                    ),
                },
                {
                    "id": "mm_ui_mindmap",
                    "title": "Interactive Capabilities Mindmap & Matrix",
                    "badge": "SVG Graph + Table",
                    "status": "live",
                    "summary": (
                        "Visualizes all 6 architectural pillars and 32 Ligase components with interactive branch "
                        "filtering, zoom, semantic table toggle, and 1-click prompt or live endpoint launch."
                    ),
                    "backing": ["GET /api/mindmap", "ligase/webapp/mindmap.py"],
                    "sample_prompt": (
                        "Summarize how Ligase combines live NIAGADS Open Access API v2.0 endpoints with Biomni "
                        "domain tools and sandboxed Python verification."
                    ),
                },
                {
                    "id": "mm_ui_oa_explorer",
                    "title": "NIAGADS Open Access Live API Console",
                    "badge": "1-Click Presets",
                    "status": "live",
                    "summary": (
                        "Interactive point-and-click console on the Web Portal for testing live `api.niagads.org` "
                        "endpoints, inspecting structured tables & raw JSON, and piping results to `gpt-6-luna`."
                    ),
                    "backing": ["GET /api/niagads/live", "GET /api/niagads/endpoints"],
                    "sample_prompt": (
                        "Use `niagads_open_access_api` to fetch live associations for `BIN1` and summarize top "
                        "tracks by ancestry."
                    ),
                    "live_api_preset": {"action": "auto", "target": "rs6733839", "loc": ""},
                },
                {
                    "id": "mm_ui_uploads",
                    "title": "Genomic & Tabular Dataset Uploads",
                    "badge": "15 MB · 14 Formats",
                    "status": "live",
                    "summary": (
                        "Accepts `.vcf`, `.bed`, `.tsv`, `.csv`, `.fasta`, `.gff`, `.gtf`, `.json`, and script "
                        "attachments isolated per client session and staged into run workspaces."
                    ),
                    "backing": ["POST /api/uploads", "read_file", "run_python"],
                    "sample_prompt": (
                        "Explain how I can upload a candidate `.vcf` or `.bed` interval list and cross-reference "
                        "each locus against NIAGADS Open Access API v2.0 and FILER."
                    ),
                },
                {
                    "id": "mm_ui_exports",
                    "title": "SQLite Study History, CLI & Run Bundles",
                    "badge": ".md · .zip · CLI",
                    "status": "live",
                    "summary": (
                        "Persists multi-thread study history in SQLite, exports publication-ready Markdown reports "
                        "and `.zip` run bundles, and mirrors capabilities in the `ligase` CLI."
                    ),
                    "backing": [
                        "GET /api/runs/{run_id}/report.md",
                        "GET /api/runs/{run_id}/bundle.zip",
                        "ligase/cli.py",
                    ],
                    "sample_prompt": (
                        "Generate a publication-ready executive brief comparing AD genetic architecture across "
                        "European and African ancestry cohorts in NIAGADS."
                    ),
                },
            ],
        },
    ]

    total_components = sum(len(b["components"]) for b in branches)
    live_presets = sum(
        1 for b in branches for c in b["components"] if c.get("live_api_preset")
    )

    return {
        "root": {
            "id": "ligase_root",
            "title": "Ligase Platform",
            "subtitle": f"v{VERSION} · {model_name} Biomedical & NIAGADS Co-Scientist",
            "summary": (
                "Unified biomedical AI co-scientist joining the live NIAGADS Open Access API v2.0 "
                "(api.niagads.org), curated multi-cohort ADRD quantitative panels (FILER, MiGA, ADSP, PSP), "
                "180+ Biomni domain tools, and AST-verified Python bioinformatics."
            ),
        },
        "stats": {
            "pillars": len(branches),
            "components": total_components,
            "niagads_openapi_paths": 19,
            "live_api_presets": live_presets,
            "biomni_tools": "180+",
            "niagads_dss_cohorts": 24,
        },
        "branches": branches,
    }
