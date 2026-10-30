"""Live client and ClawAgents tool integration for the NIAGADS Open Access API v2.0.

Wraps the public endpoints documented at https://api.niagads.org/open-access
(OpenAPI v2.0 specification at https://api.niagads.org/api/openapi) together with
live FILER hg38 interval overlap counts (https://tf.lisanwanglab.org/FILER/).
"""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

NIAGADS_PORTAL_URL = "https://api.niagads.org/open-access"
NIAGADS_DOCS_URL = "https://api.niagads.org/docs"
NIAGADS_OPENAPI_URL = "https://api.niagads.org/api/openapi"
NIAGADS_API_BASE = os.getenv("NIAGADS_API_BASE", "https://api.niagads.org/api").rstrip("/")
FILER_OVERLAP_URL = "https://tf.lisanwanglab.org/FILER/get_overlapping_tracks_by_coord.php"

_UA = "Ligase/0.3.2 (+https://github.com/x1jiang/ligase; Biomedical & NIAGADS Co-Scientist)"
_DEFAULT_TIMEOUT_S = float(os.getenv("NIAGADS_API_TIMEOUT", "12.0"))
_CACHE_TTL_S = 300.0
_CACHE_MAX_SIZE = 256

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Tuple[float, Any]] = {}

_RSID_RE = re.compile(r"^rs\d+$", re.I)
_ENSEMBL_GENE_RE = re.compile(r"^ENSG\d{8,}$", re.I)
_TRACK_ID_RE = re.compile(r"^NG\d{5}_[A-Z0-9_]+$", re.I)
_REGION_RE = re.compile(r"^(?:chr)?([0-9]{1,2}|X|Y|M|MT):([\d,]+)-([\d,]+)$", re.I)
_POS_VARIANT_COLON_RE = re.compile(
    r"^(?:chr)?([0-9]{1,2}|X|Y|M|MT):(\d+):([ACGTN]+):([ACGTN]+)$",
    re.I,
)
_POS_VARIANT_HGVS_RE = re.compile(
    r"^(?:chr)?([0-9]{1,2}|X|Y|M|MT):(\d+)([ACGTN]+)>([ACGTN]+)$",
    re.I,
)
_GENE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,14}$")


