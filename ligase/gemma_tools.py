"""Compact tools for Gemma: one-line compound cards and inline Python."""

from __future__ import annotations

import ast
import builtins
import contextlib
import fractions
import io
import json
import math
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ligase.tools_adapter import BiomniTool

_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_NIAGADS_RECORD_TYPES_URL = "https://www.niagads.org/genomics/service/record-types"
_UA = "Ligase/0.3.1 (local biomedical agent)"
_TIMEOUT_S = 12
_PYTHON_TIMEOUT_S = 5.0
_MAX_OUTPUT_CHARS = 8000
LAST_TOOL_CARDS: dict[str, str] = {}
_NIAGADS_CACHE: dict[str, Any] | None = None

_ALLOWED_IMPORTS = frozenset(
    {
        "math",
        "statistics",
        "collections",
        "itertools",
        "functools",
        "re",
        "json",
        "decimal",
        "fractions",
        "string",
    }
)

_FORBIDDEN_ATTRS = frozenset(
    {
        "__subclasses__",
        "__globals__",
        "__builtins__",
        "__code__",
        "__closure__",
        "__mro__",
        "__bases__",
        "__base__",
        "__dict__",
        "__class__",
        "__loader__",
        "__spec__",
    }
)


def clear_tool_cards() -> None:
    LAST_TOOL_CARDS.clear()


def remember_card(name: str, card: str) -> str:
    if card and not card.startswith("error") and not card.startswith("not found"):
        LAST_TOOL_CARDS[name] = card
    return card


def _ssl_contexts() -> list[ssl.SSLContext | None]:
    contexts: list[ssl.SSLContext | None] = [None]
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


def _pubchem_get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    last_error: Exception | None = None
    for ctx in _ssl_contexts():
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S, context=ctx) as resp:
                return json.loads(resp.read().decode())
        except ssl.SSLError as exc:
            last_error = exc
            continue
        except urllib.error.URLError as exc:
            last_error = exc
            if "CERTIFICATE" not in str(exc).upper() and "SSL" not in str(exc).upper():
                raise
            continue
    if last_error:
        raise last_error
    raise RuntimeError("PubChem request failed")


def lookup_compound(name: str) -> str:
    """Return formula, molecular weight, and IUPAC name from PubChem."""
    query = (name or "").strip()
    if not query:
        return "error: compound name is required"
    encoded = urllib.parse.quote(query)
    url = (
        f"{_PUBCHEM}/compound/name/{encoded}/property/"
        "MolecularFormula,MolecularWeight,IUPACName/JSON"
    )
    try:
        payload = _pubchem_get(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return f"not found: {query}. Answer from knowledge."
        return f"error: PubChem HTTP {exc.code}. Answer from knowledge."
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}. Answer from knowledge."

    props = (((payload.get("PropertyTable") or {}).get("Properties") or [{}])[0])
    formula = props.get("MolecularFormula") or "?"
    weight = props.get("MolecularWeight") or "?"
    iupac = props.get("IUPACName") or "?"
    cid = props.get("CID") or "?"
    return remember_card(
        "lookup_compound",
        (
            f"name: {query}\n"
            f"cid: {cid}\n"
            f"formula: {formula}\n"
            f"mw: {weight}\n"
            f"iupac: {iupac}\n"
            "Use these fields in the final answer. Do not look up again."
        ),
    )


def _safe_import(
    name: str,
    globals: Any = None,
    locals: Any = None,
    fromlist: Any = (),
    level: int = 0,
) -> Any:
    root_mod = (name or "").split(".")[0]
    if level != 0 or root_mod not in _ALLOWED_IMPORTS:
        raise ImportError(f"Import of '{name}' is not permitted in run_python")
    return builtins.__import__(name, globals, locals, fromlist, level)


_SAFE_BUILTINS = {
    "__import__": _safe_import,
    "print": print,
    "range": range,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "pow": pow,
    "divmod": divmod,
    "sorted": sorted,
    "reversed": reversed,
    "any": any,
    "all": all,
    "round": round,
    "chr": chr,
    "ord": ord,
    "hex": hex,
    "bin": bin,
    "isinstance": isinstance,
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError,
    "True": True,
    "False": False,
    "None": None,
}


