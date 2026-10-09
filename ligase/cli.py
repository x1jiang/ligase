"""
Ligase command line.

    ligase                      interactive prompt
    ligase run "<question>"     one study; writes runs/ligase_<time>_<slug>/report.md
    ligase examples             list ready-made studies
    ligase example apoe4        run one of them
    ligase doctor               check install, tools, model endpoint, sandbox

The model is picked from the environment (.env): a private OpenAI-compatible
host (GLIMMER_30B_BACKEND or LIGASE_BASE_URL) wins, else OpenAI (OPENAI_API_KEY).
"""

import argparse
import json
import logging
import os
import platform
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

BRAND = "Ligase"
VERSION = "0.2.0"
REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODULES = ["database", "literature", "genomics", "pharmacology", "biochemistry"]
QUIET_LOGGERS = ("httpx", "httpcore", "openai")  # request lines would print the private host

EXAMPLES: Dict[str, Dict[str, Any]] = {
    "apoe4": {
        "title": "Alzheimer's genetics: APOE4 via UniProt + Ensembl",
        "question": (
            "Look up APOE in UniProt. Which chromosome is APOE on, which amino-acid residues "
            "distinguish the APOE4 isoform from APOE3 and APOE2, and how does APOE4 impair "
            "amyloid-beta clearance?"
        ),
        "ad": True,
        "max_iterations": 6,
    },
    "imatinib": {
        "title": "Drug lookup: Imatinib formula, weight and target via PubChem",
        "question": (
            "Look up the oncology drug Imatinib in PubChem: give its exact molecular formula, "
            "molecular weight, and primary target kinase."
        ),
        "ad": False,
        "max_iterations": 4,
    },
    "dna": {
        "title": "Sandboxed code: transcribe and translate a DNA sequence",
        "question": (
            "Write and execute a Python script to verify: (1) transcribe DNA sequence "
            "'ATGGGCAAGTAA' to mRNA, (2) translate it to amino acids, and (3) output the "
            "resulting peptide sequence."
        ),
        "ad": False,
        "max_iterations": 6,
    },
}


class ConfigError(Exception):
    """A setup problem the user can fix; the message says how."""


