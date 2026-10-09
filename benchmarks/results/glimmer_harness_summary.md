# Muse-Glimmer-30B vs gpt-5.6-luna

- Glimmer endpoint: `http://xxx.xx.xx.xx/v1`
- Glimmer model: `Muse-Glimmer-30B`
- Luna model: `gpt-5.6-luna`
- Date: 2026-09-11 12:21 CDT

## Aggregate

| Model            | Raw mean lat   | Raw accuracy   | Gen tok/s   | TTFT   | Agent mean lat   | Agent accuracy   |
|------------------|----------------|----------------|-------------|--------|------------------|------------------|
| Muse-Glimmer-30B | n/a            | n/a            | n/a         | n/a    | 8.19s            | 95.0%            |

## Raw knowledge (no tools)

| Task   | Model   | Latency   | Accuracy   | Compl. toks   | Reason toks   | tok/s   | Status   |
|--------|---------|-----------|------------|---------------|---------------|---------|----------|

## Biomni-Plus agent tasks

| Task                                                 | Model            | Latency   | Accuracy   | Status   | Error   |
|------------------------------------------------------|------------------|-----------|------------|----------|---------|
| Genomics: UniProt P04637 / TP53                      | Muse-Glimmer-30B | 13.50s    | 100%       | Passed   |         |
| AD Risk: APOE4 Isoform & Chromosome                  | Muse-Glimmer-30B | 5.99s     | 100%       | Passed   |         |
| LabBench QA: RNA-targeting Cas Enzyme                | Muse-Glimmer-30B | 3.06s     | 100%       | Passed   |         |
| Chemoinformatics: Imatinib Molecular Formula         | Muse-Glimmer-30B | 7.83s     | 100%       | Passed   |         |
| Bioinformatics Code: DNA Transcription & Translation | Muse-Glimmer-30B | 10.57s    | 75%        | Passed   |         |