OPEN_ACCESS_ROLLOUT_CATALOG: Dict[str, Any] = {
    "portal_url": NIAGADS_PORTAL_URL,
    "docs_url": NIAGADS_DOCS_URL,
    "openapi_url": NIAGADS_OPENAPI_URL,
    "api_base": NIAGADS_API_BASE,
    "api_version": "2.0.0",
    "resources": [
        {
            "id": "genomicsdb-queries",
            "name": "Alzheimer's GenomicsDB Queries",
            "status": "available",
            "badge": "Available Now · v2.0",
            "url": "https://www.niagads.org/genomics",
            "description": "Annotated GRCh38 genes, variants, genomic regions (<100 kb), exon structures, and AD/ADRD GWAS summary-statistic associations.",
        },
        {
            "id": "adsp-r5-snvs",
            "name": "ADSP Release 5 SNVs",
            "status": "available",
            "badge": "Available Now · v2.0",
            "url": "https://www.niagads.org/genomics",
            "description": "Single-nucleotide variants from ADSP Release 5 WGS with GA4GH VRS digests, MANE consequences, and multi-cohort allele frequencies.",
        },
        {
            "id": "adsp-r5-indels",
            "name": "ADSP Release 5 INDELs",
            "status": "available",
            "badge": "Available Now · v2.0",
            "url": "https://www.niagads.org/genomics",
            "description": "Annotated short insertions and deletions from ADSP Release 5 WGS integrated into variant and region endpoints.",
        },
        {
            "id": "gvc-topgenes",
            "name": "ADSP GVC TopGenes",
            "status": "available",
            "badge": "Available Now · v2.0",
            "url": "https://topgenes.niagads.org/",
            "description": "Expert-reviewed genetic evidence for AD/ADRD risk genes curated by the ADSP Gene Verification Committee (`associated_with_known_ad_locus`).",
        },
        {
            "id": "filer-live",
            "name": "FILER Functional Genomics (58k+ Tracks)",
            "status": "partner_live",
            "badge": "Live Partner API + Catalog",
            "url": "https://tf.lisanwanglab.org/FILER/",
            "description": "Giggle-indexed harmonized human regulatory tracks (ENCODE, Roadmap, brain/microglia ATAC & ChIP-seq) queried via live coordinate overlap.",
        },
        {
            "id": "advp",
            "name": "Alzheimer's Disease Variant Portal (ADVP)",
            "status": "staged_catalog",
            "badge": "Curated in Ligase · API Rollout Next",
            "url": "https://advp.niagads.org/",
            "description": "Literature-curated ADRD genetic associations across multi-ancestry risk, CSF ATN biomarkers, and neuropathology.",
        },
        {
            "id": "adsp-r5-sv",
            "name": "ADSP R5 Structural Variants & PSP SV-WGS",
            "status": "staged_catalog",
            "badge": "Curated in Ligase · API Rollout Next",
            "url": "https://dss.niagads.org/datasets/ng00172/",
            "description": "Structural variants including the 17q21.31 MAPT ~900 kb H1/H2 inversion in PSP WGS (NG00169/NG00172) and AMP-AD SV-xQTL (NG00118).",
        },
        {
            "id": "fungen-xqtls",
            "name": "ADSP FunGen xQTL & MiGA Microglia Atlas",
            "status": "staged_catalog",
            "badge": "Curated in Ligase (NG00105) · API Following",
            "url": "https://xqtl.niagads.org/",
            "description": "Brain tissue and cell-type molecular QTLs and fine-mapping credible sets across microglia (NG00105), brain/CSF/plasma pQTLs (NG00102/NG00180).",
        },
    ],
    "endpoints": [
        {
            "action": "gene",
            "method": "GET",
            "path": "/record/gene/{gene}",
            "summary": "Canonical Gene Record & GVC TopGenes Status",
            "example_target": "APOE",
            "description": "Returns Ensembl/HGNC/UniProt/RefSeq xrefs, GRCh38 coordinates, AD locus flag, and KEGG/Reactome/GO pathway memberships.",
        },
        {
            "action": "gene_associations",
            "method": "GET",
            "path": "/record/gene/{gene}/associations",
            "summary": "Gene-Level AD/ADRD GWAS & ADSP Associations",
            "example_target": "BIN1",
            "description": "Retrieves variant-level p-values, effect directions, and HANCESTRO/DOID population ontology terms across NIAGADS tracks.",
        },
        {
            "action": "gene_structure",
            "method": "GET",
            "path": "/record/gene/{gene}/structure",
            "summary": "Gene Transcript & Exon Structure",
            "example_target": "TREM2",
            "description": "Returns canonical GRCh38 transcripts (ENST) and ranked exon coordinates (ENSE).",
        },
        {
            "action": "variant",
            "method": "GET",
            "path": "/record/variant/{variant}",
            "summary": "Variant Record (ADSP R5 SNV/INDEL & GA4GH VRS)",
            "example_target": "rs429358",
            "description": "Returns GA4GH VRS allele digest, ADSP R5 status, MANE Select coding/protein consequence, and ALFA/gnomAD/TOPMed/1000G frequencies.",
        },
        {
            "action": "variant_associations",
            "method": "GET",
            "path": "/record/variant/{variant}/associations",
            "summary": "Variant GWAS & WGS Summary-Statistic Associations",
            "example_target": "rs6733839",
            "description": "Retrieves live GWAS/WGS association p-values, effect alleles, directions, and cohort ancestry metadata for a RefSNP or positional variant.",
        },
        {
            "action": "region_associations",
            "method": "GET",
            "path": "/record/region/{region}/associations",
            "summary": "Genomic Region Associations (<100 kb)",
            "example_target": "chr2:127134000-127136000",
            "description": "Queries all AD/ADRD association signals within a genomic window up to 100,000 bp.",
        },
        {
            "action": "region_variants",
            "method": "GET",
            "path": "/record/region/{region}/variants",
            "summary": "Genomic Region ADSP R5 Variants (<100 kb)",
            "example_target": "chr19:44908500-44909000",
            "description": "Lists ordered SNVs, short insertions, and INDELs (with ADSP variant flags) across a genomic interval.",
        },
        {
            "action": "track",
            "method": "GET",
            "path": "/record/track/{track}",
            "summary": "NIAGADS Open Access Track Metadata",
            "example_target": "NG00166_04BE648F_STD_OA",
            "description": "Retrieves cohort provenance, study design, genome build, and phenotype ontology terms for a NIAGADS track.",
        },
        {
            "action": "track_data",
            "method": "GET",
            "path": "/record/track/{track}/data",
            "summary": "Slice Track Summary Statistics by Locus",
            "example_target": "NG00166_04BE648F_STD_OA",
            "example_loc": "chr2:127134000-127136000",
            "description": "Extracts live summary-statistic rows from a specific NIAGADS GWAS/WGS track within `loc`.",
        },
        {
            "action": "search",
            "method": "GET",
            "path": "/query",
            "summary": "Semantic Search Across NIAGADS Tracks & Genes",
            "example_target": "cognitive resilience",
            "description": "Full-text and semantic search across NIAGADS Open Access tracks, cohorts, phenotypes, and genes.",
        },
        {
            "action": "search_tracks",
            "method": "GET",
            "path": "/query/tracks",
            "summary": "Search NIAGADS GWAS / WGS / Endophenotype Tracks",
            "example_target": "African American",
            "description": "Finds open-access summary-statistic tracks matching ancestry, cohort, author, or biomarker keywords.",
        },
        {
            "action": "search_genes",
            "method": "GET",
            "path": "/query/genes",
            "summary": "Search Gene Nomenclature & AD Locus Annotations",
            "example_target": "ABCA7",
            "description": "Searches gene symbols, synonyms, descriptions, and known AD locus flags.",
        },
        {
            "action": "feature",
            "method": "GET",
            "path": "/service/feature",
            "summary": "Genomic Coordinate Resolver",
            "example_target": "APOE",
            "description": "Resolves any gene symbol, Ensembl ID, rsID, or NIAGADS variant ID to 1-based GRCh38 coordinates (with optional flanking bp).",
        },
        {
            "action": "filer_overlap",
            "method": "GET",
            "path": "FILER /get_overlapping_tracks_by_coord.php",
            "summary": "Live FILER hg38 Regulatory Track Overlap Count",
            "example_target": "chr2:127135200-127135300",
            "description": "Counts overlapping harmonized human functional genomics tracks in FILER at any GRCh38 coordinate, rsID, or gene.",
        },
    ],
}


def _ssl_contexts() -> List[Optional[ssl.SSLContext]]:
    contexts: List[Optional[ssl.SSLContext]] = [None]
    try:
        import certifi

        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    allow_insecure = os.getenv("LIGASE_INSECURE_SSL", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if allow_insecure:
        contexts.append(ssl._create_unverified_context())
    return contexts


def clear_niagads_api_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _http_get_json(url: str, timeout: float = _DEFAULT_TIMEOUT_S) -> Any:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(url)
        if cached and (now - cached[0]) < _CACHE_TTL_S:
            return cached[1]

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json",
        },
    )
    last_err: Optional[Exception] = None
    payload: Any = None
    for ctx in _ssl_contexts():
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                payload = json.loads(raw)
                break
        except ssl.SSLError as exc:
            last_err = exc
            continue
        except urllib.error.HTTPError as exc:
            body_preview = ""
            try:
                body_preview = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {exc.code} from {url}: {body_preview or exc.reason}") from exc
        except urllib.error.URLError as exc:
            last_err = exc
            if "CERTIFICATE" not in str(exc).upper() and "SSL" not in str(exc).upper():
                raise
            continue

    if payload is None:
        if last_err:
            raise last_err
        raise RuntimeError(f"Failed to fetch JSON from {url}")

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX_SIZE:
            oldest_key = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest_key, None)
        _CACHE[url] = (now, payload)
    return payload


