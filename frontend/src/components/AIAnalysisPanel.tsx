import type { AIAnalysis } from "../types";

interface Props {
  analysis: AIAnalysis;
  currentPrice: number;
}

const SIGNAL_STYLES = {
  BUY: "signal-buy",
  SELL: "signal-sell",
  HOLD: "signal-hold",
};

const CONFIDENCE_COLORS = {
  HIGH: "text-emerald-400",
  MEDIUM: "text-yellow-400",
  LOW: "text-red-400",
};

export default function AIAnalysisPanel({ analysis, currentPrice }: Props) {
  const signalStyle = SIGNAL_STYLES[analysis.signal] ?? "signal-hold";
  const confidenceColor = CONFIDENCE_COLORS[analysis.confidence] ?? "text-slate-400";

  const upside =
    analysis.price_target
      ? (((analysis.price_target - currentPrice) / currentPrice) * 100).toFixed(1)
      : null;

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      <div className="flex items-center gap-2 mb-5">
        <div className="w-2 h-2 bg-indigo-400 rounded-full" />
        <h3 className="font-semibold text-slate-200">AI Analysis — Claude Opus</h3>
      </div>

      {/* Signal row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p className="text-xs text-slate-500 mb-1">Signal</p>
          <span className={`text-xl font-bold px-3 py-1 rounded-lg ${signalStyle}`}>
            {analysis.signal}
          </span>
        </div>
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p className="text-xs text-slate-500 mb-1">Confidence</p>
          <p className={`text-xl font-bold ${confidenceColor}`}>{analysis.confidence}</p>
        </div>
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p className="text-xs text-slate-500 mb-1">Price Target</p>
          {analysis.price_target ? (
            <>
              <p className="text-lg font-bold text-emerald-400">
                ₹{analysis.price_target.toLocaleString("en-IN")}
              </p>
              {upside && (
                <p className={`text-xs ${parseFloat(upside) >= 0 ? "text-emerald-500" : "text-red-400"}`}>
                  {parseFloat(upside) >= 0 ? "+" : ""}{upside}%
                </p>
              )}
            </>
          ) : (
            <p className="text-slate-500">—</p>
          )}
        </div>
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p className="text-xs text-slate-500 mb-1">Stop Loss</p>
          {analysis.stop_loss ? (
            <p className="text-lg font-bold text-red-400">
              ₹{analysis.stop_loss.toLocaleString("en-IN")}
            </p>
          ) : (
            <p className="text-slate-500">—</p>
          )}
        </div>
      </div>

      {/* Horizon */}
      <div className="text-xs text-slate-400 mb-4">
        Time Horizon: <span className="text-slate-200 font-medium">{analysis.time_horizon}</span>
      </div>

      {/* Narrative */}
      <div className="bg-slate-900/60 rounded-lg p-4 mb-4">
        <p className="text-xs font-medium text-slate-400 mb-2">Analysis Narrative</p>
        <p className="text-sm text-slate-200 leading-relaxed">{analysis.narrative}</p>
      </div>

      {/* Detail grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div className="bg-slate-900/60 rounded-lg p-4">
          <p className="text-xs font-medium text-amber-400 mb-1">Elliott Wave Position</p>
          <p className="text-xs text-slate-300 leading-relaxed">{analysis.elliott_wave_position}</p>
        </div>
        <div className="bg-slate-900/60 rounded-lg p-4">
          <p className="text-xs font-medium text-indigo-400 mb-1">FII/DII Sentiment</p>
          <p className="text-xs text-slate-300 leading-relaxed">{analysis.fii_dii_sentiment}</p>
        </div>
        <div className="bg-slate-900/60 rounded-lg p-4">
          <p className="text-xs font-medium text-purple-400 mb-1">Pattern Summary</p>
          <p className="text-xs text-slate-300 leading-relaxed">{analysis.pattern_summary}</p>
        </div>
      </div>

      {/* Quarterly outlook */}
      <div className="bg-slate-900/60 rounded-lg p-4 mb-4">
        <p className="text-xs font-medium text-teal-400 mb-1">Quarterly Outlook</p>
        <p className="text-xs text-slate-300 leading-relaxed">{analysis.quarterly_outlook}</p>
      </div>

      {/* Key risks */}
      {analysis.key_risks.length > 0 && (
        <div>
          <p className="text-xs font-medium text-red-400 mb-2">Key Risks</p>
          <ul className="space-y-1">
            {analysis.key_risks.map((risk, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                <span className="text-red-500 mt-0.5">▸</span>
                {risk}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
