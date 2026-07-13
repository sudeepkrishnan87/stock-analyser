import type { QuarterlyResult } from "../types";

interface Props {
  results: QuarterlyResult[];
}

function fmt(v?: number | null, unit = "Cr") {
  if (v === undefined || v === null) return "—";
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}${unit}`;
}

export default function QuarterlyCard({ results }: Props) {
  if (!results || results.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="font-semibold text-sm text-slate-200 mb-2">Quarterly Results</h3>
        <p className="text-slate-500 text-sm">Quarterly results unavailable at this time.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <h3 className="font-semibold text-sm text-slate-200 mb-4">Quarterly Results</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-slate-700">
              <th className="text-xs text-slate-400 font-medium pb-2">Quarter</th>
              <th className="text-xs text-slate-400 font-medium pb-2 text-right">Revenue</th>
              <th className="text-xs text-slate-400 font-medium pb-2 text-right">Net Profit</th>
              <th className="text-xs text-slate-400 font-medium pb-2 text-right">Net Margin</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {results.map((q, i) => {
              const margin =
                q.revenue && q.net_profit
                  ? ((q.net_profit / q.revenue) * 100).toFixed(1)
                  : null;

              const prevProfit = results[i + 1]?.net_profit;
              const growth =
                q.net_profit && prevProfit
                  ? (((q.net_profit - prevProfit) / Math.abs(prevProfit)) * 100).toFixed(1)
                  : null;

              return (
                <tr key={i} className="group">
                  <td className="py-2.5 text-xs text-slate-300 font-medium">{q.quarter}</td>
                  <td className="py-2.5 text-xs text-slate-200 text-right">{fmt(q.revenue)}</td>
                  <td className="py-2.5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <span className={`text-xs ${q.net_profit && q.net_profit > 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {fmt(q.net_profit)}
                      </span>
                      {growth && (
                        <span className={`text-xs ${parseFloat(growth) >= 0 ? "text-emerald-500" : "text-red-400"}`}>
                          {parseFloat(growth) >= 0 ? "+" : ""}{growth}%
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 text-xs text-slate-400 text-right">
                    {margin ? `${margin}%` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-600 mt-3">Source: Yahoo Finance (yfinance). Revenue & profit in ₹ Crores.</p>
    </div>
  );
}