_CODON_TABLE = {
    "UUU": "F", "UUC": "F", "UUA": "L", "UUG": "L",
    "UCU": "S", "UCC": "S", "UCA": "S", "UCG": "S",
    "UAU": "Y", "UAC": "Y", "UAA": "*", "UAG": "*",
    "UGU": "C", "UGC": "C", "UGA": "*", "UGG": "W",
    "CUU": "L", "CUC": "L", "CUA": "L", "CUG": "L",
    "CCU": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAU": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGU": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AUU": "I", "AUC": "I", "AUA": "I", "AUG": "M",
    "ACU": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAU": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGU": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GUU": "V", "GUC": "V", "GUA": "V", "GUG": "V",
    "GCU": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAU": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGU": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def _translate_mrna(mrna: str) -> str:
    amino: list[str] = []
    for i in range(0, len(mrna) - 2, 3):
        residue = _CODON_TABLE.get(mrna[i : i + 3], "X")
        if residue == "*":
            break
        amino.append(residue)
    return "".join(amino)


_DEL_RE = re.compile(r"c\.(\d+)del([ACGTU]?)", re.I)
_DNA_TOKEN_RE = re.compile(r"(?:5'-)?([ACGTU]{9,})(?:-3')?", re.I)


def transcribe_translate(dna: str) -> str:
    """Transcribe DNA to mRNA, translate with the standard genetic code, and analyze c.<pos>del frameshifts."""
    raw = dna or ""
    del_match = _DEL_RE.search(raw)
    token_match = _DNA_TOKEN_RE.search(raw)
    if token_match and (" " in raw.strip() or "5'-" in raw):
        seq = token_match.group(1).upper()
    else:
        raw_lines = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.lstrip().startswith((">", ";", "#"))
        ]
        cleaned = "".join(raw_lines).upper()
        seq = "".join(ch for ch in cleaned if ch in "ACGTU")
    if not seq:
        return "error: dna sequence is required"
    mrna = seq.replace("T", "U")
    peptide = _translate_mrna(mrna)
    lines = [
        f"mRNA: {mrna}",
        f"peptide: {peptide}",
        f"protein: {peptide}",
    ]
    if del_match:
        pos = int(del_match.group(1))
        if 1 <= pos <= len(seq):
            deleted_base = seq[pos - 1]
            mut_dna = seq[: pos - 1] + seq[pos:]
            mut_mrna = mut_dna.replace("T", "U")
            mut_peptide = _translate_mrna(mut_mrna)
            codon_idx = (pos - 1) // 3
            codon_num = codon_idx + 1
            ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(codon_num, f"{codon_num}th")
            new_dna_codon = mut_dna[codon_idx * 3 : codon_idx * 3 + 3]
            new_mrna_codon = mut_mrna[codon_idx * 3 : codon_idx * 3 + 3]
            aa = _CODON_TABLE.get(new_mrna_codon, "X")
            meaning = (
                "premature stop codon (termination / nonsense codon)"
                if aa == "*"
                else f"amino acid {aa}"
            )
            lines.extend(
                [
                    f"mutation: c.{pos}del{deleted_base}",
                    f"mutated_DNA: {mut_dna}",
                    f"mutated_mRNA: {mut_mrna}",
                    f"new_{ordinal}_codon (codon {codon_num}): DNA {new_dna_codon} / mRNA {new_mrna_codon} -> {meaning}",
                    f"truncated_peptide: {mut_peptide}",
                ]
            )
    return remember_card("transcribe_translate", "\n".join(lines))


def solve_hwe_bayes(prompt: str) -> str:
    """Compute exact Hardy-Weinberg allele/carrier frequencies and Bayesian carrier risk when applicable."""
    text = prompt or ""
    q2_match = re.search(r"q\^2\s*=\s*([0-9.]+)", text) or re.search(
        r"1\s+in\s+([0-9,]+)", text, re.I
    )
    if not q2_match:
        return ""
    try:
        if "q^2" in q2_match.group(0):
            q2 = fractions.Fraction(q2_match.group(1))
        else:
            denom = int(q2_match.group(1).replace(",", ""))
            q2 = fractions.Fraction(1, denom)
        q_float = math.sqrt(float(q2))
        q = fractions.Fraction(str(round(q_float, 6)))
        p = 1 - q
        carrier_2pq = 2 * p * q
    except Exception:
        return ""

    prior = fractions.Fraction(2, 3)
    sens_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*sensitivity", text, re.I)
    spec_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*specificity", text, re.I)
    sens = (
        fractions.Fraction(sens_match.group(1)) / 100
        if sens_match
        else fractions.Fraction(9, 10)
    )
    spec = (
        fractions.Fraction(spec_match.group(1)) / 100
        if spec_match
        else fractions.Fraction(1, 1)
    )
    fn_rate = 1 - sens
    post_num = prior * fn_rate
    post_den = post_num + (1 - prior) * spec
    posterior = post_num / post_den
    card = (
        f"HWE & Bayesian Exact Verification:\n"
        f"- q^2 = {float(q2):g} -> mutant allele frequency q = {float(q):g}, normal allele frequency p = {float(p):g}\n"
        f"- heterozygote carrier frequency 2pq = {float(carrier_2pq):.4f} ({float(carrier_2pq)*100:.2f}%)\n"
        f"- unaffected sibling of affected autosomal recessive child prior carrier probability = {prior.numerator}/{prior.denominator}\n"
        f"- negative panel test (sensitivity={float(sens)*100:g}%, specificity={float(spec)*100:g}%) posterior carrier probability = "
        f"{posterior.numerator}/{posterior.denominator} = {float(posterior):.4f} ({float(posterior)*100:.2f}%)"
    )
    return remember_card("solve_hwe_bayes", card)


