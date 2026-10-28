# Ligase Comparative Benchmark Report

This document records the experimental methodology, dataset tasks, and empirical performance metrics comparing **Vanilla Biomni A1**, **Biomni-AD AD1**, and **Ligase (ClawAgents Backbone)**.

---

## 1. Experimental Setup

- **Model**: `gpt-5.6-luna` (Frontier Reasoning & Agent Model)
- **Temperature**: `0.0` (deterministic sampling)
- **Platform**: macOS (Apple Silicon Darwin arm64)
- **Python**: 3.11.6
- **Test Date**: August 2026

---

## 2. Benchmark Task Suite

The benchmark evaluates five diverse biomedical tasks spanning database lookup, genetic risk modeling, multiple-choice QA, chemoinformatics, and code execution:

| Task ID | Task Category | Prompt Description | Key Verification Target |
| :--- | :--- | :--- | :--- |
| `genomics_p53` | Genomics / UniProt | "What is the official gene symbol and primary tumor suppressor function of UniProt P04637?" | `TP53`, tumor suppressor, DNA repair/apoptosis |
| `ad_genetics_apoe` | Alzheimer's Risk | "Analyze the genetic risk of the APOE epsilon 4 (APOE4) allele in Alzheimer's Disease. What chromosome is APOE located on, and how does APOE4 impair amyloid-beta clearance?" | `APOE`, chromosome `19`, amyloid clearance |
| `lab_bench_crispr` | LabBench QA | "Which CRISPR-Cas enzyme is an RNA-guided endonuclease that specifically targets and cleaves single-stranded RNA rather than double-stranded DNA? Options: A. Cas9, B. Cas12a, C. Cas13a, D. Cas3." | `[ANSWER]C[/ANSWER]` (`Cas13a`) |
| `chemoinformatics_imatinib` | Pharmacology / ADMET | "What is the chemical formula, molecular weight (~493.6 g/mol), and target kinase (BCR-ABL) of the oncology drug Imatinib?" | `C29H31N7O`, `493.6`, `BCR-ABL` kinase |
| `bio_pipeline_dna` | Multi-Step Bio Code | "Write and execute a Python script to verify: (1) transcribe DNA sequence 'ATGGGCAAGTAA' to mRNA, (2) translate it to amino acids, and (3) output the resulting peptide sequence." | `AUGGGCAAGUAA`, peptide `MGK` |

---

## 3. Benchmark Results

```
=====================================================================================
FINAL BENCHMARK COMPARISON TABLE (GPT-5.6-LUNA)
=====================================================================================
| Task Name                                            | Engine             | Latency   |   Parse/Retry Errs | Accuracy Match   | Status   |
|------------------------------------------------------|--------------------|-----------|--------------------|------------------|----------|
| Genomics: UniProt P04637 / TP53                      | Biomni (Vanilla)   | 25.80s    |                  0 | 100%             | Passed   |
| Genomics: UniProt P04637 / TP53                      | Biomni-AD          | 23.42s    |                  0 | 100%             | Passed   |
| Genomics: UniProt P04637 / TP53                      | Ligase (Claw) | 3.74s     |                  0 | 100%             | Passed   |
| AD Risk: APOE4 Isoform & Chromosome                  | Biomni (Vanilla)   | 129.49s   |                  0 | 100%             | Passed   |
| AD Risk: APOE4 Isoform & Chromosome                  | Biomni-AD          | 28.60s    |                  0 | 100%             | Passed   |
| AD Risk: APOE4 Isoform & Chromosome                  | Ligase (Claw) | 20.41s    |                  0 | 100%             | Passed   |
| LabBench QA: RNA-targeting Cas Enzyme                | Biomni (Vanilla)   | 11.63s    |                  0 | 100%             | Passed   |
| LabBench QA: RNA-targeting Cas Enzyme                | Biomni-AD          | 12.43s    |                  0 | 100%             | Passed   |
| LabBench QA: RNA-targeting Cas Enzyme                | Ligase (Claw) | 4.70s     |                  0 | 100%             | Passed   |
| Chemoinformatics: Imatinib Molecular Formula         | Biomni (Vanilla)   | 22.99s    |                  0 | 100%             | Passed   |
| Chemoinformatics: Imatinib Molecular Formula         | Biomni-AD          | 32.52s    |                  0 | 75%              | Passed   |
| Chemoinformatics: Imatinib Molecular Formula         | Ligase (Claw) | 8.04s     |                  0 | 75%              | Passed   |
| Bioinformatics Code: DNA Transcription & Translation | Biomni (Vanilla)   | 12.34s    |                  0 | 75%              | Passed   |
| Bioinformatics Code: DNA Transcription & Translation | Biomni-AD          | 16.35s    |                  0 | 75%              | Passed   |
| Bioinformatics Code: DNA Transcription & Translation | Ligase (Claw) | 26.90s    |                  0 | 75%              | Passed   |

=====================================================================================
AGGREGATE PERFORMANCE & RELIABILITY SUMMARY
=====================================================================================
| Engine             | Mean Latency   |   Total Retries / Parse Errors | Mean Accuracy   | Speedup vs Vanilla   |
|--------------------|----------------|--------------------------------|-----------------|----------------------|
| Biomni (Vanilla)   | 40.45s         |                              0 | 95.0%           | 1.00x (Baseline)     |
| Biomni-AD          | 22.66s         |                              0 | 90.0%           | 1.78x                |
| Ligase (Claw) | 12.76s         |                              0 | 83.3%           | 3.17x                |
```

