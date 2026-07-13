import type { CandlestickPattern } from "../types";

interface Props {
  patterns: CandlestickPattern[];
}

const SIGNAL_BADGE = {
  bullish: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  bearish: "bg-red-500/10 text-red-400 border-red-500/30",
  neutral: "bg-slate-500/10 text-slate-400 border-slate-500/30",
};

const SIGNAL_DOT = {
  bullish: "bg-emerald-400",
  bearish: "bg-red-400",
  neutral: "bg-slate-400",
};

export default function CandlestickPatterns({ patterns }: Props) {
  if (!patterns || patterns.length === 0) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <h3 className="font-semibold text-sm text-slate-200 mb-3">Candlestick Patterns</h3>
        <p className="text-slate-500 text-sm">No significant patterns detected in recent candles.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm text-slate-200">Candlestick Patterns</h3>
        <span className="text-xs text-slate-500">{patterns.length} detected</span>
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {patterns.map((p, i) => (
          <div
            key={i}
            className="flex items-start gap-3 p-3 bg-slate-900/50 rounded-lg"
          >
            <div className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${SIGNAL_DOT[p.signal] || SIGNAL_DOT.neutral}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-slate-200">{p.pattern}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${SIGNAL_BADGE[p.signal] || SIGNAL_BADGE.neutral}`}>
                  {p.signal}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">{p.description}</p>
              <p className="text-xs text-slate-600 mt-0.5">{p.date}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
