"""
The "logger agent" — not a decision-maker, a thin wrapper the orchestrator puts around
every agent.run() call.

Deliberately extends the existing plain-text stdlib logging convention (main.py's one
logging.basicConfig(), everything else via logging.getLogger(__name__)) instead of
introducing a new structured-logging system — so `sudo docker compose logs api | grep`
keeps working exactly as already documented in docs/DEPLOYMENT.md. The structure lives
in the key=value tags inside the message, not in a new log format:

    grep "trace=<id>"                    -> full lineage of one symbol's decision, in order
    grep "agent=SectorConcentrationAgent" -> every decision that one agent has ever made
    grep "verdict=VETO"                   -> every blocked candidate, with which agent and why
    grep "verdict=ERROR"                  -> agents that threw, isolated from legitimate vetoes
"""

import logging
import time

from agents.base import AgentContext, AgentResult, BaseAgent, Verdict

logger = logging.getLogger(__name__)


def run_traced(agent: BaseAgent, ctx: AgentContext) -> AgentResult:
    """
    Runs one agent with failure isolation — an agent that raises never crashes the
    orchestrator or any other agent. Converted to PASS or VETO per that agent's own
    fail_open flag (see base.py), not a blanket default.
    """
    start = time.perf_counter()
    try:
        result = agent.run(ctx)
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        treated_as = Verdict.PASS if agent.fail_open else Verdict.VETO
        logger.error(
            f"[AGENT] trace={ctx.trace_id} symbol={ctx.symbol} agent={agent.name} "
            f"verdict=ERROR duration_ms={duration_ms:.0f} fail_open={agent.fail_open} "
            f"treated_as={treated_as.value} error={e}"
        )
        return AgentResult(
            agent_name=agent.name, verdict=treated_as,
            reason=f"agent raised: {e}", duration_ms=duration_ms,
        )

    duration_ms = (time.perf_counter() - start) * 1000
    result.duration_ms = duration_ms
    logger.info(
        f"[AGENT] trace={ctx.trace_id} symbol={ctx.symbol} agent={agent.name} "
        f"verdict={result.verdict.value} duration_ms={duration_ms:.0f} reason={result.reason}"
    )
    return result
