import { useEffect, useState } from "react";
import type { PendingSignal } from "../types";
import { getRecentSignals } from "../api/client";
import { SOURCE_LABEL, SOURCE_STYLE } from "../utils/tradeDisplay";
import SizingMathTable from "./SizingMathTable";

function outcomeBadge(s: PendingSignal): { label: string; style: string } {
  if (s.status === "EXPIRED") return { label: "⏱ Expired — never actioned", style: "bg-slate-700/50 text-slate-400 border-slate-600" };
  if (s.status === "REJECTED") return { label: "🚫 You rejected this", style: "bg-slate-700/50 text-slate-400 border-slate-600" };
  const resStatus = s.resolution?.status;
  if (resStatus === "EXECUTED") return { label: "✅ Order placed", style: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" };
  if (resStatus === "ERROR") return { label: "⚠️ Broker error", style: "bg-red-500/20 text-red-300 border-red-500/40" };
  return { label: "❌ Rejected", style: "bg-red-500/20 text-red-300 border-red-500/40" };
}

interface Props {
  /** Bumped by the parent whenever pending signals refresh (e.g. right after an
   * approve/reject click), so this list updates without a manual click too. */
  refreshTrigger?: number;
}

export default function RecentDecisions({ refreshTrigger }: Props) {
  const [signals, setSignals] = useState<PendingSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getRecentSignals(20)
      .then((data) => setSignals(data.signals))
      .catch(() => setError("Could not load recent decisions."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTrigger]);

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-300">Recent Decisions</h3>
          <p className="text-slate-500 text-xs">
            What happened to signals you already approved or rejected — including why, if it didn't go through.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs bg-slate-800 hover:bg-slate-700 disabled:opacity-50 px-3 py-1.5 rounded-lg border border-slate-700 transition-colors"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {!error && !loading && signals.length === 0 && (
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-6 text-center text-slate-500 text-sm">
          No resolved signals yet.
        </div>
      )}

      <div className="space-y-3">
        {signals.map((s) => {
          const outcome = outcomeBadge(s);
          const breakdown = s.resolution?.sizing_breakdown;
          return (
            <div key={s.id} className="bg-slate-800 rounded-xl border border-slate-700 p-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold">{s.symbol}</span>
                {s.direction === "SHORT" && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 border border-red-500/40">
                    SHORT
                  </span>
                )}
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${SOURCE_STYLE[s.source]}`}>
                  {SOURCE_LABEL[s.source]}
                </span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${outcome.style}`}>
                  {outcome.label}
                </span>
              </div>

              {(s.status === "APPROVED" && s.resolution?.status !== "EXECUTED") && (
                <p className="text-slate-400 text-xs mt-2">{s.resolution?.reason}</p>
              )}
              {s.resolution?.status === "EXECUTED" && (
                <p className="text-slate-400 text-xs mt-2">
                  Qty {s.resolution.quantity} @ ₹{s.resolution.entry_price}
                </p>
              )}

              {breakdown && <SizingMathTable symbol={s.symbol} b={breakdown} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
