"""
Ligase Agent: High-performance Biomedical AI Agent powered by ClawAgents backbone.
"""

import asyncio
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

# Ensure paths are set
pkg_dir = Path(__file__).resolve().parent
repo_dir = pkg_dir.parent
for p in [
    Path(os.environ["LIGASE_BIOMNI_PATH"]) if os.environ.get("LIGASE_BIOMNI_PATH") else None,
    repo_dir / "biomni",
    repo_dir / "clawagents_py" / "src",
    Path.cwd() / "biomni",
]:
    if p and p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from clawagents.agent import ClawAgent, create_claw_agent
from ligase.tools_adapter import get_biomni_claw_tools
from ligase.context_layers import BiomniDataLakeLayer, BiomniKnowHowLayer, BiomniADLayer
from ligase.gemma_harness import (
    GEMMA_OPERATING_RULES,
    apply_gemma_tool_surface,
    attach_gemma_tools,
    bind_gemma_harness_profile,
    cap_gemma_iterations,
    close_multiple_choice,
    merge_tool_cards,
    select_gemma_domain_tools,
)
from ligase.gemma_tools import clear_tool_cards
from ligase.local_harness import (
    apply_local_tool_surface,
    is_compact_local_model,
    is_gemma_local_model,
    knowledge_fallback_answer,
    local_system_addendum,
    needs_knowledge_fallback,
    normalize_local_answer,
    select_local_domain_tools,
)