def normalize_variant_id(raw: str) -> str:
    """Normalize rsIDs and positional variants (e.g. chr2:127135234C>T -> 2:127135234:C:T)."""
    s = (raw or "").strip()
    if _RSID_RE.match(s):
        return s.lower()
    m_colon = _POS_VARIANT_COLON_RE.match(s)
    if m_colon:
        chrom, pos, ref, alt = m_colon.groups()
        return f"{chrom.upper()}:{pos}:{ref.upper()}:{alt.upper()}"
    m_hgvs = _POS_VARIANT_HGVS_RE.match(s)
    if m_hgvs:
        chrom, pos, ref, alt = m_hgvs.groups()
        return f"{chrom.upper()}:{pos}:{ref.upper()}:{alt.upper()}"
    return s


def normalize_region(raw: str, max_span: int = 99_000) -> Tuple[str, Optional[str]]:
    """Normalize genomic region to `chrN:start-end` and clamp >100 kb windows cleanly."""
    s = (raw or "").strip()
    m = _REGION_RE.match(s)
    if not m:
        return s, None
    chrom_raw, start_raw, end_raw = m.groups()
    chrom = chrom_raw.upper()
    if chrom == "MT":
        chrom = "M"
    start = int(start_raw.replace(",", ""))
    end = int(end_raw.replace(",", ""))
    if end < start:
        start, end = end, start
    note: Optional[str] = None
    if (end - start) >= 100_000:
        mid = (start + end) // 2
        half = max_span // 2
        new_start = max(1, mid - half)
        new_end = new_start + max_span
        note = (
            f"Clamped requested {end - start:,} bp interval to {max_span:,} bp centered window "
            f"`chr{chrom}:{new_start}-{new_end}` (NIAGADS region endpoint max is 100,000 bp)."
        )
        start, end = new_start, new_end
    return f"chr{chrom}:{start}-{end}", note


def _trait_summary(traits: Any) -> str:
    if not isinstance(traits, dict):
        return ""
    parts: List[str] = []
    for key in ("disease", "population", "race", "ethnicity", "biomarker", "neuropathology"):
        items = traits.get(key)
        if isinstance(items, list):
            terms = [str(it.get("term")) for it in items if isinstance(it, dict) and it.get("term")]
            if terms:
                parts.append("/".join(terms[:2]))
    return " · ".join(parts)