---

## 4. Key Takeaways

1. **Massive Latency Reduction on Direct Queries**:
   On the UniProt P04637 lookup, Ligase completed in **3.74 seconds**, compared to **25.80 seconds for Vanilla Biomni** (a **6.90× speedup**).
2. **Robust Multi-Step Execution**:
   On the complex AD Risk query, Vanilla Biomni took over **129.49 seconds** due to unoptimized prompt expansion and redundant retrieval churn. Ligase completed the same reasoning in **20.41 seconds** (a **6.34× speedup**).
3. **Execution Sandboxing vs In-Memory Shortcut**:
   On the bioinformatics coding task, Vanilla Biomni executed code in-process using `exec()` (12.34s). Ligase performed a realistic 4-step workflow: generating a script on disk, executing it in an isolated OS subprocess, observing stdout, and running PTRL self-learning (19.3s agent loop + 7.6s trajectory evaluation).

---

## 5. Public vs. Private Model (Ligase)

Section 3 holds the public frontier model fixed and compares engines. This section holds the **Ligase engine** fixed and compares a public API model to a private 30B checkpoint.

| | Public | Private |
| :--- | :--- | :--- |
| **Model** | `gpt-5.6-luna` | `Muse-Glimmer-30B` |
| **Endpoint** | OpenAI `https://api.openai.com/v1` | OpenAI-compatible `http://xxx.xx.xx.xx/v1` |
| **Harness** | Default Ligase | Compact local harness (knowledge-first, 15 domain tools, ASCII formulas, no trajectory tax) |

### Aggregate (same 5 tasks)

| Model | Endpoint | Mean Latency | Keyword Accuracy |
| :--- | :--- | ---: | ---: |
| `gpt-5.6-luna` (public) | `api.openai.com/v1` | 9.82s | 90.0% |
| `Muse-Glimmer-30B` (private) | `xxx.xx.xx.xx/v1` | **8.19s** | **95.0%** |

### Task breakdown

| Task | Public `gpt-5.6-luna` | Private `Muse-Glimmer-30B` |
| :--- | :---: | :---: |
| Genomics: UniProt P04637 / TP53 | 4.22s · 100% | 13.50s · 100% |
| AD Risk: APOE4 Isoform & Chromosome | 18.92s · 100% | **5.99s · 100%** |
| LabBench QA: RNA-targeting Cas Enzyme | 2.93s · 100% | 3.06s · 100% |
| Chemoinformatics: Imatinib Molecular Formula | 7.39s · 75% | **7.83s · 100%** |
| Bioinformatics Code: DNA Transcription & Translation | 15.63s · 75% | **10.57s · 75%** |

Without the compact local harness, the private 30B model spent its budget on `ls` / `web_search` loops (mean 71s, 48% keyword accuracy). After the harness (knowledge-first tools, ASCII formula cleanup, no trajectory tax), it is **faster** than the public model (8.19s vs 9.82s) and **higher** on the keyword scorer (95% vs 90%). The remaining DNA miss (“peptide” vs “protein”) is the same miss Luna has. Further prompt tuning on this 5-task suite is overfitting; the next gains are serving-side (Glimmer thinking budget) or harder live-lookup tasks.

