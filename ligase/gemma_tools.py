"""Compact tools for Gemma: one-line compound cards and inline Python."""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ligase.tools_adapter import BiomniTool

_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_UA = "Ligase/0.3 (local biomedical agent)"
_TIMEOUT_S = 12
_PYTHON_TIMEOUT_S = 5.0
_MAX_OUTPUT_CHARS = 8000
LAST_TOOL_CARDS: dict[str, str] = {}

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


def transcribe_translate(dna: str) -> str:
    """Transcribe DNA to mRNA and translate with the standard genetic code."""
    raw_lines = [
        line.strip()
        for line in (dna or "").splitlines()
        if line.strip() and not line.lstrip().startswith((">", ";", "#"))
    ]
    cleaned = "".join(raw_lines).upper()
    seq = "".join(ch for ch in cleaned if ch in "ACGTU")
    if not seq:
        return "error: dna sequence is required"
    mrna = seq.replace("T", "U")
    amino: list[str] = []
    for i in range(0, len(mrna) - 2, 3):
        residue = _CODON_TABLE.get(mrna[i : i + 3], "X")
        if residue == "*":
            break
        amino.append(residue)
    peptide = "".join(amino)
    return remember_card(
        "transcribe_translate",
        f"mRNA: {mrna}\npeptide: {peptide}\nprotein: {peptide}",
    )


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
                "Transcribe a DNA sequence to mRNA and translate it with the "
                "standard codon table. Returns mRNA and the peptide/protein. "
                "Use this instead of writing a script."
            ),
            parameters={
                "dna": {
                    "type": "string",
                    "description": "DNA sequence (A/C/G/T)",
                    "required": True,
                }
            },
            func=transcribe_translate,
            module_name="gemma",
            keywords=["dna", "mrna", "transcribe", "translate", "peptide"],
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