def _summarize_gene_record(payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    records = payload.get("data") or []
    if not records:
        return "No gene records returned from NIAGADS Open Access API.", []
    lines: List[str] = ["### NIAGADS Open Access Gene Record (GRCh38)"]
    rows: List[Dict[str, Any]] = []
    for rec in records[:8]:
        sym = rec.get("gene_symbol") or rec.get("id") or "?"
        ensg = rec.get("id") or (rec.get("xrefs") or {}).get("ensembl_gene_id") or "?"
        name = rec.get("gene_name") or ""
        loc = rec.get("location") or "?"
        cyto = rec.get("cytogenic_location") or ""
        gtype = rec.get("gene_type") or ""
        ad_flag = rec.get("associated_with_known_ad_locus")
        xrefs = rec.get("xrefs") or {}
        uniprot = xrefs.get("uniprot_id") or "—"
        hgnc = xrefs.get("hgnc_id") or "—"
        entrez = xrefs.get("entrez_id") or "—"
        refseq = xrefs.get("refseq_accession") or "—"

        pathways = ((rec.get("memberships") or {}).get("pathways") or [])[:6]
        pw_str = ", ".join(
            f"{p.get('pathway_name')} ({p.get('data_source')}:{p.get('pathway_id')})"
            for p in pathways
            if isinstance(p, dict) and p.get("pathway_name")
        )
        ad_badge = "Yes (GVC Known AD Locus)" if ad_flag else ("No" if ad_flag is False else "Unspecified")
        lines.append(
            f"- **{sym}** (`{ensg}`){f' — {name}' if name else ''}\n"
            f"  - **Location:** `{loc}` {f'(`{cyto}`)' if cyto else ''} · **Biotype:** `{gtype}` · **Known AD Locus:** **{ad_badge}**\n"
            f"  - **Cross-References:** UniProt `{uniprot}` · HGNC `{hgnc}` · Entrez `{entrez}` · RefSeq `{refseq}`"
        )
        if pw_str:
            lines.append(f"  - **Pathways:** {pw_str}")
        rows.append(
            {
                "gene_symbol": sym,
                "ensembl_id": ensg,
                "location": loc,
                "cytogenetic": cyto or "—",
                "known_ad_locus": ad_badge,
                "uniprot": uniprot,
            }
        )
    return "\n".join(lines), rows


def _summarize_gene_structure(payload: Dict[str, Any], gene: str) -> Tuple[str, List[Dict[str, Any]]]:
    data = payload.get("data") or []
    if not data:
        return f"No transcript structure found for `{gene}`.", []
    first = data[0] if isinstance(data[0], dict) else {}
    loc = first.get("location") or "?"
    transcripts = first.get("transcripts") or []
    lines = [
        f"### NIAGADS GRCh38 Transcript & Exon Structure — `{gene}` (`{loc}`)",
        f"- **Total Transcripts:** {len(transcripts)}",
        "",
        "| Transcript ID | Name | Span | Exon Count | First Exon | Last Exon |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    rows: List[Dict[str, Any]] = []
    for tx in transcripts[:12]:
        if not isinstance(tx, dict):
            continue
        tid = tx.get("id") or "?"
        tname = tx.get("name") or "—"
        tloc = tx.get("location") or "—"
        exons = tx.get("exons") or []
        e_first = exons[0].get("location") if exons and isinstance(exons[0], dict) else "—"
        e_last = exons[-1].get("location") if exons and isinstance(exons[-1], dict) else "—"
        lines.append(f"| `{tid}` | {tname} | `{tloc}` | {len(exons)} | `{e_first}` | `{e_last}` |")
        rows.append(
            {
                "transcript_id": tid,
                "name": tname,
                "location": tloc,
                "exon_count": len(exons),
            }
        )
    return "\n".join(lines), rows


def _summarize_variant_record(payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    records = payload.get("data") or []
    if not records:
        return "No variant records returned from NIAGADS Open Access API.", []
    lines = ["### NIAGADS Open Access Variant Record (ADSP R5 & GA4GH VRS)"]
    rows: List[Dict[str, Any]] = []
    for rec in records[:8]:
        rsid = rec.get("ref_snp_id") or "—"
        vid = rec.get("id") or rec.get("normalized_positional_id") or "?"
        vclass = rec.get("variant_class") or "SNV"
        is_adsp = bool(rec.get("is_adsp_variant"))
        vrs_id = ((rec.get("ga4gh_vrs") or {}).get("id")) or "—"

        msc = rec.get("most_severe_consequence") or {}
        impact = msc.get("impact") or "—"
        terms = ", ".join(msc.get("consequence_terms") or []) if isinstance(msc.get("consequence_terms"), list) else (msc.get("consequence") or "")
        feat = msc.get("feature") or {}
        gene_info = feat.get("gene") or {}
        gene_sym = gene_info.get("gene_symbol") or gene_info.get("id") or "—"
        hgvsc = feat.get("hgvsc") or "—"
        hgvsp = ((feat.get("protein") or {}).get("hgvsp")) or "—"
        if not terms:
            emb = ((rec.get("functional_annotation_summary") or {}).get("embedded_text") or "")
            m_cons = re.search(r"Transcript consequence ([^\n.]+)", emb)
            if m_cons:
                terms = m_cons.group(1)

        freqs = rec.get("allele_frequency") or {}
        alfa = freqs.get("ALFA") if isinstance(freqs, dict) else None
        freq_bits: List[str] = []
        if isinstance(alfa, dict):
            for pop_key in ("GnomAD_genomes", "GnomAD_exomes", "TOPMED", "1000Genomes", "ExAC"):
                if pop_key in alfa and alfa[pop_key] is not None:
                    try:
                        freq_bits.append(f"{pop_key}={float(alfa[pop_key]):.4f}")
                    except (TypeError, ValueError):
                        freq_bits.append(f"{pop_key}={alfa[pop_key]}")

        lines.append(
            f"- **{rsid}** (`{vid}`) · Class: `{vclass}` · **ADSP R5 Variant:** `{'Yes' if is_adsp else 'No'}`\n"
            f"  - **GA4GH VRS:** `{vrs_id}`\n"
            f"  - **Consequence:** {terms or 'non-coding / regulatory'} (Impact: `{impact}`, Gene: `{gene_sym}`, HGVSc: `{hgvsc}`, HGVSp: `{hgvsp}`)"
        )
        if freq_bits:
            lines.append(f"  - **Population Allele Frequencies:** {', '.join(freq_bits)}")

        rows.append(
            {
                "rsid": rsid,
                "variant_id": vid,
                "class": vclass,
                "adsp_r5": "Yes" if is_adsp else "No",
                "gene": gene_sym,
                "consequence": terms or impact,
                "frequencies": ", ".join(freq_bits[:3]) or "—",
            }
        )
    return "\n".join(lines), rows


def _summarize_associations(payload: Dict[str, Any], label: str) -> Tuple[str, List[Dict[str, Any]]]:
    data = payload.get("data") or []
    pagination = payload.get("pagination") or {}
    total = pagination.get("total_records", len(data))
    if not data:
        return f"No genome-wide/open-access associations returned for `{label}` (0 records).", []

    # Summary-mode rows have `num_associations` per track rather than variant rows
    if isinstance(data[0], dict) and "num_associations" in data[0] and "pvalue" not in data[0]:
        lines = [
            f"### NIAGADS Association Track Summary — `{label}` ({total} track groups)",
            "",
            "| Track ID | Associations | Trait / Cohort Ontology |",
            "| :--- | :--- | :--- |",
        ]
        rows: List[Dict[str, Any]] = []
        for item in data[:20]:
            trk = item.get("track") or item.get("track_id") or "?"
            cnt = item.get("num_associations", 0)
            ts = _trait_summary(item.get("traits")) or "AD/ADRD"
            lines.append(f"| `{trk}` | {cnt} | {ts} |")
            rows.append({"track": trk, "num_associations": cnt, "traits": ts})
        return "\n".join(lines), rows

    # Sort full association records by neg_log10_pvalue descending when present
    def _score(r: Dict[str, Any]) -> float:
        try:
            return float(r.get("neg_log10_pvalue") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    sorted_rows = sorted([r for r in data if isinstance(r, dict)], key=_score, reverse=True)
    lines = [
        f"### NIAGADS Open Access Genetic Associations — `{label}` (showing top {min(15, len(sorted_rows))} of {total} total records)",
        "",
        "| Variant | Test Allele | p-value | -log10(p) | Dir | Track ID | Trait & Ancestry |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    rows = []
    for r in sorted_rows[:15]:
        var = r.get("variant") or r.get("ref_snp_id") or "?"
        allele = r.get("test_allele") or r.get("alt") or "—"
        pval = r.get("pvalue") or "—"
        nlog = r.get("neg_log10_pvalue")
        nlog_s = f"{float(nlog):.2f}" if isinstance(nlog, (int, float)) else str(nlog or "—")
        direction = r.get("effect_direction") or "—"
        trk = r.get("track") or r.get("track_id") or "—"
        ts = _trait_summary(r.get("traits")) or "AD/ADRD"
        lines.append(f"| `{var}` | `{allele}` | `{pval}` | {nlog_s} | `{direction}` | `{trk}` | {ts} |")
        rows.append(
            {
                "variant": var,
                "test_allele": allele,
                "pvalue": str(pval),
                "neg_log10_p": nlog_s,
                "direction": direction,
                "track": trk,
                "traits": ts,
            }
        )
    return "\n".join(lines), rows


def _summarize_region_variants(payload: Dict[str, Any], region: str) -> Tuple[str, List[Dict[str, Any]]]:
    data = payload.get("data") or []
    pagination = payload.get("pagination") or {}
    total = pagination.get("total_records", len(data))
    if not data:
        return f"No variants found in region `{region}`.", []
    adsp_count = sum(1 for r in data if isinstance(r, dict) and r.get("is_adsp_variant"))
    lines = [
        f"### NIAGADS Region Variants — `{region}` ({total} total in page={pagination.get('page', 1)}; {adsp_count}/{len(data)} flagged ADSP R5 on this page)",
        "",
        "| RefSNP | Positional / NIAGADS ID | Class | ADSP R5 | Most Severe Consequence |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    rows: List[Dict[str, Any]] = []
    # Prioritize ADSP variants and rsID-bearing variants in the preview table
    ranked = sorted(
        [r for r in data if isinstance(r, dict)],
        key=lambda x: (1 if x.get("is_adsp_variant") else 0, 1 if x.get("ref_snp_id") else 0),
        reverse=True,
    )
    for r in ranked[:15]:
        rsid = r.get("ref_snp_id") or "—"
        vid = r.get("id") or "?"
        vcls = r.get("variant_class") or "SNV"
        adsp = "Yes" if r.get("is_adsp_variant") else "No"
        msc = r.get("most_severe_consequence")
        if isinstance(msc, dict):
            cons = ", ".join(msc.get("consequence_terms") or []) or msc.get("impact") or "—"
        else:
            cons = str(msc or "—")
        lines.append(f"| `{rsid}` | `{vid}` | `{vcls}` | {adsp} | {cons} |")
        rows.append(
            {
                "rsid": rsid,
                "variant_id": vid,
                "class": vcls,
                "adsp_r5": adsp,
                "consequence": cons,
            }
        )
    return "\n".join(lines), rows


def _summarize_tracks(payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    data = payload.get("data") or []
    if not data:
        return "No track metadata records returned.", []
    lines = ["### NIAGADS Open Access Track Metadata"]
    rows: List[Dict[str, Any]] = []
    for t in data[:10]:
        if not isinstance(t, dict):
            continue
        tid = t.get("id") or "?"
        name = t.get("name") or t.get("label") or "Unnamed Track"
        build = t.get("genome_build") or "GRCh38"
        desc = (t.get("description") or "").strip()
        prov = t.get("provenance") or {}
        accession = prov.get("study_accession") or tid.split("_")[0]
        lines.append(
            f"- **`{tid}`** — **{name}** (`{build}`, Study `{accession}`)\n"
            f"  - {desc[:360]}"
        )
        rows.append(
            {
                "track_id": tid,
                "study": accession,
                "genome_build": build,
                "name": name,
                "description": desc[:200],
            }
        )
    return "\n".join(lines), rows


def _summarize_search(payload: Dict[str, Any], query_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    data = payload.get("data") or []
    pagination = payload.get("pagination") or {}
    total = pagination.get("total_records", len(data))
    if not data:
        return f"No NIAGADS Open Access search matches for `{query_text}`.", []
    lines = [
        f"### NIAGADS Open Access Semantic Search — `{query_text}` ({total} matches)",
        "",
        "| ID | Type | Label | Summary |",
        "| :--- | :--- | :--- | :--- |",
    ]
    rows: List[Dict[str, Any]] = []
    for item in data[:15]:
        if not isinstance(item, dict):
            continue
        rec_id = item.get("id") or "?"
        rtype = item.get("matched_record_type") or "RECORD"
        details = item.get("matched_record_details") or {}
        label = details.get("label") or rec_id
        desc = (details.get("description") or "").replace("\n", " ").strip()
        annot = details.get("annotation")
        if isinstance(annot, dict) and annot.get("location"):
            desc = f"[{annot.get('location')}] {desc}".strip()
        lines.append(f"| `{rec_id}` | `{rtype}` | **{label}** | {desc[:180]} |")
        rows.append(
            {
                "id": rec_id,
                "type": rtype,
                "label": label,
                "description": desc[:220],
            }
        )
    return "\n".join(lines), rows


def resolve_feature_coords(feature_id: str, flank: int = 0) -> Dict[str, Any]:
    fid = urllib.parse.quote((feature_id or "").strip(), safe=":")
    flank_clamped = max(0, min(1_000_000, int(flank or 0)))
    url = f"{NIAGADS_API_BASE}/service/feature?id={fid}&flank={flank_clamped}"
    return _http_get_json(url)


def query_filer_overlap_count(region_or_feature: str) -> Dict[str, Any]:
    """Query live FILER hg38 overlapping functional genomics track count."""
    norm_reg, clamp_note = normalize_region(region_or_feature, max_span=50_000)
    if not _REGION_RE.match(norm_reg):
        coords = resolve_feature_coords(region_or_feature, flank=250)
        chrom = str(coords.get("chr") or "").lstrip("chr")
        start = int(coords.get("start") or 0)
        end = int(coords.get("end") or start)
        if end <= start:
            start = max(1, start - 250)
            end = end + 250
        norm_reg = f"chr{chrom}:{start}-{end}"

    url = (
        f"{FILER_OVERLAP_URL}?genomeBuild=hg38&region="
        f"{urllib.parse.quote(norm_reg, safe=':-')}&outputFormat=json"
    )
    arr = _http_get_json(url)
    track_hits = len(arr) if isinstance(arr, list) else 0
    total_intervals = (
        sum(int(item.get("numOverlaps", 0)) for item in arr if isinstance(item, dict))
        if isinstance(arr, list)
        else 0
    )
    return {
        "region": norm_reg,
        "overlapping_tracks": track_hits,
        "overlapping_intervals": total_intervals,
        "note": clamp_note,
    }


def execute_niagads_action(
    *,
    action: str = "auto",
    target: str = "",
    loc: str = "",
    flank: int = 0,
    content: str = "full",
    limit: int = 10,
    page: int = 1,
) -> Dict[str, Any]:
    """Execute a structured NIAGADS Open Access API v2.0 query and return both Markdown & JSON."""
    act = (action or "auto").strip().lower()
    tgt = (target or "").strip()
    loc_clean = (loc or "").strip()
    content_mode = content if content in ("full", "summary", "ids") else "full"
    assoc_content = "summary" if content == "summary" else "full"
    page_num = max(1, min(100, int(page or 1)))
    limit_num = max(1, min(50, int(limit or 10)))
    flank_bp = max(0, min(1_000_000, int(flank or 0)))

    if not tgt and loc_clean:
        tgt = loc_clean

    if not tgt:
        return {
            "ok": False,
            "action": act,
            "endpoint": "",
            "request_id": None,
            "elapsed_ms": 0,
            "summary_markdown": "error: `target` (gene symbol, rsID, region `chrN:start-end`, track ID, or search phrase) is required.",
            "rows": [],
            "raw": None,
        }

    t0 = time.monotonic()

    try:
        # Auto-routing across all NIAGADS Open Access v2.0 entity types
        if act == "auto":
            norm_v = normalize_variant_id(tgt)
            if _RSID_RE.match(norm_v) or _POS_VARIANT_COLON_RE.match(norm_v):
                v_url = f"{NIAGADS_API_BASE}/record/variant/{urllib.parse.quote(norm_v, safe=':')}?content=full"
                a_url = f"{NIAGADS_API_BASE}/record/variant/{urllib.parse.quote(norm_v, safe=':')}/associations?content=full&flank={flank_bp}&page={page_num}"
                v_payload = _http_get_json(v_url)
                v_md, v_rows = _summarize_variant_record(v_payload)
                sections = [v_md]
                combined_rows = list(v_rows)
                a_payload: Dict[str, Any] = {}
                try:
                    a_payload = _http_get_json(a_url)
                    a_md, a_rows = _summarize_associations(a_payload, norm_v)
                    sections.append(a_md)
                    if a_rows:
                        combined_rows = a_rows
                except Exception as assoc_exc:
                    sections.append(f"_Association lookup note: {assoc_exc}_")

                # Add live FILER hg38 regulatory track overlap at variant coordinate
                v_first = (v_payload.get("data") or [{}])[0]
                if isinstance(v_first, dict) and v_first.get("chromosome") and v_first.get("position"):
                    pos = int(v_first["position"])
                    chrom = str(v_first["chromosome"]).lstrip("chr")
                    try:
                        filer_info = query_filer_overlap_count(f"chr{chrom}:{max(1, pos - 250)}-{pos + 250}")
                        sections.append(
                            f"### Live FILER Functional Genomics Overlap (`{filer_info['region']}`, GRCh38)\n"
                            f"- **Overlapping Harmonized Regulatory Tracks:** **{filer_info['overlapping_tracks']:,}** "
                            f"({filer_info['overlapping_intervals']:,} intervals across ENCODE/Roadmap/brain/immune tracks)"
                        )
                    except Exception:
                        pass

                elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))
                req_id = ((v_payload.get("request") or {}).get("request_id"))
                return {
                    "ok": True,
                    "action": "auto_variant",
                    "endpoint": f"/record/variant/{norm_v} + /associations",
                    "request_id": req_id,
                    "elapsed_ms": elapsed_ms,
                    "summary_markdown": "\n\n".join(sections),
                    "rows": combined_rows,
                    "raw": {"variant": v_payload, "associations": a_payload},
                }

            if _REGION_RE.match(tgt):
                reg_str, reg_note = normalize_region(tgt)
                r_url = f"{NIAGADS_API_BASE}/record/region/{urllib.parse.quote(reg_str, safe=':-')}/associations?content={assoc_content}&page={page_num}"
                v_url = f"{NIAGADS_API_BASE}/record/region/{urllib.parse.quote(reg_str, safe=':-')}/variants?content=summary&page=1"
                r_payload = _http_get_json(r_url)
                r_md, r_rows = _summarize_associations(r_payload, reg_str)
                sections = ([f"> {reg_note}"] if reg_note else []) + [r_md]
                try:
                    rv_payload = _http_get_json(v_url)
                    rv_md, _ = _summarize_region_variants(rv_payload, reg_str)
                    sections.append(rv_md)
                except Exception:
                    rv_payload = {}
                elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))
                return {
                    "ok": True,
                    "action": "auto_region",
                    "endpoint": f"/record/region/{reg_str}/associations",
                    "request_id": ((r_payload.get("request") or {}).get("request_id")),
                    "elapsed_ms": elapsed_ms,
                    "summary_markdown": "\n\n".join(sections),
                    "rows": r_rows,
                    "raw": {"associations": r_payload, "variants_summary": rv_payload},
                }

            if _TRACK_ID_RE.match(tgt):
                act = "track_data" if loc_clean else "track"
            elif _ENSEMBL_GENE_RE.match(tgt) or (_GENE_SYMBOL_RE.match(tgt.upper()) and " " not in tgt and len(tgt) <= 12):
                g_sym = tgt.upper()
                g_url = f"{NIAGADS_API_BASE}/record/gene/{urllib.parse.quote(g_sym)}?content=full"
                ga_url = f"{NIAGADS_API_BASE}/record/gene/{urllib.parse.quote(g_sym)}/associations?content=full&flank={flank_bp}&page={page_num}"
                try:
                    g_payload = _http_get_json(g_url)
                    g_md, g_rows = _summarize_gene_record(g_payload)
                    sections = [g_md]
                    ga_payload: Dict[str, Any] = {}
                    try:
                        ga_payload = _http_get_json(ga_url)
                        ga_md, ga_rows = _summarize_associations(ga_payload, g_sym)
                        sections.append(ga_md)
                        if ga_rows:
                            g_rows = ga_rows
                    except Exception:
                        pass
                    elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))
                    return {
                        "ok": True,
                        "action": "auto_gene",
                        "endpoint": f"/record/gene/{g_sym} + /associations",
                        "request_id": ((g_payload.get("request") or {}).get("request_id")),
                        "elapsed_ms": elapsed_ms,
                        "summary_markdown": "\n\n".join(sections),
                        "rows": g_rows,
                        "raw": {"gene": g_payload, "associations": ga_payload},
                    }
                except Exception:
                    # Not an exact gene ID; fall through to semantic search
                    act = "search"
            else:
                act = "search"

        # Explicit action dispatch
        if act == "gene":
            if "," in tgt:
                ids_q = urllib.parse.quote(tgt)
                endpoint = f"/record/gene/?ids={ids_q}&content={content_mode}&page={page_num}"
            else:
                endpoint = f"/record/gene/{urllib.parse.quote(tgt.upper())}?content={content_mode}"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_gene_record(payload)

        elif act == "gene_associations":
            endpoint = (
                f"/record/gene/{urllib.parse.quote(tgt.upper())}/associations"
                f"?content={assoc_content}&flank={flank_bp}&page={page_num}"
            )
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_associations(payload, tgt.upper())

        elif act == "gene_structure":
            endpoint = f"/record/gene/{urllib.parse.quote(tgt.upper())}/structure"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_gene_structure(payload, tgt.upper())

        elif act == "variant":
            if "," in tgt:
                norm_ids = ",".join(normalize_variant_id(x) for x in tgt.split(",") if x.strip())
                endpoint = f"/record/variant/?ids={urllib.parse.quote(norm_ids, safe=',:')}&content={content_mode}&page={page_num}"
            else:
                norm_v = normalize_variant_id(tgt)
                endpoint = f"/record/variant/{urllib.parse.quote(norm_v, safe=':')}?content={content_mode}"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_variant_record(payload)

        elif act == "variant_associations":
            norm_v = normalize_variant_id(tgt)
            endpoint = (
                f"/record/variant/{urllib.parse.quote(norm_v, safe=':')}/associations"
                f"?content={assoc_content}&flank={flank_bp}&page={page_num}"
            )
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_associations(payload, norm_v)

        elif act == "region_associations":
            reg_str, reg_note = normalize_region(tgt)
            if not _REGION_RE.match(reg_str):
                coords = resolve_feature_coords(tgt, flank=max(flank_bp, 25_000))
                reg_str, reg_note = normalize_region(f"{coords['chr']}:{coords['start']}-{coords['end']}")
            endpoint = (
                f"/record/region/{urllib.parse.quote(reg_str, safe=':-')}/associations"
                f"?content={assoc_content}&page={page_num}"
            )
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_associations(payload, reg_str)
            if reg_note:
                md = f"> {reg_note}\n\n{md}"

        elif act == "region_variants":
            reg_str, reg_note = normalize_region(tgt)
            if not _REGION_RE.match(reg_str):
                coords = resolve_feature_coords(tgt, flank=max(flank_bp, 5_000))
                reg_str, reg_note = normalize_region(f"{coords['chr']}:{coords['start']}-{coords['end']}")
            endpoint = (
                f"/record/region/{urllib.parse.quote(reg_str, safe=':-')}/variants"
                f"?content={'summary' if content_mode != 'full' else 'full'}&page={page_num}"
            )
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_region_variants(payload, reg_str)
            if reg_note:
                md = f"> {reg_note}\n\n{md}"

        elif act == "track":
            if "," in tgt:
                endpoint = f"/record/track/?ids={urllib.parse.quote(tgt)}&content={content_mode}&page={page_num}"
            else:
                endpoint = f"/record/track/{urllib.parse.quote(tgt)}?content={content_mode}"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_tracks(payload)

        elif act == "track_data":
            if not loc_clean:
                raise ValueError("`loc` (e.g. `chr2:127134000-127136000` or gene symbol) is required for `track_data`.")
            reg_str, reg_note = normalize_region(loc_clean)
            if not _REGION_RE.match(reg_str):
                coords = resolve_feature_coords(loc_clean, flank=max(flank_bp, 25_000))
                reg_str, reg_note = normalize_region(f"{coords['chr']}:{coords['start']}-{coords['end']}")
            endpoint = (
                f"/record/track/{urllib.parse.quote(tgt)}/data"
                f"?loc={urllib.parse.quote(reg_str, safe=':-')}&content={assoc_content}&page={page_num}"
            )
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_associations(payload, f"{tgt} @ {reg_str}")
            if reg_note:
                md = f"> {reg_note}\n\n{md}"

        elif act == "search":
            endpoint = f"/query?text={urllib.parse.quote(tgt)}&limit={limit_num}&page={page_num}"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_search(payload, tgt)

        elif act == "search_tracks":
            endpoint = f"/query/tracks?text={urllib.parse.quote(tgt)}&limit={limit_num}&page={page_num}"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_search(payload, tgt)

        elif act == "search_genes":
            endpoint = f"/query/genes?text={urllib.parse.quote(tgt)}&limit={limit_num}&page={page_num}"
            payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
            md, rows = _summarize_search(payload, tgt)

        elif act == "search_variants":
            norm_v = normalize_variant_id(tgt)
            if _RSID_RE.match(norm_v) or _POS_VARIANT_COLON_RE.match(norm_v):
                return execute_niagads_action(
                    action="variant",
                    target=norm_v,
                    content=content_mode,
                    page=page_num,
                )
            if _REGION_RE.match(tgt):
                return execute_niagads_action(
                    action="region_variants",
                    target=tgt,
                    content=content_mode,
                    page=page_num,
                )
            endpoint = f"/query/variants?text={urllib.parse.quote(tgt)}&limit={limit_num}&page={page_num}"
            try:
                payload = _http_get_json(f"{NIAGADS_API_BASE}{endpoint}")
                md, rows = _summarize_search(payload, tgt)
            except Exception:
                # Upstream /query/variants is currently unimplemented on api.niagads.org;
                # fall back to resolving feature coordinates + region variants.
                coords = resolve_feature_coords(tgt, flank=2_500)
                reg = f"{coords['chr']}:{coords['start']}-{coords['end']}"
                return execute_niagads_action(
                    action="region_variants",
                    target=reg,
                    content="summary",
                    page=page_num,
                )

        elif act == "feature":
            payload = resolve_feature_coords(tgt, flank=flank_bp)
            endpoint = f"/service/feature?id={urllib.parse.quote(tgt)}&flank={flank_bp}"
            chrom = payload.get("chr") or "?"
            start = payload.get("start") or 0
            end = payload.get("end") or 0
            span_str = f"{chrom}:{start}-{end}"
            md = (
                f"### NIAGADS Genomic Coordinate Resolution (`{tgt}`)\n"
                f"- **GRCh38 Coordinates:** `{span_str}` (span: `{max(0, int(end) - int(start) + 1):,}` bp, flank: `{flank_bp:,}` bp)"
            )
            rows = [{"feature": tgt, "chromosome": chrom, "start": start, "end": end, "region": span_str}]

        elif act == "filer_overlap":
            filer_res = query_filer_overlap_count(tgt)
            payload = filer_res
            endpoint = f"FILER hg38 overlap ({filer_res['region']})"
            md = (
                f"### Live FILER Functional Genomics Overlap — `{filer_res['region']}` (GRCh38)\n"
                f"- **Overlapping Harmonized Regulatory Tracks:** **{filer_res['overlapping_tracks']:,}**\n"
                f"- **Total Overlapping Intervals:** **{filer_res['overlapping_intervals']:,}**"
            )
            if filer_res.get("note"):
                md = f"> {filer_res['note']}\n\n{md}"
            rows = [filer_res]

        else:
            raise ValueError(
                f"Unsupported action `{act}`. Choose from: auto, gene, gene_associations, gene_structure, "
                "variant, variant_associations, region_associations, region_variants, track, track_data, "
                "search, search_tracks, search_genes, search_variants, feature, filer_overlap."
            )

        elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))
        req_id = ((payload.get("request") or {}).get("request_id")) if isinstance(payload, dict) else None
        return {
            "ok": True,
            "action": act,
            "endpoint": endpoint,
            "request_id": req_id,
            "elapsed_ms": elapsed_ms,
            "summary_markdown": md,
            "rows": rows,
            "raw": payload,
        }

    except Exception as exc:
        elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))
        return {
            "ok": False,
            "action": act,
            "endpoint": act,
            "request_id": None,
            "elapsed_ms": elapsed_ms,
            "summary_markdown": f"error: NIAGADS Open Access API ({act} on `{tgt}`): {exc}",
            "rows": [],
            "raw": None,
        }


