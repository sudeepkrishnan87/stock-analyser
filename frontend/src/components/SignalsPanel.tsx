import { useEffect, useState } from "react";
import type { PendingSignal } from "../types";
import { approveSignal, rejectSignal } from "../api/client";

interface Props {
  signals: PendingSignal[];
  onResolved: () => void;
}

function timeLeft(expiresAt: string): string {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const mins = Math.floor(ms / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}

export default function SignalsPanel({ signals, onResolved }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [resultMsg, setResultMsg] = useState<Record<string, string>>({});
  // Re-render every second so the countdown ticks without re-polling the API.
  const [, forceTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const act = async (id: string, action: "approve" | "reject") => {
    setBusyId(id);
    try {
      const result = action === "approve" ? await approveSignal(id) : await rejectSignal(id);
      const msg =
        result.status === "EXECUTED"
          ? `Order placed — qty ${result.quantity} @ ₹${result.entry_price}`
          : result.status === "REJECTED"
          ? `Rejected: ${result.reason || "by risk gate"}`
          : result.status === "ERROR"
          ? `Error: ${result.reason}`
          : "Done";
      setResultMsg((m) => ({ ...m, [id]: msg }));
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Request failed";
      setResultMsg((m) => ({ ...m, [id]: `Error: ${msg}` }));
    } finally {
      setBusyId(null);
      onResolved();
    }
  };

  if (signals.length === 0) {
    return (
      <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-10 text-center">
        <div className="w-12 h-12 mx-auto mb-3 rounded-full border-2 border-cyan-500/40 flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        </div>
        <p className="text-slate-400">No signals awaiting approval.</p>
        <p className="text-slate-600 text-xs mt-1">
          Jarvis is watching the market — STRONG BUY breakouts will show up here the moment they fire.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {signals.map((s) => (
        <div
          key={s.id}
          className="bg-slate-800 rounded-xl border border-amber-500/30 shadow-[0_0_20px_-8px_rgba(245,158,11,0.4)] p-5"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold tracking-wide">{s.symbol}</span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/40">
                  {s.signal}
                </span>
              </div>
              <p className="text-slate-500 text-xs mt-1">
                Score {s.signal_score}/100{s.breakout_signal ? ` · ${s.breakout_signal}` : ""}
              </p>
            </div>
            <div className="text-right">
              <p className="text-slate-500 text-xs">Expires in</p>
              <p className="text-sm font-mono text-amber-400">{timeLeft(s.expires_at)}</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mt-4 text-sm">
            <div>
              <p className="text-slate-500 text-xs">Entry</p>
              <p className="font-semibold">₹{s.entry.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">Stop Loss</p>
              <p className="font-semibold text-red-400">₹{s.stop_loss.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">Target</p>
              <p className="font-semibold text-emerald-400">₹{s.target.toFixed(2)}</p>
            </div>
          </div>
          <p className="text-slate-500 text-xs mt-2">R:R 1:{s.rr_ratio}</p>

          {resultMsg[s.id] ? (
            <p className="mt-4 text-sm text-slate-300 bg-slate-900/60 rounded-lg px-3 py-2">
              {resultMsg[s.id]}
            </p>
          ) : (
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => act(s.id, "approve")}
                disabled={busyId === s.id}
                className="flex-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold py-2 rounded-lg transition-colors"
              >
                {busyId === s.id ? "Placing order…" : "Approve & Enter Trade"}
              </button>
              <button
                onClick={() => act(s.id, "reject")}
                disabled={busyId === s.id}
                className="flex-1 bg-slate-700 hover:bg-red-900/50 disabled:opacity-50 text-slate-300 hover:text-red-300 text-sm font-semibold py-2 rounded-lg transition-colors border border-slate-600 hover:border-red-700/50"
              >
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
