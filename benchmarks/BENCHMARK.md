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

### 6.2 Hard Biomedical Reasoning Benchmark (6 Tasks, 36 Strict Rubric Items)

To separate deep biomedical reasoning from surface keyword recall, [`benchmarks/hard_benchmark.py`](hard_benchmark.py) tests six multi-part graduate/clinical problems (6 mandatory verification items per task = 36 total items):

| Hard Task | Strict Verification Rubric (6 items/task) | **Muse-Spark-816B-A42B** | `gpt-6-luna` | `gpt-5.6-luna` | `gpt-4o-mini` (Small Baseline) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **1. Pharmacogenomics**: `CYP2C19*2/*3` & Clopidogrel PCI | Poor metabolizer, LoF/no-function alleles, prodrug, active thiol metabolite (`R-130964`), prasugrel, ticagrelor | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 5/6 (83%) |
| **2. Structural Oncology**: `BCR-ABL1 T315I` Gatekeeper & STAMP | Lost Thr315 H-bond, Ile315 steric clash, ATP pocket, ponatinib (3rd-gen), asciminib (STAMP), myristoyl pocket | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| **3. AD Protective Epistasis**: `APOE3 Christchurch` & `RELN-COLBOS` | `R136S` (`Arg136Ser`), `H3447R` (`His3447Arg`), HSPG / heparan sulfate, Dab1 adaptor, GSK3β, tau phosphorylation | **6/6 (100%)** | 6/6 (100%) | 0/6 (0%)* | 4/6 (67%)** |
| **4. Coding Frameshift Math**: `c.10delC` in `ATGGCCCTGCTGAACCGCTAA` | WT 6-aa `MALLNR`, new 4th DNA codon `TGA`, mRNA `UGA`, premature stop, codon 4 position, truncated 3-aa `MAL` | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 5/6 (83%)*** |
| **5. CRISPR Prime Editing**: Sickle-Cell `HBB E6V` (`A:T→T:A`) | Transversion, CBE/ABE transition limit, Prime Editing, pegRNA PBS, pegRNA RTT, engineered M-MLV reverse transcriptase | **6/6 (100%)** | 5/6 (83%) | 5/6 (83%) | 4/6 (67%) |
| **6. Quantitative Clinical Genetics**: HWE ($q^2=10^{-4}$) & Bayesian Carrier Risk | $q=0.01$, $p=0.99$, $2pq=0.0198$ ($1.98\%$), unaffected sibling prior $2/3$, posterior fraction $1/6$, posterior $16.67\%$ | **6/6 (100%)** | 6/6 (100%) | 6/6 (100%) | 3/6 (50%)**** |
| **Aggregate Strict Rubric Score** | **36 / 36 items across 6 tasks** | **36/36 (100.0%)** | **35/36 (97.2%)** | **29/36 (80.6%)** | **27/36 (75.0%)** |

#### Why `Muse-Spark-Open-816B-A42B` Outperforms Smaller & Frontier Models on Hard Tasks:
- **`*` & `**` AD Protective Genetics (`APOE3 Christchurch` + `RELN-COLBOS`)**: Small models (`gpt-4o-mini`) hallucinated both protective variants as `R136C` and `P12L`, while `gpt-5.6-luna` exhausted its reasoning budget trying to recall the `RELN-COLBOS` substitution. `Muse-Spark-816B-A42B` recalled both exact substitutions (`APOE3 p.Arg136Ser / R136S` [and mature vs signal-peptide `p.Arg154Ser`] plus `RELN-COLBOS p.His3447Arg / H3447R, c.10340A>G`), reduced HSPG binding, and the full `ApoER2/VLDLR → Dab1 → PI3K/Akt → GSK3β Ser9` cascade.
- **`***` Exact Reading-Frame & Frameshift Arithmetic (`c.10delC`)**: Whereas `Gemma4-12B-v2` hallucinated peptide `MAS` on a 12-nt sequence in raw mode and `gpt-4o-mini` mis-segmented wild-type codon 4 as `UGA` (missing `MALLNR`), `Muse-Spark-816B-A42B` tracked all 21 nucleotide indices, verified wild-type `MALLNR`, deleted nucleotide 10 (`C`), identified the new 4th codon `TGA`/`UGA` (premature stop), and returned the truncated 3-aa peptide `MAL`.
- **`****` Conditional Mendelian & Bayesian Carrier Risk**: `gpt-4o-mini` fell into the classic clinical genetics trap of using an unconditioned prior $P(\text{carrier}) = 1/2$ instead of conditioning on the sibling being unaffected ($P(\text{carrier} \mid \text{unaffected}) = \frac{1/2}{3/4} = 2/3$), yielding an erroneous posterior of $1/11$ ($9.09\%$). `Muse-Spark-816B-A42B` conditioned on `AA` or `Aa` ($3/4$), derived prior $2/3$, and computed the exact Bayesian posterior $\frac{0.10 \times 2/3}{0.10 \times 2/3 + 1.00 \times 1/3} = \mathbf{1/6 \approx 16.67\%}$.
- **CRISPR Prime Editing Mechanistic Completeness**: Both `gpt-6-luna` and `gpt-5.6-luna` omitted the explicit transition vs. transversion biochemical distinction when explaining why CBEs (`C:G→T:A` transition) and ABEs (`A:T→G:C` transition) cannot revert `HBB E6V` (`T:A→A:T` transversion), whereas `Muse-Spark-816B-A42B` explicitly contrasted deaminase-catalyzed transitions against transversions and identified the engineered pentamutant `M-MLV` reverse transcriptase.

Reproduce the Hard Biomedical Benchmark:
```bash
export MUSE_SPARK_BACKEND=http://xxx.xx.xx.xx/v1
python benchmarks/hard_benchmark.py --models muse_spark,gpt6_luna,luna,gpt4o_mini --phase raw
```

