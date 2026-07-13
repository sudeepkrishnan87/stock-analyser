import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
} from "lightweight-charts";
import type { CandleData, ElliottWave, FibonacciLevel } from "../types";

interface Props {
  dailyCandles: CandleData[];
  weeklyCandles: CandleData[];
  monthlyCandles: CandleData[];
  elliottWaves: ElliottWave[];
  fibonacciLevels: FibonacciLevel[];
}

type Timeframe = "daily" | "weekly" | "monthly";

const CHART_OPTIONS = {
  layout: {
    background: { type: ColorType.Solid, color: "#0f172a" },
    textColor: "#94a3b8",
  },
  grid: {
    vertLines: { color: "#1e293b" },
    horzLines: { color: "#1e293b" },
  },
  rightPriceScale: {
    borderColor: "#334155",
    scaleMargins: { top: 0.1, bottom: 0.2 },
  },
  timeScale: {
    borderColor: "#334155",
    timeVisible: true,
    secondsVisible: false,
  },
  crosshair: { mode: 1 },
};

const CANDLE_OPTIONS: Partial<CandlestickSeriesOptions> = {
  upColor: "#22c55e",
  downColor: "#ef4444",
  borderUpColor: "#22c55e",
  borderDownColor: "#ef4444",
  wickUpColor: "#22c55e",
  wickDownColor: "#ef4444",
};

const WAVE_COLORS: Record<string, string> = {
  "1": "#f59e0b", "2": "#f59e0b", "3": "#f59e0b", "4": "#f59e0b", "5": "#f59e0b",
  "A": "#a78bfa", "B": "#a78bfa", "C": "#a78bfa",
};

function buildChartData(candles: CandleData[]) {
  return candles.map((c) => ({
    time: c.date as `${number}-${number}-${number}`,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

export default function MultiTimeframeChart({
  dailyCandles,
  weeklyCandles,
  monthlyCandles,
  elliottWaves,
  fibonacciLevels,
}: Props) {
  const [activeTab, setActiveTab] = useState<Timeframe>("daily");
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  // Track price lines ourselves since the series API has no priceLines() getter
  const priceLineRefs = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);

  const candlesMap: Record<Timeframe, CandleData[]> = {
    daily: dailyCandles,
    weekly: weeklyCandles,
    monthly: monthlyCandles,
  };

  // Initialize chart once
  useEffect(() => {
    if (!chartRef.current) return;

    const chart = createChart(chartRef.current, {
      ...CHART_OPTIONS,
      width: chartRef.current.clientWidth,
      height: 420,
    } as Parameters<typeof createChart>[1]);

    const candleSeries = chart.addCandlestickSeries(CANDLE_OPTIONS);
    chartApiRef.current = chart;
    candleSeriesRef.current = candleSeries;

    const handleResize = () => {
      if (chartRef.current) chart.resize(chartRef.current.clientWidth, 420);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Update data when tab or candles change
  useEffect(() => {
    const chart = chartApiRef.current;
    const series = candleSeriesRef.current;
    if (!chart || !series) return;

    const candles = candlesMap[activeTab];
    series.setData(buildChartData(candles));

    // Remove old Elliott Wave lines (recreate chart series)
    // For simplicity, we apply wave markers on the series
    if (activeTab === "daily" && elliottWaves.length > 0) {
      const markers = elliottWaves.map((w) => ({
        time: w.end_date as `${number}-${number}-${number}`,
        position: w.end_price > w.start_price ? "aboveBar" as const : "belowBar" as const,
        color: WAVE_COLORS[w.wave_number] || "#f59e0b",
        shape: "circle" as const,
        text: `W${w.wave_number}`,
        size: 1,
      }));
      series.setMarkers(markers);

      // Remove previously drawn Fibonacci price lines then redraw
      priceLineRefs.current.forEach((l) => series.removePriceLine(l));
      priceLineRefs.current = [];

      fibonacciLevels.slice(0, 8).forEach((fib) => {
        const line = series.createPriceLine({
          price: fib.price,
          color: fib.level <= 1 ? "#6366f1" : "#8b5cf6",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: fib.label,
        });
        priceLineRefs.current.push(line);
      });
    } else {
      series.setMarkers([]);
    }

    chart.timeScale().fitContent();
  }, [activeTab, dailyCandles, weeklyCandles, monthlyCandles, elliottWaves, fibonacciLevels]);

  const tabs: { key: Timeframe; label: string }[] = [
    { key: "daily", label: "Daily" },
    { key: "weekly", label: "Weekly" },
    { key: "monthly", label: "Monthly" },
  ];

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <h3 className="font-semibold text-sm text-slate-200">Price Chart</h3>
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                activeTab === t.key
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-700 text-slate-400 hover:bg-slate-600"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "daily" && elliottWaves.length > 0 && (
        <div className="px-4 pb-1 flex flex-wrap gap-2">
          {elliottWaves.map((w, i) => (
            <span
              key={i}
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                background: `${WAVE_COLORS[w.wave_number] || "#f59e0b"}20`,
                color: WAVE_COLORS[w.wave_number] || "#f59e0b",
                border: `1px solid ${WAVE_COLORS[w.wave_number] || "#f59e0b"}40`,
              }}
            >
              Wave {w.wave_number} — ₹{w.start_price.toLocaleString("en-IN")} → ₹{w.end_price.toLocaleString("en-IN")}
            </span>
          ))}
        </div>
      )}

      <div ref={chartRef} className="chart-container" />
    </div>
  );
}
