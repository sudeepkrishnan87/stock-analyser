import { useEffect, useState, useCallback } from "react";
import type { OpenPosition, ClosedTrade, PortfolioSummary } from "../types";
import { getPortfolio, getOpenPositions, getTradeHistory } from "../api/client";
import { SOURCE_LABEL, SOURCE_STYLE, formatINR, formatPct, pnlColorClass } from "../utils/tradeDisplay";

function StatTile({ label, value, valueClass = "text-slate-100" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <p className="text-slate-500 text-xs">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueClass}`}>{value}</p>
    </div>
  );
}

function ReasonCell({ reason }: { reason: string }) {
  if (!reason) return <span className="text-slate-600">—</span>;
  return (
    <span className="text-slate-400 text-xs line-clamp-2 max-w-xs" title={reason}>
      {reason}
    </span>
  );
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function TradeBook() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [trades, setTrades] = useState<ClosedTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, pos, hist] = await Promise.all([
        getPortfolio(),
        getOpenPositions(),
        getTradeHistory(100),
      ]);
      setPortfolio(p);
      setPositions(pos.positions);
      setTrades(hist.trades);
    } catch {
      setError("Could not load trade book. Try refreshing.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !portfolio) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-900/30 border border-red-500/50 rounded-xl text-red-300 text-sm">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Trade Book</h2>
          <p className="text-slate-500 text-sm">
            Only trades Jarvis itself identified and you approved — never your pre-existing holdings.
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

      {/* ── Stat tiles ─────────────────────────────────────────────────── */}
      {portfolio && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile
            label="Realized P&L"
            value={formatINR(portfolio.realized_pnl)}
            valueClass={pnlColorClass(portfolio.realized_pnl)}
          />
          <StatTile
            label="Win Rate"
            value={`${portfolio.win_rate.toFixed(1)}%`}
            valueClass={portfolio.win_rate >= 50 ? "text-emerald-400" : "text-slate-100"}
          />
          <StatTile label="Total Trades" value={String(portfolio.total_trades)} />
          <StatTile
            label="Open Positions"
            value={String(portfolio.open_positions)}
            valueClass={portfolio.open_positions > 0 ? "text-amber-400" : "text-slate-100"}
          />
        </div>
      )}

      {/* ── Open positions ─────────────────────────────────────────────── */}
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Open Positions</h3>
        {positions.length === 0 ? (
          <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-6 text-center text-slate-500 text-sm">
            No open positions right now.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-800 text-slate-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-left px-3 py-2">Source</th>
                  <th className="text-right px-3 py-2">Entry</th>
                  <th className="text-right px-3 py-2">Stop Loss</th>
                  <th className="text-right px-3 py-2">Target</th>
                  <th className="text-right px-3 py-2">Qty</th>
                  <th className="text-right px-3 py-2">Risk ₹</th>
                  <th className="text-right px-3 py-2">Score</th>
                  <th className="text-left px-3 py-2">Reason</th>
                  <th className="text-left px-3 py-2">Entered</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {positions.map((p) => (
                  <tr key={p.symbol} className="bg-slate-900/40 hover:bg-slate-800/60">
                    <td className="px-3 py-2 font-semibold">
                      {p.symbol}
                      <span className="ml-1.5 text-xs text-slate-500">{p.direction}</span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${SOURCE_STYLE[p.source]}`}>
                        {SOURCE_LABEL[p.source]}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">₹{p.entry_price.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-red-400">₹{p.stop_loss.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-emerald-400">₹{p.target.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right">{p.quantity}</td>
                    <td className="px-3 py-2 text-right">₹{p.risk_amount.toFixed(0)}</td>
                    <td className="px-3 py-2 text-right">{p.signal_score}</td>
                    <td className="px-3 py-2"><ReasonCell reason={p.reason} /></td>
                    <td className="px-3 py-2 text-slate-500 text-xs whitespace-nowrap">{fmtTime(p.entry_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Closed trade history ───────────────────────────────────────── */}
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Trade History</h3>
        {trades.length === 0 ? (
          <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-6 text-center text-slate-500 text-sm">
            No closed trades yet.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-800 text-slate-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-left px-3 py-2">Source</th>
                  <th className="text-right px-3 py-2">Entry</th>
                  <th className="text-right px-3 py-2">Exit</th>
                  <th className="text-right px-3 py-2">P&L</th>
                  <th className="text-left px-3 py-2">Exit Reason</th>
                  <th className="text-right px-3 py-2">Score</th>
                  <th className="text-left px-3 py-2">Reason</th>
                  <th className="text-left px-3 py-2">Closed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {trades.map((t, i) => (
                  <tr key={`${t.symbol}-${t.exit_time}-${i}`} className="bg-slate-900/40 hover:bg-slate-800/60">
                    <td className="px-3 py-2 font-semibold">
                      {t.symbol}
                      <span className="ml-1.5 text-xs text-slate-500">{t.direction}</span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${SOURCE_STYLE[t.source]}`}>
                        {SOURCE_LABEL[t.source]}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">₹{t.entry_price.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right">₹{t.exit_price.toFixed(2)}</td>
                    <td className={`px-3 py-2 text-right font-semibold ${pnlColorClass(t.pnl)}`}>
                      {formatINR(t.pnl, 0)}
                      <span className="block text-xs font-normal">{formatPct(t.pnl_pct)}</span>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-400">{t.exit_reason}</td>
                    <td className="px-3 py-2 text-right">{t.signal_score}</td>
                    <td className="px-3 py-2"><ReasonCell reason={t.reason} /></td>
                    <td className="px-3 py-2 text-slate-500 text-xs whitespace-nowrap">{fmtTime(t.exit_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
