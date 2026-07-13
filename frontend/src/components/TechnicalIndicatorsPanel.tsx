import type { TechnicalIndicators } from "../types";

interface Props {
  indicators: TechnicalIndicators;
  currentPrice: number;
}

function rsiColor(rsi?: number) {
  if (!rsi) return "text-slate-400";
  if (rsi >= 70) return "text-red-400";
  if (rsi <= 30) return "text-emerald-400";
  return "text-yellow-400";
}

function rsiLabel(rsi?: number) {
  if (!rsi) return "";
  if (rsi >= 70) return "Overbought";
  if (rsi <= 30) return "Oversold";
  return "Neutral";
}

function fmt(v?: number) {
  if (v === undefined || v === null) return "—";
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function TechnicalIndicatorsPanel({ indicators, currentPrice }: Props) {
  const close = currentPrice;

  const aboveSma = (sma?: number) => {
    if (!sma) return null;
    return close > sma;
  };

  const macdBull = indicators.macd !== undefined && indicators.macd_signal !== undefined
    ? indicators.macd > indicators.macd_signal
    : null;

  const bbPosition = (() => {
    if (!indicators.bb_upper || !indicators.bb_lower || !indicators.bb_middle) return null;
    if (close > indicators.bb_upper) return "Above Upper Band";
    if (close < indicators.bb_lower) return "Below Lower Band";
    if (close > indicators.bb_middle) return "Upper Half";
    return "Lower Half";
  })();

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <h3 className="font-semibold text-sm text-slate-200 mb-4">Technical Indicators</h3>

      <div className="space-y-3">
        {/* RSI */}
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400">RSI (14)</span>
          </div>
          <div className="text-right">
            <span className={`text-sm font-semibold ${rsiColor(indicators.rsi)}`}>
              {indicators.rsi ? indicators.rsi.toFixed(1) : "—"}
            </span>
            {indicators.rsi && (
              <span className="text-xs text-slate-500 ml-2">{rsiLabel(indicators.rsi)}</span>
            )}
          </div>
        </div>
        {indicators.rsi && (
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${rsiColor(indicators.rsi).replace("text-", "bg-")}`}
              style={{ width: `${Math.min(indicators.rsi, 100)}%` }}
            />
          </div>
        )}

        {/* MACD */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">MACD</span>
          <div className="text-right">
            <span className={`text-sm font-semibold ${macdBull === true ? "text-emerald-400" : macdBull === false ? "text-red-400" : "text-slate-400"}`}>
              {fmt(indicators.macd)}
            </span>
            {macdBull !== null && (
              <span className="text-xs text-slate-500 ml-2">
                {macdBull ? "Bullish crossover" : "Bearish crossover"}
              </span>
            )}
          </div>
        </div>

        <div className="border-t border-slate-700/50 pt-3 space-y-2">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Moving Averages</p>
          {[
            { label: "SMA 20", val: indicators.sma_20 },
            { label: "SMA 50", val: indicators.sma_50 },
            { label: "SMA 200", val: indicators.sma_200 },
          ].map(({ label, val }) => {
            const above = aboveSma(val);
            return (
              <div key={label} className="flex items-center justify-between">
                <span className="text-xs text-slate-400">{label}</span>
                <div className="text-right">
                  <span className="text-xs text-slate-200">₹{fmt(val)}</span>
                  {above !== null && (
                    <span className={`text-xs ml-2 ${above ? "text-emerald-400" : "text-red-400"}`}>
                      {above ? "↑ Above" : "↓ Below"}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="border-t border-slate-700/50 pt-3 space-y-2">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Bollinger Bands</p>
          {[
            { label: "Upper", val: indicators.bb_upper, color: "text-red-400" },
            { label: "Middle", val: indicators.bb_middle, color: "text-slate-300" },
            { label: "Lower", val: indicators.bb_lower, color: "text-emerald-400" },
          ].map(({ label, val, color }) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-xs text-slate-400">BB {label}</span>
              <span className={`text-xs ${color}`}>₹{fmt(val)}</span>
            </div>
          ))}
          {bbPosition && (
            <div className="text-xs text-slate-400 bg-slate-900/50 rounded px-2 py-1">
              Price is in: <span className="text-slate-200">{bbPosition}</span>
            </div>
          )}
        </div>

        {indicators.volume_ratio !== undefined && (
          <div className="border-t border-slate-700/50 pt-3 flex items-center justify-between">
            <span className="text-xs text-slate-400">Volume vs 20-day avg</span>
            <span className={`text-xs font-semibold ${indicators.volume_ratio > 1.5 ? "text-amber-400" : "text-slate-300"}`}>
              {indicators.volume_ratio.toFixed(2)}x
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
