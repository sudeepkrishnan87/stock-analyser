"""
ScoringAgent — a pure wrapper around the existing, unchanged screener_service.scan_symbol().

Every other agent evaluates or adjusts a candidate that already exists; this one produces
it. It still implements the same run(ctx) -> AgentResult contract as every other agent
(for a uniform interface through the tracing/orchestrator plumbing) — the caller passes
the pre-fetched candle DataFrame in via ctx.candidate rather than a candidate to judge.

Deliberately does not reimplement any scoring math — see docs/TRADING_LOGIC.md §1/§1a
for the actual composite scoring engine, which stays exactly as-is.
"""

from agents.base import AgentContext, AgentResult, BaseAgent, Verdict


class ScoringAgent(BaseAgent):
    name = "ScoringAgent"
    fail_open = True

    def run(self, ctx: AgentContext) -> AgentResult:
        from services import screener_service

        df = ctx.candidate.get("df")
        include_fundamentals = ctx.candidate.get("include_fundamentals", False)
        if df is None:
            return AgentResult(
                agent_name=self.name, verdict=Verdict.VETO,
                reason="no candle data provided in ctx.candidate['df']",
            )

        result = screener_service.scan_symbol(ctx.symbol, df, include_fundamentals=include_fundamentals)
        return AgentResult(
            agent_name=self.name,
            verdict=Verdict.INFO,
            reason=(
                f"signal={result.get('signal')} score={result.get('signal_score')} "
                f"short_signal={result.get('short_signal')} short_score={result.get('short_signal_score')}"
            ),
            data=result,
        )
