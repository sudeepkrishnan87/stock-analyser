"""
Agent contract — every agent in backend/agents/ implements this and only this.

Deliberately sync (matches the rest of the codebase: sync routers, BackgroundScheduler,
sync broker SDKs — see docs/TRADING_LOGIC.md and the agent architecture plan). Parallel
fan-out across agents is done by the orchestrator via ThreadPoolExecutor, not asyncio.

Deliberately not LLM-driven — every agent here is a deterministic Python rule, same as
screener_service.py's scoring functions. Claude stays narrative-only per CLAUDE.md; this
package doesn't change that.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional


class Verdict(Enum):
    PASS = "PASS"       # no objection
    VETO = "VETO"       # hard block — orchestrator must not let the candidate proceed
    ADJUST = "ADJUST"   # modifies score/sizing/SL/target via `data`, doesn't block
    INFO = "INFO"       # advisory only — logged, never blocks, never adjusts


@dataclass
class AgentContext:
    trace_id: str
    symbol: str
    candidate: dict            # the evolving candidate: scoring output, later adjusted by ADJUST verdicts
    now: datetime
    shared: Dict = field(default_factory=dict)  # per-scan-cycle cache (Nifty trend, VIX, sector map, ...)
                                                 # fetched once per tick, not once per symbol x per agent


@dataclass
class AgentResult:
    agent_name: str
    verdict: Verdict
    reason: str
    data: Optional[Dict] = None
    duration_ms: float = 0.0


class BaseAgent(ABC):
    """
    name and fail_open are class attributes, not instance state — every agent is a
    stateless rule, so a single module-level instance can be shared/registered once.
    """
    name: str = "BaseAgent"
    # What happens if run() raises, before the orchestrator ever sees a verdict:
    # True  -> treated as PASS (a buggy low-stakes agent can't block trading)
    # False -> treated as VETO (a buggy safety-critical agent doesn't silently fail open)
    # Must be set explicitly per agent — no safe universal default.
    fail_open: bool = True

    @abstractmethod
    def run(self, ctx: AgentContext) -> AgentResult:
        ...
