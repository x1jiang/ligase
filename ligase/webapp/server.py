"""FastAPI + SSE server for the Ligase Biomedical & NIAGADS Web Application."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import html
import inspect
import json
import logging
import os
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ligase import __version__ as VERSION
from ligase.examples_catalog import EXAMPLES
from ligase.gemma_harness import merge_tool_cards
from ligase.gemma_tools import clear_tool_cards
from ligase.niagads_api import OPEN_ACCESS_ROLLOUT_CATALOG, execute_niagads_action
from ligase.webapp.mindmap import build_capabilities_mindmap
from ligase.webapp.planner import generate_plan_or_triage
from ligase.webapp.store import ThreadStore
from ligase.webapp.usage_tracker import UsageTracker

# Kept as a patchable module attribute for tests while avoiding eager ClawAgents/LangChain imports on boot.
create_agent: Optional[Any] = None


def _get_create_agent() -> Any:
    if create_agent is not None:
        return create_agent
    from ligase.agent import create_agent as _real_create_agent

    return _real_create_agent


class _SSESafeGZipMiddleware:
    """Apply GZip compression to HTML/CSS/JS/JSON while keeping SSE (/api/chat/stream) unbuffered."""

    def __init__(self, app: Any, minimum_size: int = 500) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/api/chat/stream":
            await self.app(scope, receive, send)
            return
        await self._gzip(scope, receive, send)

logger = logging.getLogger("ligase.webapp")

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent.parent
STATIC_DIR = PKG_DIR / "static"
CATALOG_PATH = PKG_DIR.parent / "resources" / "niagads_catalog.json"

IS_CLOUD = os.getenv("LIGASE_CLOUD", "").strip().lower() in ("1", "true", "yes", "on")
if not IS_CLOUD:
    load_dotenv(REPO_DIR / ".env", override=True)

# Capture API credentials once at import and scrub OPENAI_API_KEY from os.environ in cloud mode
# so no child process or user code can read secrets from the environment.
_CAPTURED_OPENAI_KEY: Optional[str] = (os.getenv("OPENAI_API_KEY") or "").strip() or None
if IS_CLOUD and os.getenv("LIGASE_SCRUB_ENV", "1").strip() != "0":
    os.environ.pop("OPENAI_API_KEY", None)

DEFAULT_WEB_MODEL = (
    os.getenv("LIGASE_WEB_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gpt-6-luna"
).strip() or "gpt-6-luna"

STATE_DIR = Path(
    os.getenv("LIGASE_STATE_DIR")
    or ("/tmp/ligase_state" if IS_CLOUD else str(REPO_DIR / "runs" / ".webapp_state"))
).resolve()

RUNS_ROOT = Path(
    os.getenv("LIGASE_OUTPUT_ROOT")
    or ("/tmp/ligase_runs" if IS_CLOUD else str(REPO_DIR / "runs"))
).resolve()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_UPLOAD_EXTS = {
    ".tsv",
    ".csv",
    ".txt",
    ".vcf",
    ".bed",
    ".fasta",
    ".fa",
    ".json",
    ".md",
    ".py",
    ".r",
    ".gff",
    ".gtf",
}
IMAGE_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".webp"}

STARTER_META: Dict[str, Dict[str, str]] = {
    "niagads_live": {
        "badge": "NIAGADS Open Access v2.0 · Live",
        "accent": "indigo",
        "short_title": "Live ADSP R5 SNVs/VRS, GVC TopGenes & Multi-Ancestry GWAS",
        "subtitle": "Real-time api.niagads.org v2.0 records for TREM2 exons, rs6733839 & rs429358 + FILER overlap",
    },
    "niagads": {
        "badge": "NIAGADS V2F · Fine-Mapping",
        "accent": "indigo",
        "short_title": "BIN1 rs6733839 Bayesian PIP & Microglial Epistasis",
        "subtitle": "FILER PU.1/MEF2C enhancers + MiGA NG00105 eQTLs & TREM2 R47H × PLCG2 P522R rescue",
    },
    "adsp": {
        "badge": "Multi-Ancestry ADSP",
        "accent": "teal",
        "short_title": "ABCA7 rs115550680 8.7× PAF & APOE ε4 Stratification",
        "subtitle": "ADSP Umbrella NG00067 (VCPA/FAVOR) & AA-AD GWAS NG00100 vs. European IGAP NG00075",
    },
    "psp": {
        "badge": "4R-Tauopathy · Cross-Disorder",
        "accent": "amber",
        "short_title": "APOE ε2/ε2 + MAPT H1/H1 56.8× PSP vs. AD Shift",
        "subtitle": "PSP WGS SNVs/SVs (NG00169/NG00172) + CSF Biomarkers (NG00049) exon 10 splicing",
    },
    "apoe4": {
        "badge": "Neurogenetics · UniProt + Ensembl",
        "accent": "violet",
        "short_title": "APOE Isoform Structural Genetics & Aβ Clearance",
        "subtitle": "Chromosome 19q13.32 locus, Cys112Arg / Arg158Cys isoforms, and lipidated Aβ transport",
    },
    "imatinib": {
        "badge": "Pharmacology · PubChem",
        "accent": "emerald",
        "short_title": "Imatinib Formula, Exact Mass & BCR-ABL1 Target",
        "subtitle": "Ground-truth compound properties via PubChem PUG-REST & kinase selectivity",
    },
    "dna": {
        "badge": "Bioinformatics · Python Sandbox",
        "accent": "rose",
        "short_title": "DNA Transcription, ORF Translation & Verification",
        "subtitle": "Execute deterministic Python verification of mRNA codons and peptide translation",
    },
}


def _sanitize_client_id(raw: Optional[str]) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", (raw or "").strip())
    if 8 <= len(cleaned) <= 64:
        return cleaned
    return "local_default"


def _client_id_from_request(request: Request) -> str:
    hdr = request.headers.get("x-ligase-client-id") or request.query_params.get("client_id")
    return _sanitize_client_id(hdr)


def _load_niagads_summary() -> Dict[str, Any]:
    if not CATALOG_PATH.is_file():
        return {"platforms": [], "datasets": []}
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        platforms = [
            {
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "url": p.get("url", ""),
                "summary": p.get("summary", ""),
            }
            for p in (raw.get("platforms") or [])
        ]
        datasets = [
            {
                "id": d.get("id", ""),
                "title": d.get("title", ""),
                "access": d.get("access", "open"),
                "url": d.get("dataset_url", ""),
                "description": d.get("study_description", ""),
                "file_count": d.get("file_count", 0),
            }
            for d in (raw.get("datasets") or [])
        ]
        return {"platforms": platforms, "datasets": datasets}
    except Exception:
        return {"platforms": [], "datasets": []}


def _resolve_web_credentials() -> tuple[str, Optional[str], Optional[str]]:
    model = (
        os.getenv("LIGASE_WEB_MODEL")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_WEB_MODEL
    ).strip() or "gpt-6-luna"
    api_key = _CAPTURED_OPENAI_KEY or (os.getenv("OPENAI_API_KEY") or "").strip() or None
    base_url = (os.getenv("LIGASE_WEB_BASE_URL") or "").strip() or None
    return model, api_key, base_url


def _build_starters() -> List[Dict[str, Any]]:
    ordered_keys = ["niagads_live", "niagads", "adsp", "psp", "apoe4", "imatinib", "dna"]
    out: List[Dict[str, Any]] = []
    for key in ordered_keys:
        ex = EXAMPLES.get(key)
        if not ex:
            continue
        meta = STARTER_META.get(key, {})
        out.append(
            {
                "id": key,
                "badge": meta.get("badge", "Biomedical Study"),
                "accent": meta.get("accent", "indigo"),
                "title": meta.get("short_title", ex["title"]),
                "subtitle": meta.get("subtitle", ex["title"]),
                "question": ex["question"],
                "profile": "ad1" if ex.get("ad") else "a1",
                "max_iterations": ex.get("max_iterations", 8),
            }
        )
    return out


def _compact_json(value: Any, limit: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    except Exception:
        text = str(value)
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + " … [truncated]"
    return text


def _build_contextual_prompt(
    prompt: str,
    history: List[Dict[str, Any]],
    attachments: List[str],
    approved_plan: Optional[str],
) -> str:
    parts: List[str] = []
    recent = [
        m for m in history[-6:] if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
    ]
    if recent:
        ctx_lines = ["### Prior Conversation Context"]
        for m in recent:
            role_label = "Researcher" if m["role"] == "user" else "Ligase"
            snippet = str(m["content"]).strip()
            if len(snippet) > 1600:
                snippet = snippet[:1600] + "\n...[truncated]..."
            ctx_lines.append(f"**{role_label}:** {snippet}")
        parts.append("\n\n".join(ctx_lines))

    if approved_plan:
        parts.append(
            "### Researcher-Approved Scientific Plan\n"
            "Follow this approved methodology rigorously using Ligase's ground-truth tools:\n\n"
            f"{approved_plan.strip()}"
        )

    parts.append(f"### Current Research Question\n{prompt.strip()}")

    if attachments:
        att_lines = ["### Attached Workspace Files", "The researcher attached these files in the workspace:"]
        for p in attachments:
            att_lines.append(f"- `{p}`")
        parts.append("\n".join(att_lines))

    return "\n\n---\n\n".join(parts) if len(parts) > 1 else prompt.strip()


def _format_markdown_report(
    *,
    run_id: str,
    model: str,
    profile: str,
    prompt: str,
    answer: str,
    elapsed_s: float,
    iterations: int,
    tool_trace: List[Dict[str, Any]],
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    profile_label = (
        "AD1 · Alzheimer's & NIAGADS Co-Scientist"
        if profile == "ad1"
        else "A1 · General Biomedical Research Agent"
    )
    lines = [
        "# Ligase Scientific Study Report",
        "",
        f"- **Run ID:** `{run_id}`",
        f"- **Timestamp:** {ts}",
        f"- **Engine:** Ligase `v{VERSION}` (`{model}`)",
        f"- **Profile:** {profile_label}",
        f"- **Latency / Rounds:** `{elapsed_s:.2f}s` · `{iterations}` iteration(s) · `{len(tool_trace)}` tool call(s)",
        "",
        "## Research Question",
        "",
        prompt.strip(),
        "",
    ]
    if tool_trace:
        lines.extend(["## Grounded Tool Execution Trace", ""])
        for idx, t in enumerate(tool_trace, 1):
            status_icon = "✓" if t.get("success", True) else "✗"
            dur = f"{t.get('elapsed_ms', 0)} ms"
            lines.append(f"{idx}. **`{t.get('tool_name', 'tool')}`** ({status_icon} {dur}) — `{t.get('args_preview', '')}`")
        lines.append("")
    lines.extend(["## Scientific Synthesis", "", answer.strip(), ""])
    return "\n".join(lines)


class CreateThreadRequest(BaseModel):
    title: str = "New Biomedical Study"
    profile: str = "ad1"
    mode: str = "direct"


class UpdateThreadRequest(BaseModel):
    title: Optional[str] = None
    profile: Optional[str] = None
    mode: Optional[str] = None


class PlanRequest(BaseModel):
    thread_id: Optional[str] = None
    prompt: str = Field(..., min_length=1, max_length=16000)
    profile: str = "ad1"
    revision_note: Optional[str] = None


class ChatStreamRequest(BaseModel):
    thread_id: Optional[str] = None
    prompt: str = Field(..., min_length=1, max_length=16000)
    profile: str = "ad1"
    speed_mode: str = "fast"
    max_iterations: int = Field(default=10, ge=1, le=25)
    attachments: List[str] = Field(default_factory=list)
    approved_plan: Optional[str] = None


_PREGROUND_RSID_RE = re.compile(r"\brs\d{3,12}\b", re.I)
_PREGROUND_DNA_RE = re.compile(r"(?:5'-)?[ACGT]{9,}(?:-3')?", re.I)
_PREGROUND_NIAGADS_RE = re.compile(
    r"\b(niagads|filer|advp|adsp|vcpa|gcad|miga|topgenes|vrs|ng00\d{3}|"
    r"apoe|bin1|trem2|abca7|plcg2|abi3|mapt|supranuclear\s+palsy|4r-tauopathy|"
    r"rs6733839|rs429358|rs115550680|rs7412)\b",
    re.I,
)
_PREGROUND_LIVE_OA_RE = re.compile(
    r"\b(open[\s-]?access|api\.niagads\.org|vrs|topgenes|adsp\s+r(?:elease\s*)?5|exon\s+structure|ng00166)\b",
    re.I,
)
_PREGROUND_AD_GENES = ("TREM2", "APOE", "BIN1", "ABCA7", "MAPT", "PLCG2", "ABI3", "SORL1", "CLU", "CR1")
_PREGROUND_COMPOUNDS = (
    "imatinib",
    "aspirin",
    "donepezil",
    "memantine",
    "galantamine",
    "rivastigmine",
    "venetoclax",
    "olaparib",
    "metformin",
    "paclitaxel",
    "doxorubicin",
)


def _parallel_preground_prompt(
    prompt: str,
    emit_tool_start: Any,
    emit_tool_result: Any,
) -> str:
    """Execute deterministic ground-truth lookups concurrently (<350 ms) in fast mode."""
    text = (prompt or "").strip()
    if not text:
        return ""
    low = text.lower()
    tasks: List[Tuple[str, Dict[str, Any], Any]] = []

    # 1. NIAGADS curated cohort & V2F / ADSP / PSP catalog card (<5 ms local)
    if _PREGROUND_NIAGADS_RE.search(text):
        from ligase.gemma_tools import query_niagads

        tasks.append(("query_niagads", {"query": text[:120]}, lambda q=text: query_niagads(q)))

    # 2. Live NIAGADS Open Access v2.0 REST lookup for explicit rsIDs or AD genes
    if os.getenv("LIGASE_DISABLE_LIVE_NIAGADS", "").strip().lower() not in ("1", "true", "yes"):
        rsids: List[str] = []
        for m in _PREGROUND_RSID_RE.findall(text):
            norm_r = m.lower()
            if norm_r not in rsids:
                rsids.append(norm_r)
        wants_live = bool(_PREGROUND_LIVE_OA_RE.search(text))
        for rsid in rsids[:2]:
            if wants_live or len(rsids) == 1:
                from ligase.niagads_api import niagads_open_access_api

                tasks.append(
                    (
                        "niagads_open_access_api",
                        {"action": "auto", "target": rsid},
                        lambda r=rsid: niagads_open_access_api(action="auto", target=r),
                    )
                )
        if wants_live:
            upper_words = set(re.findall(r"\b[A-Z0-9]{3,10}\b", text.upper()))
            for gsym in _PREGROUND_AD_GENES:
                if gsym in upper_words and len(tasks) < 4:
                    from ligase.niagads_api import niagads_open_access_api

                    act = "gene_structure" if "exon" in low or "transcript" in low else "gene"
                    tasks.append(
                        (
                            "niagads_open_access_api",
                            {"action": act, "target": gsym},
                            lambda a=act, g=gsym: niagads_open_access_api(action=a, target=g),
                        )
                    )
                    break

    # 3. Deterministic DNA transcription / ORF translation (<2 ms)
    if _PREGROUND_DNA_RE.search(text) and any(
        w in low for w in ("transcribe", "translate", "codon", "orf", "mrna", "peptide", "del", "frameshift")
    ):
        from ligase.gemma_tools import transcribe_translate

        tasks.append(("transcribe_translate", {"dna": text[:90]}, lambda q=text: transcribe_translate(q)))

    # 4. PubChem compound ground-truth card
    if any(w in low for w in ("formula", "molecular weight", "smiles", "iupac", "pubchem", "compound", "kinase", "bcr-abl")):
        for comp in _PREGROUND_COMPOUNDS:
            if comp in low:
                from ligase.gemma_tools import lookup_compound

                tasks.append(("lookup_compound", {"name": comp.capitalize()}, lambda c=comp.capitalize(): lookup_compound(c)))
                break

    if not tasks:
        return ""

    call_entries: List[Tuple[str, str, Dict[str, Any], Any]] = []
    for idx, (tname, targs, fn) in enumerate(tasks[:4], 1):
        cid = f"preground_{idx}_{tname}"
        emit_tool_start(cid, tname, targs)
        call_entries.append((cid, tname, targs, fn))

    evidence_blocks: List[str] = []

    def _run_one(entry: Tuple[str, str, Dict[str, Any], Any]) -> Tuple[str, str, bool, int, str]:
        cid, tname, _targs, fn = entry
        t_start = time.monotonic()
        try:
            out = str(fn() or "").strip()
            ok = bool(out) and not out.lower().startswith("error")
        except Exception as exc:
            out = f"Pre-grounding lookup skipped: {exc}"
            ok = False
        dur_ms = max(1, int((time.monotonic() - t_start) * 1000))
        return cid, tname, ok, dur_ms, out

    with ThreadPoolExecutor(max_workers=min(4, len(call_entries))) as pool:
        results = list(pool.map(_run_one, call_entries))

    for cid, tname, ok, dur_ms, out in results:
        emit_tool_result(cid, tname, ok, dur_ms, out)
        if ok and out:
            trimmed = out[:5500] + ("\n...[truncated]" if len(out) > 5500 else "")
            evidence_blocks.append(f"#### Ground-Truth Tool Output (`{tname}`)\n{trimmed}")

    if not evidence_blocks:
        return ""
    return (
        "### [Pre-Grounded Verified Evidence]\n"
        "The following ground-truth records were fetched in parallel for this study. "
        "Synthesize directly from these exact figures without re-calling tools for the same targets:\n\n"
        + "\n\n".join(evidence_blocks)
    )


TOOL_CATALOG: List[Dict[str, str]] = [
    {
        "name": "niagads_open_access_api",
        "category": "NIAGADS Open Access v2.0 (Live)",
        "description": "Live REST client for https://api.niagads.org/api (OpenAPI v2.0): GRCh38 genes, GVC TopGenes, exon structures, ADSP Release 5 SNVs/INDELs, GA4GH VRS digests, GWAS/WGS associations, <100 kb regions, track slices, and live FILER hg38 overlaps.",
    },
    {
        "name": "query_niagads",
        "category": "Alzheimer's & NIAGADS",
        "description": "Quantitative NIAGADS DSS, GenomicsDB, ADVP, FILER (>58k functional tracks), MiGA NG00105 eQTLs, multi-ancestry ADSP (NG00067/NG00100), and PSP 4R-tauopathy WGS (NG00169/NG00172) + hybrid Open Access supplement.",
    },
    {
        "name": "query_uniprot",
        "category": "Proteomics & Isoforms",
        "description": "Retrieve curated UniProtKB protein entries, functional domains, isoform sequences, and disease variants.",
    },
    {
        "name": "query_ensembl",
        "category": "Genomics & Coordinates",
        "description": "Query Ensembl GRCh38 gene structures, cytogenetic bands, canonical transcripts, and variant consequences.",
    },
    {
        "name": "query_ncbi_gene",
        "category": "Genomics & Coordinates",
        "description": "Fetch NCBI Entrez Gene summaries, aliases, chromosomal locations, and RefSeq annotations.",
    },
    {
        "name": "lookup_compound",
        "category": "Pharmacology & Chemistry",
        "description": "Ground-truth PubChem PUG-REST lookup for exact molecular formula, molecular weight, IUPAC name, and SMILES.",
    },
    {
        "name": "transcribe_translate",
        "category": "Molecular Biology",
        "description": "Deterministic DNA/RNA transcription, 6-frame ORF translation, and frameshift/nonsense mutation analysis.",
    },
    {
        "name": "search_pubmed",
        "category": "Biomedical Literature",
        "description": "Query NCBI PubMed / E-utilities for peer-reviewed biomedical studies, clinical trials, and PMIDs.",
    },
    {
        "name": "run_python",
        "category": "Quantitative Sandbox",
        "description": "Sandboxed Python execution for Bayesian fine-mapping math, PAF/OR calculations, and sequence verification.",
    },
]

PROFILES_CATALOG: List[Dict[str, str]] = [
    {
        "id": "ad1",
        "name": "AD1 · Alzheimer's & NIAGADS",
        "tagline": "Alzheimer's Disease & Related Dementias Co-Scientist",
        "description": "Live NIAGADS Open Access API v2.0 (ADSP R5 SNVs/INDELs, GVC TopGenes, GenomicsDB) + FILER, MiGA (NG00105), ADSP (NG00067/NG00100), IGAP (NG00075), and PSP WGS (NG00169/NG00172).",
    },
    {
        "id": "a1",
        "name": "A1 · General Biomedical",
        "tagline": "Broad Genomics, Pharmacology & Molecular Biology Agent",
        "description": "Cross-disciplinary biomedical research across UniProt, Ensembl, NCBI, PubChem, PubMed, NIAGADS Open Access API, and sandboxed Python bioinformatics.",
    },
]


def _render_starters_ssr(starters: List[Dict[str, Any]]) -> str:
    cards: List[str] = []
    for s in starters:
        sid = html.escape(str(s.get("id") or ""), quote=True)
        badge = html.escape(str(s.get("badge") or ""))
        title = html.escape(str(s.get("title") or ""))
        sub = html.escape(str(s.get("subtitle") or ""))
        cards.append(
            f'<button type="button" class="starter-card" data-starter-id="{sid}">'
            f'<span class="starter-badge">{badge}</span>'
            f'<div class="starter-title">{title}</div>'
            f'<div class="starter-sub">{sub}</div>'
            f"</button>"
        )
    return "".join(cards)


def _safe_json_for_script_tag(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("</", "<\\/").replace("<!--", "<\\!--")


_WARMUP_STARTED = False
_WARMUP_LOCK = threading.Lock()


def _warmup_agent_runtime() -> None:
    """Warm ClawAgents, persistent loop, Biomni lazy descriptors, context layers, and NIAGADS preset in background."""
    try:
        from ligase.agent import _get_persistent_agent_loop, create_agent as _real_ca
        from ligase.context_layers import warmup_context_layers
        from ligase.tools_adapter import get_biomni_claw_tools

        _get_persistent_agent_loop()
        get_biomni_claw_tools(lazy=True)
        warmup_context_layers()
        # Prime fast system prompt & domain tool cache (<2 ms)
        _real_ca(model=DEFAULT_WEB_MODEL, is_ad_specialized=True, speed_mode="fast", api_key=_CAPTURED_OPENAI_KEY or "warmup")
        if os.getenv("LIGASE_DISABLE_LIVE_NIAGADS", "").strip().lower() not in ("1", "true", "yes"):
            execute_niagads_action(action="auto", target="rs6733839")
    except Exception as exc:
        logger.debug("Background warmup skipped/partial: %s", exc)


def create_webapp(state_dir: Optional[Path] = None, runs_root: Optional[Path] = None) -> FastAPI:
    resolved_state = Path(state_dir or STATE_DIR).resolve()
    resolved_runs = Path(runs_root or RUNS_ROOT).resolve()
    resolved_state.mkdir(parents=True, exist_ok=True)
    resolved_runs.mkdir(parents=True, exist_ok=True)

    db_path = resolved_state / "ligase_webapp.sqlite3"
    store = ThreadStore(db_path)
    usage_tracker = UsageTracker(db_path)
    niagads_summary = _load_niagads_summary()
    starters_list = _build_starters()
    starters_ssr_html = _render_starters_ssr(starters_list)
    niagads_full = {
        **niagads_summary,
        "open_access": OPEN_ACCESS_ROLLOUT_CATALOG,
    }
    mindmap_cache: Dict[str, Dict[str, Any]] = {}
    index_html_cache: Dict[Tuple[str, bool], str] = {}
    index_template = (
        (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        if (STATIC_DIR / "index.html").is_file()
        else ""
    )
    active_cancels: Dict[str, threading.Event] = {}

    def _get_mindmap(model_name: str) -> Dict[str, Any]:
        cached = mindmap_cache.get(model_name)
        if cached is None:
            cached = build_capabilities_mindmap(model_name=model_name)
            mindmap_cache[model_name] = cached
        return cached

    def _build_lean_boot(model_name: str, is_ready: bool) -> Dict[str, Any]:
        """Above-the-fold bootstrap (~3.5 KB raw) so GET / streams in <60 ms."""
        return {
            "brand": "Ligase",
            "version": VERSION,
            "model": model_name,
            "ready": is_ready,
            "cloud_mode": IS_CLOUD,
            "sandbox_mode": "AST + Isolated Workspace" if IS_CLOUD else "OS Sandbox (Seatbelt/Bubblewrap)",
            "profiles": PROFILES_CATALOG,
            "starters": starters_list,
        }

    def _build_meta(model_name: str, is_ready: bool) -> Dict[str, Any]:
        return {
            **_build_lean_boot(model_name, is_ready),
            "tools": TOOL_CATALOG,
            "niagads": niagads_full,
        }

    def _etag_json_response(request: Request, payload: Dict[str, Any], max_age: int = 0) -> Response:
        body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        etag = f'W/"{hashlib.md5(body_bytes).hexdigest()[:16]}"'
        cache_hdr = f"public, max-age={max_age}" if max_age > 0 else "no-cache"
        inm = request.headers.get("if-none-match") or ""
        if etag in inm:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_hdr})
        return Response(
            content=body_bytes,
            media_type="application/json",
            headers={"ETag": etag, "Cache-Control": cache_hdr},
        )

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        global _WARMUP_STARTED
        if os.getenv("LIGASE_SKIP_WARMUP", "").strip() != "1":
            with _WARMUP_LOCK:
                if not _WARMUP_STARTED:
                    _WARMUP_STARTED = True
                    threading.Thread(target=_warmup_agent_runtime, name="ligase-warmup", daemon=True).start()
        yield

    webapp = FastAPI(
        title="Ligase Biomedical Co-Scientist",
        version=VERSION,
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )
    webapp.add_middleware(_SSESafeGZipMiddleware, minimum_size=500)
    webapp.state.store = store
    webapp.state.usage_tracker = usage_tracker
    webapp.state.runs_root = resolved_runs
    webapp.state.active_cancels = active_cancels

    if STATIC_DIR.is_dir():
        webapp.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @webapp.middleware("http")
    async def _security_and_cache_headers(request: Request, call_next):
        resp: Response = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/static/"):
            if "v=" in (request.url.query or ""):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                resp.headers.setdefault("Cache-Control", "public, max-age=86400")
        return resp

    @webapp.get("/healthz")
    @webapp.get("/api/health")
    async def healthz() -> Dict[str, Any]:
        return {"ok": True, "service": "ligase-webapp", "version": VERSION}

    @webapp.get("/readyz")
    async def readyz() -> JSONResponse:
        model, api_key, base_url = _resolve_web_credentials()
        ready = bool(api_key or base_url)
        payload = {
            "ok": ready,
            "service": "ligase-webapp",
            "version": VERSION,
            "model": model,
            "cloud_mode": IS_CLOUD,
        }
        return JSONResponse(status_code=200 if ready else 503, content=payload)

    @webapp.get("/", response_class=HTMLResponse)
    @webapp.get("/usage", response_class=HTMLResponse)
    @webapp.get("/admin", response_class=HTMLResponse)
    async def index() -> Response:
        if not index_template:
            return HTMLResponse("<h1>Ligase WebApp</h1><p>Static bundle missing.</p>", status_code=500)
        model, api_key, base_url = _resolve_web_credentials()
        is_ready = bool(api_key or base_url)
        cache_key = (model, is_ready)
        rendered = index_html_cache.get(cache_key)
        if rendered is None:
            bootstrap_obj = {"boot": _build_lean_boot(model, is_ready)}
            bootstrap_tag = (
                f'<script id="ligase-bootstrap" type="application/json">'
                f"{_safe_json_for_script_tag(bootstrap_obj)}</script>"
            )
            rendered = (
                index_template.replace("<!-- LIGASE_STARTERS_SSR -->", starters_ssr_html)
                .replace("<!-- LIGASE_BOOTSTRAP_JSON -->", bootstrap_tag)
            )
            index_html_cache[cache_key] = rendered
        return HTMLResponse(rendered, headers={"Cache-Control": "no-cache"})

    @webapp.get("/api/meta")
    async def api_meta(request: Request) -> Response:
        model, api_key, base_url = _resolve_web_credentials()
        return _etag_json_response(request, _build_meta(model, bool(api_key or base_url)), max_age=60)

    @webapp.get("/api/mindmap")
    async def api_mindmap(request: Request) -> Response:
        model, _, _ = _resolve_web_credentials()
        return _etag_json_response(request, _get_mindmap(model), max_age=120)

    @webapp.get("/api/usage")
    async def api_usage(request: Request, days: str = "all") -> Response:
        model, _, _ = _resolve_web_credentials()
        payload = usage_tracker.get_dashboard_summary(days=days, active_model=model)
        return _etag_json_response(request, payload, max_age=0)

    @webapp.get("/api/usage/export.json")
    async def api_usage_export_json(days: str = "all") -> Response:
        model, _, _ = _resolve_web_credentials()
        payload = usage_tracker.get_dashboard_summary(days=days, active_model=model)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="ligase_usage_{days}_{stamp}.json"',
                "Cache-Control": "no-store",
            },
        )

    @webapp.get("/api/usage/export.md")
    async def api_usage_export_md(days: str = "all") -> Response:
        model, _, _ = _resolve_web_credentials()
        md = usage_tracker.export_markdown_report(days=days, active_model=model)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return PlainTextResponse(
            md,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="ligase_usage_report_{days}_{stamp}.md"',
                "Cache-Control": "no-store",
            },
        )

    @webapp.get("/api/usage/export.csv")
    async def api_usage_export_csv(days: str = "all") -> Response:
        model, _, _ = _resolve_web_credentials()
        zip_bytes = usage_tracker.export_csv_bundle_zip(days=days, active_model=model)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="ligase_usage_csv_bundle_{days}_{stamp}.zip"',
                "Cache-Control": "no-store",
            },
        )

    @webapp.get("/api/niagads/endpoints")
    async def api_niagads_endpoints() -> Dict[str, Any]:
        return OPEN_ACCESS_ROLLOUT_CATALOG

    @webapp.get("/api/niagads/live")
    async def api_niagads_live(
        request: Request,
        action: str = "auto",
        target: str = "",
        loc: str = "",
        flank: int = 0,
        content: str = "full",
        limit: int = 10,
        page: int = 1,
    ) -> JSONResponse:
        if not (target or "").strip() and not (loc or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Query parameter 'target' (e.g. APOE, rs6733839, chr2:127134000-127136000) is required.",
            )
        cid = _client_id_from_request(request)
        t_start = time.monotonic()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: execute_niagads_action(
                action=action,
                target=target,
                loc=loc,
                flank=flank,
                content=content,
                limit=limit,
                page=page,
            ),
        )
        dur_ms = int(result.get("elapsed_ms") or max(1, int((time.monotonic() - t_start) * 1000)))
        try:
            payload_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception:
            payload_bytes = 0
        try:
            usage_tracker.record_niagads_api_call(
                client_id=cid,
                action=action,
                target=target or loc,
                endpoint=str(result.get("endpoint") or action),
                ok=bool(result.get("ok")),
                elapsed_ms=dur_ms,
                payload_bytes=payload_bytes,
            )
        except Exception:
            pass
        return JSONResponse(status_code=200 if result.get("ok") else 502, content=result)

    @webapp.get("/api/threads")
    async def list_threads(request: Request) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        return {"threads": store.list_threads(cid)}

    @webapp.post("/api/threads")
    async def create_thread_route(request: Request, body: CreateThreadRequest) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        thread = store.create_thread(cid, title=body.title, profile=body.profile, mode=body.mode)
        return {"thread": thread}

    @webapp.get("/api/threads/{thread_id}")
    async def get_thread_route(request: Request, thread_id: str) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        thread = store.get_thread(cid, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"thread": thread}

    @webapp.patch("/api/threads/{thread_id}")
    async def update_thread_route(request: Request, thread_id: str, body: UpdateThreadRequest) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        ok = store.update_thread(cid, thread_id, title=body.title, profile=body.profile, mode=body.mode)
        if not ok:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"ok": True}

    @webapp.delete("/api/threads/{thread_id}")
    async def delete_thread_route(request: Request, thread_id: str) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        ok = store.delete_thread(cid, thread_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"ok": True}

    @webapp.post("/api/uploads")
    async def upload_file_route(request: Request) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        raw_name = request.headers.get("x-upload-filename") or "dataset.txt"
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(raw_name).name)[:100] or "dataset.txt"
        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTS))}",
            )
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds 15 MB upload limit")

        uploads_dir = resolved_runs / "uploads" / cid
        uploads_dir.mkdir(parents=True, exist_ok=True)
        stamped_name = f"{int(time.time())}_{uuid.uuid4().hex[:6]}_{safe_name}"
        dest = (uploads_dir / stamped_name).resolve()
        if not str(dest).startswith(str(uploads_dir)):
            raise HTTPException(status_code=400, detail="Invalid upload filename")
        dest.write_bytes(payload)
        try:
            usage_tracker.record_file_upload(client_id=cid, filename=safe_name, size_bytes=len(payload))
        except Exception:
            pass

        rel_token = f"{cid}/{stamped_name}"
        return {
            "ok": True,
            "name": safe_name,
            "size_bytes": len(payload),
            "token": rel_token,
        }

    @webapp.post("/api/plan")
    async def plan_route(request: Request, body: PlanRequest) -> Dict[str, Any]:
        cid = _client_id_from_request(request)
        model, api_key, base_url = _resolve_web_credentials()
        if not (api_key or base_url):
            raise HTTPException(status_code=503, detail="Model API credentials are not configured on this server.")
        history: List[Dict[str, str]] = []
        if body.thread_id:
            thread = store.get_thread(cid, body.thread_id)
            if thread:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in thread.get("messages", [])
                    if m.get("role") in ("user", "assistant")
                ]
        t_plan0 = time.monotonic()
        try:
            plan_res = await generate_plan_or_triage(
                prompt=body.prompt,
                profile=body.profile,
                history=history,
                model=model,
                api_key=api_key,
                base_url=base_url,
                revision_note=body.revision_note,
            )
        except Exception as exc:
            logger.exception("Plan generation failed")
            raise HTTPException(status_code=502, detail=f"Model planning error: {type(exc).__name__}: {exc}") from exc
        plan_elapsed_ms = max(1, int((time.monotonic() - t_plan0) * 1000))
        # If triage answered directly, persist the exchange into the thread right away.
        if not plan_res.get("needs_plan") and plan_res.get("direct_answer"):
            tid = body.thread_id
            if not tid or not store.get_thread(cid, tid):
                created = store.create_thread(cid, profile=body.profile, mode="plan")
                tid = created["id"]
            user_msg = store.append_message(cid, tid, "user", body.prompt)
            store.append_message(
                cid,
                tid,
                "assistant",
                plan_res["direct_answer"],
                metadata={"triage_direct": True, "model": model},
            )
            plan_res["thread_id"] = tid
            plan_res["thread_title"] = user_msg.get("thread_title")
        try:
            usage_tracker.record_plan_triage(
                client_id=cid,
                thread_id=str(plan_res.get("thread_id") or body.thread_id or ""),
                prompt=body.prompt,
                model=model,
                profile=body.profile,
                needs_plan=bool(plan_res.get("needs_plan")),
                elapsed_ms=plan_elapsed_ms,
                usage=plan_res.get("usage"),
            )
        except Exception:
            pass
        return plan_res

    @webapp.post("/api/runs/{run_id}/cancel")
    async def cancel_run_route(run_id: str) -> Dict[str, Any]:
        ev = active_cancels.get(run_id)
        if ev is not None:
            ev.set()
            return {"ok": True, "cancelled": True}
        return {"ok": True, "cancelled": False}

    @webapp.post("/api/chat/stream")
    async def chat_stream_route(request: Request, body: ChatStreamRequest) -> StreamingResponse:
        cid = _client_id_from_request(request)
        model, api_key, base_url = _resolve_web_credentials()
        if not (api_key or base_url):
            raise HTTPException(status_code=503, detail="Model API credentials are not configured on this server.")

        profile_norm = "a1" if str(body.profile).lower() == "a1" else "ad1"
        tid = body.thread_id
        existing_thread = store.get_thread(cid, tid) if tid else None
        if not existing_thread:
            created = store.create_thread(cid, profile=profile_norm)
            tid = created["id"]
            prior_messages: List[Dict[str, Any]] = []
        else:
            tid = existing_thread["id"]
            prior_messages = existing_thread.get("messages", [])

        # Resolve safe attachment paths inside the run directory
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        run_dir = (resolved_runs / cid / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        resolved_attachments: List[str] = []
        uploads_root = (resolved_runs / "uploads" / cid).resolve()
        for token in body.attachments[:8]:
            clean_rel = str(token).lstrip("/")
            if not clean_rel.startswith(f"{cid}/"):
                continue
            src = (resolved_runs / "uploads" / clean_rel).resolve()
            if src.is_file() and str(src).startswith(str(uploads_root)):
                copied = run_dir / src.name
                copied.write_bytes(src.read_bytes())
                resolved_attachments.append(str(copied))

        user_msg = store.append_message(
            cid,
            tid,
            "user",
            body.prompt,
            run_id=run_id,
            metadata={"attachments": [Path(p).name for p in resolved_attachments]},
        )
        thread_title = user_msg.get("thread_title") or "Biomedical Study"
        store.record_run_start(
            run_id=run_id,
            client_id=cid,
            thread_id=tid,
            prompt=body.prompt,
            model=model,
            profile=profile_norm,
            run_dir=str(run_dir),
        )

        contextual_prompt = _build_contextual_prompt(
            body.prompt,
            prior_messages,
            resolved_attachments,
            body.approved_plan,
        )

        speed_norm = "deep" if str(body.speed_mode or "").strip().lower() == "deep" else "fast"
        attachment_bytes = sum(Path(p).stat().st_size for p in resolved_attachments if Path(p).is_file())
        mode_norm = "plan" if body.approved_plan else "direct"

        cancel_event = threading.Event()
        active_cancels[run_id] = cancel_event

        async def _event_stream() -> AsyncGenerator[str, None]:
            loop = asyncio.get_running_loop()
            q: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
            tool_starts: Dict[str, float] = {}
            tool_trace: List[Dict[str, Any]] = []
            usage_totals: Dict[str, int] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cached_input_tokens": 0,
            }
            ttft_holder: List[int] = []
            initial_files = {p.name for p in run_dir.iterdir() if p.is_file()}
            t0 = time.monotonic()

            def _mark_ttft(explicit_ms: int = 0) -> None:
                if not ttft_holder:
                    ms = explicit_ms if explicit_ms > 0 else max(1, int((time.monotonic() - t0) * 1000))
                    ttft_holder.append(ms)

            def _push(event_type: str, payload: Dict[str, Any]) -> None:
                if cancel_event.is_set() and event_type not in ("run_cancelled", "run_error"):
                    return
                loop.call_soon_threadsafe(q.put_nowait, {"event": event_type, "data": payload})

            def _record_and_emit_tool_start(call_id: str, tname: str, args: Any) -> None:
                _mark_ttft()
                tool_starts[call_id] = time.monotonic()
                args_preview = _compact_json(args, limit=320)
                tool_trace.append(
                    {
                        "call_id": call_id,
                        "tool_name": tname,
                        "args_preview": args_preview,
                        "success": True,
                        "elapsed_ms": 0,
                        "output_preview": "",
                    }
                )
                _push(
                    "tool_started",
                    {
                        "call_id": call_id,
                        "tool_name": tname,
                        "args_preview": args_preview,
                    },
                )

            def _record_and_emit_tool_result(
                call_id: str,
                tname: str,
                success: bool,
                elapsed_ms: int,
                out_str: str,
            ) -> None:
                preview = _compact_json(out_str, limit=1400)
                for entry in reversed(tool_trace):
                    if entry["call_id"] == call_id or entry["tool_name"] == tname:
                        entry["success"] = success
                        entry["elapsed_ms"] = elapsed_ms
                        entry["output_preview"] = preview
                        break
                _push(
                    "tool_result",
                    {
                        "call_id": call_id,
                        "tool_name": tname,
                        "success": success,
                        "elapsed_ms": elapsed_ms,
                        "output_preview": preview,
                    },
                )

            def _worker() -> None:
                try:
                    clear_tool_cards()
                    agent_factory = _get_create_agent()
                    factory_kwargs: Dict[str, Any] = {
                        "model": model,
                        "data_path": str(run_dir),
                        "is_ad_specialized": (profile_norm == "ad1"),
                        "api_key": api_key,
                        "base_url": base_url,
                        "streaming": True,
                        "max_iterations": min(body.max_iterations, 6) if speed_norm == "fast" else body.max_iterations,
                        "sandbox_enabled": True,
                    }
                    try:
                        sig = inspect.signature(agent_factory)
                        has_var_kw = any(
                            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                        )
                        if has_var_kw or "speed_mode" in sig.parameters:
                            factory_kwargs["speed_mode"] = speed_norm
                    except Exception:
                        pass

                    agent = agent_factory(**factory_kwargs)

                    # Parallel instant pre-grounding (<350 ms) in fast mode when running the real engine
                    effective_prompt = contextual_prompt
                    allow_preground = (
                        speed_norm == "fast"
                        and os.getenv("LIGASE_DISABLE_WEB_PREGROUND", "").strip().lower() not in ("1", "true", "yes")
                        and (
                            create_agent is None
                            or os.getenv("LIGASE_FORCE_WEB_PREGROUND", "").strip() == "1"
                        )
                    )
                    if allow_preground:
                        pregrounded_block = _parallel_preground_prompt(
                            body.prompt,
                            _record_and_emit_tool_start,
                            _record_and_emit_tool_result,
                        )
                        if pregrounded_block:
                            effective_prompt = f"{contextual_prompt}\n\n---\n\n{pregrounded_block}"

                    # On public Cloud Run, confine execution to AST-verified `run_python`,
                    # workspace `read_file`, and domain tools unless LIGASE_ALLOW_CLOUD_EXEC=1.
                    if IS_CLOUD and os.getenv("LIGASE_ALLOW_CLOUD_EXEC", "").strip() != "1":
                        reg = getattr(agent.claw_agent, "tools", None)
                        if reg is not None and hasattr(reg, "list_registered") and hasattr(reg, "set_active_tools"):
                            blocked = {
                                "execute",
                                "bash",
                                "write_file",
                                "edit_file",
                                "web_search",
                                "web_fetch",
                                "ls",
                                "glob",
                                "grep",
                                "tree",
                            }
                            allowed = {t.name for t in reg.list_registered() if t.name not in blocked}
                            reg.set_active_tools(allowed)

                    def _on_stream_event(ev: Any) -> None:
                        if cancel_event.is_set():
                            raise InterruptedError("Run stopped by researcher.")
                        kind = getattr(ev, "kind", "") or ""
                        ev_data = getattr(ev, "data", {}) or {}
                        if kind == "turn_started":
                            _push("turn_started", {"iteration": getattr(ev, "iteration", 0)})
                        elif kind == "tool_started":
                            call_id = getattr(ev, "call_id", "") or ev_data.get("call_id") or f"call_{len(tool_trace) + 1}"
                            tname = getattr(ev, "tool_name", "") or ev_data.get("tool_name") or "tool"
                            args = getattr(ev, "args", None) or ev_data.get("args") or {}
                            _record_and_emit_tool_start(str(call_id), str(tname), args)
                        elif kind == "tool_progress":
                            delta = getattr(ev, "delta", "") or ev_data.get("delta", "") or ""
                            if delta:
                                _push(
                                    "tool_progress",
                                    {
                                        "tool_name": getattr(ev, "tool_name", "tool"),
                                        "delta": str(delta)[:600],
                                    },
                                )
                        elif kind == "tool_result":
                            call_id = str(getattr(ev, "call_id", "") or ev_data.get("call_id") or "")
                            tname = str(getattr(ev, "tool_name", "") or ev_data.get("tool_name") or "tool")
                            success = bool(getattr(ev, "success", ev_data.get("success", True)))
                            out_str = str(
                                getattr(ev, "output", "")
                                or getattr(ev, "error", "")
                                or ev_data.get("output", "")
                                or ev_data.get("error", "")
                                or ""
                            )
                            started_at = tool_starts.get(call_id, time.monotonic())
                            elapsed_ms = max(1, int((time.monotonic() - started_at) * 1000))
                            _record_and_emit_tool_result(call_id, tname, success, elapsed_ms, out_str)
                        elif kind == "assistant_delta":
                            delta = getattr(ev, "delta", "") or ev_data.get("content", "") or ev_data.get("delta", "")
                            if delta:
                                _mark_ttft()
                                _push("assistant_delta", {"delta": str(delta)})
                        elif kind == "usage":
                            uncached_inp = int(getattr(ev, "input_tokens", 0) or ev_data.get("input_tokens", 0) or 0)
                            prompt_inp = int(getattr(ev, "prompt_tokens", 0) or ev_data.get("prompt_tokens", 0) or 0)
                            out = int(getattr(ev, "output_tokens", 0) or ev_data.get("output_tokens", 0) or 0)
                            tot = int(getattr(ev, "total_tokens", 0) or ev_data.get("total_tokens", 0) or 0)
                            inferred_prompt = max(prompt_inp, max(0, tot - out) if tot > out else 0)
                            cached = int(
                                getattr(ev, "cached_input_tokens", 0)
                                or ev_data.get("cached_input_tokens", 0)
                                or ev_data.get("cache_read_tokens", 0)
                                or (max(0, inferred_prompt - uncached_inp) if inferred_prompt > uncached_inp > 0 else 0)
                            )
                            full_inp = max(inferred_prompt, uncached_inp + cached)
                            full_tot = max(tot, full_inp + out)
                            ev_ttft = int(getattr(ev, "time_to_first_token_ms", 0) or ev_data.get("time_to_first_token_ms", 0) or 0)
                            if ev_ttft > 0:
                                _mark_ttft(ev_ttft)
                            usage_totals["input_tokens"] += full_inp
                            usage_totals["output_tokens"] += out
                            usage_totals["total_tokens"] += full_tot
                            usage_totals["cached_input_tokens"] += min(full_inp, cached)

                    agent.claw_agent.on_stream_event = _on_stream_event
                    final_answer = agent.go(effective_prompt)
                    final_answer = merge_tool_cards(str(final_answer or "").strip())
                    elapsed_s = round(time.monotonic() - t0, 2)
                    iterations = int(getattr(agent.last_state, "iterations", 1) or 1)
                    resolved_ttft_ms = ttft_holder[0] if ttft_holder else max(1, int(elapsed_s * 200))

                    # Detect any newly created figure files inside run_dir
                    figures: List[Dict[str, str]] = []
                    for item in sorted(run_dir.iterdir()):
                        if (
                            item.is_file()
                            and item.name not in initial_files
                            and item.suffix.lower() in IMAGE_EXTS
                        ):
                            fig_url = f"/api/runs/{run_id}/files/{item.name}?client_id={cid}"
                            figures.append({"name": item.name, "url": fig_url})
                            _push("figure", {"name": item.name, "url": fig_url})

                    # Write durable report.md and run.json into run_dir
                    report_md = _format_markdown_report(
                        run_id=run_id,
                        model=model,
                        profile=profile_norm,
                        prompt=body.prompt,
                        answer=final_answer,
                        elapsed_s=elapsed_s,
                        iterations=iterations,
                        tool_trace=tool_trace,
                    )
                    report_bytes = len(report_md.encode("utf-8"))
                    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
                    run_record = {
                        "run_id": run_id,
                        "thread_id": tid,
                        "model": model,
                        "profile": profile_norm,
                        "speed_mode": speed_norm,
                        "prompt": body.prompt,
                        "answer": final_answer,
                        "elapsed_s": elapsed_s,
                        "ttft_ms": resolved_ttft_ms,
                        "iterations": iterations,
                        "tool_trace": tool_trace,
                        "usage": usage_totals,
                        "figures": figures,
                    }
                    (run_dir / "run.json").write_text(
                        json.dumps(run_record, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )

                    report_url = f"/api/runs/{run_id}/report.md?client_id={cid}"
                    bundle_url = f"/api/runs/{run_id}/bundle.zip?client_id={cid}"
                    msg_meta = {
                        "model": model,
                        "profile": profile_norm,
                        "speed_mode": speed_norm,
                        "elapsed_s": elapsed_s,
                        "ttft_ms": resolved_ttft_ms,
                        "iterations": iterations,
                        "tool_trace": tool_trace,
                        "usage": usage_totals,
                        "figures": figures,
                        "report_url": report_url,
                        "bundle_url": bundle_url,
                    }
                    store.append_message(
                        cid,
                        tid,
                        "assistant",
                        final_answer,
                        run_id=run_id,
                        metadata=msg_meta,
                    )
                    store.record_run_finish(
                        run_id=run_id,
                        status="completed",
                        answer=final_answer,
                        elapsed_s=elapsed_s,
                        iterations=iterations,
                        tool_trace=tool_trace,
                        usage=usage_totals,
                    )
                    try:
                        usage_tracker.record_study_run(
                            run_id=run_id,
                            client_id=cid,
                            thread_id=tid,
                            prompt=body.prompt,
                            answer=final_answer,
                            model=model,
                            profile=profile_norm,
                            mode=mode_norm,
                            speed_mode=speed_norm,
                            status="completed",
                            elapsed_s=elapsed_s,
                            ttft_ms=resolved_ttft_ms,
                            iterations=iterations,
                            tool_trace=tool_trace,
                            usage=usage_totals,
                            attachment_bytes=attachment_bytes,
                            report_bytes=report_bytes,
                        )
                    except Exception:
                        pass
                    _push(
                        "run_complete",
                        {
                            "run_id": run_id,
                            "thread_id": tid,
                            "thread_title": thread_title,
                            "model": model,
                            "profile": profile_norm,
                            "speed_mode": speed_norm,
                            "content": final_answer,
                            "elapsed_s": elapsed_s,
                            "ttft_ms": resolved_ttft_ms,
                            "iterations": iterations,
                            "tool_trace": tool_trace,
                            "usage": usage_totals,
                            "figures": figures,
                            "report_url": report_url,
                            "bundle_url": bundle_url,
                        },
                    )
                except InterruptedError:
                    elapsed_s = round(time.monotonic() - t0, 2)
                    store.record_run_finish(
                        run_id=run_id,
                        status="cancelled",
                        answer="",
                        elapsed_s=elapsed_s,
                        iterations=len(tool_trace),
                        tool_trace=tool_trace,
                        usage=usage_totals,
                    )
                    try:
                        usage_tracker.record_study_run(
                            run_id=run_id,
                            client_id=cid,
                            thread_id=tid,
                            prompt=body.prompt,
                            answer="",
                            model=model,
                            profile=profile_norm,
                            mode=mode_norm,
                            speed_mode=speed_norm,
                            status="cancelled",
                            elapsed_s=elapsed_s,
                            ttft_ms=ttft_holder[0] if ttft_holder else 0,
                            iterations=len(tool_trace),
                            tool_trace=tool_trace,
                            usage=usage_totals,
                            attachment_bytes=attachment_bytes,
                        )
                    except Exception:
                        pass
                    loop.call_soon_threadsafe(
                        q.put_nowait,
                        {"event": "run_cancelled", "data": {"run_id": run_id, "elapsed_s": elapsed_s}},
                    )
                except Exception as exc:
                    logger.exception("Agent run %s failed", run_id)
                    elapsed_s = round(time.monotonic() - t0, 2)
                    store.record_run_finish(
                        run_id=run_id,
                        status="failed",
                        answer="",
                        elapsed_s=elapsed_s,
                        iterations=len(tool_trace),
                        tool_trace=tool_trace,
                        usage=usage_totals,
                    )
                    try:
                        usage_tracker.record_study_run(
                            run_id=run_id,
                            client_id=cid,
                            thread_id=tid,
                            prompt=body.prompt,
                            answer="",
                            model=model,
                            profile=profile_norm,
                            mode=mode_norm,
                            speed_mode=speed_norm,
                            status="failed",
                            elapsed_s=elapsed_s,
                            ttft_ms=ttft_holder[0] if ttft_holder else 0,
                            iterations=len(tool_trace),
                            tool_trace=tool_trace,
                            usage=usage_totals,
                            attachment_bytes=attachment_bytes,
                        )
                    except Exception:
                        pass
                    loop.call_soon_threadsafe(
                        q.put_nowait,
                        {
                            "event": "run_error",
                            "data": {"run_id": run_id, "message": f"{type(exc).__name__}: {exc}"},
                        },
                    )
                finally:
                    active_cancels.pop(run_id, None)
                    loop.call_soon_threadsafe(q.put_nowait, None)

            # Emit run_started immediately before starting worker
            init_payload = {
                "run_id": run_id,
                "thread_id": tid,
                "thread_title": thread_title,
                "model": model,
                "profile": profile_norm,
            }
            yield f"event: run_started\ndata: {json.dumps(init_payload, ensure_ascii=False)}\n\n"

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()

            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=12.0)
                except asyncio.TimeoutError:
                    # SSE keepalive comment so Cloud Run / load balancers never drop long tool calls
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                ev_name = item["event"]
                ev_data = json.dumps(item["data"], ensure_ascii=False)
                yield f"event: {ev_name}\ndata: {ev_data}\n\n"

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @webapp.get("/api/runs/{run_id}/report.md")
    async def download_report_route(request: Request, run_id: str) -> Response:
        cid = _client_id_from_request(request)
        run_rec = store.get_run(cid, run_id)
        if not run_rec:
            raise HTTPException(status_code=404, detail="Run not found")
        run_dir = Path(run_rec["run_dir"]).resolve()
        report_file = run_dir / "report.md"
        if report_file.is_file():
            content = report_file.read_text(encoding="utf-8")
        else:
            content = _format_markdown_report(
                run_id=run_id,
                model=run_rec["model"],
                profile=run_rec["profile"],
                prompt=run_rec["prompt"],
                answer=run_rec["answer"],
                elapsed_s=run_rec["elapsed_s"],
                iterations=run_rec["iterations"],
                tool_trace=run_rec["tool_trace"],
            )
        return PlainTextResponse(
            content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{run_id}_report.md"'},
        )

    @webapp.get("/api/runs/{run_id}/bundle.zip")
    async def download_bundle_route(request: Request, run_id: str) -> Response:
        cid = _client_id_from_request(request)
        run_rec = store.get_run(cid, run_id)
        if not run_rec:
            raise HTTPException(status_code=404, detail="Run not found")
        run_dir = Path(run_rec["run_dir"]).resolve()
        if not run_dir.is_dir():
            raise HTTPException(status_code=404, detail="Run workspace no longer present")

        packages_dir = run_dir.parent / ".packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        zip_path = packages_dir / f"{run_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(run_dir.rglob("*")):
                if item.is_file() and not item.name.startswith("."):
                    zf.write(item, arcname=f"{run_id}/{item.relative_to(run_dir)}")
        return FileResponse(
            str(zip_path),
            media_type="application/zip",
            filename=f"{run_id}_bundle.zip",
        )

    @webapp.get("/api/runs/{run_id}/files/{filename}")
    async def serve_run_file(request: Request, run_id: str, filename: str) -> Response:
        cid = _client_id_from_request(request)
        run_rec = store.get_run(cid, run_id)
        if not run_rec:
            raise HTTPException(status_code=404, detail="Run not found")
        safe_name = Path(filename).name
        run_dir = Path(run_rec["run_dir"]).resolve()
        target = (run_dir / safe_name).resolve()
        if not str(target).startswith(str(run_dir)) or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(str(target))

    return webapp


app = create_webapp()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("ligase.webapp.server:app", host="0.0.0.0", port=port, log_level="info")