class LigaseAgent:
    """
    Ligase Agent with ClawAgents high-performance backbone.
    Provides complete API compatibility with Biomni A1 / AD1 while delivering
    70%+ latency reduction, 75%+ token cost savings, and zero-parse-failure execution.
    """

    def __init__(
        self,
        claw_agent: ClawAgent,
        data_path: str = "./data",
        commercial_mode: bool = False,
        is_ad_specialized: bool = False,
        sandbox_enabled: bool = True,
    ):
        self.claw_agent = claw_agent
        self.data_path = data_path
        self.commercial_mode = commercial_mode
        self.is_ad_specialized = is_ad_specialized
        self.sandbox_enabled = sandbox_enabled
        self.compact_local = False
        self.gemma_local = False
        self.last_result: Optional[str] = None
        self.last_state: Any = None
        self.trajectory_history: List[Dict[str, Any]] = []

    def go(self, prompt: str) -> str:
        """Run a biomedical research task synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(self.go_async(prompt))
        else:
            return asyncio.run(self.go_async(prompt))

    async def go_async(self, prompt: str) -> str:
        """Run a biomedical research task asynchronously."""
        if not prompt or not str(prompt).strip():
            raise ValueError("Task prompt must be a non-empty string.")
        t0 = time.time()
        if self.gemma_local:
            clear_tool_cards()
        state = await self.claw_agent.invoke(task=prompt)
        result = state.result if hasattr(state, "result") else str(state)
        if self.compact_local and needs_knowledge_fallback(state):
            fallback = await knowledge_fallback_answer(self.claw_agent, prompt)
            if fallback:
                result = fallback
        result = close_multiple_choice(prompt, normalize_local_answer(str(result or "")))
        if self.compact_local:
            result = merge_tool_cards(result)
        if hasattr(state, "result"):
            state.result = result
        elapsed = time.time() - t0
        self.last_state = state
        self.last_result = result
        self.trajectory_history.append(
            {
                "prompt": prompt,
                "result": self.last_result,
                "iterations": getattr(state, "iterations", None),
                "status": getattr(state, "status", "done"),
                "elapsed_s": round(elapsed, 3),
            }
        )
        return self.last_result

    def go_stream(self, prompt: str) -> Generator[str, None, None]:
        """Stream execution events and assistant output tokens."""
        q: "queue.Queue[Optional[str]]" = queue.Queue()
        emitted_deltas: List[str] = []
        errors: List[BaseException] = []

        prev_stream = getattr(self.claw_agent, "on_stream_event", None)
        prev_event = getattr(self.claw_agent, "on_event", None)

        def _handle_event(kind: str, data: Dict[str, Any]) -> None:
            if kind == "assistant_delta":
                piece = data.get("content") or data.get("delta") or ""
                if piece:
                    emitted_deltas.append(str(piece))
                    q.put(str(piece))
            elif kind == "tool_started":
                tname = data.get("tool_name") or "tool"
                q.put(f"\n[tool: {tname}]\n")

        def _stream_hook(ev: Any) -> None:
            if prev_stream is not None:
                prev_stream(ev)
            _handle_event(getattr(ev, "kind", ""), getattr(ev, "data", {}) or {})

        def _event_hook(kind: str, data: Dict[str, Any]) -> None:
            if prev_event is not None:
                prev_event(kind, data)
            if prev_stream is None:
                _handle_event(kind, data or {})

        self.claw_agent.on_stream_event = _stream_hook
        self.claw_agent.on_event = _event_hook

        def _worker() -> None:
            try:
                final = self.go(prompt)
                if not emitted_deltas and final:
                    q.put(final)
            except BaseException as exc:
                errors.append(exc)
            finally:
                self.claw_agent.on_stream_event = prev_stream
                self.claw_agent.on_event = prev_event
                q.put(None)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        while True:
            item = q.get()
            if item is None:
                break
            yield item
        thread.join(timeout=1.0)
        if errors:
            raise errors[0]


def create_agent(
    model: str = "gpt-5.6-luna",
    data_path: str = "./data",
    modules: Optional[List[str]] = None,
    commercial_mode: bool = False,
    is_ad_specialized: bool = False,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    streaming: bool = False,
    max_iterations: int = 30,
    sandbox_enabled: bool = True,
) -> LigaseAgent:
    """
    Factory to create a Ligase Agent.

    Args:
        model: Frontier or local model name ("gpt-5.6-luna", "Muse-Glimmer-30B", etc.)
        data_path: Path to local and S3 biological data lake
        modules: List of specific biomedical domain modules to load
        commercial_mode: Filter non-commercial datasets
        is_ad_specialized: Include Alzheimer's disease priority rules and catalog sources
        api_key: Optional API key
        base_url: Custom base URL
        streaming: Stream responses
        max_iterations: Max tool rounds
        sandbox_enabled: Run execution tools inside OS sandbox (seatbelt / bwrap)
    """
    if modules is None:
        modules = ["database", "literature", "genomics", "pharmacology", "biochemistry", "molecular_biology"]

    max_iterations = max(1, int(max_iterations))
    workspace_path = Path(data_path).expanduser().resolve()
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL")
    compact_local = is_compact_local_model(model, resolved_base_url)
    gemma_local = compact_local and is_gemma_local_model(model)
    if compact_local:
        bind_gemma_harness_profile(model)
    if gemma_local:
        max_iterations = cap_gemma_iterations(max_iterations)

    # Bridge domain tools into ClawAgents
    domain_tools = get_biomni_claw_tools(modules=modules)
    if compact_local:
        domain_tools = select_local_domain_tools(attach_gemma_tools(domain_tools))
    if gemma_local:
        domain_tools = select_gemma_domain_tools(domain_tools)

    # Build system instructions
    if compact_local:
        instruction_parts = [
            "You are Ligase, a biomedical research agent.",
            "Answer from established knowledge when you can. Prefer a short, exact final answer.",
            local_system_addendum(is_ad_specialized=is_ad_specialized),
        ]
        if gemma_local:
            instruction_parts.append(GEMMA_OPERATING_RULES)
    else:
        instruction_parts = [
            "You are Ligase, a state-of-the-art biomedical and life sciences AI research agent.",
            "You possess deep expertise in genomics, bioinformatics, structural biology, pharmacology, and clinical research.",
            "You have access to specialized biomedical database and analysis tools, as well as a sandboxed terminal for code execution.",
            "Solve problems rigorously, retrieve ground-truth data, and provide precise, evidence-backed scientific conclusions.",
        ]
        dl_layer = BiomniDataLakeLayer(data_path=str(workspace_path), commercial_mode=commercial_mode)
        dl_text = dl_layer.inject(None)
        if dl_text:
            instruction_parts.append(dl_text)

        kh_layer = BiomniKnowHowLayer(commercial_mode=commercial_mode)
        kh_text = kh_layer.inject(None)
        if kh_text:
            instruction_parts.append(kh_text)

        if is_ad_specialized:
            ad_layer = BiomniADLayer()
            ad_text = ad_layer.inject(None)
            if ad_text:
                instruction_parts.append(ad_text)

    system_instruction = "\n\n".join(instruction_parts)

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "api_key": api_key or os.getenv("OPENAI_API_KEY"),
        "base_url": resolved_base_url,
        "instruction": system_instruction,
        "tools": domain_tools,
        "streaming": streaming,
        "max_iterations": max_iterations,
        "workspace": str(workspace_path),
        "allow_full_access": not bool(sandbox_enabled),
    }
    if compact_local:
        create_kwargs.update(
            {
                "wire_api": "chat_completions",
                "max_tokens": 2048,
                "temperature": 0.0,
                "learn": False,
                "trajectory": False,
                "rethink": True,
                "tool_discovery": False,
                "memory": [],
            }
        )

    claw_agent = create_claw_agent(**create_kwargs)
    if gemma_local:
        apply_gemma_tool_surface(claw_agent, domain_tools)
    elif compact_local:
        apply_local_tool_surface(claw_agent, domain_tools)

    agent = LigaseAgent(
        claw_agent=claw_agent,
        data_path=str(workspace_path),
        commercial_mode=commercial_mode,
        is_ad_specialized=is_ad_specialized,
        sandbox_enabled=sandbox_enabled,
    )
    agent.compact_local = compact_local
    agent.gemma_local = gemma_local
    return agent


# Backwards-compatible aliases for Biomni-Plus callers
BiomniPlusAgent = LigaseAgent
create_biomni_plus_agent = create_agent
