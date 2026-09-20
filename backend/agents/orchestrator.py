"""
Orchestrator — fans out to registered risk/context agents in parallel, aggregates their
verdicts, then runs any sequential (sizing/SL-target) agents, and returns one decision.

Parallel fan-out uses ThreadPoolExecutor, not asyncio — the whole backend is synchronous
(sync routers, BackgroundScheduler, sync broker SDKs; see the agent architecture plan),
so this is the concurrency primitive that actually fits, with zero changes required
anywhere else in the codebase.

Phase 0 (current state): no risk agents are registered yet, so evaluate_candidate()
always approves — it exists purely to prove the tracing/plumbing works before any real
decision depends on it. See scheduler_service.py's shadow-mode call sites.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pytz

from agents.base import AgentContext, AgentResult, BaseAgent, Verdict
from agents.tracing import run_traced

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_executor: Optional[ThreadPoolExecutor] = None


def start_orchestrator() -> None:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent")
        logger.info("[ORCHESTRATOR] Started (ThreadPoolExecutor, max_workers=8)")


def stop_orchestrator() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None
        logger.info("[ORCHESTRATOR] Stopped")


@dataclass
class OrchestratorDecision:
    trace_id: str
    symbol: str
    approved: bool
    candidate: dict
    results: List[AgentResult] = field(default_factory=list)
    veto_reason: Optional[str] = None


class Orchestrator:
    def __init__(self) -> None:
        self._risk_agents: List[BaseAgent] = []
        self._sequential_agents: List[BaseAgent] = []  # sizing/SL-target — run after fan-out, in order

    def register(self, agent: BaseAgent, sequential: bool = False) -> None:
        (self._sequential_agents if sequential else self._risk_agents).append(agent)
        logger.info(f"[ORCHESTRATOR] Registered agent={agent.name} sequential={sequential}")

    def _run_parallel(self, agents: List[BaseAgent], ctx: AgentContext) -> List[AgentResult]:
        if not agents:
            return []
        if _executor is None:
            # Orchestrator wasn't started (e.g. a stray call before app startup) — run
            # inline rather than silently skipping every risk agent.
            logger.warning("[ORCHESTRATOR] Executor not started — running agents inline, not in parallel.")
            return [run_traced(agent, ctx) for agent in agents]
        futures = {_executor.submit(run_traced, agent, ctx): agent for agent in agents}
        results = []
        for future in as_completed(futures):
            results.append(future.result())
        return results

    def evaluate_candidate(self, symbol: str, candidate: dict, shared: Optional[Dict] = None) -> OrchestratorDecision:
        trace_id = uuid.uuid4().hex[:12]
        now = datetime.now(IST)
        shared = shared or {}

        ctx = AgentContext(trace_id=trace_id, symbol=symbol, candidate=candidate, now=now, shared=shared)
        results = self._run_parallel(self._risk_agents, ctx)

        veto = next((r for r in results if r.verdict == Verdict.VETO), None)
        if veto:
            logger.info(f"[ORCHESTRATOR] trace={trace_id} symbol={symbol} REJECTED by {veto.agent_name}: {veto.reason}")
            return OrchestratorDecision(
                trace_id=trace_id, symbol=symbol, approved=False,
                candidate=candidate, results=results, veto_reason=f"{veto.agent_name}: {veto.reason}",
            )

        adjusted = dict(candidate)
        for r in results:
            if r.verdict == Verdict.ADJUST and r.data:
                adjusted.update(r.data)

        for agent in self._sequential_agents:
            seq_ctx = AgentContext(trace_id=trace_id, symbol=symbol, candidate=adjusted, now=now, shared=shared)
            result = run_traced(agent, seq_ctx)
            results.append(result)
            if result.verdict == Verdict.VETO:
                logger.info(f"[ORCHESTRATOR] trace={trace_id} symbol={symbol} REJECTED by {result.agent_name}: {result.reason}")
                return OrchestratorDecision(
                    trace_id=trace_id, symbol=symbol, approved=False,
                    candidate=adjusted, results=results, veto_reason=f"{result.agent_name}: {result.reason}",
                )
            if result.verdict == Verdict.ADJUST and result.data:
                adjusted.update(result.data)

        logger.info(f"[ORCHESTRATOR] trace={trace_id} symbol={symbol} APPROVED ({len(results)} agents consulted)")
        return OrchestratorDecision(trace_id=trace_id, symbol=symbol, approved=True, candidate=adjusted, results=results)


# Module-level singleton — agents register onto this one instance at import/startup time,
# matching how services/scheduler_service.py's _scheduler singleton already works.
orchestrator = Orchestrator()