def niagads_open_access_api(
    action: str = "auto",
    target: str = "",
    loc: str = "",
    flank: int = 0,
    content: str = "full",
    limit: int = 10,
    page: int = 1,
) -> str:
    """ClawAgents tool wrapper returning structured Markdown from the live NIAGADS Open Access API v2.0."""
    res = execute_niagads_action(
        action=action,
        target=target,
        loc=loc,
        flank=flank,
        content=content,
        limit=limit,
        page=page,
    )
    return res["summary_markdown"]


_LIVE_ENRICH_RSID_RE = re.compile(r"\brs\d{3,12}\b", re.I)
_LIVE_ENRICH_REGION_RE = re.compile(r"\b(?:chr)?(?:[0-9]{1,2}|X|Y):[\d,]+-[\d,]+\b", re.I)
_LIVE_ENRICH_TRACK_RE = re.compile(r"\bNG\d{5}_[A-Z0-9_]+\b", re.I)
_KNOWN_AD_GENES = (
    "APOE",
    "BIN1",
    "TREM2",
    "ABCA7",
    "PLCG2",
    "ABI3",
    "SORL1",
    "PICALM",
    "CR1",
    "CLU",
    "MS4A6A",
    "CD33",
    "SPI1",
    "MAPT",
    "RELN",
    "RBFOX1",
    "CASS4",
    "ADAM10",
    "EIF2AK3",
    "MOBP",
    "STX6",
)