# ── Model selection ──────────────────────────────────────────────────────────

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read a setting, treating .env.example placeholders ("your_..._here") as unset."""
    value = os.getenv(name)
    if not value or (value.startswith("your_") and value.endswith("_here")):
        return default
    return value


def model_presets() -> Dict[str, Dict[str, Any]]:
    """Presets read the environment at call time so .env edits apply."""
    return {
        "glimmer": {
            "model": os.getenv("GLIMMER_30B_MODEL", "Muse-Glimmer-30B"),
            "base_url": _env("GLIMMER_30B_BACKEND"),
            "base_url_env": "GLIMMER_30B_BACKEND",
            "api_key": os.getenv("GLIMMER_API_KEY", "not-needed"),
            "where": "private host · OpenAI-compatible",
        },
        "openai": {
            "model": os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
            "base_url": None,
            "api_key": _env("OPENAI_API_KEY"),
            "api_key_env": "OPENAI_API_KEY",
            "where": "OpenAI API",
        },
        "gemma": {
            "model": os.getenv("GEMMA_AGENTIC_MODEL", "gemma4-agentic-v2"),
            "base_url": os.getenv("GEMMA_AGENTIC_BASE_URL", "http://127.0.0.1:18080/v1"),
            "base_url_env": "GEMMA_AGENTIC_BASE_URL",
            "api_key": os.getenv("GEMMA_AGENTIC_API_KEY", "not-needed"),
            "where": "local GGUF server",
        },
        "custom": {
            "model": os.getenv("LIGASE_MODEL", ""),
            "base_url": _env("LIGASE_BASE_URL"),
            "base_url_env": "LIGASE_BASE_URL",
            "api_key": os.getenv("LIGASE_API_KEY", "not-needed"),
            "where": "OpenAI-compatible host",
        },
    }


MODEL_CHOICES = ["auto", "glimmer", "openai", "luna", "gemma", "custom"]


def resolve_model(name: str = "auto") -> Dict[str, Any]:
    presets = model_presets()
    if name == "auto":
        if presets["glimmer"]["base_url"]:
            name = "glimmer"
        elif presets["custom"]["base_url"]:
            name = "custom"
        elif presets["openai"]["api_key"]:
            name = "openai"
        else:
            raise ConfigError(
                "No model configured. Put one of these in .env:\n"
                "  GLIMMER_30B_BACKEND=http://<host>/v1   (private Muse Glimmer)\n"
                "  OPENAI_API_KEY=sk-...                  (OpenAI)\n"
                "then run `ligase doctor`."
            )
    name = "openai" if name == "luna" else name  # benchmark-era alias
    if name not in presets:
        raise ConfigError(f"Unknown model '{name}'. Choose from: {', '.join(MODEL_CHOICES)}.")
    cfg = dict(presets[name], name=name)
    if cfg.get("base_url_env") and not cfg["base_url"]:
        raise ConfigError(f"Set {cfg['base_url_env']} in .env to use --model {name}.")
    if cfg.get("api_key_env") and not cfg["api_key"]:
        raise ConfigError(f"Set {cfg['api_key_env']} in .env to use --model {name}.")
    if name == "custom" and not cfg["model"]:
        raise ConfigError("Set LIGASE_MODEL in .env to the model name served at LIGASE_BASE_URL.")
    return cfg


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_env() -> None:
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(REPO_DIR / ".env", override=False)


def _slug(text: str, n: int = 4) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "_".join(words[:n]) or "task"


def _short(value: Any, limit: int = 60) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def escape_inline_stars(text: str) -> str:
    """Keep allele names like APOE*4 literal instead of starting markdown italics."""
    return re.sub(r"(?<=\w)\*(?=\w)", r"\\*", text)


def _quiet_http_logs() -> None:
    for name in QUIET_LOGGERS:
        logging.getLogger(name).disabled = True
    quiet = logging.Filter()
    quiet.filter = lambda rec: not rec.name.startswith(QUIET_LOGGERS)
    for handler in logging.getLogger().handlers:
        handler.addFilter(quiet)


def _data_path() -> str:
    return str(Path(os.getenv("LIGASE_DATA_PATH") or os.getenv("BIOMNI_DATA_PATH") or "data").resolve())


# ── Running a study ──────────────────────────────────────────────────────────

def run_question(
    console: Console,
    question: str,
    cfg: Dict[str, Any],
    *,
    ad: bool = False,
    max_iterations: int = 15,
    out: str = "runs",
) -> int:
    if cfg["base_url"]:
        # Route Biomni's tool-internal LLM calls (query builders) to the same model.
        os.environ.setdefault("BIOMNI_LLM", cfg["model"])
        os.environ.setdefault("BIOMNI_SOURCE", "Custom")
        os.environ.setdefault("BIOMNI_CUSTOM_BASE_URL", cfg["base_url"])
        os.environ.setdefault("BIOMNI_CUSTOM_API_KEY", cfg["api_key"] or "not-needed")
    from ligase import create_agent

    t0 = time.time()
    agent = create_agent(
        model=cfg["model"],
        data_path=_data_path(),
        modules=DEFAULT_MODULES,
        is_ad_specialized=ad,
        max_iterations=max_iterations,
        api_key=cfg["api_key"] or "not-needed",
        base_url=cfg["base_url"],
    )
    setup = time.time() - t0
    _quiet_http_logs()
    n_tools = len(agent.claw_agent.tools.list())
    header = Table.grid(padding=(0, 2))
    header.add_row("[dim]model[/dim]", f"[bold]{cfg['model']}[/bold]  [dim]({cfg['where']})[/dim]")
    header.add_row("[dim]tools[/dim]", f"{n_tools} biomedical tools · OS sandbox on" + (" · AD layer" if ad else ""))
    header.add_row("[dim]task[/dim]", question)
    console.print(Panel(header, title=f"[bold cyan]{BRAND}[/bold cyan] v{VERSION}", title_align="left", border_style="cyan"))

    calls = []
    started = {}

    def on_event(kind, data):
        if kind == "tool_started":
            started[data.get("call_id")] = time.time()
            calls.append({"name": data.get("tool_name"), "args": data.get("args")})
            console.print(f"  [yellow]▸[/yellow] [bold]{data.get('tool_name')}[/bold] [dim]{_short(data.get('args') or {})}[/dim]")
        elif kind == "tool_result":
            ok = data.get("success") and '"success": false' not in str(data.get("output") or "")
            dt = time.time() - started.get(data.get("call_id"), time.time())
            mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
            preview = _short(data.get("output") or data.get("error") or "", 70)
            console.print(f"    {mark} [dim]{dt:.1f}s  {preview}[/dim]")
            if calls:
                calls[-1]["ok"] = ok
        elif kind == "warn":
            console.print(f"  [dim yellow]! {data.get('message')}[/dim yellow]")

    # Typed stream events carry tool args/call ids; the legacy channel only adds warnings.
    agent.claw_agent.on_stream_event = lambda ev: on_event(ev.kind, ev.data) if ev.kind != "warn" else None
    agent.claw_agent.on_event = lambda kind, data: on_event(kind, data) if kind == "warn" else None
    t1 = time.time()
    try:
        with console.status("[cyan]reasoning…[/cyan]", spinner="dots"):
            answer = agent.go(question)
    except KeyboardInterrupt:
        console.print("[yellow]Stopped.[/yellow]")
        return 130
    except Exception as exc:
        console.print(f"[red]Run failed: {type(exc).__name__}: {_short(str(exc), 200)}[/red]")
        console.print("Run [bold]ligase doctor[/bold] to check the model endpoint and tools.")
        return 1
    elapsed = time.time() - t1

    console.print(Panel(Markdown(escape_inline_stars(answer or "(no answer)")), title="[bold green]Answer[/bold green]", title_align="left", border_style="green"))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(out) / f"ligase_{stamp}_{_slug(question)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    iterations = getattr(agent.last_state, "iterations", "?")
    lines = [
        f"# {BRAND} run report",
        "",
        f"- **Question:** {question}",
        f"- **Model:** {cfg['model']} ({cfg['where']})",
        f"- **Agent time:** {elapsed:.1f}s (+{setup:.1f}s tool loading) · {len(calls)} tool calls · {iterations} iterations",
        "",
        "## Tool trace",
        "",
    ]
    lines += [
        f"{i}. `{c['name']}` {'ok' if c.get('ok') else 'failed'} · {_short(c.get('args') or {}, 120)}"
        for i, c in enumerate(calls, 1)
    ] or ["(answered from model knowledge, no tools)"]
    lines += ["", "## Answer", "", answer or ""]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n")

    console.print(
        f"[green]✓[/green] {len(calls)} tool call{'s' * (len(calls) != 1)} · {iterations} iteration{'s' * (iterations != 1)}"
        f" · [bold]{elapsed:.1f}s[/bold] [dim](+{setup:.1f}s tool load)[/dim]"
        f"  [dim]→ {run_dir}/report.md[/dim]"
    )
    return 0


# ── Doctor ───────────────────────────────────────────────────────────────────

def _probe_endpoint(base_url: str, api_key: Optional[str], timeout: float = 6.0) -> str:
    """Return '' when GET /models answers 200, else a short reason. Never echoes the host."""
    import httpx  # certifi-backed TLS; urllib fails on python.org builds without a cert bundle

    headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "not-needed" else {}
    try:
        resp = httpx.get(base_url.rstrip("/") + "/models", headers=headers, timeout=timeout)
    except Exception as exc:
        return type(exc).__name__
    if resp.status_code == 401:
        return "HTTP 401: API key rejected"
    return "" if resp.status_code == 200 else f"HTTP {resp.status_code}"


def doctor(console: Console) -> int:
    rows = []  # (status, check, detail)

    def add(ok: Optional[bool], check: str, detail: str) -> None:
        rows.append(("[green]ok[/green]" if ok else "[yellow]warn[/yellow]" if ok is None else "[red]fail[/red]", check, detail))

    add(sys.version_info >= (3, 10), "Python", platform.python_version())
    biomni_dir = REPO_DIR / "biomni" / "biomni"
    add(biomni_dir.is_dir(), "Biomni tool library", "found" if biomni_dir.is_dir() else "missing: run ./install.sh")
    add((REPO_DIR / ".env").exists() or (Path.cwd() / ".env").exists(), ".env file", "found" if (REPO_DIR / ".env").exists() else "missing: cp .env.example .env")

    if biomni_dir.is_dir():
        try:
            from ligase.tools_adapter import SKIPPED_MODULES, get_biomni_claw_tools

            n = len(get_biomni_claw_tools(modules=DEFAULT_MODULES))
            add(n > 0, "Domain tools", f"{n} loaded")
            for mod, reason in sorted(SKIPPED_MODULES.items()):
                add(None, f"  module {mod}", f"skipped ({_short(reason, 40)}); ./install.sh --genomics" if mod == "genomics" else f"skipped ({_short(reason, 50)})")
        except Exception as exc:
            add(False, "Domain tools", _short(f"{type(exc).__name__}: {exc}", 70))

    sandbox = "sandbox-exec" if sys.platform == "darwin" else "bwrap"
    add(bool(shutil.which(sandbox)) or None, "OS sandbox", sandbox if shutil.which(sandbox) else f"{sandbox} not found")

    try:
        cfg = resolve_model("auto")
        add(True, "Model", f"{cfg['model']} ({cfg['name']}, {cfg['where']})")
        url = cfg["base_url"] or "https://api.openai.com/v1"
        problem = _probe_endpoint(url, cfg["api_key"])
        add(not problem, "Model endpoint", "reachable" if not problem else f"not reachable ({problem})")
    except ConfigError as exc:
        add(False, "Model", str(exc).splitlines()[0])

    table = Table(title=f"{BRAND} doctor", show_header=True, header_style="bold")
    table.add_column("", width=5)
    table.add_column("Check")
    table.add_column("Detail")
    for row in rows:
        table.add_row(*row)
    console.print(table)
    failed = sum(1 for r in rows if "fail" in r[0])
    if failed:
        console.print(f"[red]{failed} check(s) failed.[/red] Fix the first one, then run [bold]ligase doctor[/bold] again.")
        return 1
    console.print("[green]Ready.[/green] Try: [bold]ligase example apoe4[/bold]")
    return 0


# ── Entry point ──────────────────────────────────────────────────────────────

def _print_examples(console: Console) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Study")
    for name, ex in EXAMPLES.items():
        table.add_row(name, ex["title"])
    console.print(table)
    console.print("Run one: [bold]ligase example apoe4[/bold]")


def _interactive(console: Console, cfg: Dict[str, Any], ad: bool, max_iterations: int, out: str) -> int:
    console.print(f"[bold cyan]{BRAND}[/bold cyan] · {cfg['model']} · type a research question, [bold]examples[/bold] to list studies, [bold]exit[/bold] to quit.")
    while True:
        try:
            question = console.input("[bold green]?[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit", ":q"}:
            return 0
        if question.lower() == "examples":
            _print_examples(console)
            continue
        if question.lower() in EXAMPLES:
            ex = EXAMPLES[question.lower()]
            run_question(console, ex["question"], cfg, ad=ex["ad"], max_iterations=ex["max_iterations"], out=out)
            continue
        run_question(console, question, cfg, ad=ad, max_iterations=max_iterations, out=out)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="auto", choices=MODEL_CHOICES, help="model preset (default: auto from .env)")
    common.add_argument("--out", default="runs", help="directory for run reports (default: runs)")
    common.add_argument("--record", help="also save the terminal session as SVG")

    parser = argparse.ArgumentParser(prog="ligase", description=f"{BRAND}: local-first biomedical research agent", parents=[common])
    parser.add_argument("--version", action="version", version=f"{BRAND} {VERSION}")
    parser.add_argument("--ad", action="store_true", help="enable Alzheimer's disease context layer")
    parser.add_argument("--max-iterations", type=int, default=15)
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", parents=[common], help="run one research question")
    run.add_argument("question")
    run.add_argument("--ad", action="store_true", help="enable Alzheimer's disease context layer")
    run.add_argument("--max-iterations", type=int, default=15, help="cap on tool rounds (default: 15)")

    example = sub.add_parser("example", parents=[common], help="run a ready-made study")
    example.add_argument("name", choices=sorted(EXAMPLES))

    sub.add_parser("examples", help="list ready-made studies")
    sub.add_parser("doctor", help="check install, tools, model endpoint and sandbox")
    sub.add_parser("chat", parents=[common], help="interactive prompt (same as no command)")
    return parser


def main(argv=None) -> int:
    _load_env()
    args = build_parser().parse_args(argv)
    console = Console(record=bool(getattr(args, "record", None)), width=100)
    if getattr(args, "record", None):
        shown = [a for a in (argv or sys.argv[1:]) if not a.startswith("--record") and a != args.record]
        console.print("[bold green]$[/bold green] ligase " + " ".join(f'"{a}"' if " " in a else a for a in shown))

    try:
        if args.cmd == "examples":
            _print_examples(console)
            return 0
        if args.cmd == "doctor":
            return doctor(console)
        cfg = resolve_model(args.model)
        if args.cmd == "run":
            code = run_question(console, args.question, cfg, ad=args.ad, max_iterations=args.max_iterations, out=args.out)
        elif args.cmd == "example":
            ex = EXAMPLES[args.name]
            code = run_question(console, ex["question"], cfg, ad=ex["ad"], max_iterations=ex["max_iterations"], out=args.out)
        else:
            code = _interactive(console, cfg, getattr(args, "ad", False), getattr(args, "max_iterations", 15), args.out)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    if getattr(args, "record", None):
        console.save_svg(args.record, title=f"ligase {args.cmd or 'chat'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
