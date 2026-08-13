import { useEffect, useState } from "react";
import type { ScanSymbolResult, DryRunResult } from "../types";
import { scanSymbol, dryRunTrade, enterTrade } from "../api/client";

interface Props {
  symbol: string;
}

const SIGNAL_STYLE: Record<string, string> = {
  "STRONG BUY": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  "BUY": "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  "WATCH": "bg-amber-500/20 text-amber-300 border-amber-500/40",
  "NEUTRAL": "bg-slate-500/20 text-slate-400 border-slate-500/40",
};

export default function TradeSetupCard({ symbol }: Props) {
  const [scan, setScan] = useState<ScanSymbolResult | null>(null);
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [entering, setEntering] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setScan(null);
    setDryRun(null);
    setResult(null);

    scanSymbol(symbol)
      .then(async (s) => {
        if (cancelled) return;
        setScan(s);
        if (s.trade_suggestion) {
          try {
            const dr = await dryRunTrade({
              symbol,
              direction: "LONG",
              entry_price: s.trade_suggestion.entry,
              stop_loss: s.trade_suggestion.stop_loss,
              target: s.trade_suggestion.target,
              trade_type: s.trade_suggestion.trade_type,
            });
            if (!cancelled) setDryRun(dr);
          } catch {
            // Quantity preview is best-effort — Approve still works without it.
          }
        }
      })
      .catch(() => {
        if (!cancelled) setScan(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const approve = async () => {
    if (!scan?.trade_suggestion) return;
    setEntering(true);
    setResult(null);
    try {
      const ts = scan.trade_suggestion;
      const res = await enterTrade({
        symbol,
        direction: "LONG",
        entry_price: ts.entry,
        stop_loss: ts.stop_loss,
        target: ts.target,
        trade_type: ts.trade_type,
        product: ts.trade_type === "INTRADAY" ? "MIS" : "CNC",
        signal_score: scan.signal_score,
        source: "MANUAL",
        reason: `Manually approved from Research tab, score ${scan.signal_score}/130`,
      });
      setResult(
        res.status === "EXECUTED"
          ? `Order placed — qty ${res.quantity} @ ₹${res.entry_price}`
          : res.status || "Done"
      );
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Request failed";
      setResult(`Error: ${msg}`);
    } finally {
      setEntering(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <div className="flex items-center gap-3 text-slate-500 text-sm">
          <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          Checking trade setup…
        </div>
      </div>
    );
  }

  if (!scan) {
    return null; // scoring is best-effort — don't block the rest of the page over it
  }

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
      <div className="flex items-center gap-2 flex-wrap">
        <h3 className="text-sm font-semibold text-slate-300">Trade Setup</h3>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${SIGNAL_STYLE[scan.signal] ?? SIGNAL_STYLE.NEUTRAL}`}>
          {scan.signal}
        </span>
        <span className="text-slate-500 text-xs">Score {scan.signal_score}/130</span>
      </div>

      {!scan.trade_suggestion ? (
        <p className="text-slate-500 text-sm mt-3">
          {scan.error
            ? `No viable trade setup — ${scan.error}.`
            : "No viable trade setup right now — signal doesn't clear the BUY threshold, or R:R is below 1.5."}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-sm">
            <div>
              <p className="text-slate-500 text-xs">Entry</p>
              <p className="font-semibold">₹{scan.trade_suggestion.entry.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">Stop Loss</p>
              <p className="font-semibold text-red-400">₹{scan.trade_suggestion.stop_loss.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">Target</p>
              <p className="font-semibold text-emerald-400">₹{scan.trade_suggestion.target.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">R:R</p>
              <p className="font-semibold">1:{scan.trade_suggestion.rr_ratio}</p>
            </div>
          </div>

          <p className="text-xs mt-3">
            <span className="text-slate-500">Est. Qty: </span>
            {dryRun ? (
              <span className="font-semibold text-slate-300">
                {dryRun.quantity} shares (₹
                {(dryRun.quantity * dryRun.entry_price).toLocaleString("en-IN", { maximumFractionDigits: 0 })})
              </span>
            ) : (
              <span className="text-slate-600">unavailable</span>
            )}
          </p>

          {result ? (
            <p className="mt-4 text-sm text-slate-300 bg-slate-900/60 rounded-lg px-3 py-2">{result}</p>
          ) : (
            <button
              onClick={approve}
              disabled={entering}
              className="mt-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold py-2 px-4 rounded-lg transition-colors"
            >
              {entering
                ? "Placing order…"
                : `Approve & Enter (${scan.trade_suggestion.trade_type === "INTRADAY" ? "MIS" : "CNC"})`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