def fetch_live_niagads_supplement(query: str) -> str:
    """Best-effort live NIAGADS Open Access API v2.0 enrichment for `query_niagads(query)`.

    Disabled when `LIGASE_DISABLE_LIVE_NIAGADS=1` (e.g. strict offline tests) and fails silently
    if offline so deterministic catalog cards always succeed.
    """
    if os.getenv("LIGASE_DISABLE_LIVE_NIAGADS", "").strip().lower() in ("1", "true", "yes"):
        return ""
    text = (query or "").strip()
    if not text:
        return ""

    snippets: List[str] = []

    rsids = list(dict.fromkeys(m.group(0).lower() for m in _LIVE_ENRICH_RSID_RE.finditer(text)))
    tracks = list(dict.fromkeys(m.group(0).upper() for m in _LIVE_ENRICH_TRACK_RE.finditer(text)))
    regions = list(dict.fromkeys(m.group(0) for m in _LIVE_ENRICH_REGION_RE.finditer(text)))

    upper_tokens = set(re.findall(r"\b[A-Z0-9]{3,10}\b", text.upper()))
    matched_genes = [g for g in _KNOWN_AD_GENES if g in upper_tokens]

    # Cap total live calls in hybrid mode to keep latency crisp (~300-700 ms)
    for rsid in rsids[:2]:
        res = execute_niagads_action(action="auto", target=rsid, content="full")
        if res.get("ok") and res.get("summary_markdown"):
            snippets.append(res["summary_markdown"])

    if not snippets and tracks:
        res = execute_niagads_action(
            action="track_data" if regions else "track",
            target=tracks[0],
            loc=regions[0] if regions else "",
        )
        if res.get("ok") and res.get("summary_markdown"):
            snippets.append(res["summary_markdown"])

    if not snippets and regions:
        res = execute_niagads_action(action="auto", target=regions[0])
        if res.get("ok") and res.get("summary_markdown"):
            snippets.append(res["summary_markdown"])

    if len(snippets) < 2 and matched_genes:
        g_res = execute_niagads_action(action="gene", target=matched_genes[0], content="full")
        if g_res.get("ok") and g_res.get("summary_markdown"):
            snippets.append(g_res["summary_markdown"])
        ga_res = execute_niagads_action(action="gene_associations", target=matched_genes[0], content="summary")
        if ga_res.get("ok") and ga_res.get("summary_markdown") and "0 records" not in ga_res["summary_markdown"]:
            snippets.append(ga_res["summary_markdown"])

    if not snippets and len(text) <= 120:
        s_res = execute_niagads_action(action="search_tracks", target=text, limit=4)
        if s_res.get("ok") and s_res.get("rows"):
            snippets.append(s_res["summary_markdown"])

    if not snippets:
        return ""
    return (
        "\n\n[Live NIAGADS Open Access API v2.0 (`https://api.niagads.org/api`)]\n"
        + "\n\n".join(snippets)
    )