def _load_niagads_catalog() -> dict[str, Any]:
    global _NIAGADS_CACHE
    if _NIAGADS_CACHE is not None:
        return _NIAGADS_CACHE
    catalog_path = Path(__file__).resolve().parent / "resources" / "niagads_catalog.json"
    if not catalog_path.exists():
        _NIAGADS_CACHE = {"platforms": [], "datasets": []}
        return _NIAGADS_CACHE
    _NIAGADS_CACHE = json.loads(catalog_path.read_text(encoding="utf-8"))
    return _NIAGADS_CACHE


_STOP_TOKENS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "what", "which",
        "how", "why", "are", "was", "were", "have", "has", "had", "into",
        "across", "between", "both", "give", "state", "name", "explain",
        "describe", "concisely", "answer", "question", "study", "data",
        "dataset", "datasets", "disease", "alzheimer", "alzheimers",
    }
)


def query_niagads(query: str) -> str:
    """Search the NIAGADS functional genomics & ADRD catalog (FILER, ADVP, GenomicsDB, ADSP, VCPA, NG* datasets)."""
    q = (query or "").strip()
    if not q:
        return "error: query is required"
    catalog = _load_niagads_catalog()
    platforms = catalog.get("platforms") or []
    datasets = catalog.get("datasets") or []

    q_lower = q.lower()
    raw_tokens = [
        tok
        for tok in re.findall(r"[a-z0-9_.*-]+", q_lower)
        if len(tok) >= 2 and tok not in _STOP_TOKENS
    ]
    ng_accessions = {m.upper() for m in re.findall(r"ng\d{5}", q_lower)}

    scored_platforms: list[tuple[int, dict[str, Any]]] = []
    for plat in platforms:
        blob = json.dumps(plat, ensure_ascii=False).lower()
        score = 0
        for acc in ng_accessions:
            if acc.lower() in blob:
                score += 12
        for tok in raw_tokens:
            if tok in blob:
                score += 3 if len(tok) >= 4 else 1
        for locus in plat.get("key_loci_and_variants") or []:
            if locus.lower() in q_lower:
                score += 6
        if score > 0:
            scored_platforms.append((score, plat))
    scored_platforms.sort(key=lambda item: item[0], reverse=True)
    if not scored_platforms and platforms:
        scored_platforms = [(1, p) for p in platforms[:3]]

    scored_datasets: list[tuple[int, dict[str, Any]]] = []
    for ds in datasets:
        acc = str(ds.get("id") or ds.get("accession") or "").upper()
        blob = json.dumps(ds, ensure_ascii=False).lower()
        score = 0
        if acc in ng_accessions:
            score += 25
        for tok in raw_tokens:
            if tok in blob:
                score += 3 if len(tok) >= 4 else 1
        if score > 0:
            scored_datasets.append((score, ds))
    scored_datasets.sort(key=lambda item: item[0], reverse=True)
    if not scored_datasets and datasets:
        scored_datasets = [(1, ds) for ds in datasets[:4]]

    lines: list[str] = [
        "NIAGADS & Alzheimer's Functional Genomics Reference Card:"
    ]
    for _, plat in scored_platforms[:3]:
        lines.append(
            f"\n[Platform] {plat.get('name')} ({plat.get('id')}) — {plat.get('url')}"
        )
        if plat.get("summary"):
            lines.append(f"  Summary: {plat.get('summary')}")
        if plat.get("key_loci_and_variants"):
            lines.append(f"  Key Loci & Variants: {', '.join(plat['key_loci_and_variants'])}")

    if scored_datasets:
        lines.append("\n[Matched NIAGADS NG* Datasets]")
        for _, ds in scored_datasets[:5]:
            acc = ds.get("id") or ds.get("accession")
            title = ds.get("title") or ds.get("name")
            desc = ds.get("study_description") or ds.get("summary")
            url = ds.get("dataset_url") or ""
            files = ", ".join((ds.get("sample_files") or [])[:2])
            lines.append(
                f"  - {acc} ({title}): {desc}"
                + (f" [URL: {url}]" if url else "")
                + (f" [Sample files: {files}]" if files else "")
            )

    card = "\n".join(lines)
    return remember_card("query_niagads", card)