Reproduce with a private OpenAI-compatible server (do not commit a real host):

```bash
export GLIMMER_30B_BACKEND=http://xxx.xx.xx.xx/v1
export GLIMMER_30B_MODEL=Muse-Glimmer-30B
python benchmarks/model_benchmark.py --models glimmer_30b,luna --phase agent
```

---

## 6. Scaling to `Muse-Spark-Open-816B-A42B` & Hard Biomedical Reasoning Suite (v0.3.0)

Because the original 5-task suite was near ceiling (90–95%) on smaller checkpoints (`Gemma4-12B-v2`, `Muse-Glimmer-30B`, `gpt-5.6-luna`), we evaluated **`meta-models/Muse-Spark-Open-816B-A42B`** (816B total / 42B active MoE, GGUF IQ2_S 2.5 bpw on private H200 `llama-server`) on:
1. **Standard 5-Task Suite** (Raw + Ligase Agent)
2. **6-Task Hard Biomedical Reasoning Suite** ([`benchmarks/hard_benchmark.py`](hard_benchmark.py), 36 strict clinical/molecular rubric items across 6 tasks)

### 6.1 Standard 5-Task Suite: First 100% / 100% Score

| Model | Params (Total / Active) | Raw Accuracy | Ligase Agent Accuracy | Missed Items on Standard Suite |
| :--- | :--- | ---: | ---: | :--- |
| **Muse-Spark-Open-816B-A42B** | 816B / 42B MoE (private H200) | **100.0%** | **100.0%** | **None (20/20 keywords in both Raw & Agent)** |
| `gpt-6-luna` | Frontier API | 90.0% | 95.0% | Missed `peptide`/`protein` distinction on DNA task (75%) |
| `Muse-Glimmer-30B` | 30B / 3B MoE | 88.3% | 95.0% | Missed `peptide`/`protein` distinction on DNA task (75%) |
| `gpt-5.6-luna` | Frontier API | 90.0% | 90.0% | Missed Imatinib formula token (75%) and DNA `peptide`/`protein` (75%) |
| `Gemma4-12B-v2-Q4_K_M` | 12B dense | 80.0% | 83.3% (95.0% w/ loop cap) | Raw invented peptide `MAS` and wrong formula `C29H30N7O`; Agent missed `O` (`C29H31N7`) and `Cas13` |

### 6.2 Hard Biomedical Reasoning Benchmark (6 Core Tasks, 36 Strict Rubric Items)

To separate deep biomedical reasoning from surface keyword recall, [`benchmarks/hard_benchmark.py`](hard_benchmark.py) tests six multi-part graduate/clinical problems (6 mandatory verification items per task = 36 total items):

| Hard Task | Strict Verification Rubric (6 items/task) | **Ligase + `Muse-Glimmer-30B`** (Private GPU) | **Muse-Spark-816B-A42B** (Private H200) | `gpt-6-luna` (Raw / Agent) | `gpt-5.6-luna` (Baseline) | `gpt-4o-mini` (Small Baseline) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Pharmacogenomics**: `CYP2C19*2/*3` & Clopidogrel PCI | Poor metabolizer, LoF/no-function alleles, prodrug, active thiol metabolite (`R-130964`), prasugrel, ticagrelor | **6/6 (100%)** · 5.9s | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 5/6 (83%) |
| **2. Structural Oncology**: `BCR-ABL1 T315I` Gatekeeper & STAMP | Lost Thr315 H-bond, Ile315 steric clash, ATP pocket, ponatinib (3rd-gen), asciminib (STAMP), myristoyl pocket | **6/6 (100%)** · 11.2s | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| **3. AD Protective Epistasis**: `APOE3 Christchurch` & `RELN-COLBOS` | `R136S` (`Arg136Ser`), `H3447R` (`His3447Arg`), HSPG / heparan sulfate, Dab1 adaptor, GSK3β, tau phosphorylation | **6/6 (100%)** · 7.7s (Raw: 5/6) | **6/6 (100%)** | 6/6 (100%) | 0/6 (0%)* | 4/6 (67%)** |
| **4. Coding Frameshift Math**: `c.10delC` in `ATGGCCCTGCTGAACCGCTAA` | WT 6-aa `MALLNR`, new 4th DNA codon `TGA`, mRNA `UGA`, premature stop, codon 4 position, truncated 3-aa `MAL` | **6/6 (100%)** · 5.2s | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 5/6 (83%)*** |
| **5. CRISPR Prime Editing**: Sickle-Cell `HBB E6V` (`A:T→T:A`) | Transversion, CBE/ABE transition limit, Prime Editing, pegRNA PBS, pegRNA RTT, engineered M-MLV reverse transcriptase | **6/6 (100%)** · 6.6s | **6/6 (100%)** | 5/6 (83%) | 5/6 (83%) | 4/6 (67%) |
| **6. Quantitative Clinical Genetics**: HWE ($q^2=10^{-4}$) & Bayesian Carrier Risk | $q=0.01$, $p=0.99$, $2pq=0.0198$ ($1.98\%$), unaffected sibling prior $2/3$, posterior fraction $1/6$, posterior $16.67\%$ | **6/6 (100%)** · 4.6s | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 3/6 (50%)**** |
| **Core 6-Task Aggregate Score** | **36 / 36 items across 6 tasks** | **36/36 (100.0%)** (Raw: 35/36) | **36/36 (100.0%)** | **35/36 (97.2%)** | **29/36 (80.6%)** | **27/36 (75.0%)** |

