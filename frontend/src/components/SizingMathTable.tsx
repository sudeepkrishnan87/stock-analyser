import type { SizingBreakdown } from "../types";

export function fmtINR(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * The "shopping allowance" math table — same framing used to explain a real
 * rejection in chat, shared between RecentDecisions (after the fact) and
 * SignalsPanel (before you ever click Approve). Mirrors
 * trading_service._position_size_breakdown() field-for-field.
 */
export default function SizingMathTable({ symbol, b }: { symbol: string; b: SizingBreakdown }) {
  return (
    <div className="mt-3 bg-slate-900/60 rounded-lg border border-slate-700 p-3 text-xs">
      <p className="text-slate-400 font-semibold mb-2">Why there wasn't room for {symbol}</p>
      <table className="w-full">
        <tbody className="divide-y divide-slate-800">
          <tr>
            <td className="py-1 text-slate-500">Your total money (free cash + already in stocks)</td>
            <td className="py-1 text-right font-semibold text-slate-200">{fmtINR(b.effective_capital)}</td>
          </tr>
          <tr>
            <td className="py-1 text-slate-500">Safety rule: never use more than</td>
            <td className="py-1 text-right font-semibold text-slate-200">{b.max_exposure_pct}%</td>
          </tr>
          <tr>
            <td className="py-1 text-slate-500">Already tied up in other stocks</td>
            <td className="py-1 text-right font-semibold text-amber-400">{fmtINR(b.deployed_capital)}</td>
          </tr>
          <tr>
            <td className="py-1 text-slate-500">Room left for something new</td>
            <td className={`py-1 text-right font-bold ${b.max_deployable < b.entry_price ? "text-red-400" : "text-emerald-400"}`}>
              {fmtINR(b.max_deployable)}
            </td>
          </tr>
          {!!b.additional_funds_needed && (
            <tr>
              <td className="py-1 text-slate-500">Top up this much to afford at least 1 share</td>
              <td className="py-1 text-right font-bold text-sky-400">
                {fmtINR(b.additional_funds_needed)}
                {b.shortfall_reason && <span className="text-slate-500 font-normal"> ({b.shortfall_reason})</span>}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="text-slate-500 mt-2">
        {symbol} needs at least <span className="text-slate-300 font-semibold">{fmtINR(b.entry_price)}</span> for
        just 1 share, but only <span className="text-slate-300 font-semibold">{fmtINR(b.max_deployable)}</span> of
        room was left — same rule as spending only 60% of an allowance and keeping 40% back as a cushion.
      </p>
      {b.available_funds !== null && (
        <p className="text-slate-600 mt-1">
          (Live Zerodha balance at the time: {fmtINR(b.available_funds)} free + {fmtINR(b.deployed_capital)} already
          in stocks = {fmtINR(b.effective_capital)} total.)
        </p>
      )}
    </div>
  );
}
