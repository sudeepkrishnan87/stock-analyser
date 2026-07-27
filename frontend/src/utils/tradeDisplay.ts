// Shared display helpers for anything showing a signal/trade's source or a ₹ P&L figure.
// Extracted so SignalsPanel and TradeBook render the same source exactly the same way.

export const SOURCE_LABEL: Record<string, string> = {
  PREMARKET: "Pre-Market",
  INTRADAY: "Intraday",
  SWING: "Swing (next day)",
  MANUAL: "Manual",
};

export const SOURCE_STYLE: Record<string, string> = {
  PREMARKET: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40",
  INTRADAY: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
  SWING: "bg-purple-500/20 text-purple-300 border-purple-500/40",
  MANUAL: "bg-slate-500/20 text-slate-300 border-slate-500/40",
};

/** ₹ amount with an explicit +/- sign — never rely on color alone to convey polarity. */
export function formatINR(amount: number, decimals = 2): string {
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  return `${sign}₹${Math.abs(amount).toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export function formatPct(pct: number, decimals = 2): string {
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(decimals)}%`;
}

export function pnlColorClass(amount: number): string {
  if (amount > 0) return "text-emerald-400";
  if (amount < 0) return "text-red-400";
  return "text-slate-400";
}
