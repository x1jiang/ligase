"""Tests for the Gemma-Biomni loop guard and compact tools."""

from types import SimpleNamespace
from unittest.mock import patch

from ligase.gemma_harness import (
    GEMMA_MAX_ITERATIONS,
    GemmaLoopGuard,
    apply_gemma_tool_surface,
    attach_gemma_tools,
    cap_gemma_iterations,
    close_multiple_choice,
    merge_tool_cards,
    select_gemma_domain_tools,
)
from ligase.gemma_tools import (
    LAST_TOOL_CARDS,
    clear_tool_cards,
    lookup_compound,
    query_niagads,
    run_python,
    solve_hwe_bayes,
    transcribe_translate,
)
from ligase.local_harness import is_gemma_local_model


def test_detects_gemma_and_skips_glimmer():
    assert is_gemma_local_model("gemma4-agentic-v2")
    assert is_gemma_local_model("gemma-4-12B-it")
    assert not is_gemma_local_model("Muse-Glimmer-30B")
    assert not is_gemma_local_model("gpt-5.6-luna")
    assert not is_gemma_local_model(None)


def test_caps_iterations_at_four():
    assert cap_gemma_iterations(15) == GEMMA_MAX_ITERATIONS
    assert cap_gemma_iterations(2) == 2


def test_selects_compact_gemma_tools():
    tools = attach_gemma_tools(
        [SimpleNamespace(name="query_pubchem"), SimpleNamespace(name="query_uniprot")]
    )
    selected = select_gemma_domain_tools(tools)
    names = {t.name for t in selected}
    assert "lookup_compound" in names
    assert "run_python" in names
    assert "transcribe_translate" in names
    assert "query_uniprot" in names
    assert "query_pubchem" not in names


def test_loop_guard_blocks_second_lookup():
    guard = GemmaLoopGuard()
    assert guard.before("lookup_compound", {"name": "imatinib"}) is True
    denied = guard.before("query_uniprot", {"id": "P04637"})
    assert denied.allowed is False
    assert "Lookup already used" in denied.reason


def test_loop_guard_blocks_third_code_run():
    guard = GemmaLoopGuard()
    assert guard.before("run_python", {"code": "print(1)"}) is True
    assert guard.before("run_python", {"code": "print(2)"}) is True
    denied = guard.before("run_python", {"code": "print(3)"})
    assert denied.allowed is False


def test_loop_guard_consumes_slot_on_allow():
    guard = GemmaLoopGuard()
    assert guard.before("lookup_compound", {"name": "imatinib"}) is True
    denied = guard.before("lookup_compound", {"name": "imatinib"})
    assert denied.allowed is False


def test_merge_tool_cards_keeps_formula_and_peptide():
    clear_tool_cards()
    LAST_TOOL_CARDS["lookup_compound"] = "formula: C29H31N7O\nmw: 493.6"
    LAST_TOOL_CARDS["transcribe_translate"] = "mRNA: AUGGGCAAGUAA\npeptide: MGK\nprotein: MGK"
    merged = merge_tool_cards("Imatinib is C29H30N7O. Peptide MASKL.")
    assert "C29H31N7O" in merged
    assert "AUGGGCAAGUAA" in merged
    assert "MGK" in merged
    clear_tool_cards()


def test_close_multiple_choice_appends_option_name():
    prompt = "Options: A. Cas9, B. Cas12a, C. Cas13a, D. Cas3."
    assert close_multiple_choice(prompt, "[ANSWER]C[/ANSWER]") == "[ANSWER]C[/ANSWER] Cas13a"
    assert close_multiple_choice(prompt, "Cas13a is correct [ANSWER]C[/ANSWER]") == (
        "Cas13a is correct [ANSWER]C[/ANSWER]"
    )


def test_transcribe_translate_mgk():
    out = transcribe_translate("ATGGGCAAGTAA")
    assert "AUGGGCAAGUAA" in out
    assert "MGK" in out
    assert "protein: MGK" in out


def test_run_python_returns_stdout():
    out = run_python("print('AUGGGCAAGUAA')\nprint('MGK')")
    assert "AUGGGCAAGUAA" in out
    assert "MGK" in out


def test_lookup_compound_formats_pubchem_card():
    fake = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 5291,
                    "MolecularFormula": "C29H31N7O",
                    "MolecularWeight": "493.6",
                    "IUPACName": "imatinib",
                }
            ]
        }
    }
    with patch("ligase.gemma_tools._pubchem_get", return_value=fake):
        card = lookup_compound("Imatinib")
    assert "formula: C29H31N7O" in card
    assert "mw: 493.6" in card


class _FakeRegistry:
    def __init__(self, names):
        self.tools = {n: SimpleNamespace(name=n) for n in names}
        self.active = None

    def list_registered(self):
        return list(self.tools.values())

    def set_active_tools(self, names):
        self.active = set(names)


def test_apply_gemma_surface_hides_pubchem_and_write_file():
    domain = [
        SimpleNamespace(name="lookup_compound"),
        SimpleNamespace(name="run_python"),
        SimpleNamespace(name="query_uniprot"),
    ]
    registry = _FakeRegistry(
        [
            "lookup_compound",
            "run_python",
            "query_uniprot",
            "query_pubchem",
            "write_file",
            "execute",
            "ls",
        ]
    )
    agent = SimpleNamespace(tools=registry, before_tool=None, after_tool=None)
    active = apply_gemma_tool_surface(agent, domain)
    assert "lookup_compound" in active
    assert "query_pubchem" not in active
    assert "write_file" not in active
    denied = agent.before_tool("query_pubchem", {})
    assert denied is False or getattr(denied, "allowed", True) is False


def test_transcribe_translate_strips_fasta_header():
    fasta = ">gene_1_human_atg_control\nATGGGCAAGTAA\n"
    out = transcribe_translate(fasta)
    assert "mRNA: AUGGGCAAGUAA" in out
    assert "peptide: MGK" in out


def test_run_python_allows_safe_imports_and_blocks_unsafe():
    assert run_python("import math\nprint(round(math.pi, 2))") == "3.14"
    assert "ImportError" in run_python("import os\nprint(os.getcwd())")
    assert "SecurityError" in run_python("print(().__class__.__bases__)")


def test_run_python_enforces_timeout():
    out = run_python("while True:\n    pass", timeout=0.15)
    assert "TimeoutError" in out


def test_transcribe_translate_frameshift_c10del():
    out = transcribe_translate("5'-ATGGCCCTGCTGAACCGCTAA-3' with c.10delC")
    assert "peptide: MALLNR" in out
    assert "DNA TGA / mRNA UGA" in out
    assert "truncated_peptide: MAL" in out


def test_solve_hwe_bayes_exact():
    out = solve_hwe_bayes(
        "incidence of 1 in 10,000 (q^2 = 0.0001) in a Hardy-Weinberg population, "
        "90% sensitivity and 100% specificity, posterior carrier probability"
    )
    assert "0.0198" in out
    assert "2/3" in out
    assert "1/6" in out
    assert "16.67%" in out


def test_query_niagads_catalog_lookup():
    clear_tool_cards()
    out = query_niagads("FILER microglia enhancers SPI1 BIN1 NG00105 NG00075 TREM2 PLCG2")
    assert "FILER" in out
    assert "NG00105" in out
    assert "TREM2" in out or "PLCG2" in out
    assert "query_niagads" in LAST_TOOL_CARDS
    clear_tool_cards()