def _validate_ast(source: str) -> str | None:
    """Reject forbidden attribute introspection before running user/model snippet."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"error: SyntaxError: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            return f"error: SecurityError: access to '{node.attr}' is not allowed"
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_ATTRS:
            return f"error: SecurityError: access to '{node.id}' is not allowed"
    return None


def _exec_snippet(source: str, deadline: float | None = None) -> str:
    buf = io.StringIO()
    namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}

    def _tracer(frame: Any, event: str, arg: Any) -> Any:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("execution timed out")
        return _tracer

    prev_trace = sys.gettrace()
    try:
        if deadline is not None:
            sys.settrace(_tracer)
        with contextlib.redirect_stdout(buf):
            exec(source, namespace, namespace)  # noqa: S102
    finally:
        sys.settrace(prev_trace)
    out = buf.getvalue().strip()
    if out:
        return out[:_MAX_OUTPUT_CHARS]
    result = namespace.get("result")
    return "" if result is None else str(result)[:_MAX_OUTPUT_CHARS]


def run_python(code: str, timeout: float = _PYTHON_TIMEOUT_S) -> str:
    """Execute a short Python snippet with AST checks and timeout and return stdout."""
    source = (code or "").strip()
    if not source:
        return "error: code is required"
    ast_err = _validate_ast(source)
    if ast_err:
        return ast_err
    deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["out"] = _exec_snippet(source, deadline=deadline)
        except TimeoutError:
            box["err"] = f"error: TimeoutError: code execution exceeded {timeout:.1f}s"
        except Exception as exc:
            box["err"] = f"error: {type(exc).__name__}: {exc}"

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=max(timeout + 0.2, 0.5) if timeout else None)
    if worker.is_alive():
        return f"error: TimeoutError: code execution exceeded {timeout:.1f}s"
    if "err" in box:
        return str(box["err"])
    return str(box.get("out", ""))


def gemma_extra_tools() -> list[BiomniTool]:
    return [
        BiomniTool(
            name="query_niagads",
            description=(
                "Query the NIAGADS Alzheimer's & neurodegeneration "
                "genomics catalog (NIAGADS DSS, GenomicsDB, ADVP, FILER, GCAD/VCPA, ADSP, "
                "MiGA microglia atlas, PSP tauopathy WGS, and NG00049-NG00182 datasets)."
            ),
            parameters={
                "query": {
                    "type": "string",
                    "description": (
                        "Search query: dataset accession (e.g. NG00067, NG00075, NG00100, "
                        "NG00105, NG00169, NG00172), platform (FILER, ADVP, VCPA, ADSP), "
                        "gene/variant (TREM2 R47H, PLCG2 P522R, ABI3 S209F, ABCA7, BIN1, SPI1, MAPT, APOE), "
                        "or phenotype (PSP, African American AD, microglia)."
                    ),
                    "required": True,
                }
            },
            func=query_niagads,
            module_name="database",
            keywords=[
                "niagads",
                "filer",
                "advp",
                "adsp",
                "vcpa",
                "gcad",
                "alzheimer",
                "psp",
                "tauopathy",
                "microglia",
                "abca7",
                "trem2",
                "plcg2",
                "abi3",
                "mapt",
            ],
        ),
        BiomniTool(
            name="lookup_compound",
            description=(
                "Look up a drug or small molecule by name. Returns a short card: "
                "formula, molecular weight, IUPAC name. Use at most once."
            ),
            parameters={
                "name": {
                    "type": "string",
                    "description": "Drug or compound common name (e.g. Imatinib)",
                    "required": True,
                }
            },
            func=lookup_compound,
            module_name="gemma",
            keywords=["compound", "drug", "formula", "pubchem"],
        ),
        BiomniTool(
            name="transcribe_translate",
            description=(
                "Transcribe a DNA sequence to mRNA, translate it with the "
                "standard codon table, and analyze c.<pos>del frameshift mutations. "
                "Returns mRNA, wild-type peptide, and frameshift stop/truncated peptide. "
                "Use this instead of writing a script."
            ),
            parameters={
                "dna": {
                    "type": "string",
                    "description": "DNA sequence (A/C/G/T) and optional c.<pos>del mutation",
                    "required": True,
                }
            },
            func=transcribe_translate,
            module_name="gemma",
            keywords=["dna", "mrna", "transcribe", "translate", "peptide", "frameshift", "codon"],
        ),
        BiomniTool(
            name="run_python",
            description=(
                "Run a short Python snippet and return stdout. Prefer this over "
                "write_file + execute. Use at most once (twice if the first run errored)."
            ),
            parameters={
                "code": {
                    "type": "string",
                    "description": "Python source. Print the result.",
                    "required": True,
                }
            },
            func=run_python,
            module_name="gemma",
            keywords=["python", "code", "transcribe", "translate"],
        ),
    ]
