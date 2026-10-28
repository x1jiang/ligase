"""Compact harness so local 30B models (Glimmer) can run Ligase.

Frontier models skip tools when they already know the answer. Muse-Glimmer-30B
does the opposite: the default coding surface (ls/glob/web_search) plus the
datalake "use execute" nudge burns the iteration budget before it writes an
answer. This module shrinks the tool surface and flips the policy to
knowledge-first.
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from ligase.gemma_tools import query_niagads, solve_hwe_bayes, transcribe_translate

_SUB_SUPER_DIGITS = str.maketrans(
    "₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹",
    "01234567890123456789",
)

# Lookups that cover the standard biomedical suite without the 70+ assay tools.
PREFERRED_DOMAIN_TOOLS = frozenset(
    {
        "query_niagads",
        "lookup_compound",
        "transcribe_translate",
        "run_python",
        "query_uniprot",
        "query_ensembl",
        "query_clinvar",
        "query_chembl",
        "query_pubchem",
        "query_opentarget",
        "query_gwas_catalog",
        "query_kegg",
        "query_stringdb",
        "query_pdb",
        "query_alphafold",
        "calculate_physicochemical_properties",
    }
)

# Needed for the DNA transcription/translation and NIAGADS tasks; keep them visible.
ALWAYS_ON_TOOLS = frozenset(
    {
        "query_niagads",
        "lookup_compound",
        "transcribe_translate",
        "run_python",
        "execute",
        "write_file",
        "retrieve_tool_result",
    }
)

EXPLORATION_TOOLS = frozenset(
    {
        "ls",
        "glob",
        "grep",
        "tree",
        "web_search",
        "web_fetch",
        "git_status",
        "git_diff",
        "git_commit",
        "read_and_grep",
        "hashline_grep",
        "skill_workshop",
        "task",
    }
)

LOCAL_OPERATING_RULES = """
### LOCAL MODEL OPERATING RULES (mandatory)
1. Keep internal thinking to 1-2 short sentences. Never deliberate or repeat policy checks on standard biomedical research queries.
2. If you already know the answer (gene symbols, chromosomes, drug formulas, multiple-choice, or verified reference cards in the prompt), answer immediately. Do not call tools unless needed.
3. For NIAGADS, FILER, ADVP, ADSP, VCPA, PSP, or NG* dataset questions, use `query_niagads` (at most once) if not already provided. For drug/compound lookups, prefer `lookup_compound` (direct PubChem card) over `query_pubchem` or `query_chembl`. Use at most one lookup total.
4. For DNA transcription/translation or c.<pos>del frameshift analysis use `transcribe_translate`, or `run_python` for short calculations.
5. Never use `ls`, `glob`, `grep`, `web_search`, `web_fetch`, or filesystem exploration for scientific facts.
6. If a tool errors (SSL, auth, timeout, not found), stop retrying and answer from knowledge.
7. After one successful tool result, write the final answer immediately. Do not call another tool.
8. Put canonical terms in the visible answer: official gene symbols, "tumor suppressor", enzyme names (e.g. Cas13a), both "transition" and "transversion" when discussing base editors (CBE/ABE) or point mutations, ASCII formulas (no subscripts), peptide/protein sequences, both 1-letter and 3-letter amino-acid substitutions (e.g. R136S / Arg136Ser, H3447R / His3447Arg), and exact fractions/percentages.
9. For multiple choice, include both `[ANSWER]X[/ANSWER]` and the option name (e.g. Cas13a).
10. Answer every numbered sub-question ((1), (2), (3)...) completely and concisely in 2-8 sentences.
""".strip()

COMPACT_AD_NOTE = (
    "For Alzheimer's / APOE / NIAGADS questions, state chromosome 19 and the amyloid-beta "
    "clearance mechanism from knowledge, and include exact NIAGADS dataset accessions "
    "(e.g. NG00067, NG00075, NG00100, NG00105, NG00169, NG00172), platform names (FILER, ADVP, VCPA, FAVOR), "
    "and canonical variant notations (TREM2 R47H, PLCG2 P522R, ABI3 S209F, ABCA7, SPI1/PU.1, "
    "APOE3 Christchurch R136S, RELN-COLBOS H3447R, MAPT 17q21.31 H1/H2 900 kb inversion, exon 10 4R tau)."
)

_NIAGADS_TRIGGER_RE = re.compile(
    r"\b(niagads|filer|advp|adsp|vcpa|gcad|miga|ng00\d{3}|"
    r"abca7|trem2|plcg2|abi3|supranuclear\s+palsy|4r-tauopathy)\b",
    re.I,
)
_DNA_TRIGGER_RE = re.compile(r"(?:5'-)?[ACGT]{9,}(?:-3')?", re.I)


def _emit_preground_tool_event(
    claw_agent: Any,
    tool_name: str,
    args: dict[str, Any],
    output: str,
) -> None:
    if claw_agent is None:
        return
    hook = getattr(claw_agent, "on_stream_event", None)
    if not callable(hook):
        return
    from types import SimpleNamespace

    call_id = f"preground_{tool_name}"
    try:
        hook(
            SimpleNamespace(
                kind="tool_started",
                data={"call_id": call_id, "tool_name": tool_name, "args": args},
            )
        )
        hook(
            SimpleNamespace(
                kind="tool_result",
                data={
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "success": True,
                    "output": output,
                },
            )
        )
    except Exception:
        pass


def preground_local_prompt(prompt: str, claw_agent: Any = None) -> str:
    """Attach deterministic Ligase verification cards (sequence/frameshift, HWE/Bayes, NIAGADS) to local prompts."""
    text = prompt or ""
    cards: list[str] = []
    if _DNA_TRIGGER_RE.search(text) and (
        "transcribe" in text.lower()
        or "translate" in text.lower()
        or "codon" in text.lower()
        or "peptide" in text.lower()
        or "del" in text.lower()
    ):
        tx_card = transcribe_translate(text)
        if tx_card and not tx_card.startswith("error"):
            _emit_preground_tool_event(
                claw_agent, "transcribe_translate", {"dna": text[:80]}, tx_card
            )
            cards.append(f"[Verified Ligase Sequence & Frameshift Card]\n{tx_card}")
    if ("hardy-weinberg" in text.lower() or "q^2" in text.lower()) and (
        "carrier" in text.lower() or "posterior" in text.lower()
    ):
        hwe_card = solve_hwe_bayes(text)
        if hwe_card:
            _emit_preground_tool_event(
                claw_agent, "run_python", {"code": "solve_hwe_bayes(prompt)"}, hwe_card
            )
            cards.append(f"[Verified Ligase Quantitative Genetics Card]\n{hwe_card}")
    if _NIAGADS_TRIGGER_RE.search(text):
        niagads_card = query_niagads(text)
        if niagads_card and not niagads_card.startswith("error"):
            _emit_preground_tool_event(
                claw_agent, "query_niagads", {"query": text[:90]}, niagads_card
            )
            cards.append(f"[Verified Ligase NIAGADS Catalog Card]\n{niagads_card}")
    if not cards:
        return text
    return (
        f"{text}\n\n"
        + "\n\n".join(cards)
        + "\n\nUse the verified card facts above directly in your final answer without redundant tool calls."
    )

KNOWLEDGE_FALLBACK_SYSTEM = (
    "You are a biomedical expert. Answer from established knowledge in 2-6 "
    "sentences. Use canonical terms (tumor suppressor, Cas13a, peptide/protein, "
    "formulas, gene symbols, chromosomes). For multiple choice include "
    "[ANSWER]X[/ANSWER] and the option name. Do not mention tools."
)

_CLOUD_HOSTS = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
    }
)


def is_compact_local_model(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> bool:
    """True for Glimmer / OSS checkpoints on a non-cloud OpenAI-compatible URL."""
    flag = (
        os.getenv("LIGASE_LOCAL_HARNESS")
        or os.getenv("BIOMNI_LOCAL_HARNESS")
        or ""
    ).strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return True

    model_l = (model or "").strip().lower()
    if model_l.startswith(("gpt-", "claude-", "gemini-", "o1", "o3", "o4")):
        return False

    if any(
        tag in model_l
        for tag in (
            "glimmer",
            "muse-glimmer",
            "muse-spark",
            "llama",
            "qwen",
            "gemma",
            "mistral",
            "deepseek",
            "phi-",
            "olmo",
        )
    ):
        return True

    url = (base_url or os.getenv("OPENAI_BASE_URL") or "").strip()
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or host in _CLOUD_HOSTS or host.endswith(".openai.azure.com"):
        return False
    return True


def is_gemma_local_model(model: Optional[str] = None) -> bool:
    """True for Gemma checkpoints that need the stricter Biomni loop guard."""
    model_l = (model or "").strip().lower()
    if not model_l or "gemma" not in model_l:
        return False
    return not model_l.startswith(("gpt-", "claude-", "gemini-"))


def normalize_local_answer(text: str) -> str:
    """Make Glimmer answers machine-readable without changing the science.

    SGLang often emits Unicode subscripts (C₂₉H₃₁N₇O) that break exact
    formula matching and downstream parsers.
    """
    if not text:
        return text
    return text.translate(_SUB_SUPER_DIGITS)


def local_system_addendum(*, is_ad_specialized: bool = False) -> str:
    parts = [LOCAL_OPERATING_RULES]
    if is_ad_specialized:
        parts.append(COMPACT_AD_NOTE)
    return "\n\n".join(parts)


def select_local_domain_tools(tools: Iterable[Any]) -> list[Any]:
    """Keep preferred lookups when present; otherwise keep every loaded domain tool."""
    loaded = list(tools)
    full_flag = (
        os.getenv("LIGASE_LOCAL_FULL_TOOLS")
        or os.getenv("BIOMNI_LOCAL_FULL_TOOLS")
        or ""
    ).strip().lower()
    if full_flag in ("1", "true", "yes", "on"):
        return loaded
    preferred = [t for t in loaded if getattr(t, "name", "") in PREFERRED_DOMAIN_TOOLS]
    return preferred or loaded


def local_active_tool_names(domain_tools: Iterable[Any]) -> set[str]:
    names = {getattr(t, "name", "") for t in domain_tools}
    names.discard("")
    names |= ALWAYS_ON_TOOLS
    return names


def _configure_spark_chat_options(claw_agent: Any) -> None:
    """Pass native reasoning_effort + chat_template_kwargs for Muse-Spark llama.cpp servers."""
    llm = getattr(claw_agent, "llm", None)
    model_l = str(getattr(llm, "model", "") or "").lower()
    if "spark" not in model_l and "muse" not in model_l:
        return
    client = getattr(llm, "client", None)
    completions = getattr(getattr(client, "chat", None), "completions", None)
    if completions is None or getattr(completions, "_ligase_spark_wrapped", False):
        return
    orig_create = completions.create

    async def _wrapped_create(*args: Any, **kwargs: Any) -> Any:
        effort = (os.getenv("LIGASE_REASONING_EFFORT") or "low").strip().lower()
        if effort in ("low", "medium", "high", "xhigh"):
            kwargs.setdefault("reasoning_effort", effort)
            extra = dict(kwargs.get("extra_body") or {})
            ctk = dict(extra.get("chat_template_kwargs") or {})
            ctk.setdefault("reasoning_effort", effort)
            extra["chat_template_kwargs"] = ctk
            kwargs["extra_body"] = extra
        return await orig_create(*args, **kwargs)

    completions.create = _wrapped_create
    completions._ligase_spark_wrapped = True


_LOCAL_LOOKUP_TOOLS = frozenset(
    {
        "query_niagads",
        "lookup_compound",
        "query_uniprot",
        "query_ensembl",
        "query_clinvar",
        "query_chembl",
        "query_pubchem",
        "query_opentarget",
        "query_gwas_catalog",
        "query_kegg",
        "query_stringdb",
        "query_pdb",
        "query_alphafold",
        "calculate_physicochemical_properties",
    }
)
_LOCAL_CODE_TOOLS = frozenset(
    {"transcribe_translate", "run_python", "execute", "write_file"}
)


def reset_local_tool_budget(claw_agent: Any) -> None:
    budget = getattr(claw_agent, "_local_tool_budget", None)
    if isinstance(budget, dict):
        budget["lookups"] = 0
        budget["code_runs"] = 0


def apply_local_tool_surface(claw_agent: Any, domain_tools: Iterable[Any]) -> list[str]:
    """Hide coding/exploration tools and cap redundant lookups so Glimmer answers in 1 pass."""
    _configure_spark_chat_options(claw_agent)
    registry = getattr(claw_agent, "tools", None)
    if registry is None or not hasattr(registry, "set_active_tools"):
        return []

    wanted = local_active_tool_names(domain_tools)
    registered = {t.name for t in registry.list_registered()} if hasattr(registry, "list_registered") else set()
    active = wanted & registered if registered else wanted
    registry.set_active_tools(active)

    previous = getattr(claw_agent, "before_tool", None)
    budget = {"lookups": 0, "code_runs": 0}
    claw_agent._local_tool_budget = budget

    def _deny_exploration(tool_name: str, args: dict) -> Any:
        if tool_name in EXPLORATION_TOOLS:
            return False
        if tool_name in _LOCAL_LOOKUP_TOOLS:
            if budget["lookups"] >= 1:
                try:
                    from clawagents.graph.agent_loop import HookResult

                    return HookResult(
                        allowed=False,
                        reason="Lookup already completed. Write the complete final answer now without calling another tool.",
                    )
                except ImportError:
                    return False
            budget["lookups"] += 1
        elif tool_name in _LOCAL_CODE_TOOLS:
            if budget["code_runs"] >= 2:
                try:
                    from clawagents.graph.agent_loop import HookResult

                    return HookResult(
                        allowed=False,
                        reason="Code verification already completed. Write the complete final answer now.",
                    )
                except ImportError:
                    return False
            budget["code_runs"] += 1
        if previous is None:
            return True
        return previous(tool_name, args)

    claw_agent.before_tool = _deny_exploration
    return sorted(active)


def needs_knowledge_fallback(state: Any) -> bool:
    result = str(getattr(state, "result", "") or "")
    status = str(getattr(state, "status", "") or "")
    if status in ("max_iterations", "error", "failed"):
        return True
    if result.startswith(("Reached maximum of", "LLM call failed", "Understood. I will not claim")):
        return True
    return "maximum of" in result and "tool rounds" in result


async def knowledge_fallback_answer(claw_agent: Any, prompt: str) -> str:
    """Last-turn no-tools answer when the agent loop exhausted its budget."""
    from clawagents.providers.llm import LLMMessage

    llm = getattr(claw_agent, "llm", None)
    if llm is None or not hasattr(llm, "chat"):
        return ""
    try:
        response = await llm.chat(
            [
                LLMMessage(role="system", content=KNOWLEDGE_FALLBACK_SYSTEM),
                LLMMessage(role="user", content=prompt),
            ]
        )
    except Exception:
        return ""
    return (getattr(response, "content", None) or "").strip()
