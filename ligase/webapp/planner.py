"""Biomni-inspired Triage & Plan-then-Approve workflow for Ligase WebApp."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

NEEDS_PLAN_SENTINEL = "NEEDS_PLAN"

TRIAGE_SYSTEM_PROMPT = (
    "You are the intake triage assistant for Ligase, an Alzheimer's genomics, NIAGADS, and "
    "biomedical AI co-scientist.\n\n"
    f"Reply with EXACTLY `{NEEDS_PLAN_SENTINEL}` and nothing else if answering the user's "
    "message requires ANY of: querying NIAGADS, UniProt, Ensembl, NCBI Gene, PubChem, or PubMed; "
    "computing quantitative genetics metrics (Bayesian PIP, Odds Ratios, PAF, log-likelihoods); "
    "transcribing/translating sequences; running Python code; or inspecting an uploaded file.\n\n"
    "Otherwise — ONLY for brief greetings, questions about what Ligase can do, or definitions "
    "that need zero database lookups or calculations — answer concisely in 2–4 sentences. "
    f"Never guess at accession numbers, rsIDs, p-values, or molecular weights; reply `{NEEDS_PLAN_SENTINEL}`."
)

AD1_PLAN_SYSTEM_PROMPT = (
    "You are Ligase (AD1 · Alzheimer's & NIAGADS Co-Scientist) proposing a concise scientific "
    "execution plan before running tools.\n"
    "Return valid JSON ONLY with keys:\n"
    '  "summary": 1-sentence study objective,\n'
    '  "steps": array of 3 to 5 specific numbered scientific steps (strings without leading numbers),\n'
    '  "tools": array of exact Ligase tool names you will invoke (choose from: '
    "niagads_open_access_api, query_niagads, query_uniprot, query_ensembl, query_ncbi_gene, lookup_compound, "
    "transcribe_translate, search_pubmed, run_python),\n"
    '  "datasets": array of specific datasets/databases referenced (e.g., "NIAGADS Open Access API v2.0", '
    '"ADSP Release 5 SNVs/INDELs", "GVC TopGenes", "NIAGADS FILER", '
    '"MiGA NG00105", "ADSP NG00067", "AA-AD GWAS NG00100", "IGAP NG00075", "PSP WGS NG00169/NG00172", '
    '"CSF Biomarkers NG00049", "UniProtKB", "Ensembl GRCh38", "PubChem").\n'
    "Never include filesystem crawl steps. Focus strictly on the scientific methodology."
)

A1_PLAN_SYSTEM_PROMPT = (
    "You are Ligase (A1 · General Biomedical Research Agent) proposing a concise scientific "
    "execution plan before running tools.\n"
    "Return valid JSON ONLY with keys:\n"
    '  "summary": 1-sentence study objective,\n'
    '  "steps": array of 3 to 5 specific scientific steps (strings without leading numbers),\n'
    '  "tools": array of exact Ligase tool names you will invoke (e.g., '
    "lookup_compound, query_uniprot, query_ensembl, query_ncbi_gene, transcribe_translate, "
    "niagads_open_access_api, query_niagads, search_pubmed, run_python),\n"
    '  "datasets": array of databases/resources referenced (e.g., "PubChem PUG-REST", "UniProtKB", '
    '"NIAGADS Open Access API v2.0", "Ensembl REST", "NCBI Entrez", "Python Bioinformatics Sandbox").\n'
    "Focus strictly on the scientific methodology."
)


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if brace:
            text = brace.group(1)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _sync_triage_and_plan(
    *,
    prompt: str,
    profile: str,
    history: List[Dict[str, str]],
    model: str,
    api_key: Optional[str],
    base_url: Optional[str],
    revision_note: Optional[str] = None,
) -> Dict[str, Any]:
    from openai import OpenAI

    client_kwargs: Dict[str, Any] = {"api_key": api_key or "not-needed"}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    # If the user explicitly asked to revise an existing plan, skip triage.
    if not revision_note:
        triage_msgs: List[Dict[str, str]] = [{"role": "system", "content": TRIAGE_SYSTEM_PROMPT}]
        for turn in history[-4:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                triage_msgs.append({"role": turn["role"], "content": turn["content"][:1200]})
        triage_msgs.append({"role": "user", "content": prompt})
        try:
            t_resp = client.chat.completions.create(
                model=model,
                messages=triage_msgs,  # type: ignore[arg-type]
                max_completion_tokens=220,
            )
            t_text = (t_resp.choices[0].message.content or "").strip()
            if t_text and NEEDS_PLAN_SENTINEL not in t_text:
                return {"needs_plan": False, "direct_answer": t_text}
        except Exception:
            pass

    sys_prompt = AD1_PLAN_SYSTEM_PROMPT if str(profile).lower() != "a1" else A1_PLAN_SYSTEM_PROMPT
    user_payload = prompt
    if revision_note:
        user_payload = (
            f"Original research question:\n{prompt}\n\n"
            f"Researcher revision request:\n{revision_note}\n\n"
            "Produce the updated scientific plan in JSON."
        )

    plan_msgs: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]
    for turn in history[-4:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            plan_msgs.append({"role": turn["role"], "content": turn["content"][:1000]})
    plan_msgs.append({"role": "user", "content": user_payload})

    resp = client.chat.completions.create(
        model=model,
        messages=plan_msgs,  # type: ignore[arg-type]
        max_completion_tokens=700,
    )
    raw = (resp.choices[0].message.content or "").strip()
    parsed = _extract_json_object(raw) or {}

    summary = str(parsed.get("summary") or "Execute multi-step biomedical grounding and quantitative synthesis.").strip()
    raw_steps = parsed.get("steps")
    steps = [str(s).strip() for s in raw_steps if str(s).strip()] if isinstance(raw_steps, list) else []
    if not steps:
        steps = [
            "Query curated biomedical / NIAGADS reference catalogs for primary variant, gene, or compound records.",
            "Cross-validate quantitative effect sizes, allele frequencies, or functional annotations across cohorts.",
            "Synthesize an evidence-backed scientific report with structured comparison tables.",
        ]
    tools = [str(t).strip() for t in (parsed.get("tools") or []) if str(t).strip()]
    datasets = [str(d).strip() for d in (parsed.get("datasets") or []) if str(d).strip()]

    md_lines = [f"**Objective:** {summary}", "", "**Proposed Scientific Plan:**"]
    for idx, step in enumerate(steps, 1):
        cleaned = re.sub(r"^\d+[.)]\s*", "", step)
        md_lines.append(f"{idx}. {cleaned}")
    if tools:
        md_lines.append("\n**Tools:** " + ", ".join(f"`{t}`" for t in tools))
    if datasets:
        md_lines.append("**Reference Datasets:** " + ", ".join(f"`{d}`" for d in datasets))

    return {
        "needs_plan": True,
        "summary": summary,
        "steps": steps,
        "tools": tools,
        "datasets": datasets,
        "plan_markdown": "\n".join(md_lines),
    }


async def generate_plan_or_triage(
    *,
    prompt: str,
    profile: str,
    history: List[Dict[str, str]],
    model: str,
    api_key: Optional[str],
    base_url: Optional[str] = None,
    revision_note: Optional[str] = None,
) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _sync_triage_and_plan(
            prompt=prompt,
            profile=profile,
            history=history,
            model=model,
            api_key=api_key,
            base_url=base_url,
            revision_note=revision_note,
        ),
    )
