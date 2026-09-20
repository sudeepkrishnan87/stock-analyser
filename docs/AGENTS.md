# Agent architecture — `backend/agents/`

Current as of 2026-09-20 (Phase 0 only). This is the internal deterministic-agent framework that will eventually carry the enrichments in `docs/enrichment.md` — a sector-concentration check, a daily-drawdown gate that sees unrealized P&L, a market-regime filter, etc. — each as its own separately-traceable agent instead of more functions bolted onto `screener_service.py`.

**Not LLM agents.** Every agent here is a deterministic Python rule, same style as `screener_service.py`'s scoring functions. `services/claude_service.py` stays narrative-only per CLAUDE.md's "What this is NOT" — this package doesn't change that invariant. "Agent" here means "one well-bounded, independently-traceable concern," not "an LLM making a decision."

## Why this exists, and why it looks the way it does

The whole backend is synchronous — sync routers, `BackgroundScheduler` (not `AsyncIOScheduler`), sync broker SDKs (`kiteconnect`, `fyers-apiv3`), zero prior use of `asyncio.gather` anywhere. Parallel agent fan-out therefore uses `concurrent.futures.ThreadPoolExecutor`, not asyncio — converting the broker layer to async to support an asyncio design would have been a far bigger, riskier change than the feature itself.

Logging stays plain-text stdlib `logging` (the same one `logging.basicConfig()` in `main.py`, same `docker compose logs | grep` workflow documented in `docs/DEPLOYMENT.md`) — no new structured-logging system. Structure lives in `key=value` tags inside the message instead, so existing debugging habits keep working:
```
grep "trace=<id>"                    # full lineage of one symbol's decision, in order
grep "agent=SectorConcentrationAgent" # every decision that one specific agent has made
grep "verdict=VETO"                   # every blocked candidate, with which agent and why
grep "verdict=ERROR"                  # agents that threw, isolated from legitimate vetoes
```

## The contract (`agents/base.py`)

Every agent implements exactly one method: `def run(self, ctx: AgentContext) -> AgentResult`.

- **`Verdict`** — `PASS` (no objection) / `VETO` (hard block) / `ADJUST` (modifies the candidate via `data`, doesn't block) / `INFO` (advisory only).
- **`AgentContext`** — `trace_id`, `symbol`, `candidate` (the evolving dict: scoring output, later merged with `ADJUST` results), `now`, `shared` (a per-scan-cycle cache for expensive shared lookups — Nifty trend, VIX, sector map — fetched once per tick, not once per symbol × per agent).
- **`AgentResult`** — `agent_name`, `verdict`, `reason`, optional `data`, `duration_ms`.
- **`BaseAgent`** — declares `name: str` and `fail_open: bool` as class attributes. `fail_open` decides what happens if `run()` raises: `True` → treated as `PASS` (a buggy low-stakes agent can't block trading), `False` → treated as `VETO` (a buggy safety-critical agent doesn't silently fail open). Must be set explicitly per agent — there's no safe universal default.

## Tracing (`agents/tracing.py`) — the "logger agent"

`run_traced(agent, ctx)` wraps every `agent.run()` call: times it, catches any exception (converts per `fail_open`, logs `verdict=ERROR`), and logs one line per invocation in the grep-friendly format above. This is what makes "which subagent is making issues" answerable — an agent that starts erroring shows up immediately via `grep "verdict=ERROR"`, without taking down the orchestrator or any other agent.

## Orchestrator (`agents/orchestrator.py`)

Module-level singleton (`orchestrator`), started/stopped in `main.py`'s `lifespan()` alongside the existing `scheduler_service.start_scheduler()`/`stop_scheduler()` calls (`start_orchestrator()` creates the `ThreadPoolExecutor`, `stop_orchestrator()` shuts it down).

`orchestrator.register(agent, sequential=False)` — registers an agent into the parallel risk/context fan-out group (default) or the sequential group (`sequential=True`, for agents like sizing/SL-target placement that need to run *after* the fan-out's `ADJUST` results are merged in, not concurrently with them).

`orchestrator.evaluate_candidate(symbol, candidate, shared)`:
1. Builds a fresh `AgentContext` (new `trace_id` per call).
2. Fans out to every registered risk-group agent in parallel via the `ThreadPoolExecutor`.
3. Any `VETO` → rejects the candidate outright, returns immediately.
4. Otherwise, merges every `ADJUST` result's `data` into the candidate.
5. Runs sequential-group agents in registration order against the adjusted candidate — these can also `VETO`.
6. Returns an `OrchestratorDecision` (`approved`, the final `candidate`, the full list of `AgentResult`s, and `veto_reason` if rejected).

## `ScoringAgent` (`agents/scoring_agent.py`)

A pure wrapper around the existing, unchanged `screener_service.scan_symbol()` — every other agent will evaluate or adjust a candidate that already exists; this one produces it. It still implements the same `run(ctx) -> AgentResult` contract for a uniform interface: the caller passes the pre-fetched candle DataFrame in via `ctx.candidate["df"]` rather than a candidate to judge, and it returns `verdict=INFO` with the full `scan_symbol()` result dict in `data`.

## Phase 0 status (current)

**Shadow mode — zero behavior change.** `scheduler_service.job_intraday_scan()` calls `orchestrator.evaluate_candidate()` for every one of the top-3 LONG and top-3 SHORT candidates it already considers, purely to produce trace logs and prove the plumbing works end-to-end. No risk agents are registered yet, so every call trivially approves — **the existing inline alert/queue logic is completely untouched** and still makes every real decision, exactly as before this change.

Next phases (per `docs/enrichment.md` and the agent-architecture plan): `AnalyticsAgent` (read-only, win-rate by factor/source — the lowest-risk first *real* agent), then `DailyDrawdownAgent`/`SectorConcentrationAgent` behind an `AGENTS_ENFORCE_VETO` flag (shadow-logs their would-be verdicts before ever actually blocking a trade), then the remaining signal-quality and portfolio-context agents. Each phase ships independently and gets its own shadow-mode verification period before the next — never a big-bang change on a system that places real orders.

## Naming conventions

- File: `snake_case_agent.py`, one agent per file, in `backend/agents/`.
- Class: `PascalCaseAgent`, always suffixed `Agent`, inherits `BaseAgent`.
- Matches the existing `brokers/` package's ABC pattern (`base.py` + one concrete class per file) rather than `services/`'s flat-function pattern — agents are inherently polymorphic (same contract, different logic per concern), same as `BaseBroker`'s concrete subclasses.