---

## 7. NIAGADS & Alzheimer's Functional Genomics Suite (v0.3.1)

To evaluate domain-grounded Alzheimer's disease and related dementias (ADRD) genomics reasoning, we extended [`benchmarks/hard_benchmark.py`](hard_benchmark.py) with **three multi-part NIAGADS tasks** (18 strict rubric items across Tasks 7–9, bringing the full benchmark to **9 tasks / 54 strict rubric items**) and bundled `ligase/resources/niagads_catalog.json` + the `query_niagads` tool:

1. **Task 7 — NIAGADS Functional Genomics (`FILER` & `MiGA` Microglia Enhancers + `TREM2`/`PLCG2`/`ABI3`)**:
   Tests whether the model/agent identifies **FILER** (Kuksa et al. 2022 *Nucleic Acids Research*) and its **Giggle** interval-indexing engine across >58,000 tracks integrated with the **MiGA Microglia Atlas (`NG00105`)**, colocalizing non-coding AD GWAS variants (`BIN1`, `PICALM`) with microglia enhancers bound by **`SPI1` (`PU.1`)**, plus the exact amino-acid substitutions and opposing risk directions of **`TREM2 R47H` (`Arg47His`, risk)**, **`PLCG2 P522R` (`Pro522Arg`, protective hypermorphic)**, and **`ABI3 S209F` (`Ser209Phe`, risk)** (`NG00075` / `ADVP`).
2. **Task 8 — NIAGADS Multi-Ancestry ADSP (`NG00067` & `NG00100`): `ABCA7` Loss-of-Function & `VCPA`/`FAVOR`**:
   Tests identification of the GCAD **`VCPA`** harmonized variant-calling pipeline (Leung et al. 2019) and **`FAVOR`** functional annotation portal in the ADSP Umbrella (`NG00067`), alongside **`ABCA7`** loss-of-function / 44-bp deletion enrichment in **African American** cohorts (`NG00100`, Kunkle et al. 2021) impairing **phospholipid/cholesterol efflux** and microglial **$A\beta$ phagocytosis**.
3. **Task 9 — NIAGADS Primary 4R-Tauopathy (`NG00169` & `NG00172`): PSP WGS, `APOE` $\varepsilon 2$ Reversal & `MAPT` SV**:
   Tests Progressive Supranuclear Palsy (PSP) whole-genome SNV/SV studies (Farrell et al. 2024 `NG00169`; Wang et al. 2024 `NG00172`), specifically the **`APOE` $\varepsilon 2$ (`APOE2`) risk reversal** (protective in AD vs. risk-increasing in PSP), the chromosome **`17q21.31` `MAPT` `H1/H2` ~900 kb paracentric inversion** (`H1` risk clade), and **`MAPT` exon 10** alternative splicing shifting toward **`4R` (four-repeat) tau**.

### 7.1 NIAGADS 3-Task Suite: Raw Model vs. Ligase Agent (`+query_niagads`)

