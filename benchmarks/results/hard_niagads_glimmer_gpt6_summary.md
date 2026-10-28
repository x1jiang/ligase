# Hard Biomedical Reasoning Benchmark

- Endpoint: `http://xxx.xx.xx.xx/v1`
- Spark Model: `meta-models/Muse-Spark-Open-816B-A42B`

| Hard Task                                                                  | Model            | Mode         | Latency   | Strict Rubric Score   |
|----------------------------------------------------------------------------|------------------|--------------|-----------|-----------------------|
| Pharmacogenomics: CYP2C19*2/*3 & Clopidogrel Bioactivation                 | Muse-Glimmer-30B | Raw          | 4.02s     | 6/6 (100%)            |
| Pharmacogenomics: CYP2C19*2/*3 & Clopidogrel Bioactivation                 | Muse-Glimmer-30B | Ligase Agent | 5.89s     | 6/6 (100%)            |
| Pharmacogenomics: CYP2C19*2/*3 & Clopidogrel Bioactivation                 | gpt-6-luna       | Raw          | 3.07s     | 6/6 (100%)            |
| Pharmacogenomics: CYP2C19*2/*3 & Clopidogrel Bioactivation                 | gpt-6-luna       | Ligase Agent | 10.31s    | 6/6 (100%)            |
| Structural Oncology: BCR-ABL1 T315I Gatekeeper & STAMP Inhibition          | Muse-Glimmer-30B | Raw          | 9.46s     | 6/6 (100%)            |
| Structural Oncology: BCR-ABL1 T315I Gatekeeper & STAMP Inhibition          | Muse-Glimmer-30B | Ligase Agent | 11.21s    | 6/6 (100%)            |
| Structural Oncology: BCR-ABL1 T315I Gatekeeper & STAMP Inhibition          | gpt-6-luna       | Raw          | 4.69s     | 6/6 (100%)            |
| Structural Oncology: BCR-ABL1 T315I Gatekeeper & STAMP Inhibition          | gpt-6-luna       | Ligase Agent | 12.18s    | 6/6 (100%)            |
| AD Protective Genetics: APOE3 Christchurch & RELN-COLBOS Epistasis         | Muse-Glimmer-30B | Raw          | 5.04s     | 5/6 (83%)             |
| AD Protective Genetics: APOE3 Christchurch & RELN-COLBOS Epistasis         | Muse-Glimmer-30B | Ligase Agent | 7.69s     | 6/6 (100%)            |
| AD Protective Genetics: APOE3 Christchurch & RELN-COLBOS Epistasis         | gpt-6-luna       | Raw          | 4.96s     | 6/6 (100%)            |
| AD Protective Genetics: APOE3 Christchurch & RELN-COLBOS Epistasis         | gpt-6-luna       | Ligase Agent | 14.10s    | 6/6 (100%)            |
| Coding Frameshift Math: Single-Nucleotide Deletion & Premature Stop        | Muse-Glimmer-30B | Raw          | 8.71s     | 6/6 (100%)            |
| Coding Frameshift Math: Single-Nucleotide Deletion & Premature Stop        | Muse-Glimmer-30B | Ligase Agent | 5.16s     | 6/6 (100%)            |
| Coding Frameshift Math: Single-Nucleotide Deletion & Premature Stop        | gpt-6-luna       | Raw          | 3.54s     | 6/6 (100%)            |
| Coding Frameshift Math: Single-Nucleotide Deletion & Premature Stop        | gpt-6-luna       | Ligase Agent | 5.14s     | 6/6 (100%)            |
| CRISPR Engineering: HBB E6V Transversion & pegRNA Architecture             | Muse-Glimmer-30B | Raw          | 6.03s     | 6/6 (100%)            |
| CRISPR Engineering: HBB E6V Transversion & pegRNA Architecture             | Muse-Glimmer-30B | Ligase Agent | 6.64s     | 6/6 (100%)            |
| CRISPR Engineering: HBB E6V Transversion & pegRNA Architecture             | gpt-6-luna       | Raw          | 6.28s     | 5/6 (83%)             |
| CRISPR Engineering: HBB E6V Transversion & pegRNA Architecture             | gpt-6-luna       | Ligase Agent | 5.69s     | 4/6 (67%)             |
| Quantitative Clinical Genetics: HWE & Bayesian Posterior Carrier Risk      | Muse-Glimmer-30B | Raw          | 6.56s     | 6/6 (100%)            |
| Quantitative Clinical Genetics: HWE & Bayesian Posterior Carrier Risk      | Muse-Glimmer-30B | Ligase Agent | 4.55s     | 6/6 (100%)            |
| Quantitative Clinical Genetics: HWE & Bayesian Posterior Carrier Risk      | gpt-6-luna       | Raw          | 3.69s     | 6/6 (100%)            |
| Quantitative Clinical Genetics: HWE & Bayesian Posterior Carrier Risk      | gpt-6-luna       | Ligase Agent | 4.99s     | 6/6 (100%)            |
| NIAGADS Functional Genomics: FILER Microglial Enhancers & TREM2/PLCG2/ABI3 | Muse-Glimmer-30B | Raw          | 10.59s    | 4/6 (67%)             |
| NIAGADS Functional Genomics: FILER Microglial Enhancers & TREM2/PLCG2/ABI3 | Muse-Glimmer-30B | Ligase Agent | 8.84s     | 6/6 (100%)            |
| NIAGADS Functional Genomics: FILER Microglial Enhancers & TREM2/PLCG2/ABI3 | gpt-6-luna       | Raw          | 22.59s    | 5/6 (83%)             |
| NIAGADS Functional Genomics: FILER Microglial Enhancers & TREM2/PLCG2/ABI3 | gpt-6-luna       | Ligase Agent | 25.23s    | 6/6 (100%)            |
| NIAGADS Multi-Ancestry ADSP: ABCA7 Loss-of-Function & VCPA/FAVOR           | Muse-Glimmer-30B | Raw          | 12.36s    | 4/6 (67%)             |
| NIAGADS Multi-Ancestry ADSP: ABCA7 Loss-of-Function & VCPA/FAVOR           | Muse-Glimmer-30B | Ligase Agent | 8.99s     | 6/6 (100%)            |
| NIAGADS Multi-Ancestry ADSP: ABCA7 Loss-of-Function & VCPA/FAVOR           | gpt-6-luna       | Raw          | 18.41s    | 4/6 (67%)             |
| NIAGADS Multi-Ancestry ADSP: ABCA7 Loss-of-Function & VCPA/FAVOR           | gpt-6-luna       | Ligase Agent | 33.42s    | 4/6 (67%)             |
| NIAGADS Primary 4R-Tauopathy: PSP WGS (NG00169/NG00172), APOE e2 & MAPT SV | Muse-Glimmer-30B | Raw          | 9.21s     | 6/6 (100%)            |
| NIAGADS Primary 4R-Tauopathy: PSP WGS (NG00169/NG00172), APOE e2 & MAPT SV | Muse-Glimmer-30B | Ligase Agent | 6.55s     | 6/6 (100%)            |
| NIAGADS Primary 4R-Tauopathy: PSP WGS (NG00169/NG00172), APOE e2 & MAPT SV | gpt-6-luna       | Raw          | 17.77s    | 6/6 (100%)            |
| NIAGADS Primary 4R-Tauopathy: PSP WGS (NG00169/NG00172), APOE e2 & MAPT SV | gpt-6-luna       | Ligase Agent | 20.56s    | 6/6 (100%)            |
