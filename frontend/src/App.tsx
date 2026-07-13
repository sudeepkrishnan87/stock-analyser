import { useState, useEffect } from "react";
import type { StockAnalysisResponse } from "./types";
import { analyzeStock, checkAuthStatus } from "./api/client";
import Header from "./components/Header";
import StockSearch from "./components/StockSearch";
import TokenSetup from "./components/TokenSetup";
import MultiTimeframeChart from "./components/MultiTimeframeChart";
import FiiDiiChart from "./components/FiiDiiChart";
import AIAnalysisPanel from "./components/AIAnalysisPanel";
import TechnicalIndicatorsPanel from "./components/TechnicalIndicatorsPanel";
import CandlestickPatterns from "./components/CandlestickPatterns";
import QuarterlyCard from "./components/QuarterlyCard";

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [showTokenSetup, setShowTokenSetup] = useState(false);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<StockAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState("");

  useEffect(() => {
    checkAuthStatus()
      .then((s) => setIsAuthenticated(s.authenticated))
      .catch(() => setIsAuthenticated(false));
  }, []);

  const handleSearch = async (symbol: string) => {
    if (!isAuthenticated) {
      setShowTokenSetup(true);
      return;
    }
    setLoading(true);
    setError(null);
    setAnalysis(null);

    const steps = [
      "Fetching price data from Kite…",
      "Running technical analysis…",
      "Detecting Elliott Waves…",
      "Fetching FII/DII data…",
      "Generating AI analysis…",
    ];
    let stepIdx = 0;
    setLoadingStep(steps[0]);
    const stepTimer = setInterval(() => {
      stepIdx = Math.min(stepIdx + 1, steps.length - 1);
      setLoadingStep(steps[stepIdx]);
    }, 5000);

    try {
      const data = await analyzeStock(symbol);
      setAnalysis(data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } }; message?: string })
          ?.response?.data?.detail ||
        (err as { message?: string })?.message ||
        "Analysis failed. Please try again.";
      setError(msg);
    } finally {
      clearInterval(stepTimer);
      setLoading(false);
      setLoadingStep("");
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <Header
        isAuthenticated={isAuthenticated}
        onTokenSetup={() => setShowTokenSetup(true)}
      />

      {showTokenSetup && (
        <TokenSetup
          onSuccess={() => {
            setIsAuthenticated(true);
            setShowTokenSetup(false);
          }}
          onClose={() => setShowTokenSetup(false)}
        />
      )}

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <StockSearch onSearch={handleSearch} loading={loading} />

        {/* Loading state */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full spinner" />
            <p className="text-slate-400 text-sm">{loadingStep}</p>
            <p className="text-slate-600 text-xs">This takes 15-30 seconds…</p>
          </div>
        )}

        {/* Error state */}
        {error && !loading && (
          <div className="p-4 bg-red-900/30 border border-red-500/50 rounded-xl text-red-300 text-sm">
            <span className="font-semibold">Error: </span>{error}
          </div>
        )}

        {/* Analysis results */}
        {analysis && !loading && (
          <div className="space-y-6">
            {/* Stock header */}
            <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-3xl font-bold tracking-wide">{analysis.symbol}</h2>
                  <p className="text-slate-400 mt-1">{analysis.company_name}</p>
                </div>
                <div className="text-right">
                  <p className="text-4xl font-bold text-emerald-400">
                    ₹{analysis.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </p>
                  <p className="text-slate-500 text-sm mt-1">Last Traded Price</p>
                </div>
              </div>
            </div>

            {/* AI Analysis — prominent at top */}
            <AIAnalysisPanel analysis={analysis.ai_analysis} currentPrice={analysis.current_price} />

            {/* Multi-timeframe charts */}
            <MultiTimeframeChart
              dailyCandles={analysis.daily_candles}
              weeklyCandles={analysis.weekly_candles}
              monthlyCandles={analysis.monthly_candles}
              elliottWaves={analysis.elliott_waves}
              fibonacciLevels={analysis.fibonacci_levels}
            />

            {/* Technical indicators + Candlestick patterns */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <TechnicalIndicatorsPanel
                indicators={analysis.technical_indicators}
                currentPrice={analysis.current_price}
              />
              <CandlestickPatterns patterns={analysis.candlestick_patterns} />
            </div>

            {/* FII/DII */}
            <FiiDiiChart data={analysis.fii_dii_data} />

            {/* Quarterly results */}
            <QuarterlyCard results={analysis.quarterly_results} />
          </div>
        )}
      </main>
    </div>
  );
}