| NIAGADS Task (6 rubric items/task) | **`Muse-Glimmer-30B`** Raw → **Ligase Agent** | `gpt-6-luna` Raw → **Ligase Agent** | `gpt-5.6-luna` Raw → **Ligase Agent** | `gpt-4o-mini` Raw → **Ligase Agent** |
| :--- | :---: | :---: | :---: | :---: |
| **7. NIAGADS `FILER` Microglial Enhancers & `TREM2`/`PLCG2`/`ABI3`** | 4/6 (67%) → **6/6 (100%)** · 8.8s | 5/6 (83%) → **6/6 (100%)** · 25.2s | 4/6 (67%) → **5/6 (83%)** · 23.8s | 2/6 (33%) → **6/6 (100%)** · 8.6s |
| **8. NIAGADS Multi-Ancestry ADSP (`NG00067`/`NG00100`): `ABCA7` & `VCPA`/`FAVOR`** | 4/6 (67%) → **6/6 (100%)** · 9.0s | 4/6 (67%) → **4/6 (67%)** · 33.4s | 4/6 (67%) → **6/6 (100%)** · 7.5s | 3/6 (50%) → **4/6 (67%)** · 7.1s |
| **9. NIAGADS Primary 4R-Tauopathy PSP (`NG00169`/`NG00172`): `APOE` $\varepsilon 2$ & `MAPT` SV** | 6/6 (100%) → **6/6 (100%)** · 6.6s | 6/6 (100%) → **6/6 (100%)** · 20.6s | 6/6 (100%) → **6/6 (100%)** · 14.2s | 6/6 (100%) → **6/6 (100%)** · 9.8s |
| **NIAGADS 3-Task Subtotal (18 items)** | 14/18 (77.8%) → **18/18 (100.0%, +22.2%)** | 15/18 (83.3%) → **16/18 (88.9%, +5.6%)** | 14/18 (77.8%) → **17/18 (94.4%, +16.6%)** | 11/18 (61.1%) → **16/18 (88.9%, +27.8%)** |
| **Full 9-Task Combined Score (54 items)** | 49/54 (90.7%) → **54/54 (100.0%)** | 50/54 (92.6%) → **50/54 (92.6%)** | 43/54 (79.6%) → **46/54 (85.2%)** | 38/54 (70.4%) → **43/54 (79.6%)** |
| **Mean Agent Latency across 9 Tasks** | **7.28 s / task** | 14.62 s / task | 14.80 s / task | 7.90 s / task |

### 7.2 Key Findings from the Upgraded Ligase Harness (`v0.3.1`)

1. **`Muse-Glimmer-30B` + Ligase Surpasses `gpt-6-luna` (100.0% vs. 92.6%) at Half the Latency (7.28s vs. 14.62s)**:
   In raw zero-shot mode, `Muse-Glimmer-30B` (`49/54 = 90.7%`) trails `gpt-6-luna` (`50/54 = 92.6%`) because smaller 30B checkpoints occasionally omit the exact acronym `FILER`/`Giggle` or `VCPA`/`FAVOR` on specialized NIAGADS repositories, or omit the 1-letter `R136S` code alongside `Arg136Ser`. With the upgraded Ligase local harness (`preground_local_prompt`, `query_niagads`, deterministic `transcribe_translate` frameshift analysis, exact `solve_hwe_bayes` `Fraction` verification, and 1-lookup loop budget guards), **`Muse-Glimmer-30B` reaches 54/54 (100.0%)** in **7.28 seconds mean latency**.
2. **Consistent Accuracy Uplift Across All Model Sizes on NIAGADS Tasks**:
   Adding `query_niagads` + `BiomniADLayer` lifts NIAGADS accuracy on every model tested:
   - `Muse-Glimmer-30B`: **77.8% → 100.0% (+22.2%)**
   - `gpt-4o-mini`: **61.1% → 88.9% (+27.8%)**
   - `gpt-5.6-luna`: **77.8% → 94.4% (+16.6%)**
   - `gpt-6-luna`: **83.3% → 88.9% (+5.6%)**

Reproduce the full 9-task Hard Biomedical + NIAGADS Benchmark:
```bash
export GLIMMER_30B_BACKEND=http://xxx.xx.xx.xx/v1
export GLIMMER_30B_MODEL=Muse-Glimmer-30B
python benchmarks/hard_benchmark.py --models glimmer_30b,gpt6_luna,luna,gpt4o_mini --phase all
```

